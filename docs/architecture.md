# Architecture

## Components

| Component | Responsibility | Why it is separate |
| --- | --- | --- |
| WordPress (doppelherz.vn) | Source articles, WooCommerce product data, `publish` webhook | Already exposes a REST API — no website changes beyond a mu-plugin |
| n8n | Triggers (webhook, 15-minute schedule, Monday 08:00), notifications | Marketing can change schedules and notifications by drag-and-drop |
| Content Robot (FastAPI) | Claims registry, compliance, rendering, scheduling, publishing, metrics, dashboard | Everything that must be exact lives in tested code |
| Claude API | Write the social pack, legal review, rewrite on feedback, weekly insights | Structured outputs guarantee a typed response |
| Meta Graph API · Pinterest API v5 | Publish, schedule, read metrics | Official APIs only |

## Pipeline

```mermaid
flowchart TD
  A[WordPress publishes article] --> B[n8n webhook / 15-min poll]
  B --> C[Robot reads article via REST]
  C --> D[Look up XNQC claims registry]
  D --> E[Claude writes Facebook + Pinterest pack]
  E --> F{Compliance: rules R1–R6 + AI reviewer}
  F -- blocking issue --> G[Editor fixes text] --> F
  F -- pass / warn --> H[Render pin 1000×1500 + card 1200×630, add UTM]
  H --> I[Review queue + Telegram]
  I --> J{Editor decision}
  J -- reject with feedback --> E
  J -- approve --> K[Peak-hour slot]
  K --> L[Publish: Graph API /feed · Pinterest /pins]
  L --> M[Collect metrics]
  M --> N[Weekly report, Monday 08:00]
```

Every step appends to the article's **trace** (`articles.trace`): label, detail, duration and, for Claude calls, token counts and cost. The dashboard's *Luồng xử lý* page renders these traces.

## Sequence: new article

```mermaid
sequenceDiagram
  participant WP as WordPress
  participant N as n8n
  participant R as Robot
  participant C as Claude
  participant E as Editor
  WP->>N: POST /webhook/doppelherz-new-post {post_id}
  N->>R: POST /webhook/wordpress (X-Webhook-Secret, X-Trigger)
  R->>WP: GET /wp-json/wp/v2/posts/{id}
  R->>C: social pack (JSON schema)
  C-->>R: facebook + pinterest
  R->>C: legal review per channel
  C-->>R: verdict + issues
  R-->>N: {variants}
  N->>E: Telegram "n bài chờ duyệt"
  E->>R: approve (dashboard)
  R->>R: schedule into next peak slot
  N->>R: POST /api/run-due (every 15 min)
  R->>R: publish due variants
```

## Data model (SQLite)

| Table | Key columns |
| --- | --- |
| `articles` | `wp_id` (unique), title, url, categories, content, headings, image, products, analysis, status (`processed` / `skipped` / `error`), `trace` |
| `variants` | `article_id` + `channel` (unique), status (`needs_review` / `blocked` / `approved` / `scheduled` / `published` / `rejected` / `failed`), body, title, link, alt text, image, compliance status and issues, AI provider/model, approval, schedule, remote id, attempts |
| `metrics` | variant, impressions, reactions, comments, shares, saves, clicks, `simulated` flag |
| `events` | audit log: time, level, entity (`article`, `variant`, `n8n`, `claims`), message |

## Design decisions

- **Human approval is mandatory.** The company carries legal responsibility for health-supplement ads, so AI never publishes on its own; blocking findings lock the Approve button.
- **Deterministic rules before AI.** Rules are fast, explainable and testable; the AI reviewer catches semantic issues the rules cannot.
- **Graceful degradation.** If Claude fails or is unavailable the offline writer produces a draft, so the queue never stalls.
- **Dry-run first.** Publishers build the exact API payloads; switching to `live` only requires tokens.
- **Single SQLite file.** Enough for thousands of articles per year; PostgreSQL is the planned production store.
