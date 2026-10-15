"""Emergency launch adapter: use the already-armed on-VM Intelion watchdog.

Explicitly weaker than guard.py's independent external controller. This is NOT
the production spending guard. This wrapper never starts/stops a VM or changes
the underlying trainer, config or data; the watchdog handles VM stop.
"""
import json
import sys
import time
from pathlib import Path

from training.runtime_v2 import train
from training.runtime_v2.common import ROOT, require

DEADLINE = ROOT / "training/outputs/intelion_deadline.json"
SERVER_ID = 11425

def on_vm_watchdog_budget(_path, margin=0):
    require(DEADLINE.is_file(), "STOP: Intelion watchdog deadline missing")
    d = json.loads(DEADLINE.read_text(encoding="utf-8"))
    require(int(d["server_id"]) == SERVER_ID, "STOP: wrong server ID")
    deadline = float(d["deadline_epoch"])
    require(time.time() + margin < deadline - 600, "STOP: <10min deadline safety margin")
    # Training's SafetyCallback will stop on a completed optimizer step at this point.
    return {"train_stop_epoch": deadline - 600, "billing_stop_epoch": deadline}

if __name__ == "__main__":
    train.check_budget = on_vm_watchdog_budget
    train.main()
