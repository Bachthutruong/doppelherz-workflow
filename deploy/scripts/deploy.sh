#!/usr/bin/env bash
# Triển khai mã lên VPS: rsync → cài gói → khởi động lại dịch vụ.
# Dùng:  VPS=root@your-server ./deploy/scripts/deploy.sh
set -euo pipefail
: "${VPS:?Đặt VPS=user@host}"
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
rsync -az --delete \
  --exclude .git --exclude .venv --exclude data --exclude .env --exclude '__pycache__' --exclude .pytest_cache --exclude .ruff_cache \
  "$ROOT/" "$VPS:/opt/dh-robot/app/"
ssh "$VPS" 'set -e
  /opt/dh-robot/venv/bin/pip install -q /opt/dh-robot/app
  chown -R dhrobot:dhrobot /opt/dh-robot/app
  systemctl restart dh-robot
  sleep 2 && systemctl is-active dh-robot && curl -fsS http://127.0.0.1:8141/healthz'
