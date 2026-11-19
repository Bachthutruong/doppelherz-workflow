"""Đăng bài lên Facebook Page (Graph API) và Pinterest (API v5).

Chế độ dry_run dựng ĐÚNG payload như khi đăng thật rồi ghi ra data/outbox/ thay vì gọi API,
để kiểm tra được toàn bộ quy trình khi chưa có token của khách hàng.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


@dataclass
class PublishResult:
    remote_id: str
    url: str
    raw: dict[str, Any]


def facebook_message(variant: dict[str, Any]) -> str:
    """Ghép nội dung bài Facebook: thân bài + link UTM ở cuối (link ngay trong bài để tạo xem trước)."""
    body = variant["body"].rstrip()
    return f"{body}\n\n👉 {variant['link']}" if variant.get("link") and variant["link"] not in body else body


def build_facebook_payload(variant: dict[str, Any], scheduled_at: datetime | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": facebook_message(variant), "link": variant["link"]}
    if scheduled_at is not None:
        payload["published"] = "false"
        payload["scheduled_publish_time"] = str(int(scheduled_at.timestamp()))
    return payload


def build_pinterest_payload(variant: dict[str, Any], board_id: str, image_bytes: bytes | None,
                            image_url: str | None = None, ai_modified: bool = True) -> dict[str, Any]:
    if image_bytes:
        media = {"source_type": "image_base64", "content_type": "image/jpeg",
                 "data": base64.b64encode(image_bytes).decode()}
    else:
        media = {"source_type": "image_url", "url": image_url}
    payload: dict[str, Any] = {
        "board_id": board_id,
        "title": (variant.get("title") or "")[:100],
        "description": variant["body"][:800],
        "link": variant["link"],
        "alt_text": (variant.get("alt_text") or "")[:500],
        "media_source": media,
    }
    if ai_modified:
        # Ảnh ghim có chữ được ghép tự động → khai báo minh bạch theo trường ai_disclosures của API v5
        payload["ai_disclosures"] = {"values": ["AI_MODIFIED"]}
    return payload


class FacebookPublisher:
    channel = "facebook"

    def __init__(self, page_id: str, token: str, version: str = "v27.0", client: httpx.Client | None = None):
        self.page_id, self.token, self.version = page_id, token, version
        self.http = client or httpx.Client(timeout=30)

    @property
    def base(self) -> str:
        return f"https://graph.facebook.com/{self.version}"

    def publish(self, variant: dict[str, Any], scheduled_at: datetime | None = None) -> PublishResult:
        data = build_facebook_payload(variant, scheduled_at)
        data["access_token"] = self.token
        r = self.http.post(f"{self.base}/{self.page_id}/feed", data=data)
        body = r.json()
        if r.status_code >= 400 or "error" in body:
            raise RuntimeError(f"Facebook lỗi {r.status_code}: {body.get('error', body)}")
        post_id = body["id"]
        return PublishResult(post_id, f"https://www.facebook.com/{post_id}", body)

    def metrics(self, remote_id: str) -> dict[str, int]:
        r = self.http.get(f"{self.base}/{remote_id}", params={
            "fields": "shares,comments.summary(true).limit(0),reactions.summary(true).limit(0)",
            "access_token": self.token})
        b = r.json()
        return {
            "reactions": b.get("reactions", {}).get("summary", {}).get("total_count", 0),
            "comments": b.get("comments", {}).get("summary", {}).get("total_count", 0),
            "shares": b.get("shares", {}).get("count", 0),
        }


class PinterestPublisher:
    channel = "pinterest"

    def __init__(self, token: str, boards: dict[str, str], api_base: str = "https://api.pinterest.com/v5",
                 client: httpx.Client | None = None):
        self.token, self.boards, self.api_base = token, boards, api_base.rstrip("/")
        self.http = client or httpx.Client(timeout=60)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def board_id(self, board_name: str | None) -> str:
        if board_name and board_name in self.boards:
            return self.boards[board_name]
        if "default" in self.boards:
            return self.boards["default"]
        raise RuntimeError(f"Chưa cấu hình board_id cho bảng '{board_name}' (PINTEREST_BOARDS)")

    def publish(self, variant: dict[str, Any], scheduled_at: datetime | None = None) -> PublishResult:
        img = Path(variant["image_path"]).read_bytes() if variant.get("image_path") else None
        payload = build_pinterest_payload(variant, self.board_id(variant.get("board")), img)
        r = self.http.post(f"{self.api_base}/pins", headers=self._headers(), json=payload)
        body = r.json()
        if r.status_code >= 400:
            raise RuntimeError(f"Pinterest lỗi {r.status_code}: {body.get('message', body)}")
        return PublishResult(body["id"], f"https://www.pinterest.com/pin/{body['id']}/", body)

    def metrics(self, remote_id: str, start: str, end: str) -> dict[str, int]:
        r = self.http.get(f"{self.api_base}/pins/{remote_id}/analytics", headers=self._headers(), params={
            "start_date": start, "end_date": end, "metric_types": "IMPRESSION,SAVE,PIN_CLICK,OUTBOUND_CLICK"})
        lifetime = r.json().get("all", {}).get("lifetime_metrics", {})
        return {"impressions": lifetime.get("IMPRESSION", 0), "saves": lifetime.get("SAVE", 0),
                "clicks": lifetime.get("OUTBOUND_CLICK", 0) + lifetime.get("PIN_CLICK", 0)}


class DryRunPublisher:
    """Mô phỏng đăng bài: ghi payload thật ra outbox, trả ID giả có tiền tố dryrun-."""

    def __init__(self, channel: str, outbox: Path, boards: dict[str, str] | None = None):
        self.channel, self.outbox, self.boards = channel, outbox, boards or {}

    def publish(self, variant: dict[str, Any], scheduled_at: datetime | None = None) -> PublishResult:
        if self.channel == "facebook":
            payload = build_facebook_payload(variant, None)
            payload["access_token"] = "<FB_PAGE_TOKEN>"
            endpoint = "POST https://graph.facebook.com/v27.0/<FB_PAGE_ID>/feed"
        else:
            img = Path(variant["image_path"]).read_bytes() if variant.get("image_path") else None
            board = self.boards.get(variant.get("board") or "", f"<board_id: {variant.get('board')}>")
            payload = build_pinterest_payload(variant, board, img)
            if payload["media_source"].get("data"):
                payload["media_source"]["data"] = payload["media_source"]["data"][:60] + f"...(base64, {len(img or b'')} bytes)"
            endpoint = "POST https://api.pinterest.com/v5/pins"
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
        rid = f"dryrun-{self.channel[:2]}-{digest}"
        self.outbox.mkdir(parents=True, exist_ok=True)
        (self.outbox / f"{variant['id']:04d}_{self.channel}.json").write_text(json.dumps(
            {"endpoint": endpoint, "payload": payload, "remote_id": rid,
             "published_at": datetime.now(UTC).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        return PublishResult(rid, f"(mô phỏng) {rid}", {"id": rid})

    def metrics(self, remote_id: str, hours_live: float) -> dict[str, int]:
        """Số liệu MÔ PHỎNG (luôn gắn cờ simulated) để trình diễn báo cáo khi chưa đăng thật."""
        rnd = random.Random(remote_id)
        ramp = max(0.35, min(1.0, hours_live / 72))
        if self.channel == "facebook":
            reach = int(rnd.randint(1800, 9000) * ramp)
            return {"impressions": reach, "reactions": int(reach * rnd.uniform(0.01, 0.04)),
                    "comments": int(reach * rnd.uniform(0.001, 0.006)), "shares": int(reach * rnd.uniform(0.001, 0.005)),
                    "clicks": int(reach * rnd.uniform(0.008, 0.025)), "saves": 0}
        imp = int(rnd.randint(300, 2500) * ramp)
        return {"impressions": imp, "saves": int(imp * rnd.uniform(0.01, 0.05)), "clicks": int(imp * rnd.uniform(0.005, 0.02)),
                "reactions": 0, "comments": 0, "shares": 0}
