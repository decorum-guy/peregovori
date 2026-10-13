#!/usr/bin/env bash
set -euo pipefail
DEMO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEMO_ROOT"
for tool in python3 node npm; do
  command -v "$tool" >/dev/null || { echo "Нужен $tool. Установите Python 3.9+ и Node.js 20+."; exit 1; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo "Нужен Python 3.9+."; exit 1; }
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' || { echo "Нужен Node.js 20+."; exit 1; }
if [[ ! -x web/.venv/bin/python ]]; then
  python3 -m venv web/.venv
fi
DEMO_PYTHON="$DEMO_ROOT/web/.venv/bin/python"
if ! "$DEMO_PYTHON" -c 'import fastapi, httpx, pydantic, dotenv, uvicorn; assert int(pydantic.__version__.split(".")[0]) == 2' 2>/dev/null; then
  "$DEMO_PYTHON" -m pip install -r web/backend/requirements.txt
fi
if [[ ! -f web/.env ]]; then
  cp web/.env.example web/.env
  chmod 600 web/.env
  echo "Создан web/.env. Внесите туда ключ OpenRouter и при необходимости HTTP(S)-прокси."
fi
PYTHONPATH=web/backend "$DEMO_PYTHON" - <<'PY'
from app.config import Settings
settings = Settings.from_env()
try:
    settings.validate()
except ValueError as exc:
    print(str(exc))
    raise SystemExit(1)
if settings.provider_mode == 'unconfigured':
    print('Ключ OpenRouter ещё не задан: сайт откроется, настоящая игра потребует OPENROUTER_API_KEY в web/.env.')
elif settings.provider_mode == 'test_mock':
    print('LLM_MODE=mock: только явно отмеченные тестовые кейсы и ответы.')
PY
if [[ ! -d web/frontend/node_modules ]] || [[ web/frontend/package-lock.json -nt web/frontend/node_modules/.package-lock.json ]]; then
  (cd web/frontend && npm ci)
fi
if "$DEMO_PYTHON" - <<'PY'
from pathlib import Path
root=Path('web/frontend')
stamp=root/'dist/.demo-build'
files=list((root/'src').rglob('*')) + [root/name for name in ('package.json','package-lock.json','index.html','vite.config.ts','tsconfig.json','tailwind.config.js','postcss.config.js')]
stale=not (root/'dist/index.html').is_file() or not stamp.is_file() or any(p.is_file() and p.stat().st_mtime > stamp.stat().st_mtime for p in files)
raise SystemExit(0 if stale else 1)
PY
then
  (cd web/frontend && npm run build)
  touch web/frontend/dist/.demo-build
fi
"$DEMO_PYTHON" - <<'PY'
import socket
with socket.socket() as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('127.0.0.1',8000))
    except OSError:
        print('Порт 8000 уже занят. Проверьте http://127.0.0.1:8000 или завершите прежний локальный запуск.')
        raise SystemExit(1)
PY
echo "Линия решения: http://127.0.0.1:8000"
echo "Каталог игр: http://127.0.0.1:8000/games"
echo "Остановка приложения: Ctrl+C. Сессии сохраняются в SQLite."
exec "$DEMO_PYTHON" -m uvicorn app.main:app --app-dir web/backend --host 127.0.0.1 --port 8000
