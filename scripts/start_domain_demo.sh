#!/usr/bin/env bash
set -euo pipefail
DEMO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEMO_ROOT"
DEMO_CONFIG="${1:-web/cloudflared.local.yml}"
if [[ $# -gt 2 || ( $# -eq 2 && "${2:-}" != "--check" ) ]]; then
  echo "Использование: bash scripts/start_domain_demo.sh [config.yml] [--check]"
  exit 1
fi
if [[ ! -f "$DEMO_CONFIG" ]]; then
  echo "Скопируйте deploy/cloudflared.demo.example.yml в web/cloudflared.local.yml и заполните домен, UUID и путь credentials."
  exit 1
fi
if LC_ALL=C grep -q 'REPLACE_' "$DEMO_CONFIG"; then
  echo "Конфигурация ещё не заполнена: нужны ваш домен, UUID туннеля и путь к локальному credentials-файлу."
  exit 1
fi
command -v cloudflared >/dev/null || { echo "Нужен официальный cloudflared; инструкция в web/README_DEMO.md."; exit 1; }
cloudflared tunnel --no-autoupdate --config "$DEMO_CONFIG" ingress validate
if [[ "${2:-}" == "--check" ]]; then
  echo "Конфигурация маршрутизации проверена; туннель не запускался."
  exit 0
fi
curl --fail --silent --show-error --noproxy '*' --max-time 3 http://127.0.0.1:8000/api/health >/dev/null || {
  echo "Сначала запустите сайт: bash scripts/start_demo_mac.sh"
  exit 1
}
echo "Запуск настроенного домена к Mac. Каталог: /games; игра: /games/line-decision. Остановка: Ctrl+C."
exec cloudflared tunnel --no-autoupdate --config "$DEMO_CONFIG" run
