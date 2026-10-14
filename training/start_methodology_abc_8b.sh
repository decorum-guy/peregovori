#!/usr/bin/env bash
# Run ONLY AFTER current 14B Intelion job FINISHED AND server was restarted.
# Same server VM11425 and 8B V2 disk. Cost cap 85min from this launcher.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PY="$PWD/.venv/bin/python"
SERVER=11425
SESSION=methodology-abc-8b
LOG="eval_private/results/methodology_abc_8b_v2_review/pipeline.log"
DEADLINE="training/outputs/intelion_deadline.json"

# NEVER shut down an actively running OTHER experiment.
if tmux has-session -t qwen14b-epochs 2>/dev/null ||
   tmux has-session -t qlora-8b-e2 2>/dev/null ||
   pgrep -f '/training/run_14b_epochs_and_stop.py' >/dev/null ||
   pgrep -f '/training/train_qlora.py' >/dev/null; then
   echo "NOT STARTING A/B/C: other GPU experiment still running."
   echo "No provider stop requested: leave the existing training uninterrupted."
   exit 1
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "NOT STARTING: A/B/C already running"
  exit 1
fi

OWNED=0
HANDOFF=0
cleanup() {
  status=$?
  trap - EXIT
  if (( OWNED == 1 && HANDOFF == 0 )); then
    echo "A/B/C LAUNCH FAILED: attempting immediate Intelion STOP; verify in dashboard"
    "$PY" training/intelion_autostop.py stop --server-id "$SERVER" || true
  fi
  exit "$status"
}
trap cleanup EXIT

test -x "$PY" || { echo "STOP: missing venv"; exit 1; }
command -v nvidia-smi >/dev/null || { echo "STOP: GPU missing"; exit 1; }
command -v tmux >/dev/null || { echo "STOP: tmux missing"; exit 1; }
"$PY" -m py_compile evaluation/methodology_context.py evaluation/run_gpu.py \
  evaluation/compare_methodology_abc.py evaluation/run_methodology_abc_and_stop.py
bash -n training/start_methodology_abc_8b.sh
"$PY" evaluation/methodology_context.py --validate-only
"$PY" training/upload_private_release.py check
for path in "eval_private/dev/cases.jsonl" "eval_private/dev/probes.jsonl" \
  "eval_private/results/qwen3_8b_e2/lora.jsonl" \
  "eval_private/results/qwen3_8b_e2/run_config.json" \
  "training/outputs/qlora_v2_e2/adapter/adapter_config.json"; do
  test -s "$path" || { echo "STOP: missing original frozen artifact $path"; exit 1; }
done
test ! -e "$LOG" || { echo "STOP: prior A/B/C run present ($LOG); inspect before repeat"; exit 1; }
test ! -e "eval_private/results/methodology_abc_8b_v2_B/lora.jsonl" || {
  echo "STOP: partial B already exists; inspect before repeat"; exit 1;
}
test ! -e "eval_private/results/methodology_abc_8b_v2_C/lora.jsonl" || {
  echo "STOP: partial C already exists; inspect before repeat"; exit 1;
}
if pgrep -f '/training/intelion_autostop.py _watch' >/dev/null; then
  echo "STOP: previous watchdog still active; do not overwrite"
  exit 1
fi
OWNED=1
if [[ -f "$DEADLINE" ]]; then
  mv "$DEADLINE" "training/outputs/intelion_deadline_before_abc_$(date -u +%Y%m%dT%H%M%SZ).json"
fi
echo "Arming independent 85min cloud hard-stop. Disable Intelion AUTO-RENEW."
"$PY" training/intelion_autostop.py arm --server-id "$SERVER" --minutes 85
"$PY" training/intelion_autostop.py status
sleep 1
if ! pgrep -f '/training/intelion_autostop.py _watch' >/dev/null; then
  echo "ERROR: hard-stop watchdog process not alive"
  false
fi

mkdir -p "$(dirname "$LOG")"
tmux new-session -d -s "$SESSION" \
  "cd '$PWD' && '$PY' -u evaluation/run_methodology_abc_and_stop.py --candidate 8b-e2 --server-id '$SERVER' > '$LOG' 2>&1"
HANDOFF=1

echo "STARTED: $SESSION"
echo "REUSED original A=75; now generating B=75 and C=75 with unchanged 8B E2 weights"
echo "Expected private GitHub Release: methodology-abc-8b-v2-20261014-vm11425"
echo "Watch: tail -f $LOG"
echo "Check provider STOPPED status when done. Ctrl+C only exits log viewer."
