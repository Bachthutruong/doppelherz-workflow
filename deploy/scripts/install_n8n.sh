#!/usr/bin/env bash
# Cài Node.js 24 riêng cho n8n (không đụng Node hệ thống) và n8n vào /opt/dh-robot.
set -euo pipefail
BASE=/opt/dh-robot
N8N_VERSION=${N8N_VERSION:-2.48.6}
cd "$BASE"
TB=$(curl -fsSL https://nodejs.org/dist/latest-v24.x/ | grep -o 'node-v24[0-9.]*-linux-x64.tar.xz' | head -n 1)
curl -fsSLO "https://nodejs.org/dist/latest-v24.x/$TB"
tar -xJf "$TB" && rm "$TB" && rm -rf node24 && mv "${TB%.tar.xz}" node24
PATH="$BASE/node24/bin:$PATH" npm install --prefix "$BASE/n8n-pkg" "n8n@$N8N_VERSION" --no-audit --no-fund --loglevel=error
chown -R dhrobot:dhrobot "$BASE/node24" "$BASE/n8n-pkg"
echo "n8n $N8N_VERSION installed"
