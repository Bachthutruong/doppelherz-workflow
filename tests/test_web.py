"""Smoke test giao diện: mọi trang trả 200 và hiển thị đúng dữ liệu chính."""
import json

from fastapi.testclient import TestClient

from content_robot.config import Settings
from content_robot.pipeline import Robot
from content_robot.web import create_app
from tests.helpers import FIX, FakeWP


def make_client(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.ensure_dirs()
    bot = Robot(s, wp=FakeWP(json.loads((FIX / "post_39906.json").read_text()), json.loads((FIX / "products.json").read_text())),
                render_images=False)
    bot.sync(limit=1)
    return TestClient(create_app(s, bot)), bot


def test_all_pages_render(tmp_path):
    c, bot = make_client(tmp_path)
    for path in ["/", "/noi-dung", "/noi-dung?tab=review", "/bai/1", "/lich", "/luong", "/so-xnqc", "/bao-cao",
                 "/nhat-ky", "/gioi-thieu", "/healthz"]:
        r = c.get(path)
        assert r.status_code == 200, path
    assert "Lỗ hổng miễn dịch" in c.get("/bai/1").text
    assert "Kinder Immune syrup" in c.get("/so-xnqc").text
    assert "Tra sổ XNQC" in c.get("/luong").text  # vết chạy thật được ghi


def test_n8n_trigger_is_logged_and_actions_work(tmp_path):
    c, bot = make_client(tmp_path)
    r = c.post("/api/sync", headers={"X-Trigger": "n8n:cron-15m"})
    assert r.status_code == 200
    assert "n8n · Lịch 15 phút" in c.get("/luong").text
    vid = bot.db.one("SELECT id FROM variants WHERE channel = 'pinterest'")["id"]
    r = c.post(f"/ui/variant/{vid}/approve", follow_redirects=False)
    assert r.status_code == 303 and bot.variant(vid)["status"] == "scheduled"
    r = c.post(f"/ui/variant/{vid - 1}/edit", data={"body": "Kinder Immune giúp chữa khỏi ốm vặt."}, follow_redirects=False)
    assert bot.variant(vid - 1)["status"] == "blocked"
