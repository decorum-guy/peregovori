#!/usr/bin/env python3
"""Two extra GPU DEV passes on existing 8B V2, then blind review, private backup, Intelion STOP.

A: REUSE the original 75 V2 responses, exact historical prompt.
B: same adapter + generic concise course rules.
C: same adapter + B + TEN relevant but NON-EXCLUSIVE techniques.

This deliberately does NOT touch ongoing 14B run, TRAIN weights or sealed TEST.
All private data is sent to private-peregovori Release, NEVER public Git.
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PRIVATE = ROOT / "eval_private"
BASE = PRIVATE / "results" / "qwen3_8b_e2"
RESULTS = PRIVATE / "results"
OUT = RESULTS / "methodology_abc_8b_v2_review"
ADAPTER = ROOT / "training" / "outputs" / "qlora_v2_e2" / "adapter"
CASES = PRIVATE / "dev" / "cases.jsonl"
PROBES = PRIVATE / "dev" / "probes.jsonl"
DEADLINE = ROOT / "training" / "outputs" / "intelion_deadline.json"
LOG = OUT / "pipeline.log"
TAG = "methodology-abc-8b-v2-20261014-vm11425"


def call(script, *params):
    cmd = [sys.executable, script, *map(str, params)]
    print("RUN:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def time_left():
    cfg = json.loads(DEADLINE.read_text(encoding="utf-8"))
    if int(cfg["server_id"]) != 11425:
        raise RuntimeError("Unexpected Intelion VM 11425 watchdog ID")
    return float(cfg["deadline_epoch"]) - time.time()


def zip_private():
    path = PRIVATE / "methodology_abc_8b_v2_private.tar.gz"
    with tarfile.open(path,"w:gz") as tar:
        for where, to in [
            (CASES,"dev/cases.jsonl"),(PROBES,"dev/probes.jsonl"),
            (BASE / "lora.jsonl","previous_A/lora.jsonl"),
            (BASE / "run_config.json","previous_A/run_config.json"),
            (RESULTS / "methodology_abc_8b_v2_B","variant_B"),
            (RESULTS / "methodology_abc_8b_v2_C","variant_C"),
            (OUT,"blind_review"),
        ]:
            if Path(where).exists():
                tar.add(where,arcname=to)
    digest=sha(path)
    checksum=Path(str(path)+".sha256")
    checksum.write_text(f"{digest}  {path.name}\n",encoding="ascii")
    print(f"ARCHIVED PRIVATE A/B/C: {path} sha256={digest}",flush=True)
    return path,checksum


def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--server-id",type=int,default=11425)
    args=arg.parse_args()
    if args.server_id != 11425:
        raise SystemExit("Wrong cloud server")
    OUT.mkdir(parents=True,exist_ok=True)
    state={"model":"Qwen/Qwen3-8B","adapter":"V2 E2 rank16",
           "A":"reused existing historical DEV",
           "B":"not_started","C":"not_started","blind":"not_started",
           "private_backup":"not_started","timestamp_utc":datetime.now(timezone.utc).isoformat()}
    failure=None
    try:
        source=json.loads((BASE/"run_config.json").read_text(encoding="utf-8"))
        if source["model"]!="Qwen/Qwen3-8B" or source.get("adapter_weights_sha256") is None:
            raise RuntimeError("Expected existing real 8B V2 LoRA results for baseline A")
        from evaluation.run_gpu import validate_adapter
        if validate_adapter(ADAPTER)!=source["adapter_weights_sha256"]:
            raise RuntimeError("Current adapter differs from frozen historical V2")
        for k,p in (("case_sha256",CASES),("probe_sha256",PROBES)):
            if source[k]!=sha(p):
                raise RuntimeError("Private frozen DEV changed since original 8B V2: "+k)
        from evaluation.methodology_context import identity_manifest
        print(json.dumps(identity_manifest(),ensure_ascii=False,indent=2),flush=True)
        # Validate input/fingerprints without inference before using GPU minutes.
        for name in ("B","C"):
            if time_left() < 30*60:
                raise RuntimeError(f"Insufficient time for {name} + private backup")
            state[name]="generating"
            folder=RESULTS / f"methodology_abc_8b_v2_{name}"
            call("evaluation/run_gpu.py","--suite","dev","--lora-only",
                 "--model","Qwen/Qwen3-8B","--adapter",ADAPTER,
                 "--prompt-variant",name,"--max-new-tokens","192",
                 "--max-prompt-tokens","6144","--cases",CASES,"--probes",PROBES,
                 "--output",folder,"--deadline-file",DEADLINE,
                 "--stop-margin-minutes","10")
            state[name]="completed_75"
        if time_left() < 8*60:
            raise RuntimeError("No time left for blind comparison/private backup")
        call("evaluation/compare_methodology_abc.py",
             "--a-dir",BASE,"--b-dir",RESULTS/"methodology_abc_8b_v2_B",
             "--c-dir",RESULTS/"methodology_abc_8b_v2_C",
             "--cases",CASES,"--probes",PROBES,"--output",OUT)
        state["blind"]="ready_unscored"
    except BaseException as exc:
        failure=f"{type(exc).__name__}: {exc}"
        print("A/B/C pipeline incomplete:",failure,flush=True)
        traceback.print_exc()
    finally:
        state["error"]=failure
        state["private_backup"]="preparing"
        status=OUT/"experiment_status.json"
        status.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        try:
            archive,checksum=zip_private()
            if time_left() < 5*60:
                state["private_backup"]="skipped_insufficient_time"
                print("SKIPPING upload (watchdog imminent); files stay on Intelion disk",flush=True)
            else:
                call("training/upload_private_release.py","upload","--tag",TAG,
                     "--file",archive,"--file",checksum)
                state["private_backup"]="verified"
        except BaseException as exc:
            state["private_backup"]="FAILED"
            print("PRIVATE BACKUP FAILED; files stay on server disk:",exc,flush=True)
        status.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.sync()
        print("Requesting Intelion provider STOP, watchdog also active",flush=True)
        try:
            call("training/intelion_autostop.py","stop","--server-id",args.server_id)
        except BaseException as exc:
            print("CRITICAL: STOP API failed; STOP VM IN INTELION CONSOLE:",exc,flush=True)
    if state["blind"]!="ready_unscored":
        raise SystemExit("A/B/C incomplete. Inspect private status and partial outputs.")


if __name__=="__main__":
    main()
