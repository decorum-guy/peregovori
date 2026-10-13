#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/qwen_python.sh"
if [[ "${1:-}" != "" && "${1:-}" != "--foreground" ]]; then
  echo "Использование: bash scripts/start_qwen_server.sh [--foreground]"
  exit 1
fi
if [[ "${1:-}" != "--foreground" ]] && command -v tmux >/dev/null && tmux has-session -t line-qwen 2>/dev/null; then
  echo "tmux line-qwen уже существует. Новый процесс не запущен."
  exec bash scripts/status_qwen_server.sh
fi
"$QWEN_PYTHON" - "$QWEN_LISTEN_PORT" <<'PY'
import socket, sys
with socket.socket() as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('127.0.0.1', int(sys.argv[1])))
    except OSError:
        print('QWEN_PORT уже занят. Проверьте status_qwen_server.sh; новый процесс не запущен.')
        raise SystemExit(1)
PY
"$QWEN_PYTHON" -m inference.preflight --gpu
echo "Qwen API: http://127.0.0.1:$QWEN_LISTEN_PORT (только loopback)."
echo "Готовность: bash scripts/status_qwen_server.sh. Лог: inference/logs/qwen.log."
if [[ "${1:-}" != "--foreground" ]] && command -v tmux >/dev/null; then
  printf -v QWEN_COMMAND 'cd %q && exec %q -u -m inference.server' "$QWEN_ROOT" "$QWEN_PYTHON"
  tmux new-session -d -s line-qwen "$QWEN_COMMAND"
  echo "Запущено в tmux line-qwen. Загрузка может занять несколько минут; SSH можно закрыть."
  echo "Посмотреть процесс: tmux attach -t line-qwen (отсоединиться: Ctrl+B, затем D)."
else
  echo "Запуск в текущем терминале. Для работы после закрытия SSH установите tmux."
  exec "$QWEN_PYTHON" -u -m inference.server
fi
