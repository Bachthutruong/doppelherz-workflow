# Deployment

## Local

```bash
make install && make test
cp .env.example .env            # optional: ANTHROPIC_API_KEY, tokens
make demo && make serve         # http://127.0.0.1:8000
```

## Docker Compose (robot + n8n)

```bash
cp .env.example .env
docker compose up -d --build
```

- Dashboard: http://localhost:8000 · n8n: http://localhost:5678 (create the owner account on first visit).
- The n8n container imports `workflows/n8n/doppelherz_content_sync.json` and publishes it on every start.
- Trigger the pipeline: `curl -X POST http://localhost:5678/webhook/doppelherz-new-post -H 'Content-Type: application/json' -d '{"post_id": 39906}'`.

## VPS (as running at https://doppelherz-workflow.jiudi.cloud)

Ubuntu, nginx and certbot already installed.

```bash
# 1. User and folders
useradd --system --home /opt/dh-robot --shell /usr/sbin/nologin dhrobot
mkdir -p /opt/dh-robot/{app,data,downloads,n8n-home}

# 2. Code and Python environment (from your machine)
VPS=root@your-server ./deploy/scripts/deploy.sh      # first run: create the venv before, see below
python3 -m venv /opt/dh-robot/venv && /opt/dh-robot/venv/bin/pip install /opt/dh-robot/app

# 3. Configuration (never commit these files)
cp /opt/dh-robot/app/.env.example /opt/dh-robot/.env          # set DATA_DIR=/opt/dh-robot/data, WEBHOOK_SECRET, ANTHROPIC_API_KEY…
cp /opt/dh-robot/app/deploy/n8n.env.example /opt/dh-robot/n8n.env
chown root:dhrobot /opt/dh-robot/*.env && chmod 640 /opt/dh-robot/*.env

# 4. n8n (needs Node.js ≥ 24; installed privately, system Node untouched)
bash /opt/dh-robot/app/deploy/scripts/install_n8n.sh

# 5. Services
cp /opt/dh-robot/app/deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now dh-robot dh-n8n

# 6. Import and activate the workflow (as dhrobot, with n8n.env loaded)
cd /opt/dh-robot/n8n-home
runuser -u dhrobot -- env $(grep -v '^#' /opt/dh-robot/n8n.env | xargs) PATH=/opt/dh-robot/node24/bin:$PATH \
  /opt/dh-robot/n8n-pkg/node_modules/.bin/n8n import:workflow --input=/opt/dh-robot/app/workflows/n8n/doppelherz_content_sync.json
runuser -u dhrobot -- env $(grep -v '^#' /opt/dh-robot/n8n.env | xargs) PATH=/opt/dh-robot/node24/bin:$PATH \
  /opt/dh-robot/n8n-pkg/node_modules/.bin/n8n publish:workflow --id=DhContentSync01
systemctl restart dh-n8n

# 7. nginx + TLS
cp /opt/dh-robot/app/deploy/nginx/doppelherz-workflow.conf /etc/nginx/sites-available/dh-robot-jiudi
ln -s /etc/nginx/sites-available/dh-robot-jiudi /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d doppelherz-workflow.jiudi.cloud --redirect

# 8. Seed demo data
bash /opt/dh-robot/app/deploy/scripts/reseed.sh
```

The n8n editor listens on 127.0.0.1 only. Open it through an SSH tunnel: `ssh -L 5678:127.0.0.1:5678 root@your-server`, then http://localhost:5678.

## WordPress

Copy `integrations/wordpress/doppelherz-robot-webhook.php` to `wp-content/mu-plugins/` and define in `wp-config.php`:

```php
define('DH_ROBOT_WEBHOOK_URL', 'https://doppelherz-workflow.jiudi.cloud/n8n-webhook/doppelherz-new-post');
define('DH_ROBOT_WEBHOOK_SECRET', 'your-secret');
```

## Going live

1. Create a Meta app, add the Page admin as an app role, generate a Page access token (`pages_manage_posts`, `pages_read_engagement`).
2. Create a Pinterest app (`pins:write`, `boards:read`), test on `https://api-sandbox.pinterest.com/v5` until Standard access is granted.
3. Set `FB_PAGE_ID`, `FB_PAGE_TOKEN`, `PINTEREST_TOKEN`, `PINTEREST_BOARDS`, then `PUBLISH_MODE=live` and restart `dh-robot`.
