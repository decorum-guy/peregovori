#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 || "$1" == -* || "$1" =~ [[:space:]] ]]; then
  echo "Использование: bash scripts/start_qwen_tunnel.sh root@INTELION_IP (или SSH-алиас)"
  exit 1
fi
echo "Mac: http://127.0.0.1:18080 → Intelion: 127.0.0.1:8001. Остановка туннеля: Ctrl+C."
exec ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:18080:127.0.0.1:8001 "$1"
