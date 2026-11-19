"""Dòng lệnh: content-robot <lệnh>  (hoặc python -m content_robot <lệnh>)"""
from __future__ import annotations

import argparse
import json

from .config import load_settings
from .pipeline import Robot


def main() -> None:
    ap = argparse.ArgumentParser(prog="content-robot", description="Robot đồng bộ nội dung Doppelherz: Website → Facebook, Pinterest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sync", help="Lấy bài mới từ website và tạo bản cho từng kênh")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--category", type=int, default=3, help="ID chuyên mục WordPress (3 = Kiến thức sức khỏe; 0 = tất cả)")
    p.add_argument("--wp-id", type=int, nargs="*")
    sub.add_parser("list", help="Liệt kê các bản và trạng thái")
    a = sub.add_parser("approve", help="Duyệt và xếp lịch")
    a.add_argument("ids", type=int, nargs="*")
    a.add_argument("--all-clean", action="store_true", help="Duyệt mọi bản 'Chờ duyệt' không có cảnh báo")
    r = sub.add_parser("run-due", help="Đăng các bản đến giờ")
    r.add_argument("--force", action="store_true", help="Đăng ngay mọi bản đã lên lịch (demo)")
    sub.add_parser("metrics", help="Cập nhật số liệu tương tác")
    sub.add_parser("report", help="In báo cáo tuần")
    sub.add_parser("claims", help="In sổ XNQC lấy từ website")
    sv = sub.add_parser("serve", help="Chạy dashboard + webhook")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    s = load_settings()
    if args.cmd == "serve":
        import uvicorn

        from .web import create_app

        uvicorn.run(create_app(s), host=args.host, port=args.port)
        return
    bot = Robot(s)
    if args.cmd == "sync":
        ids = bot.sync(limit=args.limit, categories=[args.category] if args.category else None, wp_ids=args.wp_id)
        print(f"Bài mới: {len(ids)}")
        for v in bot.db.all("SELECT v.id, v.channel, v.status, v.compliance_status, a.title FROM variants v JOIN articles a ON a.id=v.article_id WHERE a.id IN (" + ",".join("?" * len(ids)) + ")", tuple(ids)) if ids else []:
            print(f"  #{v['id']:<3} {v['channel']:<9} {v['status']:<13} kiểm duyệt={v['compliance_status']:<5} {v['title'][:60]}")
    elif args.cmd == "list":
        for v in bot.db.all("SELECT v.id, v.channel, v.status, v.scheduled_at, a.title FROM variants v JOIN articles a ON a.id=v.article_id ORDER BY v.id"):
            print(f"#{v['id']:<3} {v['channel']:<9} {v['status']:<13} {v['scheduled_at'] or '':<26} {v['title'][:55]}")
    elif args.cmd == "approve":
        ids = list(args.ids)
        if args.all_clean:
            ids += [v["id"] for v in bot.db.all("SELECT id FROM variants WHERE status='needs_review' AND compliance_status='pass'")]
        for i in ids:
            v = bot.approve(i, user="cli")
            print(f"#{i} {v['channel']} → lên lịch {v['scheduled_at']}")
    elif args.cmd == "run-due":
        print("Đã đăng:", bot.run_due(force=args.force))
    elif args.cmd == "metrics":
        print("Số bản đã cập nhật số liệu:", bot.collect_metrics())
    elif args.cmd == "report":
        from .reporting import insights, weekly_data, weekly_text

        data = weekly_data(bot)
        print(weekly_text(data, insights(bot, data)))
    elif args.cmd == "claims":
        for p in bot.registry.products:
            print(json.dumps({"san_pham": p.short_name, "xnqc": p.xnqc, "cong_dung": p.claims}, ensure_ascii=False))


if __name__ == "__main__":
    main()
