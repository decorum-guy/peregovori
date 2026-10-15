"""Budget guard for FUTURE authorized runs. Never creates or starts a server.

watch must run on an independent always-on controller. run executes preflight,
training, bounded off-VM backup and provider stop in finally. Neither is a
provider-side spending guarantee. Secrets are read only from the environment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .common import ROOT, load_config, read_json, require, write_json


def stop_confirmed(server):
    # SDK constants: PAUSED=-1; PAUSING=0 is not a stopped VM.
    return (server.status == -1 and server.server_state == 0 and
            (server.usage_act is None or bool(server.usage_act.stop_dt)))


def provider_client():
    from intelion_cloud import IntelionCloud
    token = os.environ.get("INTELION_CLOUD_TOKEN", "")
    require(bool(token), "Provider token must be set outside Git/logs")
    return IntelionCloud(token=token)


def stop_and_verify(server_id, report_path, client_factory=provider_client, sleep=time.sleep, attempts=8):
    observations = []
    for attempt in range(attempts):
        try:
            with client_factory() as client:
                server = client.cloud_servers.get(server_id)
                if stop_confirmed(server):
                    result = {"status": "PROVIDER_STOP_CONFIRMED", "server_id": server_id,
                              "confirmed_epoch": time.time(), "observations": observations}
                    write_json(report_path, result)
                    return result
                observations.append({"status": server.status, "server_state": server.server_state,
                                     "open_usage_act": server.usage_act is not None})
                client.cloud_servers.stop(server_id=server_id)
        except Exception as exc:
            # No exception text: HTTP clients may include authentication/connection details.
            observations.append({"error_type": type(exc).__name__})
        if attempt + 1 < attempts:
            sleep(15)
    result = {"status": "STOP_UNCONFIRMED_MANUAL_ACTION_REQUIRED", "server_id": server_id,
              "observations": observations}
    write_json(report_path, result)
    raise RuntimeError("Provider stop/billing closure NOT confirmed; stop in dashboard immediately")


def watch(budget_path, report):
    b = read_json(budget_path)
    require(b["provider_stop_verified"] and b["external_watchdog_armed"], "Missing provider/controller evidence")
    with provider_client() as client:
        server = client.cloud_servers.get(b["server_id"])
        require(server.status == 2 and server.is_auto_renewal is False,
                "Controller cannot verify the existing ACTIVE server/auto-renew setting")
        require(server.hourly_price_rub_cents / 100 <= b["max_hourly_rub"], "Controller tariff exceeds budget")
    print(json.dumps({"status": "EXTERNAL_WATCHDOG_ARMED", "server_id": b["server_id"],
                      "billing_stop_epoch": b["billing_stop_epoch"]}), flush=True)
    while time.time() < b["billing_stop_epoch"]:
        # Bounded waits; controller must be kept alive independently of the training VM.
        time.sleep(min(15, max(.01, b["billing_stop_epoch"] - time.time())))
    return stop_and_verify(b["server_id"], report)


def bounded_child(command, deadline, grace_seconds=120):
    require(time.time() < deadline, "Budget exhausted before child start")
    child = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
    try:
        while child.poll() is None and time.time() < deadline:
            time.sleep(1)
        if child.poll() is None:
            # Signal only this child's process group. Trainer saves at a step boundary.
            import signal
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        return child.returncode
    finally:
        if child.poll() is None:
            import signal
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


def run(a):
    from .train import check_budget
    b = read_json(a.budget)
    # Validate backup command before GPU work; no shell interpolation or credentials in JSON.
    backup = read_json(a.backup_command)
    require(isinstance(backup, list) and backup and all(isinstance(v, str) for v in backup), "Backup argv JSON required")
    c = load_config(a.config)
    out = ROOT / c["output_dir"]
    report_path = ROOT / "training/outputs/runtime_v2" / (c["name"] + ".provider_stop.json")
    result = {"status": "STARTING", "server_id": b["server_id"]}
    try:
        check_budget(a.budget, margin=180)
        with provider_client() as client:
            server = client.cloud_servers.get(b["server_id"])
            require(server.status == 2 and server.is_auto_renewal is False, "Existing ACTIVE server; auto-renew must be off")
            require(server.hourly_price_rub_cents / 100 <= b["max_hourly_rub"], "Actual hourly tariff exceeds approval")
        base = [sys.executable, "-m", "training.runtime_v2.train"]
        common = ["--config", a.config, "--corpus", a.corpus, "--budget", a.budget, "--execute"]
        if a.tokenizer_local:
            common += ["--tokenizer-local", a.tokenizer_local]
        if a.offline:
            common += ["--offline"]
        pf = str(out.with_name(out.name + "_preflight") / "preflight.json")
        if not a.resume:
            result["preflight_exit"] = bounded_child(base + ["preflight"] + common, b["train_stop_epoch"])
            require(result["preflight_exit"] == 0, "CUDA preflight failed; no training retry")
        command = base + ["train"] + common + ["--preflight-report", pf]
        if a.resume:
            command += ["--resume", a.resume]
        result["training_exit"] = bounded_child(command, b["train_stop_epoch"])
        if result["training_exit"] == 0:
            from .check_adapter import check_adapter
            result["adapter_check"] = check_adapter(out)
        result["status"] = "COMPLETE" if result["training_exit"] == 0 else "INCOMPLETE_OR_FAILED"
    except BaseException:
        result["status"] = "FAILED_OR_INTERRUPTED"
        raise
    finally:
        # Never let backup failure postpone provider stop beyond its deadline.
        try:
            result["backup_exit"] = bounded_child(backup, min(time.time()+120, b["billing_stop_epoch"]-150), 5)
        except Exception as exc:
            result["backup_error"] = type(exc).__name__
        finally:
            write_json(report_path.with_suffix(".run.json"), result)
            stop_and_verify(b["server_id"], report_path)
    require(result["status"] == "COMPLETE" and result.get("backup_exit") == 0,
            "Experiment/backup incomplete; inspect private outputs and provider status")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    w = sub.add_parser("watch")
    w.add_argument("--budget", required=True)
    w.add_argument("--report", required=True)
    w.add_argument("--external-controller", action="store_true", required=True)
    stop_parser = sub.add_parser("stop")
    stop_parser.add_argument("--budget", required=True)
    stop_parser.add_argument("--report", required=True)
    s = sub.add_parser("run")
    for n in ("config", "corpus", "budget", "backup-command"):
        s.add_argument("--" + n, required=True)
    s.add_argument("--tokenizer-local")
    s.add_argument("--offline", action="store_true")
    s.add_argument("--resume")
    for parser in [w, s, stop_parser]:
        parser.add_argument("--execute", action="store_true")
    a = p.parse_args()
    require(a.execute, "No execution; provider/GPU operations require separate authorization and --execute")
    if a.action == "watch":
        result = watch(a.budget, a.report)
    elif a.action == "stop":
        result = stop_and_verify(read_json(a.budget)["server_id"], a.report)
    else:
        result = run(a)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
