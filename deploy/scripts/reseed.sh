#!/usr/bin/env bash
# Nạp lại dữ liệu demo trên VPS (ví dụ sau khi thêm ANTHROPIC_API_KEY để Claude viết nội dung).
set -euo pipefail
systemctl stop dh-robot
ts=$(date +%Y%m%d-%H%M%S)
[ -d /opt/dh-robot/data ] && mv /opt/dh-robot/data "/opt/dh-robot/data.bak-$ts"
mkdir -p /opt/dh-robot/data && chown dhrobot:dhrobot /opt/dh-robot/data
systemctl start dh-robot && sleep 3
cd /opt/dh-robot/app
runuser -u dhrobot -- bash -c "set -a; . /opt/dh-robot/.env; set +a; SIMULATE_CLOCK=0 /opt/dh-robot/venv/bin/python scripts/demo_scenario.py"
curl -fsS -X POST http://127.0.0.1:5678/webhook/doppelherz-new-post -H 'Content-Type: application/json' -d '{"post_id": 40004}'
echo
echo "Done. Previous data: /opt/dh-robot/data.bak-$ts"
