"""Báo cáo tuần: số bài, tỷ lệ duyệt, lỗi tuân thủ, lịch tuần tới, tương tác theo kênh."""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from .ai import load_prompt, render
from .pipeline import Robot


def weekly_data(robot: Robot, days: int = 7) -> dict[str, Any]:
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    db = robot.db
    arts = db.all("SELECT * FROM articles WHERE fetched_at >= ?", (since,))
    vars_ = db.all("SELECT v.*, a.title AS article_title, a.url AS article_url FROM variants v "
                   "JOIN articles a ON a.id = v.article_id WHERE v.created_at >= ?", (since,))
    st = Counter(v["status"] for v in vars_)
    reviewed = [v for v in vars_ if v["approved_at"]]
    approve_minutes = [
        (datetime.fromisoformat(v["approved_at"]) - datetime.fromisoformat(v["created_at"])).total_seconds() / 60
        for v in reviewed]
    issue_counter: Counter[str] = Counter()
    for v in vars_:
        for i in v["compliance_issues"] or []:
            issue_counter[f"{i['severity']}:{i['code']}"] += 1

    latest = db.all("""SELECT m.*, v.channel, a.title FROM metrics m JOIN variants v ON v.id = m.variant_id
                       JOIN articles a ON a.id = v.article_id
                       WHERE m.id IN (SELECT MAX(id) FROM metrics GROUP BY variant_id)""")
    per_channel: dict[str, dict[str, int]] = {}
    for m in latest:
        c = per_channel.setdefault(m["channel"], {"posts": 0, "impressions": 0, "engagements": 0, "clicks": 0, "saves": 0})
        c["posts"] += 1
        c["impressions"] += m["impressions"] or 0
        c["engagements"] += (m["reactions"] or 0) + (m["comments"] or 0) + (m["shares"] or 0) + (m["saves"] or 0)
        c["clicks"] += m["clicks"] or 0
        c["saves"] += m["saves"] or 0
    top = sorted(latest, key=lambda m: (m["clicks"] or 0), reverse=True)[:3]
    upcoming = db.all("SELECT v.channel, v.scheduled_at, a.title FROM variants v JOIN articles a ON a.id = v.article_id "
                      "WHERE v.status = 'scheduled' ORDER BY v.scheduled_at LIMIT 10")
    return {
        "period_days": days,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "articles_received": len(arts),
        "articles_skipped": sum(1 for a in arts if a["status"] == "skipped"),
        "variants_created": len(vars_),
        "variants_by_status": dict(st),
        "approval_rate_pct": round(100 * len(reviewed) / len(vars_), 1) if vars_ else 0.0,
        "median_minutes_to_approve": round(sorted(approve_minutes)[len(approve_minutes) // 2], 1) if approve_minutes else None,
        "compliance_issues": dict(issue_counter.most_common()),
        "ai_provider": Counter(v["ai_provider"] for v in vars_).most_common(1)[0][0] if vars_ else None,
        "per_channel": per_channel,
        "top_posts_by_clicks": [{"channel": m["channel"], "title": m["title"], "clicks": m["clicks"],
                                 "impressions": m["impressions"]} for m in top],
        "upcoming": upcoming,
        "simulated": any(m["simulated"] for m in latest),
    }


def insights(robot: Robot, data: dict[str, Any]) -> dict[str, list[str]]:
    """Nhận định: dùng Claude nếu có (prompt 04), nếu không thì quy tắc đơn giản."""
    writer = robot.writer
    if hasattr(writer, "_json_call"):
        try:
            schema = {"type": "object", "additionalProperties": False, "required": ["summary", "actions"],
                      "properties": {"summary": {"type": "array", "items": {"type": "string"}},
                                     "actions": {"type": "array", "items": {"type": "string"}}}}
            prompt = render(load_prompt("04_weekly_report.md"), week=data["generated_at"][:10],
                            metrics_json=json.dumps(data, ensure_ascii=False, default=str))
            return writer._json_call(prompt, schema, max_tokens=4000)
        except Exception as e:
            robot.db.log(f"AI báo cáo lỗi: {e}", "warn")
    s = data
    summary = [
        f"Robot nhận {s['articles_received']} bài web, tạo {s['variants_created']} bản mạng xã hội; "
        f"{s['variants_by_status'].get('published', 0)} bản đã đăng, {s['variants_by_status'].get('scheduled', 0)} bản đang chờ giờ đăng.",
        f"Tỷ lệ được duyệt {s['approval_rate_pct']}%; {s['variants_by_status'].get('blocked', 0)} bản bị chặn bởi bộ luật tuân thủ "
        f"và {s['variants_by_status'].get('needs_review', 0)} bản còn chờ biên tập.",
    ]
    for ch, c in s["per_channel"].items():
        rate = round(100 * c["clicks"] / c["impressions"], 2) if c["impressions"] else 0
        summary.append(f"{ch.title()}: {c['impressions']:,} lượt hiển thị, {c['clicks']:,} lượt nhấp (CTR {rate}%)"
                       + (" — số liệu mô phỏng" if s["simulated"] else ""))
    actions = ["Biên tập viên xử lý hết hàng chờ duyệt trước 17:00 mỗi ngày để giữ đủ 2 bài/ngày/kênh."]
    real_issues = [k for k in s["compliance_issues"] if not k.startswith("fixed:")]
    if real_issues:
        top_issue = real_issues[0]
        actions.append(f"Marketing cùng pháp chế rà lỗi thường gặp nhất ({top_issue}) và bổ sung ví dụ vào prompt.")
    return {"summary": summary, "actions": actions}


def weekly_text(data: dict[str, Any], ins: dict[str, list[str]]) -> str:
    lines = [f"BÁO CÁO TUẦN — ROBOT NỘI DUNG DOPPELHERZ ({data['generated_at'][:10]})", ""]
    lines += [f"• {x}" for x in ins["summary"]]
    lines += ["", "Đề xuất:"] + [f"→ {x}" for x in ins["actions"]]
    return "\n".join(lines)
