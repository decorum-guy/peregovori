#!/usr/bin/env python3
"""Unattended 14B BASE DEV experiment on Intelion server 11425.

One Qwen3-14B in 4-bit mode, 75 private DEV probes, compare with
already saved 8B and 8B+QLoRA V1 on IDENTICAL inputs/decoding.
Always preserve partial results then request Intelion provider stop.
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
PRIVATE = ROOT / "eval_private"
OUT = PRIVATE / "results" / "qwen3_14b_base"
REF = PRIVATE / "results" / "dev"
CASES = PRIVATE / "dev" / "cases.jsonl"
PROBES = PRIVATE / "dev" / "probes.jsonl"
DEADLINE = ROOT / "training" / "outputs" / "intelion_deadline.json"
ARCHIVE = PRIVATE / "qwen3_14b_dev_outputs.tar.gz"
ARCHIVE_HASH = PRIVATE / "qwen3_14b_dev_outputs.tar.gz.sha256"


def run(cmd):
    print("\nRUN:", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pack():
    with tarfile.open(ARCHIVE, mode="w:gz") as tar:
        tar.add(OUT, arcname="qwen3_14b_base")
        for name in ("base.jsonl", "lora.jsonl", "run_config.json"):
            p = REF / name
            if p.exists():
                tar.add(p, arcname="reference_8b/" + name)
        for p in (CASES, PROBES):
            if p.exists():
                tar.add(p, arcname="dev_private/" + p.name)
    digest = file_sha(ARCHIVE)
    ARCHIVE_HASH.write_text(f"{digest}  {ARCHIVE.name}\n", encoding="ascii")
    print(f"ARCHIVED: {ARCHIVE} ({ARCHIVE.stat().st_size:,} bytes), sha256={digest}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-id", type=int, required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    success = False
    try:
        if args.server_id != 11425:
            raise RuntimeError("Refusing unknown Intelion server ID")
        if not DEADLINE.is_file():
            raise RuntimeError("No watchdog deadline; run evaluation/start_14b.sh")
        d = json.loads(DEADLINE.read_text(encoding="utf-8"))
        if int(d["server_id"]) != args.server_id or d["deadline_epoch"] < time.time() + 25 * 60:
            raise RuntimeError("Expired/mismatched watchdog; need >=25min before hard stop")
        # FROZEN private DEV. Never copy to GitHub / TRAIN.
        if not CASES.is_file() or not PROBES.is_file():
            raise RuntimeError("DEV data absent; import original DEV_frozen.zip first")
        if not (REF / "base.jsonl").is_file() or not (REF / "lora.jsonl").is_file():
            raise RuntimeError("Previous 8B / QLoRA reference responses missing")
        py = sys.executable
        run([
            py, "evaluation/run_gpu.py",
            "--suite", "dev", "--base-only", "--validate-only",
            "--model", "Qwen/Qwen3-14B",
            "--cases", str(CASES), "--probes", str(PROBES),
            "--output", str(OUT),
        ])
        run([
            py, "evaluation/run_gpu.py",
            "--suite", "dev", "--base-only",
            "--model", "Qwen/Qwen3-14B",
            "--cases", str(CASES), "--probes", str(PROBES),
            "--output", str(OUT),
            "--deadline-file", str(DEADLINE),
            "--max-new-tokens", "192",
        ])
        run([
            py, "evaluation/compare_14b.py",
            "--reference-dir", str(REF), "--candidate-dir", str(OUT),
            "--private-cases", str(CASES), "--private-probes", str(PROBES),
        ])
        success = True
    except BaseException:
        traceback.print_exc()
        print("INCOMPLETE: preserving any generated 14B replies and logs.", flush=True)
    finally:
        (OUT / "final_status.json").write_text(json.dumps({
            "experiment": "Qwen/Qwen3-14B base only",
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "success": success, "server_id": args.server_id,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            pack()
        except Exception as exc:
            print(f"CRITICAL: could not archive results: {exc}", flush=True)
        os.sync()
        print("Requesting Intelion API cloud stop. Watchdog remains independent.", flush=True)
        try:
            run([sys.executable, "training/intelion_autostop.py", "stop",
                 "--server-id", str(args.server_id)])
        except Exception as exc:
            print(f"CRITICAL: cloud stop command failed: {exc}. Stop VM in Intelion UI.", flush=True)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
