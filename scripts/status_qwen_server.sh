#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/qwen_python.sh"
if command -v tmux >/dev/null && tmux has-session -t line-qwen 2>/dev/null; then
  echo "Процесс tmux line-qwen существует; это ещё не подтверждение готовности модели."
fi
exec "$QWEN_PYTHON" scripts/test_qwen.py --base-url "http://127.0.0.1:$QWEN_LISTEN_PORT" --health-only
