#!/usr/bin/env python3
"""GPU DEV prompt A/B/C: 14B E1 (default), optional 14B E2 or legacy 8B E2.

One candidate per invocation. A = frozen 75 answers from the SAME checkpoint,
B/C = 75 additional answers each, same model, adapter, DEV and decoding.
NO training. Independent blind grading happens AFTER the private export.
Guaranteed best-effort Intelion API stop with prearmed external watchdog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PRIVATE = ROOT / "eval_private"
RESULTS = PRIVATE / "results"
OUTPUTS = ROOT / "training" / "outputs"
CASES = PRIVATE / "dev" / "cases.jsonl"
PROBES = PRIVATE / "dev" / "probes.jsonl"
DEADLINE = OUTPUTS / "intelion_deadline.json"
SERVER_ID = 11425


@dataclass(frozen=True)
class Candidate:
    code: str
    model: str
    baseline: Path
    adapter: Path
    review: Path
    tag: str
    epoch: float
    full_training_cfg: Path


def candidate_for(code: str) -> Candidate:
    cfg = {
        "14b-e1": ("Qwen/Qwen3-14B", "qwen3_14b_e1",
                   "qlora_14b_2ep/adapter_epoch_1", 1,
                   "qlora_14b_2ep/run_config.json"),
        "14b-e2": ("Qwen/Qwen3-14B", "qwen3_14b_e2",
                   "qlora_14b_2ep/adapter_epoch_2", 2,
                   "qlora_14b_2ep/run_config.json"),
        "8b-e2": ("Qwen/Qwen3-8B", "qwen3_8b_e2",
                  "qlora_v2_e2/adapter", 2,
                  "qlora_v2_e2/run_config.json"),
    }
    model, prev, path, epoch, run_cfg = cfg[code]
    suffix = code.replace("-", "_")
    return Candidate(
        code=code, model=model,
        baseline=RESULTS / prev,
        adapter=OUTPUTS / path,
        review=RESULTS / f"methodology_abc_{suffix}_review",
        tag=f"methodology-abc-{code}-20261014-vm11425",
        epoch=epoch, full_training_cfg=OUTPUTS / run_cfg,
    )


def call(script, *params):
    command = [sys.executable, script, *map(str, params)]
    print("RUN:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def time_left():
    state = json.loads(DEADLINE.read_text(encoding="utf-8"))
    if int(state["server_id"]) != SERVER_ID:
        raise RuntimeError("Unexpected Intelion hard-stop watchdog server ID")
    return float(state["deadline_epoch"]) - time.time()


def check_baseline(c):
    from evaluation.run_gpu import validate_adapter
    from evaluation.methodology_context import identity_manifest
    prior = json.loads((c.baseline / "run_config.json").read_text(encoding="utf-8"))
    if prior.get("model") != c.model or prior.get("suite") != "dev":
        raise RuntimeError(f"Wrong original model/suite for {c.code}")
    if prior.get("prompt_variant", "A") != "A":
        raise RuntimeError("Archived original A is NOT historical unmodified prompt")
    if prior.get("decoding") != {"do_sample": False, "max_new_tokens": 192, "thinking": False}:
        raise RuntimeError("Old A decoding is different; cannot compare")
    digest = prior.get("adapter_weights_sha256")
    if not digest or validate_adapter(c.adapter) != digest:
        raise RuntimeError(f"Wrong LoRA adapter for frozen A {c.code}; STOP before GPU")
    for key, path in (("case_sha256", CASES), ("probe_sha256", PROBES)):
        if prior.get(key) != sha(path):
            raise RuntimeError(f"Frozen DEV mismatch in {key}; STOP")
    a_answers = [json.loads(line) for line in (c.baseline / "lora.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    ids = [entry["probe_id"] for entry in a_answers]
    probe_rows = [json.loads(line) for line in PROBES.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    probe_ids = [p["probe_id"] for p in probe_rows]
    if (len(a_answers) != 75 or len(set(ids)) != 75 or len(probe_ids) != 75
            or set(ids) != set(probe_ids)):
        raise RuntimeError("Historical A must contain exactly the SAME 75 frozen DEV probe IDs")
    training_cfg = json.loads(c.full_training_cfg.read_text(encoding="utf-8"))
    if training_cfg.get("model") != c.model or training_cfg.get("lora_rank") != 16:
        raise RuntimeError("Mismatch between checkpoint and frozen training config")
    if c.code.startswith("14b"):
        snapshot = json.loads((c.adapter / "training_epoch.json").read_text(encoding="utf-8"))
        if (snapshot.get("model") != c.model or snapshot.get("lora_rank") != 16
                or abs(float(snapshot.get("actual_epoch", 0)) - c.epoch) > .003):
            raise RuntimeError("Actual 14B epoch snapshot metadata disagrees")
        if float(training_cfg.get("actual_epoch", 0)) < 1.99:
            raise RuntimeError("Original 14B training was not two complete epochs")
    else:
        if float(training_cfg.get("actual_epoch", 0)) < 1.99:
            raise RuntimeError("Original 8B V2 was not two complete epochs")
    print(f"FROZEN A VERIFIED: model={c.model}, candidate={c.code}, "
          f"75 DEV responses, adapter SHA256={digest}", flush=True)
    print("METHODOLOGY:", json.dumps(identity_manifest(), ensure_ascii=False), flush=True)
    return digest


def archive_private(c, status):
    # Do not leak DEV cases/oracles into Git; archive belongs ONLY to private Release.
    archive = PRIVATE / f"methodology_abc_{c.code.replace('-', '_')}_private.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        items = [
            (CASES, "dev/cases.jsonl"), (PROBES, "dev/probes.jsonl"),
            (c.baseline / "lora.jsonl", "historical_A/lora.jsonl"),
            (c.baseline / "run_config.json", "historical_A/run_config.json"),
            (c.adapter / "training_epoch.json", "checkpoint_epoch_metadata.json"),
            (c.review, "blind_comparison"),
        ]
        for variant in ("B", "C"):
            items.append((RESULTS / f"methodology_abc_{c.code.replace('-', '_')}_{variant}",
                          f"variant_{variant}"))
        for item, name in items:
            if item.exists():
                tar.add(item, arcname=name)
    checksum = Path(str(archive) + ".sha256")
    checksum.write_text(f"{sha(archive)}  {archive.name}\n", encoding="ascii")
    print(f"PRIVATE archive: {archive}, SHA256={sha(archive)}", flush=True)
    return archive, checksum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=("14b-e1", "14b-e2", "8b-e2"),
                        default="14b-e1")
    parser.add_argument("--server-id", type=int, default=SERVER_ID)
    args = parser.parse_args()
    if args.server_id != SERVER_ID:
        raise SystemExit("Wrong Intelion server ID")
    c = candidate_for(args.candidate)
    c.review.mkdir(parents=True, exist_ok=True)
    status_path = c.review / "experiment_status.json"
    state = {
        "candidate": c.code, "model": c.model, "epoch": c.epoch,
        "A": "not_verified", "B": "not_started", "C": "not_started",
        "blind": "not_started", "private_backup": "not_attempted",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    problem = None
    try:
        if time_left() < 35 * 60:
            raise RuntimeError("Less than 35min to watchdog; abort GPU to preserve archive/stop time")
        check_baseline(c)
        state["A"] = "reused_75_verified"
        for variant in ("B", "C"):
            if time_left() < 25 * 60:
                raise RuntimeError(f"Insufficient time for {variant} and safe private backup")
            folder = RESULTS / f"methodology_abc_{c.code.replace('-', '_')}_{variant}"
            state[variant] = "generating"
            call("evaluation/run_gpu.py", "--suite", "dev", "--lora-only",
                 "--model", c.model, "--adapter", c.adapter,
                 "--prompt-variant", variant, "--max-new-tokens", "192",
                 "--max-prompt-tokens", "6144", "--cases", CASES,
                 "--probes", PROBES, "--output", folder,
                 "--deadline-file", DEADLINE, "--stop-margin-minutes", "10")
            state[variant] = "completed_75"
        if time_left() < 7 * 60:
            raise RuntimeError("Insufficient time for blind analysis/private backup")
        call("evaluation/compare_methodology_abc.py",
             "--a-dir", c.baseline,
             "--b-dir", RESULTS / f"methodology_abc_{c.code.replace('-', '_')}_B",
             "--c-dir", RESULTS / f"methodology_abc_{c.code.replace('-', '_')}_C",
             "--cases", CASES, "--probes", PROBES, "--output", c.review)
        state["blind"] = "ready_unscored"
    except BaseException as exc:
        problem = f"{type(exc).__name__}: {exc}"
        print("A/B/C failed/partially completed:", problem, flush=True)
        traceback.print_exc()
    finally:
        state["error"] = problem
        status_path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n",
                               encoding="utf-8")
        try:
            archive, checksum = archive_private(c, status_path)
            if time_left() < 5 * 60:
                state["private_backup"] = "skipped_deadline"
                print("Too little time for private GitHub upload; preserve VM files and STOP", flush=True)
            else:
                call("training/upload_private_release.py", "upload", "--tag", c.tag,
                     "--file", archive, "--file", checksum, "--file", status_path)
                state["private_backup"] = "verified"
        except BaseException as exc:
            state["private_backup"] = "FAILED"
            print("PRIVATE GITHUB UPLOAD FAILED; VM files remain:", exc, flush=True)
        status_path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n",
                               encoding="utf-8")
        os.sync()
        print("Requesting Intelion provider STOP; independent watchdog armed", flush=True)
        try:
            call("training/intelion_autostop.py", "stop", "--server-id", SERVER_ID)
        except BaseException as exc:
            print("CRITICAL: API stop failed; stop manually in dashboard:", exc, flush=True)
    if state["blind"] != "ready_unscored":
        raise SystemExit("Incomplete A/B/C. Check private archive/experiment_status.json")


if __name__ == "__main__":
    main()
