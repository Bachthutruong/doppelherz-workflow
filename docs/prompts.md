# Prompts

The prompts live in [`src/content_robot/prompts`](../src/content_robot/prompts) and are used verbatim by the robot. Variables in `{{double braces}}` are filled at runtime.

| File | Prompt | Used when | Output |
| --- | --- | --- | --- |
| `00_system.md` | P0 — system: role, brand voice, 7 compliance rules | Every call | — |
| `01_social_pack.md` | P1 — Facebook post + Pinterest pin from one article | New article | JSON (analysis, facebook, pinterest) |
| `02_compliance_review.md` | P2 — AI legal reviewer, rules R1–R6 | After the rule engine | JSON (`pass` / `needs_edit` / `block`, quoted issues) |
| `03_revision.md` | P3 — rewrite from editor feedback | Editor rejects with feedback | JSON as P1 |
| `04_weekly_report.md` | P4 — weekly insights for the marketing lead | Monday 08:00 | JSON (3 insights, 2 actions) |

Call settings (`content_robot/ai.py`): model `claude-opus-5-5`, effort `medium`, `output_config.format = json_schema` (schemas `SOCIAL_PACK_SCHEMA`, `REVIEW_SCHEMA`), beta `server-side-fallback-2026-07-01` with `fallbacks: "default"`. `stop_reason` is checked for `refusal` and `max_tokens` before parsing.

The `{{approved_claims}}` block is generated from the XNQC registry, for example:

```text
Sản phẩm: Kinder Immune syrup | Số XNQC: 00359/2020/ATTP-XNQC
Công dụng được phép:
- Giúp phòng bệnh & rút ngắn thời gian phục hồi sau ốm
```
