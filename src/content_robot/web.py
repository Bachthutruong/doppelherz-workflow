"""Dashboard (giao diện biên tập) + webhook WordPress + API cho n8n."""
from __future__ import annotations

import json
import math
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .config import Settings, load_settings
from .pipeline import Robot
from .reporting import insights, weekly_data, weekly_text

HERE = Path(__file__).resolve().parent
STATUS_VI = {"needs_review": "Chờ duyệt", "blocked": "Bị chặn", "approved": "Đã duyệt", "scheduled": "Đã lên lịch",
             "published": "Đã đăng", "rejected": "Từ chối", "failed": "Lỗi đăng"}
STATUS_CLS = {"needs_review": "warn", "blocked": "err", "approved": "info", "scheduled": "info",
              "published": "ok", "rejected": "", "failed": "err"}
SEV_VI = {"block": "Chặn", "warn": "Cần xem", "fixed": "Đã tự sửa"}
SEV_CLS = {"block": "err", "warn": "warn", "fixed": "ok"}
RULE_VI = {"R1": "Công dụng vượt XNQC", "R2": "Ngụ ý chữa/phòng bệnh", "R3": "Danh nghĩa nhân viên y tế",
           "R4": "Từ tuyệt đối, so sánh", "R5": "Thiếu câu \"không phải là thuốc\"", "R6": "Thông tin ngoài bài gốc",
           "XNQC": "Số XNQC", "LEN": "Độ dài theo nền tảng", "STYLE": "Văn phong"}

ICONS = {
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "file": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M8 13h8M8 17h5"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "flow": '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M9 6h4a3 3 0 0 1 3 3v6"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M7 15v3M12 10v8M17 6v12"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "play": '<path d="m7 4 13 8-13 8z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "spark": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    "server": '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    "bot": '<rect x="3" y="8" width="18" height="12" rx="3"/><path d="M12 8V4M9 4h6"/><circle cx="9" cy="14" r="1.2"/><circle cx="15" cy="14" r="1.2"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    "logo": '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7z"/><path d="M3.5 12H8l1.5-3 3 6 1.5-3h4.5"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "left": '<path d="m15 18-6-6 6-6"/>',
    "right": '<path d="m9 18 6-6-6-6"/>',
    "comment": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "like": '<path d="M7 10v11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/><path d="M7 10l4-8a3 3 0 0 1 3 3v4h6a2 2 0 0 1 2 2.3l-1.4 8A2 2 0 0 1 18.6 21H7"/>',
    "share": '<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="m16 6-4-4-4 4"/><path d="M12 2v13"/>',
    "package": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    "db": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    "dots": '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
}


def icon(name: str, size: int = 18, sw: float = 2) -> Markup:
    return Markup(f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                  f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, "")}</svg>')


def create_app(settings: Settings | None = None, robot: Robot | None = None) -> FastAPI:
    s = settings or load_settings()
    bot = robot or Robot(s)
    tz = ZoneInfo(s.timezone)
    downloads = Path(os.environ.get("DOWNLOADS_DIR", str(s.data_dir.parent / "downloads")))
    app = FastAPI(title="Doppelherz Content Robot", docs_url="/api/docs", redoc_url=None)
    app.mount("/media", StaticFiles(directory=str(s.media_dir)), name="media")
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    env = Environment(loader=FileSystemLoader(str(HERE / "templates")), autoescape=select_autoescape(["html"]))

    def local(ts: str | None) -> datetime | None:
        return datetime.fromisoformat(ts).astimezone(tz) if ts else None

    def fmt(ts: str | None, f: str = "%d/%m %H:%M") -> str:
        d = local(ts)
        return d.strftime(f) if d else ""

    def rel(ts: str | None) -> str:
        d = local(ts)
        if not d:
            return ""
        sec = (datetime.now(tz) - d).total_seconds()
        if sec < -60:
            mins = -sec / 60
            return f"sau {int(mins)} phút" if mins < 60 else (f"sau {int(mins // 60)} giờ" if mins < 1440 else d.strftime("%d/%m %H:%M"))
        if sec < 60:
            return "vừa xong"
        if sec < 3600:
            return f"{int(sec // 60)} phút trước"
        if sec < 86400:
            return f"{int(sec // 3600)} giờ trước"
        return d.strftime("%d/%m %H:%M")

    def thumb(a: dict[str, Any] | None) -> str:
        return (a or {}).get("image_url") or "/static/placeholder.svg"

    def media(path: str | None) -> str:
        return f"/media/{Path(path).name}" if path else ""

    env.globals.update(icon=icon, fmt=fmt, rel=rel, thumb=thumb, media=media, STATUS_VI=STATUS_VI,
                       STATUS_CLS=STATUS_CLS, SEV_VI=SEV_VI, SEV_CLS=SEV_CLS, RULE_VI=RULE_VI, s=s, quote=quote)

    def ai_label() -> str:
        return f"Claude · {s.claude_model}" if s.ai_enabled else "Bộ sinh dự phòng (chưa có API key)"

    def render(name: str, request: Request, **ctx: Any) -> HTMLResponse:
        n_review = (bot.db.one("SELECT COUNT(*) AS n FROM variants WHERE status IN ('needs_review','blocked')") or {}).get("n", 0)
        last_n8n = bot.db.one("SELECT ts FROM events WHERE entity = 'n8n' ORDER BY id DESC LIMIT 1")
        ctx.update(request=request, path=request.url.path, ai_label=ai_label(), n_review=n_review,
                   live=s.publish_mode == "live", toast=request.query_params.get("ok"),
                   n8n_last=last_n8n["ts"] if last_n8n else None, v="6")
        return HTMLResponse(env.get_template(name).render(**ctx))

    def redirect(url: str, msg: str | None = None) -> RedirectResponse:
        return RedirectResponse(url + (("&" if "?" in url else "?") + "ok=" + quote(msg) if msg else ""), 303)

    # ------------------------------------------------------------------ data helpers
    def articles_with_variants(where: str = "", args: tuple = ()) -> list[dict[str, Any]]:
        arts = bot.db.all(f"SELECT * FROM articles {where} ORDER BY id DESC", args)
        by: dict[int, dict[str, dict[str, Any]]] = {}
        for v in bot.db.all("SELECT * FROM variants"):
            by.setdefault(v["article_id"], {})[v["channel"]] = v
        for a in arts:
            a["v"] = by.get(a["id"], {})
        return arts

    def ai_costs() -> dict[str, Any]:
        runs, tin, tout, cost = 0, 0, 0, 0.0
        for a in bot.db.all("SELECT trace FROM articles"):
            for t in a.get("trace") or []:
                if t.get("step") == "ai":
                    runs += 1
                    x = t.get("extra") or {}
                    tin += x.get("input_tokens", 0)
                    tout += x.get("output_tokens", 0)
                    cost += x.get("cost_usd", 0.0)
        return {"runs": runs, "tin": tin, "tout": tout, "cost": round(cost, 3)}

    def donut(parts: list[tuple[str, int, str]], size: int = 120) -> Markup:
        total = sum(n for _, n, _ in parts) or 1
        r, c = 46, 2 * math.pi * 46
        off, segs = 0.0, []
        for _, n, color in parts:
            ln = c * n / total
            segs.append(f'<circle r="{r}" cx="60" cy="60" fill="none" stroke="{color}" stroke-width="14" '
                        f'stroke-dasharray="{ln:.2f} {c - ln:.2f}" stroke-dashoffset="{-off:.2f}" transform="rotate(-90 60 60)"/>')
            off += ln
        n_all = sum(n for _, n, _ in parts)
        return Markup(f'<svg width="{size}" height="{size}" viewBox="0 0 120 120"><circle r="{r}" cx="60" cy="60" fill="none" '
                      f'stroke="#F4EFEA" stroke-width="14"/>{"".join(segs)}<text x="60" y="58" text-anchor="middle" '
                      f'font-size="22" font-weight="700" fill="#1D1A19">{n_all}</text><text x="60" y="76" text-anchor="middle" '
                      f'font-size="10.5" fill="#77706B">bản kiểm duyệt</text></svg>')

    # ------------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request) -> HTMLResponse:
        st = Counter({k: n for k, n in ((r["status"], r["n"]) for r in bot.db.all("SELECT status, COUNT(*) AS n FROM variants GROUP BY status"))})
        arts = bot.db.all("SELECT id, status FROM articles")
        comp = Counter(r["compliance_status"] for r in bot.db.all("SELECT compliance_status FROM variants"))
        queue = bot.db.all("SELECT v.*, a.title AS at, a.image_url, a.products FROM variants v JOIN articles a ON a.id = v.article_id "
                           "WHERE v.status IN ('needs_review','blocked') ORDER BY v.status = 'blocked' DESC, v.id DESC LIMIT 6")
        upcoming = bot.db.all("SELECT v.*, a.title AS at, a.image_url FROM variants v JOIN articles a ON a.id = v.article_id "
                              "WHERE v.status = 'scheduled' ORDER BY v.scheduled_at LIMIT 6")
        events = bot.db.all("SELECT * FROM events ORDER BY id DESC LIMIT 9")
        data = weekly_data(bot)
        pipe = [
            ("Bài web nhận", len(arts), "n8n + robot"),
            ("AI đã viết", sum(1 for a in arts if a["status"] in ("processed", "skipped")), "Claude"),
            ("Bản kiểm duyệt", sum(st.values()), "Bộ luật + AI"),
            ("Chờ duyệt", st["needs_review"] + st["blocked"], "Biên tập"),
            ("Đã lên lịch", st["scheduled"], "Giờ vàng"),
            ("Đã đăng", st["published"], "Graph · Pinterest"),
        ]
        dn = donut([("Đạt", comp["pass"], "#0F7B55"), ("Cần xem", comp["warn"], "#E6A23C"), ("Chặn", comp["block"], "#C1272D")])
        hour = datetime.now(tz).hour
        greet = "Chào buổi sáng" if hour < 11 else ("Chào buổi trưa" if hour < 14 else ("Chào buổi chiều" if hour < 18 else "Chào buổi tối"))
        return render("overview.html", request, title="Tổng quan", pipe=pipe, st=st, comp=comp, donut=dn, queue=queue,
                      upcoming=upcoming, events=events, data=data, greet=greet, costs=ai_costs(),
                      today=datetime.now(tz).strftime("%d/%m/%Y"))

    @app.get("/noi-dung", response_class=HTMLResponse)
    def content(request: Request, tab: str = "all", q: str = "") -> HTMLResponse:
        arts = articles_with_variants()
        def has(a: dict[str, Any], *sts: str) -> bool:
            return any(v["status"] in sts for v in a["v"].values())
        tabs = [("all", "Tất cả", arts), ("review", "Chờ duyệt", [a for a in arts if has(a, "needs_review")]),
                ("blocked", "Bị chặn", [a for a in arts if has(a, "blocked")]),
                ("scheduled", "Đã lên lịch", [a for a in arts if has(a, "scheduled")]),
                ("published", "Đã đăng", [a for a in arts if has(a, "published")]),
                ("skipped", "Bỏ qua", [a for a in arts if a["status"] in ("skipped", "error")])]
        rows = next((x for k, _, x in tabs if k == tab), arts)
        if q:
            rows = [a for a in rows if q.lower() in a["title"].lower()]
        return render("content.html", request, title="Nội dung", tabs=tabs, tab=tab, rows=rows, q=q)

    @app.get("/bai/{aid}", response_class=HTMLResponse)
    def article(request: Request, aid: int) -> HTMLResponse:
        a = bot.db.one("SELECT * FROM articles WHERE id = ?", (aid,))
        if not a:
            raise HTTPException(404, "Không có bài này")
        vs = {v["channel"]: v for v in bot.db.all("SELECT * FROM variants WHERE article_id = ?", (aid,))}
        prods = bot.registry.by_name(a.get("products") or [])
        domain = "DOPPELHERZ.VN"
        return render("article.html", request, title=a["title"], a=a, fb=vs.get("facebook"), pin=vs.get("pinterest"),
                      prods=prods, domain=domain)

    @app.get("/lich", response_class=HTMLResponse)
    def calendar(request: Request) -> HTMLResponse:
        rows = bot.db.all("SELECT v.id, v.article_id, v.channel, v.status, v.scheduled_at, v.published_at, v.title AS vt, "
                          "a.title, a.image_url FROM variants v JOIN articles a ON a.id = v.article_id "
                          "WHERE v.scheduled_at IS NOT NULL ORDER BY v.scheduled_at")
        evs = []
        for r in rows:
            d = local(r["scheduled_at"])
            evs.append({"id": r["id"], "aid": r["article_id"], "ch": r["channel"], "st": r["status"],
                        "stl": STATUS_VI.get(r["status"], r["status"]), "d": d.strftime("%Y-%m-%d"),
                        "t": d.strftime("%H:%M"), "title": r["title"], "img": r["image_url"] or ""})
        now = datetime.now(tz)
        cal = {"events": evs, "today": now.strftime("%Y-%m-%d"), "now": now.strftime("%H:%M"), "slots": s.slots,
               "cap": s.max_per_day}
        upcoming = [e for e in evs if e["st"] == "scheduled"][:6]
        week_n = Counter(e["ch"] for e in evs if (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d") <= e["d"] <=
                         (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d"))
        return render("calendar.html", request, title="Lịch đăng", cal=Markup(json.dumps(cal, ensure_ascii=False)),
                      upcoming=upcoming, week_n=week_n)

    @app.get("/luong", response_class=HTMLResponse)
    def flow(request: Request) -> HTMLResponse:
        st = Counter({r["status"]: r["n"] for r in bot.db.all("SELECT status, COUNT(*) AS n FROM variants GROUP BY status")})
        arts = bot.db.all("SELECT * FROM articles ORDER BY id DESC")
        n8n = bot.db.all("SELECT * FROM events WHERE entity = 'n8n' ORDER BY id DESC LIMIT 12")
        n8n_total = (bot.db.one("SELECT COUNT(*) AS n FROM events WHERE entity = 'n8n'") or {}).get("n", 0)
        approved = (bot.db.one("SELECT COUNT(*) AS n FROM variants WHERE approved_at IS NOT NULL") or {}).get("n", 0)
        metrics_n = (bot.db.one("SELECT COUNT(DISTINCT variant_id) AS n FROM metrics") or {}).get("n", 0)
        with_prod = sum(1 for a in arts if a.get("products"))
        costs = ai_costs()
        nprod = len(bot.registry.products)
        nx = sum(1 for p in bot.registry.products if p.xnqc)
        traces = [a for a in arts if a.get("trace")][:6]
        return render("flow.html", request, title="Luồng xử lý", st=st, arts=arts, n8n=n8n, n8n_total=n8n_total,
                      approved=approved, metrics_n=metrics_n, with_prod=with_prod, costs=costs, nprod=nprod, nx=nx,
                      traces=traces)

    @app.get("/so-xnqc", response_class=HTMLResponse)
    def claims(request: Request) -> HTMLResponse:
        prods = sorted(bot.registry.products, key=lambda p: (p.xnqc is not None, p.short_name))
        return render("claims.html", request, title="Sổ XNQC", prods=prods)

    @app.get("/bao-cao", response_class=HTMLResponse)
    def report(request: Request) -> HTMLResponse:
        data = weekly_data(bot)
        ins = insights(bot, data)
        rules = Counter()
        for v in bot.db.all("SELECT compliance_issues FROM variants"):
            for i in v.get("compliance_issues") or []:
                rules[(i["code"].replace("AI-", ""), i["severity"])] += 1
        rmax = max(rules.values() or [1])
        return render("report.html", request, title="Báo cáo", data=data, ins=ins, rules=rules.most_common(), rmax=rmax,
                      text=weekly_text(data, ins), costs=ai_costs())

    @app.get("/nhat-ky", response_class=HTMLResponse)
    def log(request: Request, entity: str = "") -> HTMLResponse:
        q = "SELECT * FROM events" + (" WHERE entity = ?" if entity else "") + " ORDER BY id DESC LIMIT 300"
        ev = bot.db.all(q, (entity,) if entity else ())
        ents = [r["entity"] for r in bot.db.all("SELECT DISTINCT entity FROM events WHERE entity IS NOT NULL")]
        return render("log.html", request, title="Nhật ký", ev=ev, ents=ents, entity=entity)

    @app.get("/gioi-thieu", response_class=HTMLResponse)
    def about(request: Request) -> HTMLResponse:
        files = sorted(p.name for p in downloads.glob("*")) if downloads.exists() else []
        return render("about.html", request, title="Về bản demo", files=files)

    @app.get("/tai-xuong/{name}")
    def download(name: str) -> FileResponse:
        f = (downloads / name).resolve()
        if downloads.resolve() not in f.parents or not f.is_file():
            raise HTTPException(404)
        return FileResponse(f, filename=name)

    # old paths → new
    for old, new in (("/calendar", "/lich"), ("/report", "/bao-cao"), ("/log", "/nhat-ky")):
        app.add_api_route(old, (lambda n=new: RedirectResponse(n, 301)), methods=["GET"], include_in_schema=False)

    @app.get("/article/{aid}", include_in_schema=False)
    def old_article(aid: int) -> RedirectResponse:
        return RedirectResponse(f"/bai/{aid}", 301)

    # ------------------------------------------------------------------ form actions
    @app.post("/ui/sync")
    def ui_sync() -> RedirectResponse:
        new = bot.sync(limit=5, categories=[3], source="bấm nút trên dashboard")
        return redirect("/", f"Đã quét website: {len(new)} bài mới")

    @app.post("/ui/run-due")
    def ui_run_due(force: int = 0) -> RedirectResponse:
        done = bot.run_due(force=bool(force))
        return redirect("/lich", f"Đã đăng {len(done)} bản (chế độ chạy thử)")

    @app.post("/ui/metrics")
    def ui_metrics() -> RedirectResponse:
        n = bot.collect_metrics()
        return redirect("/bao-cao", f"Đã cập nhật số liệu {n} bản")

    @app.post("/ui/variant/{vid}/approve")
    def ui_approve(vid: int) -> RedirectResponse:
        try:
            v = bot.approve(vid, user="bien-tap (dashboard)")
        except ValueError as ex:
            return redirect(f"/bai/{bot.variant(vid)['article_id']}", str(ex))
        return redirect(f"/bai/{v['article_id']}", f"Đã duyệt — lên lịch {fmt(v['scheduled_at'])}")

    @app.post("/ui/variant/{vid}/reject")
    def ui_reject(vid: int, feedback: str = Form("")) -> RedirectResponse:
        bot.reject(vid, feedback or "Không ghi góp ý", user="bien-tap (dashboard)")
        return redirect(f"/bai/{bot.variant(vid)['article_id']}", "Đã từ chối và lưu góp ý")

    @app.post("/ui/variant/{vid}/edit")
    def ui_edit(vid: int, body: str = Form(...), title: str | None = Form(None)) -> RedirectResponse:
        v = bot.edit(vid, body, title, user="bien-tap (dashboard)")
        msg = "Đã lưu — robot chặn vì vi phạm tuân thủ" if v["status"] == "blocked" else "Đã lưu và kiểm duyệt lại"
        return redirect(f"/bai/{v['article_id']}", msg)

    # ------------------------------------------------------------ webhook + JSON API (cho n8n)
    trig_vi = {"n8n:webhook": "n8n · Webhook bài mới", "n8n:cron-15m": "n8n · Lịch 15 phút", "n8n:weekly": "n8n · Thứ Hai 8:00"}

    def n8n_log(trigger: str | None, what: str) -> None:
        if trigger:
            bot.db.log(f"{trig_vi.get(trigger, trigger)} → {what}", entity="n8n")

    @app.post("/webhook/wordpress")
    async def webhook(request: Request, x_webhook_secret: str = Header(""), x_trigger: str | None = Header(None)) -> JSONResponse:
        if x_webhook_secret != s.webhook_secret:
            raise HTTPException(401, "Sai mã bí mật webhook")
        payload = await request.json()
        post_id = payload.get("post_id") or payload.get("ID") or (payload.get("post") or {}).get("ID")
        if not post_id:
            raise HTTPException(400, "Thiếu post_id")
        new = bot.sync(wp_ids=[int(post_id)], source="webhook WordPress qua n8n" if x_trigger else "webhook WordPress")
        pending = bot.db.all("SELECT id, channel, status FROM variants WHERE article_id IN (" + ",".join("?" * len(new)) + ")", tuple(new)) if new else []
        n8n_log(x_trigger, f"xử lý bài #{post_id}: {len(pending)} bản mới")
        return JSONResponse({"new_articles": new, "variants": pending})

    @app.get("/api/stats")
    def api_stats() -> dict[str, Any]:
        return bot.stats()

    @app.get("/api/variants")
    def api_variants(status: str | None = None) -> list[dict[str, Any]]:
        q = ("SELECT v.id, v.channel, v.status, v.title, v.scheduled_at, v.compliance_status, a.title AS article_title, a.url "
             "FROM variants v JOIN articles a ON a.id = v.article_id")
        return bot.db.all(q + (" WHERE v.status = ?" if status else "") + " ORDER BY v.id DESC", (status,) if status else ())

    @app.post("/api/sync")
    def api_sync(limit: int = 5, category: int | None = 3, x_trigger: str | None = Header(None)) -> dict[str, Any]:
        new = bot.sync(limit=limit, categories=[category] if category else None,
                       source="lịch quét 15 phút của n8n" if x_trigger else "API")
        review = len(bot.db.all("SELECT id FROM variants WHERE status = 'needs_review'"))
        n8n_log(x_trigger, f"quét website: {len(new)} bài mới, {review} bản chờ duyệt")
        return {"new_articles": new, "needs_review": review}

    @app.post("/api/run-due")
    def api_run_due(force: bool = False, x_trigger: str | None = Header(None)) -> dict[str, Any]:
        done = bot.run_due(force=force)
        n8n_log(x_trigger, f"đăng các bản đến giờ: {len(done)} bản")
        return {"published": done}

    @app.post("/api/metrics")
    def api_metrics(x_trigger: str | None = Header(None)) -> dict[str, Any]:
        n = bot.collect_metrics()
        n8n_log(x_trigger, f"cập nhật số liệu: {n} bản")
        return {"collected": n}

    @app.get("/api/report")
    def api_report(x_trigger: str | None = Header(None)) -> dict[str, Any]:
        data = weekly_data(bot)
        ins = insights(bot, data)
        n8n_log(x_trigger, "lập báo cáo tuần")
        return {"data": data, "insights": ins, "text": weekly_text(data, ins)}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "ai": ai_label(), "mode": s.publish_mode}

    return app


def app_factory() -> FastAPI:
    return create_app()
