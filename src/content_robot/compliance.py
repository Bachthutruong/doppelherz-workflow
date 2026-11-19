"""Bộ luật kiểm duyệt tuân thủ quảng cáo TPBVSK (chạy trước khi người duyệt xem bài).

Mức độ:
- block: không được đăng, phải sửa (chữa/trị bệnh, danh nghĩa nhân viên y tế, cam kết tuyệt đối...)
- warn:  người duyệt cần xem kỹ (từ so sánh, công dụng chưa khớp XNQC, vượt độ dài khuyến nghị)
- fixed: lỗi đã được robot tự sửa (thêm câu cảnh báo, số XNQC, UTM)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .claims import Product, fold

DISCLAIMER = "Thực phẩm này không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh."

# (mẫu regex có dấu, mã luật, thông điệp, chỉ chặn khi câu có nhắc sản phẩm?)
BLOCK_PATTERNS: list[tuple[str, str, str, bool]] = [
    (r"chữa (khỏi|bệnh|trị|dứt)", "R2", "Ngụ ý chữa bệnh", False),
    (r"(điều trị|đặc trị|trị dứt|trị khỏi|trị bệnh)", "R2", "Ngụ ý sản phẩm điều trị bệnh", True),
    (r"khỏi (hẳn|bệnh|hoàn toàn)", "R2", "Cam kết khỏi bệnh", True),
    (r"thay thế (cho )?thuốc", "R2", "Ngụ ý thay thế thuốc", False),
    (r"thần dược", "R2", "Từ ngữ cấm: thần dược", False),
    (r"(bác sĩ|dược sĩ|chuyên gia y tế|bệnh viện)[^.\n]{0,20}(khuyên dùng|khuyên nên dùng|chỉ định dùng|tin dùng)", "R3",
     "Dùng danh nghĩa nhân viên y tế để khuyên dùng", False),
    (r"cam kết (hiệu quả|khỏi)", "R4", "Cam kết hiệu quả", False),
    (r"(100\s?%|tuyệt đối an toàn|không (có )?tác dụng phụ)", "R4", "Khẳng định tuyệt đối", False),
    (r"phòng (ngừa|chống) (ung thư|bệnh)", "R2", "Ngụ ý sản phẩm phòng bệnh", True),
]
WARN_PATTERNS: list[tuple[str, str, str, bool]] = [
    (r"(tốt nhất|số 1|số một|duy nhất|hàng đầu|vượt trội|mạnh nhất)", "R4", "Từ so sánh, cần nguồn dẫn chứng", False),
    (r"(nghiên cứu|khoa học chứng minh|đã được chứng minh)", "R6", "Nhắc nghiên cứu — kiểm tra bài gốc có nguồn", False),
]
LIMITS = {
    "facebook": {"body": 2200},
    "pinterest": {"title": 100, "body": 800, "alt_text": 500, "body_recommended": 500},
}


@dataclass
class Issue:
    code: str
    severity: str  # block | warn | fixed
    message: str
    excerpt: str = ""


@dataclass
class ComplianceResult:
    status: str  # pass | warn | block
    issues: list[Issue] = field(default_factory=list)
    text: str = ""

    def as_list(self) -> list[dict]:
        return [asdict(i) for i in self.issues]


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    right_candidates = [x for x in (text.find(".", end), text.find("\n", end)) if x != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left:right].strip()[:180]


def _scan(text: str, patterns: list[tuple[str, str, str, bool]], severity: str,
          skip_spans: list[tuple[int, int]], products: list[Product]) -> list[Issue]:
    low = text.lower()  # giữ nguyên độ dài với tiếng Việt dựng sẵn (NFC)
    aliases = [fold(a) for p in products for a in p.aliases]
    issues: list[Issue] = []
    for pat, code, msg, product_context in patterns:
        for m in re.finditer(r"(?<![\w])" + pat, low):
            if any(s <= m.start() < e for s, e in skip_spans):
                continue
            sent = _sentence_around(text, m.start(), m.end())
            sev = severity
            if product_context and severity == "block" and not any(a in fold(sent) for a in aliases):
                sev = "warn"  # vd. "đưa trẻ đi khám để được điều trị" — không gắn với sản phẩm
                msg_out = msg + " (không gắn với sản phẩm — người duyệt kiểm tra)"
            else:
                msg_out = msg
            issues.append(Issue(code, sev, msg_out, sent))
    return issues


CLAIM_STOPWORDS = {"giup", "ho", "tro", "tang", "cuong", "cai", "thien", "bo", "sung", "cho", "va", "cac", "nhung",
                   "the", "co", "duoc", "hon", "rat", "nhat"}


def _claim_overlap(phrase: str, claims: list[str]) -> float:
    words = {w for w in re.findall(r"[a-z0-9]+", fold(phrase)) if len(w) > 1 and w not in CLAIM_STOPWORDS}
    if not words:
        return 1.0
    best = 0.0
    for c in claims:
        cw = {w for w in re.findall(r"[a-z0-9]+", fold(c)) if len(w) > 1 and w not in CLAIM_STOPWORDS}
        if cw:
            best = max(best, len(words & cw) / len(words))
    return best


def add_utm(url: str, source: str, campaign: str, content: str | None = None) -> str:
    parts = urlparse(url)
    q = dict(parse_qsl(parts.query))
    q.update({"utm_source": source, "utm_medium": "social", "utm_campaign": campaign})
    if content:
        q["utm_content"] = content
    return urlunparse(parts._replace(query=urlencode(q)))


def check(text: str, channel: str, products: list[Product], title: str = "", alt_text: str = "",
          autofix: bool = True) -> ComplianceResult:
    issues: list[Issue] = []
    text, title, alt_text = (unicodedata.normalize("NFC", x or "") for x in (text, title, alt_text))
    out = text.strip()

    # 1) Sản phẩm được nhắc → bắt buộc câu cảnh báo + số XNQC
    if products and autofix:
        if fold(DISCLAIMER) not in fold(out):
            out = f"{out}\n\n{DISCLAIMER}"
            issues.append(Issue("R5", "fixed", "Đã thêm câu bắt buộc \"không phải là thuốc\""))
        for p in products:
            if p.xnqc and p.xnqc not in out:
                out = f"{out}\nSố XNQC {p.short_name}: {p.xnqc}"
                issues.append(Issue("XNQC", "fixed", f"Đã thêm số XNQC của {p.short_name}"))
            if not p.xnqc:
                issues.append(Issue("XNQC", "block", f"{p.short_name} chưa có số XNQC — không được quảng cáo"))

    # Không bắt lỗi trong chính câu cảnh báo bắt buộc
    skip: list[tuple[int, int]] = []
    i = out.lower().find(DISCLAIMER.lower())
    if i >= 0:
        skip.append((i, i + len(DISCLAIMER)))

    full = "\n".join(x for x in (title, out, alt_text) if x)
    offset_skip = [(s + (len(title) + 1 if title else 0), e + (len(title) + 1 if title else 0)) for s, e in skip]
    issues += _scan(full, BLOCK_PATTERNS, "block", offset_skip, products)
    issues += _scan(full, WARN_PATTERNS, "warn", offset_skip, products)

    # 2) Công dụng nêu cạnh tên sản phẩm phải khớp XNQC (xét trên nội dung gốc, trước phần robot tự thêm)
    original = text.strip()
    fo = fold(original)
    for p in products:
        for alias in p.aliases:
            hits = list(re.finditer(re.escape(fold(alias)), fo))
            for m in hits:
                sent = _sentence_around(original, m.start(), m.end())
                for cm in re.finditer(r"(hỗ trợ|giúp|tăng cường|cải thiện|bổ sung)[^,.;\n]{3,80}", sent, flags=re.I):
                    if _claim_overlap(cm.group(0), p.claims) < 0.5:
                        issues.append(Issue("R1", "warn", f"Công dụng chưa khớp XNQC của {p.short_name}", cm.group(0)))
            if hits:
                break  # alias dài nhất đã khớp — không xét alias ngắn hơn để tránh trùng

    # 3) Giới hạn độ dài theo nền tảng
    lim = LIMITS.get(channel, {})
    if len(out) > lim.get("body", 10**6):
        issues.append(Issue("LEN", "block", f"Nội dung dài {len(out)} ký tự, vượt giới hạn {lim['body']}"))
    elif len(out) > lim.get("body_recommended", 10**6):
        issues.append(Issue("LEN", "warn", f"Mô tả {len(out)} ký tự, nên dưới {lim['body_recommended']}"))
    if title and len(title) > lim.get("title", 10**6):
        issues.append(Issue("LEN", "block", f"Tiêu đề {len(title)} ký tự, vượt {lim['title']}"))
    if alt_text and len(alt_text) > lim.get("alt_text", 10**6):
        issues.append(Issue("LEN", "block", f"Alt-text {len(alt_text)} ký tự, vượt {lim['alt_text']}"))
    if channel == "facebook" and len(re.findall(r"#\w+", out)) > 6:
        issues.append(Issue("STYLE", "warn", "Quá 6 hashtag"))

    status = "block" if any(x.severity == "block" for x in issues) else (
        "warn" if any(x.severity == "warn" for x in issues) else "pass")
    return ComplianceResult(status=status, issues=issues, text=out)
