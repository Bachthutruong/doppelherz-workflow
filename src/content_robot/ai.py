"""Lớp AI: viết lại bài web thành gói nội dung Facebook + Pinterest.

- ClaudeWriter: gọi Claude qua Anthropic SDK, đầu ra JSON ép theo schema (structured outputs),
  bật fallback phía máy chủ khi model từ chối.
- OfflineWriter: bộ sinh theo mẫu, không cần mạng — dùng khi chưa có API key hoặc API lỗi,
  để quy trình không bao giờ bị treo. Bài sinh offline vẫn phải qua kiểm duyệt và người duyệt.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .claims import Product, fold
from .wordpress import Article

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
BOARDS = ["Sức khỏe trẻ em", "Mẹ bầu & sức khỏe phụ nữ", "Vitamin & khoáng chất", "Xương khớp",
          "Làm đẹp từ bên trong", "Sống khỏe năng động"]


class Analysis(BaseModel):
    topic: str
    audience: str
    key_points: list[str]
    suitable_for_social: bool
    reason: str


class FacebookPost(BaseModel):
    hook: str
    body: str
    cta: str
    hashtags: list[str]


class PinterestPin(BaseModel):
    title: str = Field(max_length=100)
    description: str
    alt_text: str
    overlay_headline: str
    board: str


class SocialPack(BaseModel):
    analysis: Analysis
    facebook: FacebookPost
    pinterest: PinterestPin


class ReviewIssue(BaseModel):
    rule: str
    quote: str
    explanation: str
    suggestion: str


class Review(BaseModel):
    verdict: str
    issues: list[ReviewIssue]


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_S = {"type": "string"}
SOCIAL_PACK_SCHEMA = _obj({
    "analysis": _obj({"topic": _S, "audience": _S, "key_points": {"type": "array", "items": _S},
                      "suitable_for_social": {"type": "boolean"}, "reason": _S}),
    "facebook": _obj({"hook": _S, "body": _S, "cta": _S, "hashtags": {"type": "array", "items": _S}}),
    "pinterest": _obj({"title": _S, "description": _S, "alt_text": _S, "overlay_headline": _S,
                       "board": {"type": "string", "enum": BOARDS}}),
})
REVIEW_SCHEMA = _obj({
    "verdict": {"type": "string", "enum": ["pass", "needs_edit", "block"]},
    "issues": {"type": "array", "items": _obj({"rule": _S, "quote": _S, "explanation": _S, "suggestion": _S})},
})


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def render(template: str, **values: str) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def claims_text(products: list[Product]) -> str:
    if not products:
        return "Bài không nhắc sản phẩm nào. Không được tự thêm tên hay công dụng sản phẩm."
    return "\n\n".join(p.claims_block() for p in products)


def build_pack_prompt(article: Article, products: list[Product], max_chars: int = 12000) -> str:
    return render(
        load_prompt("01_social_pack.md"),
        url=article.url, title=article.title, categories=", ".join(article.categories) or "(không có)",
        excerpt=article.excerpt or "(không có)", headings=" | ".join(article.headings) or "(không có)",
        content=article.content_text[:max_chars], approved_claims=claims_text(products),
        boards=", ".join(BOARDS),
    )


class ClaudeWriter:
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-opus-5-5", effort: str = "medium", client: Any = None):
        import anthropic

        self.anthropic = anthropic
        self.client = client or anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=120)
        self.model = model
        self.effort = effort
        self.system = load_prompt("00_system.md")
        self.last_usage: dict[str, Any] = {}

    def _json_call(self, prompt: str, schema: dict[str, Any], max_tokens: int = 16000) -> dict[str, Any]:
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self.system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"Model từ chối yêu cầu: {getattr(resp.stop_details, 'category', None)}")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("Phản hồi bị cắt do max_tokens")
        u = getattr(resp, "usage", None)
        tin, tout = getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0
        self.last_usage = {"model": getattr(resp, "model", self.model), "input_tokens": tin, "output_tokens": tout,
                           "cost_usd": round(tin * 4 / 1e6 + tout * 20 / 1e6, 4)}
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)

    def generate(self, article: Article, products: list[Product]) -> SocialPack:
        return SocialPack.model_validate(self._json_call(build_pack_prompt(article, products), SOCIAL_PACK_SCHEMA))

    def review(self, channel: str, content: str, products: list[Product], source_excerpt: str) -> Review:
        prompt = render(load_prompt("02_compliance_review.md"), channel=channel, content=content,
                        approved_claims=claims_text(products), source_excerpt=source_excerpt[:6000])
        return Review.model_validate(self._json_call(prompt, REVIEW_SCHEMA, max_tokens=8000))

    def revise(self, channel: str, current: str, feedback: str, issues: str, article: Article,
               products: list[Product]) -> SocialPack:
        prompt = build_pack_prompt(article, products) + "\n\n" + render(
            load_prompt("03_revision.md"), channel=channel, current=current, feedback=feedback, issues=issues)
        return SocialPack.model_validate(self._json_call(prompt, SOCIAL_PACK_SCHEMA))


# ---------------------------------------------------------------- Offline


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    return [p.strip() for p in parts if len(p.strip()) > 20]


def _hashtag(s: str) -> str:
    return "#" + re.sub(r"[^A-Za-z0-9]", "", fold(s).title())


def _shorten(s: str, words: int) -> str:
    w = s.split()
    return s if len(w) <= words else " ".join(w[:words]).rstrip(",:;–-") + "…"


def _pick_board(categories: list[str], title: str) -> str:
    t = fold(" ".join(categories) + " " + title)
    rules = [("Sức khỏe trẻ em", ["tre em", "be ", "con "]),
             ("Mẹ bầu & sức khỏe phụ nữ", ["mang thai", "me bau", "phu nu", "man kinh"]),
             ("Xương khớp", ["xuong khop", "khop", "canxi"]),
             ("Làm đẹp từ bên trong", ["lam dep", "collagen", "da ", "toc"]),
             ("Vitamin & khoáng chất", ["vitamin", "khoang chat", "de khang", "mien dich"])]
    for board, keys in rules:
        if any(k in t for k in keys):
            return board
    return "Sống khỏe năng động"


class OfflineWriter:
    """Bộ sinh theo mẫu: rút ý từ đề mục và câu đầu của bài; không thêm thông tin ngoài bài gốc."""

    name = "offline-template"
    model = "rule-based-v1"
    last_usage: dict[str, Any] = {}

    def generate(self, article: Article, products: list[Product]) -> SocialPack:
        title = article.title.strip()
        sents = _sentences(article.excerpt) or _sentences(article.content_text)
        lead = sents[0] if sents else title
        points = [h for h in article.headings if 8 < len(h) < 110][:3]
        if len(points) < 3:
            points += [_shorten(s, 18) for s in _sentences(article.content_text)[1:6]][: 3 - len(points)]
        cats = [c for c in article.categories if c.lower() not in {"kiến thức sức khỏe", "uncategorized"}]
        suitable = not re.search(r"\.pdf$|danh sách trúng thưởng|chương trình .*đại lý", title.lower())
        audience = ("ba mẹ có con nhỏ" if re.search(r"\b(tre|be|con)\b", fold(title + " " + " ".join(cats)))
                    else "người quan tâm sức khỏe gia đình")
        hook = title if title.endswith("?") else f"Bạn có biết: {title[0].lower() + title[1:]}?"
        body_lines = [_shorten(lead, 45), ""] + [f"✅ {p}" for p in points] + ["", "Doppelherz tổng hợp đầy đủ trong bài viết mới trên website."]
        if any(k in fold(title) for k in ("tre", "be ", "mang thai", "me bau")):
            body_lines.append("Khi trẻ hoặc mẹ có dấu hiệu bất thường, hãy hỏi ý kiến chuyên gia y tế.")
        tags = ["#Doppelherz", "#KienThucSucKhoe"] + [_hashtag(c) for c in cats[:2]]
        desc = f"{_shorten(lead, 55)} {('Bài viết gồm: ' + '; '.join(points[:3]) + '.') if points else ''} Xem hướng dẫn chi tiết từ Doppelherz Việt Nam."
        while len(desc) > 480:
            desc = _shorten(desc, len(desc.split()) - 5)
        return SocialPack(
            analysis={"topic": _shorten(title, 12), "audience": audience, "key_points": points[:3] or [lead],
                      "suitable_for_social": bool(suitable),
                      "reason": "Bài kiến thức sức khỏe công khai" if suitable else "Bài nội bộ hoặc tài liệu cho đại lý"},
            facebook={"hook": hook, "body": "\n".join(body_lines).strip(), "cta": "👉 Đọc bài đầy đủ tại website Doppelherz:",
                      "hashtags": list(dict.fromkeys(tags))[:5]},
            pinterest={"title": title if len(title) <= 90 else _shorten(title[:88], 14), "description": desc,
                       "alt_text": (article.image_alt if article.image_alt and len(article.image_alt) >= 40
                                    else f"Ảnh minh họa bài viết “{title}” của Doppelherz Việt Nam")[:300],
                       "overlay_headline": title if len(title) <= 75 else _shorten(title, 12), "board": _pick_board(article.categories, title)},
        )

    def review(self, *args: Any, **kwargs: Any) -> Review:
        return Review(verdict="pass", issues=[])
