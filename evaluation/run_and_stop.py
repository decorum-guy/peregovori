#!/usr/bin/env python3
"""Unattended DEV base-vs-LoRA inference with provider API stop.

Requires a freshly armed Intelion timer and private DEV cases/probes.
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
OUT = ROOT / "eval_private" / "results" / "dev"
DEADLINE_FILE = ROOT / "training" / "outputs" / "intelion_deadline.json"
CASES = ROOT / "eval_private" / "dev" / "cases.jsonl"
PROBES = ROOT / "eval_private" / "dev" / "probes.jsonl"


def execute(argv):
    print("RUN", " ".join(argv), flush=True)
    subprocess.run(argv, cwd=ROOT, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server-id", type=int, required=True)
    a = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not CASES.is_file() or not PROBES.is_file():
        raise SystemExit("Upload DEV zip first; run evaluation/import_private_zip.py. No GPU inference started.")
    if not DEADLINE_FILE.exists():
        raise SystemExit("Arm a fresh provider watchdog before starting evaluation")
    deadline = json.loads(DEADLINE_FILE.read_text(encoding="utf-8"))
    if a.server_id != int(deadline["server_id"]):
        raise SystemExit("Server ID and timer do not match")
    if deadline["deadline_epoch"] - time.time() < 20 * 60:
        raise SystemExit("Insufficient GPU rental budget left. Re-arm only in a NEW VM session.")
    py = sys.executable
    passed = False
    try:
        execute([py, "training/check_result.py"])
        execute([
            py, "evaluation/run_gpu.py", "--suite", "dev",
            "--cases", str(CASES), "--probes", str(PROBES),
            "--adapter", "training/outputs/qlora_v1/adapter",
            "--output", str(OUT), "--deadline-file", str(DEADLINE_FILE),
        ])
        execute([
            py, "evaluation/compare_dev.py", "--results", str(OUT),
            "--cases", str(CASES), "--probes", str(PROBES),
        ])
        passed = True
    except Exception:
        traceback.print_exc()
        print("EVALUATION INCOMPLETE; preserving partial responses/logs.", flush=True)
    finally:
        (OUT / "final_status.json").write_text(json.dumps({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "success": passed,
            "server_id": a.server_id,
        }, indent=2) + "\n", encoding="utf-8")
        if (OUT / "base.jsonl").is_file() or (OUT / "lora.jsonl").is_file():
            try:
                execute([
                    py, "evaluation/compare_dev.py", "--results", str(OUT),
                    "--cases", str(CASES), "--probes", str(PROBES),
                ])
            except Exception as err:
                print("Could not make partial comparison:", err, flush=True)
        archive = ROOT / "eval_private" / "dev_outputs.tar.gz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(OUT, arcname="results_dev")
                tar.add(CASES, arcname="dev_cases.jsonl")
                tar.add(PROBES, arcname="dev_probes.jsonl")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            (archive.parent / (archive.name + ".sha256")).write_text(
                digest + "  " + archive.name + "\n", encoding="ascii"
            )
            print(f"SAVED {archive}; sha256={digest}", flush=True)
        except Exception as err:
            print("Could not archive evaluation:", err, flush=True)
        os.sync()
        print("Requesting Intelion cloud stop; hard-stop timer is still armed.", flush=True)
        try:
            execute([py, "training/intelion_autostop.py", "stop",
                     "--server-id", str(a.server_id)])
        except Exception as err:
            print("STOP API FAILED; manually stop server in Intelion panel:", err, flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
