"""Đọc bài viết từ WordPress REST API của doppelherz.vn."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

import httpx

UA = "DoppelherzContentRobot/1.0 (+demo)"


@dataclass
class Article:
    wp_id: int
    url: str
    title: str
    published_at: str
    categories: list[str]
    excerpt: str
    content_text: str
    headings: list[str]
    image_url: str | None = None
    image_alt: str | None = None
    image_size: tuple[int, int] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class _TextExtractor(HTMLParser):
    """Lấy văn bản thuần, đề mục h2/h3; bỏ script/style/mục lục."""

    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "br", "tr", "blockquote"}
    SKIP = {"script", "style", "noscript", "figure", "figcaption", "nav"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.headings: list[str] = []
        self._skip = 0
        self._heading: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        cls = dict(attrs).get("class") or ""
        if tag in self.SKIP or "ez-toc" in cls or "toc" == cls:
            self._skip += 1
        if tag in {"h2", "h3"} and not self._skip:
            self._heading = []
        if tag == "li" and not self._skip:
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in {"h2", "h3"} and self._heading is not None:
            text = _clean(" ".join(self._heading))
            if text and len(text) > 3:
                self.headings.append(text)
            self._heading = None
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self.parts.append(data)
        if self._heading is not None:
            self._heading.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [_clean(x) for x in raw.splitlines()]
        out: list[str] = []
        for ln in lines:
            if ln in {"", "-"}:
                continue
            if ln.lower().startswith("nội dung bài viết"):
                continue
            out.append(ln)
        return "\n".join(out)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def html_to_text(content_html: str) -> tuple[str, list[str]]:
    p = _TextExtractor()
    p.feed(content_html or "")
    return p.text(), p.headings


def parse_post(post: dict[str, Any]) -> Article:
    """Chuyển 1 bản ghi /wp-json/wp/v2/posts?_embed thành Article."""
    content_text, headings = html_to_text(post.get("content", {}).get("rendered", ""))
    excerpt, _ = html_to_text(post.get("excerpt", {}).get("rendered", ""))
    excerpt = re.sub(r"\s*\[(…|\.\.\.|&hellip;)\]\s*$", "…", excerpt).strip()

    embedded = post.get("_embedded") or {}
    categories: list[str] = []
    for group in embedded.get("wp:term") or []:
        for term in group or []:
            if term.get("taxonomy") == "category":
                categories.append(_clean(term.get("name", "")))

    image_url = image_alt = None
    image_size = None
    media = (embedded.get("wp:featuredmedia") or [None])[0]
    if isinstance(media, dict) and media.get("source_url"):
        image_url = media["source_url"]
        image_alt = _clean(media.get("alt_text") or "") or None
        md = media.get("media_details") or {}
        if md.get("width") and md.get("height"):
            image_size = (int(md["width"]), int(md["height"]))

    return Article(
        wp_id=int(post["id"]),
        url=post.get("link", ""),
        title=_clean(post.get("title", {}).get("rendered", "")),
        published_at=post.get("date", ""),
        categories=categories,
        excerpt=excerpt,
        content_text=content_text,
        headings=headings,
        image_url=image_url,
        image_alt=image_alt,
        image_size=image_size,
    )


class WordPressClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=True)

    def list_posts(self, per_page: int = 10, page: int = 1, categories: list[int] | None = None,
                   after: str | None = None, search: str | None = None) -> list[Article]:
        params: dict[str, Any] = {
            "per_page": per_page, "page": page, "orderby": "date", "order": "desc",
            "_embed": "wp:featuredmedia,wp:term",
        }
        if categories:
            params["categories"] = ",".join(map(str, categories))
        if after:
            params["after"] = after
        if search:
            params["search"] = search
        r = self.http.get(f"{self.base}/wp-json/wp/v2/posts", params=params)
        r.raise_for_status()
        return [parse_post(p) for p in r.json()]

    def get_post(self, wp_id: int) -> Article:
        r = self.http.get(f"{self.base}/wp-json/wp/v2/posts/{wp_id}", params={"_embed": "wp:featuredmedia,wp:term"})
        r.raise_for_status()
        return parse_post(r.json())

    def list_products(self) -> list[dict[str, Any]]:
        r = self.http.get(f"{self.base}/wp-json/wc/store/v1/products", params={"per_page": 100})
        r.raise_for_status()
        return r.json()
