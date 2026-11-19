"""Kiểm thử tự động cho robot nội dung (chạy offline, không gọi mạng)."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from content_robot import compliance
from content_robot.ai import SOCIAL_PACK_SCHEMA, ClaudeWriter, OfflineWriter
from content_robot.claims import ClaimsRegistry, parse_product
from content_robot.config import Settings
from content_robot.pipeline import Robot
from content_robot.publishers import FacebookPublisher, PinterestPublisher, build_facebook_payload, build_pinterest_payload
from content_robot.scheduler import next_slot
from content_robot.wordpress import parse_post
from tests.helpers import FIX, FakeWP

VN = ZoneInfo("Asia/Ho_Chi_Minh")


@pytest.fixture(scope="module")
def registry() -> ClaimsRegistry:
    return ClaimsRegistry.from_wc(json.loads((FIX / "products.json").read_text()))


@pytest.fixture(scope="module")
def article():
    return parse_post(json.loads((FIX / "post_39906.json").read_text()))


# ---------------------------------------------------------------- WordPress + sổ XNQC
def test_parse_post_extracts_text_headings_image(article):
    assert article.wp_id == 39906
    assert article.title.startswith("Lỗ hổng miễn dịch")
    assert "Sức khỏe trẻ em" in article.categories
    assert any("Nguyên nhân" in h for h in article.headings)
    assert article.image_url and article.image_url.startswith("https://doppelherz.vn/")
    assert "<" not in article.content_text


def test_claims_registry_reads_xnqc_and_claims(registry):
    assert len(registry.products) == 36
    with_xnqc = [p for p in registry.products if p.xnqc]
    assert len(with_xnqc) == 35  # Vital Pregna ghi số XNQC không theo chuẩn → để người duyệt xác nhận
    omega = next(p for p in registry.products if p.short_name.startswith("Omega-3"))
    assert omega.xnqc == "2133/2022/XNQC-ATTP"
    assert "Hỗ trợ duy trì mạch máu khỏe mạnh" in omega.claims


def test_detect_product_in_article(registry, article):
    names = [p.short_name for p in registry.detect(article.content_text)]
    assert "Kinder Immune syrup" in names


def test_parse_product_tolerates_spacing():
    p = parse_product({"id": 1, "name": "TPBVSK B-Complex", "permalink": "x",
                       "short_description": "<p>Số XNQC: 1992/2024/XNQC- ATTP</p><p>Bổ sung các vitamin nhóm B.</p>"})
    assert p.xnqc == "1992/2024/XNQC-ATTP" and p.claims == ["Bổ sung các vitamin nhóm B"]


# ---------------------------------------------------------------- Tuân thủ
def test_cure_claim_with_product_is_blocked(registry):
    prods = registry.detect("Kinder Immune")
    r = compliance.check("Siro Kinder Immune giúp chữa khỏi ốm vặt cho bé.", "facebook", prods)
    assert r.status == "block"
    assert any(i.code == "R2" and i.severity == "block" for i in r.issues)


def test_disclaimer_and_xnqc_are_added(registry):
    prods = registry.detect("Kinder Immune")
    r = compliance.check("Kinder Immune hỗ trợ tăng cường sức đề kháng cho trẻ.", "facebook", prods)
    assert compliance.DISCLAIMER in r.text
    assert "00359/2020/ATTP-XNQC" in r.text
    assert r.status in ("pass", "warn")


def test_unapproved_claim_warns(registry):
    prods = registry.detect("Kinder Immune")
    r = compliance.check("Kinder Immune giúp bé cao lớn vượt trội và thông minh hơn.", "facebook", prods)
    codes = {(i.code, i.severity) for i in r.issues}
    assert ("R1", "warn") in codes and ("R4", "warn") in codes


def test_not_yet_recovered_is_not_cure_claim():
    # "chưa khỏi" (chưa hồi phục) khác "chữa khỏi" (chữa bệnh) — bộ luật phải phân biệt dấu
    r = compliance.check("Nhiều bé ốm cả tuần vẫn chưa khỏi, ba mẹ nên đưa bé đi khám.", "facebook", [])
    assert r.status == "pass"


def test_treatment_without_product_only_warns():
    r = compliance.check("Hãy đưa trẻ đi khám để được điều trị kịp thời.", "facebook", [])
    assert r.status == "warn"


def test_doctor_endorsement_blocked():
    r = compliance.check("Sản phẩm được bác sĩ khuyên dùng cho mọi gia đình.", "facebook", [])
    assert r.status == "block" and any(i.code == "R3" for i in r.issues)


def test_pinterest_length_limits():
    r = compliance.check("x " * 450, "pinterest", [], title="t" * 120)
    assert r.status == "block"
    assert sum(1 for i in r.issues if i.code == "LEN") == 2


def test_utm():
    u = compliance.add_utm("https://doppelherz.vn/bai-viet/", "pinterest", "robot", "1")
    assert "utm_source=pinterest" in u and "utm_medium=social" in u


# ---------------------------------------------------------------- AI
def test_offline_writer_stays_within_source(article):
    pack = OfflineWriter().generate(article, [])
    assert pack.analysis.suitable_for_social
    assert len(pack.pinterest.title) <= 100 and len(pack.pinterest.description) <= 500
    assert "#Doppelherz" in pack.facebook.hashtags
    assert pack.pinterest.board == "Sức khỏe trẻ em"


def test_claude_writer_request_shape(article, registry):
    """Kiểm tra request gửi tới Claude API (mô phỏng phản hồi bằng MockTransport)."""
    sent = {}
    fake_pack = OfflineWriter().generate(article, []).model_dump()

    import httpx2  # Anthropic SDK 2.x dùng httpx2

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent["url"] = str(request.url)
        sent["headers"] = request.headers
        sent["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps(fake_pack, ensure_ascii=False)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 3000, "output_tokens": 800}})

    import anthropic
    client = anthropic.Anthropic(api_key="test-key", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    w = ClaudeWriter("test-key", client=client)
    pack = w.generate(article, registry.detect("Kinder Immune"))
    body = sent["body"]
    assert sent["url"].endswith("/v1/messages")
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in sent["headers"]["anthropic-beta"]
    assert body["output_config"]["format"]["schema"] == SOCIAL_PACK_SCHEMA
    assert "00359/2020/ATTP-XNQC" in body["messages"][0]["content"]  # sổ XNQC được đưa vào prompt
    assert "QUY TẮC TUÂN THỦ" in body["system"]
    assert pack.facebook.hook


# ---------------------------------------------------------------- Lịch + đăng
def test_scheduler_respects_slots_and_cap():
    slots = {"facebook": ["11:30", "20:30"]}
    now = datetime(2026, 11, 19, 12, 0, tzinfo=VN)
    first = next_slot("facebook", [], now, slots, {"facebook": 2})
    assert first.hour == 20 and first.minute == 30 and first.day == 19
    second = next_slot("facebook", [first], now, slots, {"facebook": 2})
    assert second.day == 20 and second.hour == 11
    capped = next_slot("facebook", [first, datetime(2026, 11, 19, 11, 30, tzinfo=VN)], now, slots, {"facebook": 2})
    assert capped.day == 20


def test_facebook_payload_and_live_call():
    v = {"id": 1, "body": "Xin chào", "link": "https://doppelherz.vn/a?utm_source=facebook"}
    when = datetime(2026, 11, 20, 20, 30, tzinfo=VN)
    p = build_facebook_payload(v, when)
    assert p["published"] == "false" and p["scheduled_publish_time"] == str(int(when.timestamp()))
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(req.url), req.content.decode()
        return httpx.Response(200, json={"id": "123_456"})

    fb = FacebookPublisher("123", "TOKEN", client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = fb.publish(v)
    assert seen["url"] == "https://graph.facebook.com/v27.0/123/feed"
    assert "access_token=TOKEN" in seen["body"] and res.remote_id == "123_456"


def test_pinterest_payload_and_live_call(tmp_path):
    img = tmp_path / "pin.jpg"
    img.write_bytes(b"\xff\xd8fakejpeg")
    v = {"id": 2, "title": "T" * 120, "body": "Mô tả", "link": "https://doppelherz.vn/b", "alt_text": "Ảnh",
         "board": "Sức khỏe trẻ em", "image_path": str(img)}
    p = build_pinterest_payload(v, "999", img.read_bytes())
    assert len(p["title"]) == 100 and p["media_source"]["source_type"] == "image_base64"
    assert p["ai_disclosures"] == {"values": ["AI_MODIFIED"]}
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["json"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(201, json={"id": "8800"})

    pin = PinterestPublisher("PTOKEN", {"Sức khỏe trẻ em": "999"}, client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = pin.publish(v)
    assert seen["url"] == "https://api.pinterest.com/v5/pins" and seen["auth"] == "Bearer PTOKEN"
    assert seen["json"]["board_id"] == "999" and res.remote_id == "8800"


# ---------------------------------------------------------------- Toàn trình
def test_end_to_end_dry_run(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.ensure_dirs()
    post = json.loads((FIX / "post_39906.json").read_text())
    products = json.loads((FIX / "products.json").read_text())
    bot = Robot(s, wp=FakeWP(post, products), render_images=False)
    ids = bot.sync(limit=1)
    assert len(ids) == 1
    vs = bot.db.all("SELECT * FROM variants ORDER BY channel")
    assert [v["channel"] for v in vs] == ["facebook", "pinterest"]
    assert all(v["status"] == "needs_review" for v in vs)
    assert "utm_source=facebook" in vs[0]["body"]
    # Biên tập viên sửa thành câu vi phạm → bị chặn, không duyệt được
    blocked = bot.edit(vs[0]["id"], "Kinder Immune giúp chữa khỏi ốm vặt.")
    assert blocked["status"] == "blocked"
    with pytest.raises(ValueError):
        bot.approve(vs[0]["id"])
    # Sửa lại đúng công dụng XNQC → được tự thêm câu cảnh báo + số XNQC
    fixed = bot.edit(vs[0]["id"], "Kinder Immune hỗ trợ tăng cường sức đề kháng cho trẻ.")
    assert fixed["status"] == "needs_review" and compliance.DISCLAIMER in fixed["body"]
    for v in vs:
        bot.approve(v["id"])
    assert len(bot.run_due(force=True)) == 2
    assert len(list(s.outbox_dir.glob("*.json"))) == 2
    assert bot.collect_metrics() == 2
    assert bot.db.one("SELECT COUNT(*) AS n FROM metrics WHERE simulated = 1")["n"] == 2
    # chạy lại không tạo trùng
    assert bot.sync(limit=1) == []
