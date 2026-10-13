#!/usr/bin/env python3
"""Intelion Cloud API stop, with a detached hard-stop watchdog.

Usage:
  python training/intelion_autostop.py token
  python training/intelion_autostop.py list
  python training/intelion_autostop.py arm --server-id 123 --minutes 210
  python training/intelion_autostop.py status
"""
import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = Path.home() / ".config" / "peregovori" / "intelion_token"
DEADLINE_FILE = REPO_ROOT / "training" / "outputs" / "intelion_deadline.json"
LOG_FILE = REPO_ROOT / "training" / "outputs" / "intelion_autostop.log"


def token():
    v = os.environ.get("INTELION_CLOUD_TOKEN", "").strip()
    if v:
        return v
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit("No API token. Run python training/intelion_autostop.py token")


def list_servers():
    try:
        from intelion_cloud import IntelionCloud
    except ImportError as exc:
        raise SystemExit("Install SDK: pip install intelion-cloud") from exc
    with IntelionCloud(token=token()) as client:
        return list(client.cloud_servers.list())


def checked_server(server_id):
    matches = [s for s in list_servers() if int(s.id) == int(server_id)]
    if len(matches) != 1:
        raise RuntimeError(f"Server ID {server_id} not found. Run list and check actual ID.")
    return matches[0]


def stop_server(server_id):
    try:
        s = checked_server(server_id)
        print(f"Request stop: ID {s.id}, name {s.name}, prior status {s.status}", flush=True)
        from intelion_cloud import IntelionCloud
        with IntelionCloud(token=token()) as client:
            client.cloud_servers.stop(server_id=int(server_id))
        print("Stop command sent. Confirm stopped status in Intelion dashboard.", flush=True)
        return True
    except Exception as exc:
        print(f"API stop failed: {type(exc).__name__}: {exc}", flush=True)
        print("IMPORTANT: manually stop server in Intelion dashboard.", flush=True)
        return False


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("token")
    sub.add_parser("list")
    x = sub.add_parser("arm")
    x.add_argument("--server-id", type=int, required=True)
    x.add_argument("--minutes", type=int, default=210)
    x = sub.add_parser("stop")
    x.add_argument("--server-id", type=int, required=True)
    sub.add_parser("status")
    x = sub.add_parser("_watch")
    x.add_argument("--server-id", type=int, required=True)
    x.add_argument("--deadline", type=float, required=True)
    a = p.parse_args()

    if a.action == "token":
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(TOKEN_FILE.parent, 0o700)
        value = getpass.getpass("Intelion API token (hidden): ").strip()
        if not value:
            raise SystemExit("Token must not be empty")
        TOKEN_FILE.write_text(value + "\n", encoding="utf-8")
        os.chmod(TOKEN_FILE, 0o600)
        print("Saved token outside repository with permission 0600.")
    elif a.action == "list":
        for s in list_servers():
            print(f"{s.id}: {s.name} — {s.status}")
    elif a.action == "arm":
        if not 20 <= a.minutes <= 300:
            raise SystemExit("Minutes must be 20..300")
        if DEADLINE_FILE.exists():
            raise SystemExit("Already armed. Check status; do not start a second timer.")
        s = checked_server(a.server_id)
        deadline = time.time() + a.minutes * 60
        DEADLINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {"server_id": a.server_id, "deadline_epoch": deadline}
        DEADLINE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.chmod(DEADLINE_FILE, 0o600)
        with LOG_FILE.open("a", encoding="utf-8") as log:
            w = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "_watch",
                 "--server-id", str(a.server_id), "--deadline", str(deadline)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True,
            )
        print(f"Armed for {s.name} / ID={s.id}; PID={w.pid}")
        print("Hard deadline:", datetime.fromtimestamp(deadline).astimezone().isoformat())
        print("Timer runs ON the VM, not provider-side. Keep auto-renew disabled if possible.")
    elif a.action == "stop":
        sys.exit(0 if stop_server(a.server_id) else 2)
    elif a.action == "status":
        if not DEADLINE_FILE.exists():
            raise SystemExit("No deadline recorded")
        j = json.loads(DEADLINE_FILE.read_text(encoding="utf-8"))
        print(f"Server ID {j['server_id']}; remaining {max(0,j['deadline_epoch']-time.time())/60:.1f} minutes")
        print("Log:", LOG_FILE)
    elif a.action == "_watch":
        print("Watchdog started UTC:", datetime.now(timezone.utc).isoformat(), flush=True)
        while time.time() < a.deadline:
            time.sleep(min(30, max(0.25, a.deadline - time.time())))
        for i in range(1, 6):
            print(f"Hard stop attempt {i}/5", flush=True)
            if stop_server(a.server_id):
                return
            time.sleep(20)
        raise SystemExit("ERROR: all API-stop attempts failed; stop manually immediately.")


if __name__ == "__main__":
    main()
