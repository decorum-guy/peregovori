#!/usr/bin/env bash
# Run on Intelion VM 11425 after the former 14B training/DEV job has finished.
# Defaults to 14B epoch 1; optional: bash training/start_methodology_abc_14b.sh --epoch 2
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PY="$PWD/.venv/bin/python"
SERVER=11425
EPOCH=1
if (( $# > 0 )); then
  if (( $# != 2 )) || [[ "$1" != "--epoch" ]] || [[ "$2" != "1" && "$2" != "2" ]]; then
    echo "Usage: bash training/start_methodology_abc_14b.sh [--epoch 1|2]"
    exit 2
  fi
  EPOCH="$2"
fi
CODE="14b-e$EPOCH"
SNAP="training/outputs/qlora_14b_2ep/adapter_epoch_$EPOCH"
BASE="eval_private/results/qwen3_14b_e$EPOCH"
REVIEW="eval_private/results/methodology_abc_14b_e$EPOCH"
REVIEW="$REVIEW"_review
LOG="$REVIEW/pipeline.log"
SESSION="methodology-abc-14b-e$EPOCH"
DEADLINE="training/outputs/intelion_deadline.json"

# Never shutdown an ongoing OTHER GPU experiment.
if tmux has-session -t qwen14b-epochs 2>/dev/null ||
   tmux has-session -t qlora-8b-e2 2>/dev/null ||
   tmux has-session -t methodology-abc-8b 2>/dev/null ||
   tmux has-session -t methodology-abc-14b-e1 2>/dev/null ||
   tmux has-session -t methodology-abc-14b-e2 2>/dev/null ||
   pgrep -f '/training/run_14b_epochs_and_stop.py' >/dev/null ||
   pgrep -f '/training/train_qlora.py' >/dev/null ||
   pgrep -f '/evaluation/run_methodology_abc_and_stop.py' >/dev/null; then
  echo "STOP: another Intelion GPU experiment active; not interrupting it."
  exit 1
fi

HANDOFF=0
cleanup() {
  status=$?
  trap - EXIT
  if (( HANDOFF == 0 )); then
    echo "A/B/C setup failure: requesting immediate Intelion provider STOP."
    if [[ -x "$PY" ]]; then
      "$PY" training/intelion_autostop.py stop --server-id "$SERVER" || true
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

test -x "$PY" || { echo "Missing prepared .venv"; exit 1; }
command -v nvidia-smi >/dev/null || { echo "Missing NVIDIA GPU driver"; exit 1; }
command -v tmux >/dev/null || { echo "Missing tmux"; exit 1; }
nvidia-smi -L
"$PY" -m py_compile evaluation/run_gpu.py evaluation/methodology_context.py \
  evaluation/run_methodology_abc_and_stop.py evaluation/compare_methodology_abc.py
bash -n training/start_methodology_abc_14b.sh

# All integrity checks happen before arming the provider timer.
for f in "eval_private/dev/cases.jsonl" "eval_private/dev/probes.jsonl" \
         "$BASE/lora.jsonl" "$BASE/run_config.json" \
         "$SNAP/adapter_config.json" "$SNAP/training_epoch.json" \
         "training/outputs/qlora_14b_2ep/run_config.json"; do
  test -s "$f" || { echo "STOP: missing original 14B data: $f"; exit 1; }
done
test -n "$(find "$SNAP" -maxdepth 1 -name '*.safetensors' -type f -print -quit)" || {
  echo "STOP: missing adapter weights .safetensors"; exit 1;
}
for result in "eval_private/results/methodology_abc_14b_e$EPOCH"_B \
              "eval_private/results/methodology_abc_14b_e$EPOCH"_C \
              "$REVIEW"; do
  test ! -e "$result" || { echo "STOP: previous/partial result exists: $result"; exit 1; }
done
if pgrep -f '/training/intelion_autostop.py _watch' >/dev/null; then
  echo "STOP: another cloud hard-stop watchdog active; leave it untouched."
  exit 1
fi
"$PY" evaluation/methodology_context.py --validate-only
"$PY" training/upload_private_release.py check
"$PY" - "$CODE" <<'PY'
import sys
from evaluation.run_methodology_abc_and_stop import candidate_for, check_baseline
check_baseline(candidate_for(sys.argv[1]))
print("Preflight passed: verified matching 14B snapshot and 75 archived A responses",flush=True)
PY

if [[ -f "$DEADLINE" ]]; then
  mv "$DEADLINE" "training/outputs/intelion_deadline_before_abc_$(date -u +%Y%m%dT%H%M%SZ).json"
fi
echo "ARMING independent 85min Intelion watchdog. Turn AUTO-RENEW OFF."
"$PY" training/intelion_autostop.py arm --server-id "$SERVER" --minutes 85
"$PY" training/intelion_autostop.py status
sleep 1
pgrep -f '/training/intelion_autostop.py _watch' >/dev/null || {
  echo "ERROR: hard-stop watchdog did not remain active"; exit 1;
}
mkdir -p "$REVIEW"
tmux new-session -d -s "$SESSION" \
  "cd '$PWD' && '$PY' -u evaluation/run_methodology_abc_and_stop.py --candidate '$CODE' --server-id '$SERVER' > '$LOG' 2>&1"
HANDOFF=1

echo "STARTED: $SESSION; candidate=$CODE"
echo "A: reuse same 14B E$EPOCH checkpoint original 75 answers; B/C: 75 new each"
echo "PRIVATE GitHub Release: methodology-abc-$CODE-20261014-vm11425"
echo "Monitor: tail -f $LOG"
echo "After completion confirm STOPPED in Intelion panel; Ctrl+C only stops log viewer."
