"""Kịch bản demo đầy đủ trên dữ liệu thật của doppelherz.vn (chế độ chạy thử — không đăng thật).

Chạy:  DATA_DIR=data/demo python scripts/demo_scenario.py   (sau khi pip install -e .)
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from content_robot.config import load_settings  # noqa: E402
from content_robot.pipeline import Robot  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
bot = Robot(load_settings())

print("1) Lấy 6 bài Kiến thức sức khỏe mới nhất + 1 thông báo CTKM dạng PDF")
bot.sync(limit=6, categories=[3])
bot.sync(wp_ids=[40507])
for a in bot.db.all("SELECT id, status, title, error FROM articles ORDER BY id"):
    print(f"   [{a['status']:<9}] {a['title'][:70]} {('— ' + a['error']) if a['error'] else ''}")

print("2) Biên tập viên thêm câu SAI luật vào bản Facebook bài 'Lỗ hổng miễn dịch'")
fb = bot.db.one("SELECT v.* FROM variants v JOIN articles a ON a.id=v.article_id WHERE a.wp_id=39906 AND v.channel='facebook'")
v = bot.edit(fb["id"], fb["body"].rstrip() + "\n\nSiro Kinder Immune được bác sĩ khuyên dùng, giúp chữa khỏi ốm vặt cho bé chỉ sau 1 tuần.",
             user="bien-tap-A")
print("   →", v["status"], [(i["code"], i["severity"]) for i in v["compliance_issues"]])

print("3) Biên tập viên nhắc sản phẩm ĐÚNG công dụng XNQC trong bản Facebook bài collagen")
fb2 = bot.db.one("SELECT v.* FROM variants v JOIN articles a ON a.id=v.article_id WHERE a.wp_id=39255 AND v.channel='facebook'")
v2 = bot.edit(fb2["id"], fb2["body"].rstrip() + "\n\nBeauty Collagen của Doppelherz hỗ trợ tăng tính đàn hồi cho da và giúp da mịn màng.",
              user="bien-tap-A")
print("   →", v2["status"], [(i["code"], i["severity"]) for i in v2["compliance_issues"]])

print("4) Trưởng Marketing duyệt 8 bản → robot xếp vào khung giờ vàng")
for vid in [x["id"] for x in bot.db.all("SELECT id FROM variants WHERE status='needs_review' ORDER BY id")][:8]:
    r = bot.approve(vid, user="truong-marketing")
    print(f"   #{vid} {r['channel']:<9} → {datetime.fromisoformat(r['scheduled_at']).astimezone(VN):%d/%m %H:%M}")

if os.environ.get("SIMULATE_CLOCK", "1") == "0":
    print("5) Bỏ qua mô phỏng đồng hồ — n8n sẽ đăng đúng giờ thật")
    raise SystemExit
sim = datetime.now(VN) + timedelta(hours=21)
print(f"5) Mô phỏng đồng hồ tới {sim:%H:%M %d/%m} → đăng các bản đến giờ (ghi payload ra outbox)")
print("   Đã đăng:", bot.run_due(now=sim))
print("6) Lấy số liệu tương tác (mô phỏng, có gắn cờ)", bot.collect_metrics())
