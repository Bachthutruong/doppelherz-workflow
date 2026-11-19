"""Sổ công dụng được phép (claims registry) dựng tự động từ WooCommerce API.

Mỗi sản phẩm trên doppelherz.vn có "Số XNQC" (xác nhận nội dung quảng cáo) và danh sách công dụng
đã được xác nhận trong phần mô tả ngắn. Robot chỉ cho AI dùng đúng các công dụng này.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .wordpress import html_to_text

CLAIM_STARTS = ("hỗ trợ", "bổ sung", "cung cấp", "giúp", "tăng cường")
STRIP_PREFIXES = ("tpbvsk ", "thực phẩm bảo vệ sức khỏe ", "doppelherz aktiv ", "doppelherz ")
STRIP_SUFFIXES = (" syrup", " capsules", " liquid", " drops", " (30 viên)", " 30 viên")


def fold(s: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt — để so khớp không phụ thuộc dấu."""
    s = s.lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


@dataclass
class Product:
    wc_id: int
    name: str
    short_name: str
    url: str
    xnqc: str | None
    xncb: str | None
    claims: list[str]
    price_vnd: int | None = None
    image_url: str | None = None
    aliases: list[str] = field(default_factory=list)

    def claims_block(self) -> str:
        lines = [f"Sản phẩm: {self.short_name} | Số XNQC: {self.xnqc or 'chưa có'}", "Công dụng được phép:"]
        lines += [f"- {c}" for c in self.claims] or ["- (chưa có — không được nêu công dụng)"]
        return "\n".join(lines)


def _short_name(name: str) -> str:
    s = name.strip()
    low = s.lower()
    for p in STRIP_PREFIXES:
        if low.startswith(p):
            s = s[len(p):]
            low = s.lower()
    return s.strip()


def _aliases(short: str) -> list[str]:
    cands = {short}
    low = short.lower()
    for p in STRIP_PREFIXES:
        if low.startswith(p):
            cands.add(short[len(p):])
    for suf in STRIP_SUFFIXES:
        for c in list(cands):
            if c.lower().endswith(suf):
                cands.add(c[: -len(suf)])
    # bỏ alias quá ngắn dễ khớp nhầm
    return sorted({c.strip() for c in cands if len(c.strip()) >= 5}, key=len, reverse=True)


def parse_product(p: dict[str, Any]) -> Product:
    text, _ = html_to_text((p.get("short_description") or "") + "\n" + (p.get("description") or "")[:3000])
    xnqc = re.search(r"XNQC\s*:?\s*([0-9]+\s*/\s*[0-9]{4}\s*/\s*(?:ATTP\s*-\s*)?XNQC(?:\s*-\s*ATTP)?)", text, re.I)
    xncb = re.search(r"XNCB\s*:?\s*([0-9]+\s*/\s*[0-9]{4}\s*/\s*ĐKSP)", text, re.I)
    short_text, _ = html_to_text(p.get("short_description") or "")
    claims: list[str] = []
    for line in short_text.splitlines():
        line = line.strip(" -•\t")
        if fold(line).startswith(tuple(fold(c) for c in CLAIM_STARTS)) and "freeship" not in fold(line):
            claims.append(line.rstrip("."))
    short = _short_name(p.get("name", ""))
    price = None
    prices = p.get("prices") or {}
    if prices.get("price"):
        try:
            price = int(prices["price"]) // (10 ** int(prices.get("currency_minor_unit", 0)))
        except (TypeError, ValueError):
            price = None
    images = p.get("images") or []
    return Product(
        wc_id=int(p.get("id", 0)), name=p.get("name", ""), short_name=short, url=p.get("permalink", ""),
        xnqc=re.sub(r"\s+", "", xnqc.group(1)) if xnqc else None,
        xncb=re.sub(r"\s+", "", xncb.group(1)) if xncb else None, claims=claims,
        price_vnd=price, image_url=images[0]["src"] if images else None, aliases=_aliases(short),
    )


class ClaimsRegistry:
    def __init__(self, products: list[Product]):
        self.products = products

    @classmethod
    def from_wc(cls, raw: list[dict[str, Any]]) -> ClaimsRegistry:
        return cls([parse_product(p) for p in raw])

    @classmethod
    def load(cls, path: Path) -> ClaimsRegistry:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls([Product(**d) for d in data])

    def save(self, path: Path) -> None:
        path.write_text(json.dumps([asdict(p) for p in self.products], ensure_ascii=False, indent=1), encoding="utf-8")

    def detect(self, text: str) -> list[Product]:
        """Tìm sản phẩm được nhắc tới trong văn bản (so khớp không dấu, theo ranh giới từ)."""
        ft = fold(text)
        found: list[Product] = []
        for p in self.products:
            for a in p.aliases:
                if re.search(r"(?<![a-z0-9])" + re.escape(fold(a)) + r"(?![a-z0-9])", ft):
                    found.append(p)
                    break
        return found

    def by_name(self, names: list[str]) -> list[Product]:
        wanted = {fold(n) for n in names}
        return [p for p in self.products if fold(p.short_name) in wanted or fold(p.name) in wanted]
