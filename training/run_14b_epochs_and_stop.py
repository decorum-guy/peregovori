#!/usr/bin/env python3
"""Qwen3-14B BASE DEV -> 14B QLoRA VRAM test -> two-epoch train with E1 snapshot -> DEV per snapshot.

Experiments run unattended on existing Intelion GPU VM 11425.
Always saves available outputs and requests PROVIDER stop, even after OOM.
All DEV/oracles/answers and artifacts go ONLY to separate PRIVATE GitHub Releases.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "training" / "outputs"
TRAIN = OUTPUTS / "qlora_14b_2ep"
PRIVATE = ROOT / "eval_private"
RESULTS = PRIVATE / "results"
CASES, PROBES = PRIVATE / "dev" / "cases.jsonl", PRIVATE / "dev" / "probes.jsonl"
DEADLINE = OUTPUTS / "intelion_deadline.json"
LOG = TRAIN / "pipeline.log"
STATUS = TRAIN / "experiment_status.json"
MODEL = "Qwen/Qwen3-14B"
TAG = "qwen3-14b-20261014-vm11425"


def run(script, *arguments):
    argv = [sys.executable, script, *map(str, arguments)]
    print("\nRUN:", " ".join(argv), flush=True)
    subprocess.run(argv, cwd=ROOT, check=True)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def left_seconds():
    d = json.loads(DEADLINE.read_text(encoding="utf-8"))
    if int(d["server_id"]) != 11425:
        raise RuntimeError("Unexpected server ID in watchdog file")
    return float(d["deadline_epoch"]) - time.time()


def budget(seconds, stage):
    remaining = left_seconds()
    print(f"TIME CHECK {stage}: {remaining / 60:.1f} min until hard-stop", flush=True)
    if remaining < seconds:
        raise RuntimeError(f"Not enough remaining budget for {stage}; preserving outputs")


def archive(path, entries):
    with tarfile.open(path, "w:gz") as tgz:
        for item, arcname in entries:
            if item.exists():
                tgz.add(item, arcname=arcname)
    digest = sha(path)
    Path(str(path) + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")
    print(f"ARCHIVED {path} size={path.stat().st_size}, sha256={digest}", flush=True)


def pack_snapshots():
    saved = []
    for ep in (1, 2):
        snap = TRAIN / f"adapter_epoch_{ep}"
        meta = snap / "training_epoch.json"
        if not (meta.is_file() and (snap / "adapter_config.json").is_file()
                and list(snap.glob("*.safetensors"))):
            continue
        cfg = json.loads(meta.read_text(encoding="utf-8"))
        if cfg.get("model") != MODEL or abs(float(cfg.get("actual_epoch", 0)) - ep) > 0.003:
            raise RuntimeError(f"Bad training epoch metadata {meta}")
        bundle = OUTPUTS / f"qlora_14b_epoch_{ep}_bundle.tar.gz"
        if not bundle.exists():
            archive(bundle, [(snap, "adapter"), (TRAIN / "run_config.json", "training_run_config.json")])
        saved.append(ep)
    return saved


def check_inputs():
    ref = RESULTS / "dev" / "run_config.json"
    if not (CASES.is_file() and PROBES.is_file() and ref.is_file()):
        raise RuntimeError("Frozen private DEV and 8B baseline are required on existing disk")
    cfg = json.loads(ref.read_text(encoding="utf-8"))
    if cfg["model"] != "Qwen/Qwen3-8B" or cfg["suite"] != "dev":
        raise RuntimeError("Previous 8B DEV run must be frozen and valid")
    for key, path in (("case_sha256", CASES), ("probe_sha256", PROBES)):
        if cfg[key] != sha(path):
            raise RuntimeError(f"Frozen DEV hash mismatch: {key}")
    expected = {"do_sample": False, "max_new_tokens": 192, "thinking": False}
    if cfg["decoding"] != expected:
        raise RuntimeError("Previous DEV decoding differs from benchmark")
    for name in ("base.jsonl", "lora.jsonl"):
        rows = [json.loads(x) for x in (RESULTS / "dev" / name).read_text(encoding="utf-8").splitlines() if x.strip()]
        if len(rows) != 75 or len({r["probe_id"] for r in rows}) != 75:
            raise RuntimeError("Original 8B comparison is incomplete: " + name)
    run("evaluation/run_gpu.py", "--suite", "dev", "--base-only", "--validate-only",
        "--model", MODEL, "--cases", CASES, "--probes", PROBES,
        "--output", RESULTS / "qwen3_14b_base")
    print("PREFLIGHT PASS: private DEV, original 8B reference, schema and checksums", flush=True)


def eval_model(label, adapter=None):
    kwargs = ["--suite", "dev", "--model", MODEL, "--cases", CASES, "--probes", PROBES,
              "--output", RESULTS / f"qwen3_14b_{label}",
              "--deadline-file", DEADLINE, "--stop-margin-minutes", "15",
              "--max-new-tokens", "192"]
    if adapter:
        kwargs += ["--lora-only", "--adapter", adapter]
    else:
        kwargs += ["--base-only"]
    run("evaluation/run_gpu.py", *kwargs)


def upload_all(paths):
    if not paths:
        print("UPLOAD SKIPPED: no artifacts", flush=True)
        return "no_artifacts"
    args = ["upload", "--tag", TAG]
    for path in paths:
        args.extend(["--file", path])
    run("training/upload_private_release.py", *args)
    return "verified"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-id", type=int, required=True)
    a = parser.parse_args()
    TRAIN.mkdir(parents=True, exist_ok=True)
    stages = {"baseline": False, "gpu_preflight": False, "trained_e1": False,
              "trained_e2": False, "eval_e1": False, "eval_e2": False,
              "comparison_complete": False}
    last_stage = "starting"
    failure = None
    upload = "not_attempted"
    packages = []
    try:
        if a.server_id != 11425:
            raise RuntimeError("Wrong Intelion server ID")
        budget(60 * 60, "startup")
        check_inputs()
        # 1. Untrained Qwen3-14B baseline on the SAME frozen DEV. Done FIRST.
        last_stage = "14b_base_inference"
        budget(45 * 60, last_stage)
        eval_model("base")
        stages["baseline"] = True

        # 2. Try an actual NF4 LoRA backward/optimizer step on the LONGEST
        #    training example (not just loading a quantized model).
        last_stage = "longest_example_backward"
        budget(45 * 60, last_stage)
        run("training/train_qlora.py", "--model", MODEL, "--epochs", "2",
            "--lora-rank", "16", "--max-steps", "1", "--preflight-longest",
            "--min-free-vram-gb", "1.0",
            "--output", "training/outputs/qlora_14b_vram_preflight",
            "--deadline-file", DEADLINE, "--save-margin-seconds", "2400")
        stages["gpu_preflight"] = True
        # Preflight run must have exited before training, releasing GPU.
        # 3. A *single continuous 2-epoch run* yields a real E1 checkpoint
        #    and a real E2 checkpoint with the SAME cosine LR schedule.
        #    This is much cheaper and more interpretable than two fresh runs.
        last_stage = "2_epoch_finetuning"
        budget(55 * 60, last_stage)
        run("training/train_qlora.py", "--model", MODEL,
            "--epochs", "2", "--lora-rank", "16", "--epoch-snapshots",
            "--output", TRAIN, "--deadline-file", DEADLINE,
            "--save-margin-seconds", "3300")
        stages["trained_e1"] = (TRAIN / "adapter_epoch_1" / "training_epoch.json").is_file()
        stages["trained_e2"] = (TRAIN / "adapter_epoch_2" / "training_epoch.json").is_file()
    except BaseException as err:
        failure = f"{type(err).__name__}: {err}"
        print("PIPELINE TRAINING/BASELINE INCOMPLETE:", failure, flush=True)
        traceback.print_exc()
    finally:
        # Even if train stops early, E1 is useful: save and test it
        # before running out of rental time; never call partial E2 "2 epochs".
        for ep in (1, 2):
            stages[f"trained_e{ep}"] = (TRAIN / f"adapter_epoch_{ep}" / "training_epoch.json").is_file()
        try:
            last_stage = "snapshot_archive"
            pack_snapshots()
        except BaseException as exc:
            print("ARCHIVE WARNING:", exc, flush=True)
        for ep in (1, 2):
            if not stages[f"trained_e{ep}"]:
                continue
            try:
                last_stage = f"dev_epoch_{ep}"
                # No inference if <~25min left; preserve snapshot/upload first.
                if left_seconds() < 25 * 60:
                    print(f"SKIPPING DEV epoch {ep}: preserve time for GitHub upload and Intelion stop", flush=True)
                    continue
                eval_model(f"e{ep}", TRAIN / f"adapter_epoch_{ep}")
                stages[f"eval_e{ep}"] = True
            except BaseException as exc:
                print(f"DEV epoch {ep} incomplete, preserve partial: {exc}", flush=True)
        if stages["baseline"] and stages["eval_e1"] and stages["eval_e2"]:
            try:
                last_stage = "blinded_comparison"
                run("evaluation/compare_14b_epochs.py")
                stages["comparison_complete"] = True
            except BaseException as exc:
                print("COMPARISON INCOMPLETE:", exc, flush=True)
        try:
            # Preserve every accessible artifact, even on OOM/time truncation.
            last_stage = "private_results_archive"
            dev_archive = PRIVATE / "qwen3_14b_epochs_dev_outputs.tar.gz"
            entries = [(CASES, "private_dev/cases.jsonl"), (PROBES, "private_dev/probes.jsonl")]
            for label in ("qwen3_14b_base", "qwen3_14b_e1", "qwen3_14b_e2",
                          "qwen3_14b_comparison"):
                entries.append((RESULTS / label, f"results/{label}"))
            entries.append((TRAIN / "run_config.json", "training/run_config.json"))
            archive(dev_archive, entries)
            packages.extend([dev_archive, Path(str(dev_archive)+".sha256")])
        except BaseException as exc:
            print("PRIVATE ARCHIVE WARNING:", exc, flush=True)
        for ep in (1, 2):
            archive_path = OUTPUTS / f"qlora_14b_epoch_{ep}_bundle.tar.gz"
            if archive_path.is_file():
                packages += [archive_path, Path(str(archive_path)+".sha256")]
        status = {
            "model": MODEL, "rank": 16, "planned_epochs": 2,
            "stages": stages, "last_stage": last_stage, "error": failure,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(), "server_id": a.server_id,
            "quality_scored": False,
            "experiment_success": bool(stages["comparison_complete"]),
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        packages.append(STATUS)
        if LOG.is_file():
            packages.append(LOG)
        try:
            last_stage = "github_backup"
            # Must keep >=5min for stop API; watchdog remains a second layer.
            if left_seconds() < 5*60:
                print("VERY LOW TIME: skip GitHub upload, stop immediately; files stay on disk", flush=True)
                upload = "skipped_budget"
            else:
                upload = upload_all([f for f in packages if Path(f).is_file()])
        except BaseException as exc:
            upload = "FAILED"
            print("PRIVATE GITHUB BACKUP FAILED:", exc, flush=True)
            print("Archives remain on attached Intelion disk. Never wait indefinitely while billing.", flush=True)
        status["private_github_upload"] = upload
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        os.sync()
        print("STOPPING INTELION VIA PROVIDER API; confirm STOPPED in panel.", flush=True)
        try:
            run("training/intelion_autostop.py", "stop", "--server-id", a.server_id)
        except BaseException as exc:
            print("CRITICAL: provider STOP request failed. Stop manually in dashboard:", exc, flush=True)
    if not stages["comparison_complete"]:
        raise SystemExit("Incomplete 14B 3-way DEV result. Examine stage status; keep partial outcomes.")


if __name__ == "__main__":
    main()
