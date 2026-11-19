# Compliance — Vietnamese health-supplement advertising

Health supplements (thực phẩm bảo vệ sức khỏe, TPBVSK) may only be advertised with the content approved in their advertising confirmation (XNQC, Decree 15/2018/NĐ-CP). From 1 July 2026 the confirmation is issued by provincial People's Committee chairs, and the Ministry of Health is stepping up post-checks of ads on social networks and marketplaces.

## Claims registry

`content_robot/claims.py` builds the registry from the WooCommerce Store API (`/wp-json/wc/store/v1/products`): for each product it parses the XNQC number, the XNCB number and the approved claims listed in the short description. On 19 Nov 2026: 36 products, 35 with a standard XNQC number. A product without a readable number is **blocked** from advertising until legal confirms it.

## Rules

| Code | Severity | Rule |
| --- | --- | --- |
| R1 | warn | Claim next to a product name does not match its approved XNQC claims |
| R2 | block | Says or implies the product cures, treats or prevents disease ("chữa khỏi", "điều trị", "đặc trị", "thay thế thuốc", "thần dược"…). Treatment words not tied to a product only warn |
| R3 | block | Uses doctors, pharmacists or medical facilities to endorse ("bác sĩ khuyên dùng") |
| R4 | block / warn | Absolute claims ("100%", "không có tác dụng phụ", "cam kết hiệu quả") block; superlatives ("tốt nhất", "số 1", "hàng đầu") warn |
| R5 | auto-fix | Product mentioned → append "Thực phẩm này không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh." |
| XNQC | auto-fix / block | Append the product's XNQC number; block if none |
| R6 | warn | Mentions research or "scientifically proven" — check the source article |
| LEN | block / warn | Pinterest title ≤ 100, description ≤ 800 (recommended 500), alt text ≤ 500; Facebook ≤ 2,200 characters |

Matching is diacritic-aware: "chưa khỏi" (not yet recovered) is allowed, "chữa khỏi" (cured) is blocked.

## Layers

1. **Prompt** — Claude may only use facts from the source article and claims from the registry (prompt P0).
2. **Rules** — the table above, run on every draft and every edit.
3. **AI legal reviewer** — prompt P2 quotes each offending sentence and returns `pass` / `needs_edit` / `block`.
4. **Human approval** — the editor is the final, accountable gate; the audit log records who approved what and when.
