#!/usr/bin/env python3
"""Run QLoRA smoke + 1 epoch unattended, then stop Intelion via its API.

Requires Intelion watchdog armed in training/outputs/intelion_deadline.json.
Log with: nohup .venv/bin/python -u training/run_and_stop.py --server-id ID \
     > training/outputs/run.log 2>&1 < /dev/null &
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

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "training" / "outputs"
DEADLINE = OUTPUTS / "intelion_deadline.json"
ADAPTER_DIR = OUTPUTS / "qlora_v1" / "adapter"
BUNDLE = OUTPUTS / "qlora_v1_bundle.tar.gz"


def run(command):
    print("\nRUN:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def safe_budget(deadline, minimum):
    left = deadline - time.time()
    print(f"Minutes remaining before hard server stop: {left/60:.1f}", flush=True)
    if left < minimum:
        raise RuntimeError(f"Too little budget: {left/60:.1f} minutes (< {minimum/60:.1f})")


def save_bundle():
    weights = list(ADAPTER_DIR.glob("*.safetensors"))
    config = ADAPTER_DIR / "adapter_config.json"
    if not weights or not config.is_file():
        raise RuntimeError(f"No valid LoRA adapter files at {ADAPTER_DIR}")
    cfg = OUTPUTS / "qlora_v1" / "run_config.json"
    if not cfg.is_file():
        raise RuntimeError("Missing training run_config.json: training did not finish saving")
    with tarfile.open(BUNDLE, "w:gz") as tar:
        tar.add(ADAPTER_DIR, arcname="adapter")
        tar.add(cfg, arcname="run_config.json")
    data = BUNDLE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    (BUNDLE.parent / (BUNDLE.name + ".sha256")).write_text(
        digest + "  " + BUNDLE.name + "\n", encoding="ascii",
    )
    print(f"SAVED {BUNDLE} ({len(data)/1024**2:.1f} MiB), sha256 {digest}", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server-id", type=int, required=True)
    p.add_argument("--skip-smoke", action="store_true")
    args = p.parse_args()
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    if not DEADLINE.exists():
        raise SystemExit("First ARM the API watchdog (see training/INTELION_RUNBOOK.md)")
    d = json.loads(DEADLINE.read_text(encoding="utf-8"))
    if int(d["server_id"]) != args.server_id:
        raise SystemExit("Refusing: server ID does not match armed watchdog")
    stop_script = str(ROOT / "training" / "intelion_autostop.py")
    python = sys.executable
    success = False
    try:
        safe_budget(d["deadline_epoch"], 25 * 60)
        # Source checksum and 895 SFT completions.
        run([python, "training/prepare_sft.py"])
        run([python, "training/train_qlora.py", "--dry-run", "--max-length", "3072"])
        if not args.skip_smoke:
            safe_budget(d["deadline_epoch"], 25 * 60)
            run([python, "training/train_qlora.py", "--max-steps", "10",
                 "--output", "training/outputs/smoke",
                 "--deadline-file", str(DEADLINE)])
            if not (OUTPUTS / "smoke" / "adapter" / "adapter_config.json").exists():
                raise RuntimeError("Smoke did not save adapter")
        safe_budget(d["deadline_epoch"], 15 * 60)
        run([python, "training/train_qlora.py", "--epochs", "1",
             "--output", "training/outputs/qlora_v1",
             "--deadline-file", str(DEADLINE)])
        save_bundle()
        success = True
    except Exception:
        traceback.print_exc()
        print("FAILED. Check training/outputs/ for logs and any partial checkpoints.", flush=True)
    finally:
        status = {"finished_utc":datetime.now(timezone.utc).isoformat(),
                  "success":success, "bundle": str(BUNDLE) if success else None,
                  "server_id":args.server_id}
        (OUTPUTS / "final_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # Flush output files to the attached disk before requesting cloud stop.
        os.sync()
        print("Stopping cloud server via Intelion API (success or failure).", flush=True)
        # Provider stop request may terminate this process before a reply is printed.
        try:
            run([python, stop_script, "stop", "--server-id", str(args.server_id)])
        except Exception as exc:
            print(f"CRITICAL: could not stop via API: {exc}", flush=True)
            print("Detached hard-stop watchdog remains armed; check dashboard.", flush=True)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
