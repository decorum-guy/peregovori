#!/usr/bin/env python3
"""Unattended paid RTX 3090 experiment: fresh 8B LoRA rank16, 2 epochs, DEV, stop.

Uses the SAME frozen train and private DEV as previous experiments.
Never retrains on DEV/TEST. Preserves old V1 outputs. Runs inside tmux.
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
TRAIN = ROOT / "training" / "outputs" / "qlora_v2_e2"
ADAPTER = TRAIN / "adapter"
RUN_CFG = TRAIN / "run_config.json"
BUNDLE = ROOT / "training" / "outputs" / "qlora_v2_e2_bundle.tar.gz"
RESULTS = ROOT / "eval_private" / "results" / "qwen3_8b_e2"
REFERENCE = ROOT / "eval_private" / "results" / "dev"
CASES = ROOT / "eval_private" / "dev" / "cases.jsonl"
PROBES = ROOT / "eval_private" / "dev" / "probes.jsonl"
PRIVATE_BUNDLE = ROOT / "eval_private" / "qwen3_8b_e2_dev_outputs.tar.gz"
DEADLINE = ROOT / "training" / "outputs" / "intelion_deadline.json"


def execute(*argv):
    cmd = [sys.executable, *map(str, argv)]
    print("\nRUN:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def archive(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tar:
        for source, name in entries:
            if source.exists():
                tar.add(source, arcname=name)
    digest = sha(path)
    Path(str(path) + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")
    print(f"SAVED {path} ({path.stat().st_size:,} bytes) SHA256={digest}", flush=True)


def check_dev_baseline():
    if not CASES.is_file() or not PROBES.is_file():
        raise RuntimeError("Private DEV 25/75 missing; use existing VM/disk")
    config = json.loads((REFERENCE / "run_config.json").read_text(encoding="utf-8"))
    if config["model"] != "Qwen/Qwen3-8B" or config["suite"] != "dev":
        raise RuntimeError("Original DEV baseline model or suite changed")
    if config["decoding"] != {"do_sample": False, "max_new_tokens": 192, "thinking": False}:
        raise RuntimeError("Original baseline decoding changed")
    if config["case_sha256"] != sha(CASES) or config["probe_sha256"] != sha(PROBES):
        raise RuntimeError("Frozen DEV hash differs from original baseline")
    for file in (REFERENCE / "base.jsonl", REFERENCE / "lora.jsonl"):
        rows = [json.loads(x) for x in file.read_text(encoding="utf-8").splitlines() if x.strip()]
        if len(rows) != 75 or len({x["probe_id"] for x in rows}) != 75:
            raise RuntimeError(f"Original 8B reference incomplete: {file}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server-id", type=int, required=True)
    args = p.parse_args()
    succeeded = False
    stage = "preflight"
    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        if args.server_id != 11425:
            raise RuntimeError("Expected original Intelion VM 11425; stop before spending GPU budget")
        if not DEADLINE.is_file():
            raise RuntimeError("No watchdog. Launch via training/start_8b_2epochs.sh")
        d = json.loads(DEADLINE.read_text(encoding="utf-8"))
        if int(d["server_id"]) != args.server_id or d["deadline_epoch"] < time.time() + 75 * 60:
            raise RuntimeError("Need fresh active watchdog with >=75min left")
        if TRAIN.exists() and (TRAIN / "run_config.json").exists():
            raise RuntimeError("V2 adapter already exists; refusing to overwrite; inspect results first")
        check_dev_baseline()
        execute("training/check_result.py")
        execute("training/prepare_sft.py")
        execute("training/train_qlora.py", "--dry-run", "--model", "Qwen/Qwen3-8B")
        stage = "training"
        execute("training/train_qlora.py", "--epochs", "2",
                "--lora-rank", "16", "--output", "training/outputs/qlora_v2_e2",
                "--deadline-file", str(DEADLINE), "--save-margin-seconds", "1500")
        config = json.loads(RUN_CFG.read_text(encoding="utf-8"))
        if not config.get("completed_target") or float(config.get("actual_epoch", 0)) < 1.99:
            raise RuntimeError(f"Training ended EARLY at epoch={config.get('actual_epoch')}; "
                               "preserving partial adapter, skipping quality comparison")
        archive(BUNDLE, [(ADAPTER, "adapter"), (RUN_CFG, "run_config.json")])
        stage = "inference"
        execute("evaluation/run_gpu.py", "--suite", "dev", "--lora-only",
                "--cases", str(CASES), "--probes", str(PROBES),
                "--adapter", str(ADAPTER), "--output", str(RESULTS),
                "--deadline-file", str(DEADLINE), "--max-new-tokens", "192")
        stage = "comparison"
        execute("evaluation/compare_8b_2epochs.py",
                "--reference-dir", str(REFERENCE), "--candidate-dir", str(RESULTS),
                "--cases", str(CASES), "--probes", str(PROBES))
        succeeded = True
        stage = "finished"
    except BaseException:
        traceback.print_exc()
        print("EXPERIMENT NOT FULLY FINISHED. Logs and partial outputs preserved.", flush=True)
    finally:
        status = {
            "experiment": "Qwen3-8B QLoRA rank16, fresh 2 epochs",
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "success": succeeded, "last_stage": stage,
            "server_id": args.server_id,
        }
        (RESULTS / "final_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Always package whatever already exists, even if only a partial trained adapter.
        try:
            if ADAPTER.is_dir() and RUN_CFG.is_file() and not BUNDLE.is_file():
                archive(BUNDLE, [(ADAPTER, "adapter"), (RUN_CFG, "run_config.json")])
        except Exception as exc:
            print(f"ERROR packaging adapter: {exc}", flush=True)
        try:
            entries = [(RESULTS, "candidate_dev_e2"),
                       (CASES, "private_dev/cases.jsonl"),
                       (PROBES, "private_dev/probes.jsonl")]
            for name in ("base.jsonl", "lora.jsonl", "run_config.json"):
                entries.append((REFERENCE / name, "reference_dev_8b/" + name))
            archive(PRIVATE_BUNDLE, entries)
        except Exception as exc:
            print(f"ERROR packaging private DEV: {exc}", flush=True)
        os.sync()
        print("Requesting Intelion provider stop now (detached watchdog also armed).", flush=True)
        try:
            execute("training/intelion_autostop.py", "stop", "--server-id", str(args.server_id))
        except BaseException as exc:
            print(f"CRITICAL: stop API failed: {exc}; stop manually in Intelion dashboard", flush=True)
    if not succeeded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
