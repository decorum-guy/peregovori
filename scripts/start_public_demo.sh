#!/usr/bin/env bash
set -euo pipefail
command -v cloudflared >/dev/null || { echo "Нужен официальный cloudflared. Сначала выполните диагностику из README_DEMO."; exit 1; }
echo "Публичный Quick Tunnel к http://127.0.0.1:8000; остановка: Ctrl+C."
exec cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:8000
