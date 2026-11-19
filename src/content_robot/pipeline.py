"""Quy trình robot: Website → AI viết lại → kiểm duyệt → duyệt → lịch đăng → đăng → đo → báo cáo."""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from . import compliance, images
from .ai import ClaudeWriter, OfflineWriter, SocialPack
from .claims import ClaimsRegistry
from .config import Settings
from .db import DB, now_iso
from .publishers import DryRunPublisher, FacebookPublisher, PinterestPublisher
from .scheduler import next_slot
from .wordpress import Article, WordPressClient

CHANNELS = ("facebook", "pinterest")


class Robot:
    def __init__(self, settings: Settings, wp: WordPressClient | None = None, writer: Any = None,
                 registry: ClaimsRegistry | None = None, publishers: dict[str, Any] | None = None,
                 render_images: bool = True):
        self.s = settings
        self.db = DB(settings.db_path)
        self.wp = wp or WordPressClient(settings.wp_base_url)
        self.fallback_writer = OfflineWriter()
        if writer is not None:
            self.writer = writer
        elif settings.ai_enabled:
            self.writer = ClaudeWriter(settings.anthropic_api_key, settings.claude_model, settings.claude_effort)
        else:
            self.writer = self.fallback_writer
        self._registry = registry
        self.publishers = publishers or self._make_publishers()
        self.render_images = render_images

    # ------------------------------------------------------------------ setup
    def _make_publishers(self) -> dict[str, Any]:
        if self.s.publish_mode == "live":
            return {
                "facebook": FacebookPublisher(self.s.fb_page_id, self.s.fb_page_token, self.s.fb_graph_version),
                "pinterest": PinterestPublisher(self.s.pinterest_token, self.s.pinterest_boards, self.s.pinterest_api_base),
            }
        return {c: DryRunPublisher(c, self.s.outbox_dir, self.s.pinterest_boards) for c in CHANNELS}

    @property
    def registry(self) -> ClaimsRegistry:
        if self._registry is None:
            cache = self.s.data_dir / "claims.json"
            if cache.exists() and (datetime.now().timestamp() - cache.stat().st_mtime) < 86400:
                self._registry = ClaimsRegistry.load(cache)
            else:
                self._registry = ClaimsRegistry.from_wc(self.wp.list_products())
                self._registry.save(cache)
                self.db.log(f"Cập nhật sổ XNQC: {len(self._registry.products)} sản phẩm", entity="claims")
        return self._registry

    # ------------------------------------------------------------------ trace (vết chạy từng bước)
    def trace(self, aid: int, step: str, label: str, detail: str = "", status: str = "ok", ms: float | None = None,
              extra: dict[str, Any] | None = None) -> None:
        a = self.db.one("SELECT trace FROM articles WHERE id = ?", (aid,))
        tr = (a or {}).get("trace") or []
        tr.append({"step": step, "label": label, "detail": detail, "status": status,
                   "ms": round(ms) if ms is not None else None, "ts": now_iso(), "extra": extra or {}})
        self.db.update("articles", aid, {"trace": tr})

    # ------------------------------------------------------------------ ingest
    def sync(self, limit: int = 5, categories: list[int] | None = None, wp_ids: list[int] | None = None,
             source: str = "quét định kỳ") -> list[int]:
        """Lấy bài mới từ website và xử lý. Trả về danh sách article_id mới."""
        t0 = time.perf_counter()
        posts = [self.wp.get_post(i) for i in wp_ids] if wp_ids else self.wp.list_posts(per_page=limit, categories=categories)
        fetch_ms = (time.perf_counter() - t0) * 1000 / max(1, len(posts))
        new_ids = []
        for art in posts:
            if self.db.one("SELECT id FROM articles WHERE wp_id = ?", (art.wp_id,)):
                continue
            new_ids.append(self.ingest(art, source=source, fetch_ms=fetch_ms))
        return new_ids

    def ingest(self, art: Article, source: str = "quét định kỳ", fetch_ms: float | None = None) -> int:
        aid = self.db.insert("articles", {
            "wp_id": art.wp_id, "url": art.url, "title": art.title, "published_at": art.published_at,
            "categories": art.categories, "excerpt": art.excerpt, "content_text": art.content_text,
            "headings": art.headings, "image_url": art.image_url, "image_alt": art.image_alt,
            "status": "new", "fetched_at": now_iso(), "trace": []})
        self.db.log(f"Nhận bài mới: {art.title}", entity="article", entity_id=aid)
        self.trace(aid, "receive", "Nhận bài từ WordPress", f"Nguồn: {source} · bài #{art.wp_id}", ms=fetch_ms)
        size = f", ảnh {art.image_size[0]}×{art.image_size[1]}" if art.image_size else ""
        self.trace(aid, "read", "Đọc và làm sạch nội dung",
                   f"{len(art.content_text):,} ký tự, {len(art.headings)} đề mục{size}".replace(",", "."))
        try:
            self.process(aid, art)
        except Exception as e:  # không để 1 bài lỗi chặn cả lô
            self.db.update("articles", aid, {"status": "error", "error": str(e)[:500]})
            self.db.log(f"Lỗi xử lý bài: {e}", "error", "article", aid)
            self.trace(aid, "error", "Lỗi xử lý", str(e)[:200], status="error")
        return aid

    # ------------------------------------------------------------------ AI + compliance
    def _write(self, art: Article, products: list) -> tuple[SocialPack, Any]:
        try:
            return self.writer.generate(art, products), self.writer
        except Exception as e:
            if self.writer is self.fallback_writer:
                raise
            self.db.log(f"AI lỗi, chuyển sang bộ sinh dự phòng: {e}", "warn", "article")
            return self.fallback_writer.generate(art, products), self.fallback_writer

    def process(self, aid: int, art: Article) -> None:
        t0 = time.perf_counter()
        products = self.registry.detect(f"{art.title}\n{art.content_text}")
        self.trace(aid, "claims", "Tra sổ XNQC",
                   ("Nhắc tới: " + ", ".join(f"{p.short_name} ({p.xnqc or 'chưa có XNQC'})" for p in products))
                   if products else "Bài không nhắc sản phẩm nào", ms=(time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        pack, used = self._write(art, products)
        u = getattr(used, "last_usage", {}) or {}
        cost = (f" · {u['input_tokens']:,} token vào, {u['output_tokens']:,} token ra · ~${u['cost_usd']}".replace(",", ".")
                if u.get("input_tokens") else "")
        self.trace(aid, "ai", "AI viết bản Facebook + Pinterest",
                   f"{'Claude ' + str(u.get('model') or getattr(used, 'model', '')) if used.name == 'claude' else 'Bộ sinh dự phòng theo mẫu'}{cost}",
                   ms=(time.perf_counter() - t0) * 1000, extra=dict(u))
        self.db.update("articles", aid, {"products": [p.short_name for p in products],
                                         "analysis": pack.analysis.model_dump(), "status": "processed"})
        if not pack.analysis.suitable_for_social:
            self.db.update("articles", aid, {"status": "skipped", "error": pack.analysis.reason})
            self.db.log(f"Bỏ qua (không phù hợp mạng xã hội): {pack.analysis.reason}", entity="article", entity_id=aid)
            self.trace(aid, "skip", "Bỏ qua — không đăng mạng xã hội", pack.analysis.reason, status="skip")
            return
        check_notes: list[str] = []
        t_check = 0.0
        t_render = 0.0

        slug = f"{art.wp_id}"
        fb_link = compliance.add_utm(art.url, "facebook", self.s.utm_campaign, slug)
        pin_link = compliance.add_utm(art.url, "pinterest", self.s.utm_campaign, slug)
        fb_text = "\n\n".join(x for x in [pack.facebook.hook, pack.facebook.body,
                                           f"{pack.facebook.cta.rstrip()} {fb_link}",
                                           " ".join(pack.facebook.hashtags)] if x)
        drafts = {
            "facebook": {"title": pack.facebook.hook, "body": fb_text, "link": fb_link, "alt_text": None,
                         "overlay": pack.pinterest.overlay_headline, "board": None},
            "pinterest": {"title": pack.pinterest.title, "body": pack.pinterest.description, "link": pin_link,
                          "alt_text": pack.pinterest.alt_text, "overlay": pack.pinterest.overlay_headline,
                          "board": pack.pinterest.board},
        }
        for channel, d in drafts.items():
            tc = time.perf_counter()
            mentioned = self.registry.detect(f"{d['title']}\n{d['body']}") or []
            res = compliance.check(d["body"], channel, mentioned, title=d["title"] if channel == "pinterest" else "",
                                   alt_text=d["alt_text"] or "")
            issues = res.as_list()
            if used is not self.fallback_writer and self.s.ai_review:
                try:
                    review = used.review(channel, res.text, mentioned, art.content_text)
                    for i in review.issues:
                        sev = "block" if review.verdict == "block" else "warn"
                        issues.append({"code": f"AI-{i.rule}", "severity": sev, "message": i.explanation,
                                       "excerpt": i.quote + (f" → gợi ý: {i.suggestion}" if i.suggestion else "")})
                except Exception as e:
                    self.db.log(f"AI kiểm duyệt lỗi: {e}", "warn", "article", aid)
            status_c = "block" if any(i["severity"] == "block" for i in issues) else (
                "warn" if any(i["severity"] == "warn" for i in issues) else "pass")
            t_check += (time.perf_counter() - tc) * 1000
            n_fix = sum(1 for i in issues if i["severity"] == "fixed")
            check_notes.append(f"{'Facebook' if channel == 'facebook' else 'Pinterest'}: {status_c}"
                               + (f" ({len(issues) - n_fix} lưu ý, {n_fix} tự sửa)" if issues else ""))
            image_path = None
            tr_ = time.perf_counter()
            if self.render_images:
                out = self.s.media_dir / f"{art.wp_id}_{channel}.jpg"
                label = next((c for c in art.categories if c.lower() != "kiến thức sức khỏe"), "Sức khỏe")[:28]
                if channel == "pinterest":
                    images.render_pin(art.image_url, d["overlay"] or art.title, label, out)
                else:
                    images.render_fb_card(art.image_url, art.title, out)
                image_path = str(out)
            t_render += (time.perf_counter() - tr_) * 1000
            status = "blocked" if status_c == "block" else (
                "approved" if (self.s.auto_approve and status_c == "pass") else "needs_review")
            vid = self.db.insert("variants", {
                "article_id": aid, "channel": channel, "status": status, "title": d["title"], "body": res.text,
                "link": d["link"], "alt_text": d["alt_text"], "overlay": d["overlay"], "board": d["board"],
                "image_path": image_path, "compliance_status": status_c, "compliance_issues": issues,
                "ai_provider": used.name, "ai_model": getattr(used, "model", None),
                "created_at": now_iso(), "updated_at": now_iso()})
            self.db.log(f"Tạo bản {channel} ({used.name}) — kiểm duyệt: {status_c}", entity="variant", entity_id=vid)
            if status == "approved":
                self.schedule(vid)
        review_note = " + AI pháp chế" if (used is not self.fallback_writer and self.s.ai_review) else ""
        self.trace(aid, "check", f"Kiểm duyệt tuân thủ: bộ luật R1–R6{review_note}", " · ".join(check_notes),
                   status="warn" if any("block" in n for n in check_notes) else "ok", ms=t_check)
        if self.render_images:
            self.trace(aid, "render", "Render ảnh ghim 1000×1500 + thẻ 1200×630", "Gắn UTM cho từng kênh", ms=t_render)
        self.trace(aid, "queue", "Vào hàng chờ duyệt", "Báo biên tập qua dashboard / Telegram")

    # ------------------------------------------------------------------ review actions
    def approve(self, vid: int, user: str = "bien-tap") -> dict[str, Any]:
        v = self.variant(vid)
        if v["status"] == "blocked":
            raise ValueError("Bản này đang bị chặn do vi phạm tuân thủ — sửa nội dung trước khi duyệt")
        self.db.update("variants", vid, {"status": "approved", "approved_by": user, "approved_at": now_iso(),
                                         "updated_at": now_iso()})
        self.db.log(f"{user} duyệt bản {v['channel']}", entity="variant", entity_id=vid)
        self.trace(v["article_id"], "approve", f"Duyệt bản {self._ch(v['channel'])}", f"Người duyệt: {user}")
        return self.schedule(vid)

    @staticmethod
    def _ch(channel: str) -> str:
        return "Facebook" if channel == "facebook" else "Pinterest"

    def reject(self, vid: int, feedback: str, user: str = "bien-tap") -> None:
        self.db.update("variants", vid, {"status": "rejected", "feedback": feedback, "updated_at": now_iso()})
        self.db.log(f"{user} từ chối: {feedback}", entity="variant", entity_id=vid)
        v = self.variant(vid)
        self.trace(v["article_id"], "reject", f"Từ chối bản {self._ch(v['channel'])}", feedback, status="warn")

    def edit(self, vid: int, body: str, title: str | None = None, user: str = "bien-tap") -> dict[str, Any]:
        v = self.variant(vid)
        art = self.db.one("SELECT * FROM articles WHERE id = ?", (v["article_id"],))
        mentioned = self.registry.detect(f"{title or v['title']}\n{body}")
        res = compliance.check(body, v["channel"], mentioned, title=(title or v["title"] or "") if v["channel"] == "pinterest" else "",
                               alt_text=v.get("alt_text") or "")
        status = "blocked" if res.status == "block" else "needs_review"
        self.db.update("variants", vid, {"body": res.text, "title": title or v["title"], "status": status,
                                         "compliance_status": res.status, "compliance_issues": res.as_list(),
                                         "updated_at": now_iso()})
        self.db.log(f"{user} sửa bản {v['channel']} của bài {art['title'][:40]} — kiểm duyệt lại: {res.status}",
                    entity="variant", entity_id=vid)
        blocks = [i.code for i in res.issues if i.severity == "block"]
        self.trace(v["article_id"], "edit", f"Biên tập sửa bản {self._ch(v['channel'])} → kiểm duyệt lại",
                   ("Bị chặn: " + ", ".join(blocks)) if blocks else f"Kết quả: {res.status}",
                   status="error" if blocks else "ok")
        return self.variant(vid)

    def schedule(self, vid: int) -> dict[str, Any]:
        v = self.variant(vid)
        taken = [datetime.fromisoformat(r["scheduled_at"]) for r in self.db.all(
            "SELECT scheduled_at FROM variants WHERE channel = ? AND scheduled_at IS NOT NULL AND status IN ('scheduled','published')",
            (v["channel"],))]
        slot = next_slot(v["channel"], taken, datetime.now(UTC), self.s.slots, self.s.max_per_day,
                         self.s.timezone, self.s.min_lead_minutes)
        self.db.update("variants", vid, {"status": "scheduled", "scheduled_at": slot.isoformat(), "updated_at": now_iso()})
        self.db.log(f"Lên lịch {v['channel']} lúc {slot:%d/%m %H:%M}", entity="variant", entity_id=vid)
        self.trace(v["article_id"], "schedule", f"Xếp lịch {self._ch(v['channel'])}", f"Khung giờ vàng {slot:%H:%M ngày %d/%m}")
        return self.variant(vid)

    # ------------------------------------------------------------------ publish + metrics
    def run_due(self, now: datetime | None = None, force: bool = False) -> list[int]:
        now = now or datetime.now(UTC)
        done = []
        for v in self.db.all("SELECT * FROM variants WHERE status = 'scheduled' ORDER BY scheduled_at"):
            if not force and datetime.fromisoformat(v["scheduled_at"]) > now:
                continue
            pub = self.publishers[v["channel"]]
            try:
                res = pub.publish(v)
                self.db.update("variants", v["id"], {"status": "published", "published_at": now.isoformat(timespec="seconds"),
                                                     "remote_id": res.remote_id, "remote_url": res.url,
                                                     "attempts": v["attempts"] + 1, "updated_at": now_iso()})
                self.db.log(f"Đã đăng {v['channel']}: {res.remote_id}", entity="variant", entity_id=v["id"])
                api = "Graph API /feed" if v["channel"] == "facebook" else "Pinterest API /pins"
                mode = " (chạy thử — ghi payload)" if isinstance(pub, DryRunPublisher) else ""
                self.trace(v["article_id"], "publish", f"Đăng {self._ch(v['channel'])}", f"{api}{mode} · {res.remote_id}")
                done.append(v["id"])
            except Exception as e:
                attempts = v["attempts"] + 1
                status = "failed" if attempts >= 3 else "scheduled"
                retry_at = (now + timedelta(minutes=15 * attempts)).isoformat()
                self.db.update("variants", v["id"], {"status": status, "attempts": attempts, "error": str(e)[:500],
                                                     "scheduled_at": retry_at if status == "scheduled" else v["scheduled_at"],
                                                     "updated_at": now_iso()})
                self.db.log(f"Đăng {v['channel']} lỗi lần {attempts}: {e}", "error", "variant", v["id"])
        return done

    def collect_metrics(self) -> int:
        n = 0
        now = datetime.now(UTC)
        for v in self.db.all("SELECT * FROM variants WHERE status = 'published'"):
            pub = self.publishers[v["channel"]]
            simulated = isinstance(pub, DryRunPublisher)
            try:
                if simulated:
                    hours = (now - datetime.fromisoformat(v["published_at"])).total_seconds() / 3600
                    m = pub.metrics(v["remote_id"], hours)
                elif v["channel"] == "facebook":
                    m = pub.metrics(v["remote_id"])
                else:
                    m = pub.metrics(v["remote_id"], (now - timedelta(days=30)).date().isoformat(), now.date().isoformat())
            except Exception as e:
                self.db.log(f"Lấy số liệu lỗi: {e}", "warn", "variant", v["id"])
                continue
            self.db.insert("metrics", {"variant_id": v["id"], "collected_at": now_iso(), "simulated": int(simulated),
                                       **{k: m.get(k, 0) for k in ("impressions", "reactions", "comments", "shares", "saves", "clicks")}})
            n += 1
        return n

    # ------------------------------------------------------------------ queries
    def variant(self, vid: int) -> dict[str, Any]:
        v = self.db.one("SELECT * FROM variants WHERE id = ?", (vid,))
        if not v:
            raise KeyError(f"Không có variant {vid}")
        return v

    def stats(self) -> dict[str, Any]:
        rows = self.db.all("SELECT channel, status, COUNT(*) AS n FROM variants GROUP BY channel, status")
        by_status: dict[str, int] = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + r["n"]
        arts = self.db.one("SELECT COUNT(*) AS n, SUM(status='skipped') AS skipped FROM articles") or {}
        return {"articles": arts.get("n", 0), "skipped": arts.get("skipped") or 0, "by_status": by_status, "rows": rows}

    def notify(self, text: str) -> None:
        """Gửi thông báo Telegram nếu đã cấu hình (dùng cho bài chờ duyệt và báo cáo tuần)."""
        if not (self.s.telegram_bot_token and self.s.telegram_chat_id):
            return
        try:
            httpx.post(f"https://api.telegram.org/bot{self.s.telegram_bot_token}/sendMessage",
                       data={"chat_id": self.s.telegram_chat_id, "text": text[:4000]}, timeout=15)
        except Exception as e:
            self.db.log(f"Telegram lỗi: {e}", "warn")
