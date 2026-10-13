#!/usr/bin/env bash
# Sourced by the two Intelion scripts. Do not source any .env as shell code.
QWEN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$QWEN_ROOT"
if [[ -n "${QWEN_PYTHON_BIN:-}" ]]; then
  QWEN_PYTHON="$QWEN_PYTHON_BIN"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  QWEN_PYTHON="$VIRTUAL_ENV/bin/python"
elif [[ -x "$QWEN_ROOT/.venv/bin/python" ]]; then
  QWEN_PYTHON="$QWEN_ROOT/.venv/bin/python"
elif [[ -x "$QWEN_ROOT/training/.venv/bin/python" ]]; then
  QWEN_PYTHON="$QWEN_ROOT/training/.venv/bin/python"
else
  QWEN_PYTHON="$(command -v python3)"
fi
"$QWEN_PYTHON" -c 'import dotenv, fastapi, uvicorn, httpx' 2>/dev/null || {
  echo "В выбранном CUDA-окружении отсутствуют API-зависимости. Выполните python -m pip install -r inference/requirements.txt."
  exit 1
}
QWEN_LISTEN_PORT="$("$QWEN_PYTHON" -c 'from inference.config import QwenSettings; print(QwenSettings.from_env().port)')"
