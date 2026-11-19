# HTTP API

Interactive OpenAPI docs: `/api/docs` (live: https://doppelherz-workflow.jiudi.cloud/api/docs).

## For n8n and WordPress

| Method | Path | Called by | Description |
| --- | --- | --- | --- |
| `POST` | `/webhook/wordpress` | n8n (from the WordPress webhook) | Body `{"post_id": 123}`; header `X-Webhook-Secret` required. Processes the article and returns the new variants |
| `POST` | `/api/sync?limit=5&category=3` | n8n, every 15 minutes | Fallback poll for new articles (category 3 = Kiến thức sức khỏe) |
| `POST` | `/api/run-due` | n8n, every 15 minutes | Publishes variants whose slot has passed (`?force=true` publishes all scheduled) |
| `POST` | `/api/metrics` | n8n | Collects engagement metrics for published variants |
| `GET` | `/api/report` | n8n, Monday 08:00 | Weekly report data, insights and the Telegram text |
| `GET` | `/api/stats` · `/api/variants?status=` | Integrations | Counts and variant list |
| `GET` | `/healthz` | Monitoring | Status, AI provider, publish mode |

Send `X-Trigger: n8n:webhook | n8n:cron-15m | n8n:weekly` so the dashboard can show which n8n branch called the robot.

## Example

```bash
curl -X POST https://doppelherz-workflow.jiudi.cloud/n8n-webhook/doppelherz-new-post \
     -H 'Content-Type: application/json' -d '{"post_id": 40004}'
# → n8n → robot /webhook/wordpress → {"new_articles": [...], "variants": [...]}
```

## Dashboard routes

`/` overview · `/noi-dung` content list · `/bai/{id}` review screen · `/lich` calendar · `/luong` workflow and traces · `/so-xnqc` claims registry · `/bao-cao` weekly report · `/nhat-ky` audit log · `/gioi-thieu` about and downloads.
