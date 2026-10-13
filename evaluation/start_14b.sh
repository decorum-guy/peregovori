#!/usr/bin/env bash
# From an SSH shell ON Intelion VM 11425: bash evaluation/start_14b.sh
# 1 command: verify inputs -> arm a fresh safety timer -> detached tmux -> API stop.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

PY="$PWD/.venv/bin/python"
ID=11425
SESSION=qwen14b-dev
LOG=eval_private/results/qwen3_14b_base/pipeline.log
DEADLINE=training/outputs/intelion_deadline.json

echo "=== Qwen3-14B BASE / DEV-75 ==="
test -x "$PY" || { echo "ERROR: .venv missing; this must run on original Intelion VM"; exit 1; }
command -v tmux >/dev/null || { echo "ERROR: tmux not installed"; exit 1; }
command -v nvidia-smi >/dev/null || { echo "ERROR: NVIDIA driver missing"; exit 1; }
nvidia-smi -L
test -f eval_private/dev/cases.jsonl || { echo "ERROR: private DEV not imported"; exit 1; }
test -f eval_private/dev/probes.jsonl || { echo "ERROR: private DEV probes not imported"; exit 1; }
test -f eval_private/results/dev/base.jsonl || { echo "ERROR: saved Qwen3-8B BASE responses missing"; exit 1; }
test -f eval_private/results/dev/lora.jsonl || { echo "ERROR: saved 8B QLoRA responses missing"; exit 1; }
test -f training/outputs/qlora_v1_bundle.tar.gz || { echo "ERROR: saved QLoRA adapter missing"; exit 1; }
test -f training/outputs/qlora_v1_bundle.tar.gz.sha256 || { echo "ERROR: adapter SHA256 missing"; exit 1; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: session $SESSION is already running; see $LOG"
  exit 1
fi

echo "Checking adapter checksum..."
(cd training/outputs && sha256sum -c qlora_v1_bundle.tar.gz.sha256)
echo "Validating frozen DEV and original 8B comparison without GPU inference..."
"$PY" evaluation/run_gpu.py --suite dev --base-only --validate-only \
  --model Qwen/Qwen3-14B \
  --cases eval_private/dev/cases.jsonl \
  --probes eval_private/dev/probes.jsonl \
  --output eval_private/results/qwen3_14b_base
"$PY" - <<'PY'
import json
from pathlib import Path
ref=Path("eval_private/results/dev")
cases=Path("eval_private/dev/cases.jsonl")
probes=Path("eval_private/dev/probes.jsonl")
config=json.loads((ref/"run_config.json").read_text(encoding="utf-8"))
assert config["model"]=="Qwen/Qwen3-8B", "Unexpected previous baseline"
import hashlib
for label,path in (("case_sha256",cases),("probe_sha256",probes)):
    assert config[label]==hashlib.sha256(path.read_bytes()).hexdigest(), "DEV has changed: "+label
assert config["decoding"]=={"do_sample":False,"max_new_tokens":192,"thinking":False}, "Different original decoding"
ids=None
for name in ("base.jsonl","lora.jsonl"):
    rows=[json.loads(line) for line in (ref/name).read_text(encoding="utf-8").splitlines() if line.strip()]
    these={r["probe_id"] for r in rows}
    assert len(rows)==75 and len(these)==75, f"{name}: expected 75 unique probes"
    if ids is not None:
        assert ids==these, "8B baseline/LoRA probe mismatch"
    ids=these
print("PRE-FLIGHT PASS: original 8B baseline + QLoRA, 75 aligned DEV probes")
PY

# A watchdog is tied to a VM session. An old JSON deadline alone is NOT a live watchdog.
if pgrep -f '/training/intelion_autostop.py _watch' >/dev/null; then
  echo "Found live Intelion safety watchdog; will reuse ONLY if time budget sufficient."
  "$PY" - <<'PY'
import json,time
d=json.load(open("training/outputs/intelion_deadline.json"))
remain=(d["deadline_epoch"]-time.time())/60
print(f"Existing hard-stop timer remaining: {remain:.1f} min")
if int(d["server_id"])!=11425 or remain<45:
    raise SystemExit("STOP: existing watchdog mismatched or <45min; resolve timer manually")
PY
else
  if [[ -e "$DEADLINE" ]]; then
    mv "$DEADLINE" "training/outputs/intelion_deadline_before_14b_$(date -u +%Y%m%dT%H%M%SZ).json"
  fi
  echo "Arming NEW 80-minute in-VM safety timer; auto-renewal should stay disabled."
  "$PY" training/intelion_autostop.py arm --server-id "$ID" --minutes 80
fi
"$PY" training/intelion_autostop.py status

mkdir -p "$(dirname "$LOG")"
ABS_PY="$PY"
tmux new-session -d -s "$SESSION" \
  "cd '$PWD' && '$ABS_PY' -u evaluation/run_14b_and_stop.py --server-id '$ID' > '$LOG' 2>&1"

echo
echo "STARTED detached tmux session: $SESSION"
echo "Model: Qwen/Qwen3-14B BASE, 4-bit NF4, non-thinking"
echo "DEV: same 75 probes as 8B; no LoRA training performed"
echo "Log: $LOG"
echo "Watch logs: tail -f $LOG  (Ctrl+C stops viewing, NOT the job)"
echo "Provider API stop requested automatically after archive, with watchdog fallback."
echo "Never commit eval_private/ to public GitHub."
