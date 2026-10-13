#!/usr/bin/env bash
# One command after starting THE SAME Intelion GPU VM 11425:
#   bash training/start_8b_2epochs.sh
# Keep auto-renew OFF; provider billing starts with VM boot, not this script.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PY="$PWD/.venv/bin/python"
ID=11425
SESSION=qlora-8b-e2
LOG=training/outputs/qlora_v2_e2/pipeline.log
DEADLINE=training/outputs/intelion_deadline.json
ARMED=0

fail_after_arm() {
  local status=$?
  if [[ "$ARMED" == "1" ]]; then
    echo "Launcher failed after arming; requesting immediate Intelion API stop."
    "$PY" training/intelion_autostop.py stop --server-id "$ID" || true
  fi
  exit "$status"
}
trap fail_after_arm ERR

echo "=== QWEN3-8B QLoRA 2 EPOCHS / RANK16 / DEV 75 ==="
test -x "$PY" || { echo "STOP: missing .venv. Use existing prepared Intelion VM."; exit 1; }
command -v tmux >/dev/null || { echo "STOP: tmux not installed"; exit 1; }
command -v nvidia-smi >/dev/null || { echo "STOP: GPU driver missing"; exit 1; }
nvidia-smi -L

test -f eval_private/dev/cases.jsonl || { echo "STOP: private DEV cases missing"; exit 1; }
test -f eval_private/dev/probes.jsonl || { echo "STOP: private DEV probes missing"; exit 1; }
test -f eval_private/results/dev/base.jsonl || { echo "STOP: original BASE reference missing"; exit 1; }
test -f eval_private/results/dev/lora.jsonl || { echo "STOP: V1 LoRA DEV reference missing"; exit 1; }
test -f training/outputs/qlora_v1_bundle.tar.gz.sha256 || { echo "STOP: original adapter digest missing"; exit 1; }
test -z "$(pgrep -f 'training/train_qlora.py' || true)" || { echo "STOP: training already running"; exit 1; }
test ! -f training/outputs/qlora_v2_e2/run_config.json || { echo "STOP: V2 final artifact already exists"; exit 1; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "STOP: tmux $SESSION already running"
  exit 1
fi
echo "Validating existing adapter and DEV reference with no new inference..."
(cd training/outputs && sha256sum -c qlora_v1_bundle.tar.gz.sha256)
"$PY" training/check_result.py
"$PY" - <<'PY'
import hashlib,json
from pathlib import Path
ref=Path("eval_private/results/dev")
cfg=json.load((ref/"run_config.json").open())
assert cfg["model"]=="Qwen/Qwen3-8B"
assert cfg["suite"]=="dev"
assert cfg["decoding"]=={"do_sample":False,"max_new_tokens":192,"thinking":False}
for field,path in (("case_sha256",Path("eval_private/dev/cases.jsonl")),
                   ("probe_sha256",Path("eval_private/dev/probes.jsonl"))):
    assert hashlib.sha256(path.read_bytes()).hexdigest()==cfg[field]
ids=[]
for name in ("base.jsonl","lora.jsonl"):
    rows=[json.loads(x) for x in (ref/name).read_text().splitlines() if x.strip()]
    assert len(rows)==75 and len({x["probe_id"] for x in rows})==75
    ids.append({x["probe_id"] for x in rows})
assert ids[0]==ids[1]
print("PASS: 75 original BASE + 75 V1 responses on IDENTICAL private frozen DEV")
PY

# An expired JSON deadline persisted on the VM's disk. Old watchdog PROCESS
# does not survive VM stop. Never overwrite a deadline with an active watcher.
if pgrep -f '/training/intelion_autostop.py _watch' >/dev/null; then
  echo "STOP: an Intelion hard-stop watchdog is already running."
  echo "Check it manually; do not create a competing timer."
  exit 1
fi
if [[ -f "$DEADLINE" ]]; then
  mv "$DEADLINE" "training/outputs/intelion_deadline_before_8b_e2_$(date -u +%Y%m%dT%H%M%SZ).json"
fi
echo "Arming hard cloud-stop IN THE VM: 100min. Check auto-renew OFF in provider UI."
"$PY" training/intelion_autostop.py arm --server-id "$ID" --minutes 100
ARMED=1
"$PY" training/intelion_autostop.py status

mkdir -p "$(dirname "$LOG")"
tmux new-session -d -s "$SESSION" \
  "cd '$PWD' && '$PY' -u training/run_8b_2epochs_and_stop.py --server-id '$ID' > '$LOG' 2>&1"

echo
echo "STARTED detached tmux session: $SESSION"
echo "GPU: Qwen3-8B NF4, LoRA rank16; TWO FRESH epochs, not resuming V1."
echo "DEV: only 75 NEW LoRA replies; existing BASE/V1 replies REUSED."
echo "Watch: tail -f $LOG  (Ctrl+C stops viewing only)."
echo "Hard stop: 100min from arming; successful/failed runner requests earlier stop."
echo "Check Intelion dashboard later: must say STOPPED."
