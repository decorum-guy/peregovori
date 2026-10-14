#!/usr/bin/env bash
# Run ON existing Intelion RTX3090 VM 11425 only, after PRIVATE repo config.
# One command: bash training/start_14b_epochs.sh
# Five-hour funded budget. Hard watchdog armed for 265min AFTER preflight,
# leaving a buffer for VM boot/provisioning. Cloud billing starts at VM boot.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PY="$PWD/.venv/bin/python"
ID=11425
SESSION=qwen14b-epochs
LOG=training/outputs/qlora_14b_2ep/pipeline.log
DEADLINE=training/outputs/intelion_deadline.json
ARMED=0
HANDOFF=0

on_exit() {
  local code=$?
  trap - EXIT
  if [[ "$HANDOFF" != "1" ]]; then
    echo "ERROR OR EARLY EXIT: requesting IMMEDIATE Intelion provider STOP even if watchdog was not armed"
    "$PY" training/intelion_autostop.py stop --server-id "$ID" || true
  fi
  exit "$code"
}
trap on_exit EXIT

echo "=== Qwen3-14B BASE + QLoRA epoch 1/2 + frozen DEV (existing VM 11425) ==="
test -x "$PY" || { echo "STOP: prepared .venv missing"; exit 1; }
command -v nvidia-smi >/dev/null || { echo "STOP: NVIDIA driver missing"; exit 1; }
command -v tmux >/dev/null || { echo "STOP: tmux missing"; exit 1; }
nvidia-smi -L
"$PY" -m py_compile training/train_qlora.py training/run_14b_epochs_and_stop.py \
  training/upload_private_release.py training/intelion_autostop.py \
  evaluation/run_gpu.py evaluation/compare_14b_epochs.py
bash -n training/start_14b_epochs.sh

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "STOP: experiment already running in tmux $SESSION"
  exit 1
fi
if pgrep -f '/training/train_qlora.py' >/dev/null; then
  echo "STOP: another training process detected; cannot share same 3090"
  exit 1
fi
if pgrep -f '/training/run_14b_epochs_and_stop.py' >/dev/null; then
  echo "STOP: 14B runner already active"
  exit 1
fi

for f in eval_private/dev/cases.jsonl eval_private/dev/probes.jsonl \
         eval_private/results/dev/base.jsonl eval_private/results/dev/lora.jsonl \
         eval_private/results/dev/run_config.json; do
  test -s "$f" || { echo "STOP: missing original frozen DEV input $f"; exit 1; }
done

echo "Preflight: PRIVATE GitHub repository and bearer token. No public release fallback."
"$PY" training/upload_private_release.py check

# The raw 14B model weights download is ~30GB. Leave ample disk margin
# for checkpoint copies, adapter snapshots and cached 8B weights.
FREE_KB=$(df -Pk /root | awk 'NR==2 {print $4}')
MIN_KB=$((40 * 1024 * 1024))
echo "Available disk: $((FREE_KB / 1024 / 1024)) GiB; required >=40 GiB"
if (( FREE_KB < MIN_KB )); then
  echo "STOP: insufficient disk for a fresh Qwen3-14B model download"
  echo "Do NOT delete prior adapters or frozen DEV; inspect disk/cache and resolve first"
  exit 1
fi
test ! -f training/outputs/qlora_14b_2ep/experiment_status.json || {
  echo "STOP: previous experiment status exists; do not overwrite"
  exit 1
}
test ! -f eval_private/results/qwen3_14b_e2/lora.jsonl || {
  echo "STOP: previous E2 DEV responses already exist; inspect before restart"
  exit 1
}
for existing in training/outputs/qlora_14b_2ep/adapter_epoch_1                 training/outputs/qlora_14b_2ep/adapter_epoch_2                 training/outputs/qlora_14b_2ep/checkpoint-112                 training/outputs/qlora_14b_2ep/pipeline.log; do
  test ! -e "$existing" || {
    echo "STOP: previous 14B experiment artifacts exist: $existing; protect data before retry"
    exit 1
  }
done

echo "Checking existing provider watchdog..."
if pgrep -f '/training/intelion_autostop.py _watch' >/dev/null; then
  echo "STOP: an existing active watchdog detected. Check timer manually; do not re-arm."
  exit 1
fi
if [[ -f "$DEADLINE" ]]; then
  mv "$DEADLINE" "training/outputs/intelion_deadline_before_14b_epochs_$(date -u +%Y%m%dT%H%M%SZ).json"
fi
echo "ARMING Intelion provider API hard-stop at 265min. Ensure AUTO-RENEW is OFF."
"$PY" training/intelion_autostop.py arm --server-id "$ID" --minutes 265
ARMED=1
"$PY" training/intelion_autostop.py status
sleep 1
if ! pgrep -f '/training/intelion_autostop.py _watch' >/dev/null; then
  echo "ERROR: detached Intelion watchdog process did not remain active"
  false
fi

mkdir -p "$(dirname "$LOG")"
tmux new-session -d -s "$SESSION" \
  "cd '$PWD' && '$PY' -u training/run_14b_epochs_and_stop.py --server-id '$ID' > '$LOG' 2>&1"
HANDOFF=1

echo "STARTED: tmux=$SESSION"
echo "Order: 14B BASE DEV75 -> 14B longest-example backward VRAM test -> fresh 2-epoch QLoRA"
echo "       -> E1/E2 distinct adapter snapshots -> 75 DEV responses on each -> blind A/B/C(+8B V2)"
echo "Hard-stop: 265min from arming; stop immediately after archive/private GitHub backup."
echo "Monitor safely: tail -f $LOG"
echo "Ctrl+C exits log viewer, not tmux job. Verify server status STOPPED in Intelion UI."
