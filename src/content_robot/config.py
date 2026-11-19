"""Cấu hình robot — đọc từ biến môi trường hoặc file .env (không phụ thuộc thư viện ngoài)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = Path.cwd()  # thư mục chạy lệnh: chứa .env và data/


def _load_dotenv(path: Path) -> None:
    """Nạp file .env đơn giản (KEY=VALUE). Biến đã có trong môi trường được giữ nguyên."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, str(default)).lower() in {"1", "true", "yes", "on"}


DEFAULT_BOARDS = {
    "Sức khỏe trẻ em": ["sức khỏe trẻ em", "trẻ em", "children"],
    "Mẹ bầu & sức khỏe phụ nữ": ["phụ nữ mang thai", "sức khỏe phụ nữ", "mãn kinh", "aktiv meno"],
    "Vitamin & khoáng chất": ["vitamin và khoáng chất", "tăng sức đề kháng"],
    "Xương khớp": ["xương khớp"],
    "Làm đẹp từ bên trong": ["làm đẹp", "rụng tóc", "beauty"],
    "Sống khỏe năng động": [],  # bảng mặc định
}


@dataclass
class Settings:
    wp_base_url: str = "https://doppelherz.vn"
    data_dir: Path = ROOT / "data"
    publish_mode: str = "dry_run"  # dry_run | live
    timezone: str = "Asia/Ho_Chi_Minh"

    # AI
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"
    ai_review: bool = True  # gọi thêm AI kiểm duyệt tuân thủ khi có API key

    # Facebook
    fb_page_id: str = ""
    fb_page_token: str = ""
    fb_graph_version: str = "v27.0"

    # Pinterest
    pinterest_token: str = ""
    pinterest_api_base: str = "https://api.pinterest.com/v5"  # sandbox: https://api-sandbox.pinterest.com/v5
    pinterest_boards: dict[str, str] = field(default_factory=dict)  # tên bảng -> board_id

    # Lịch đăng (giờ Việt Nam)
    slots: dict[str, list[str]] = field(
        default_factory=lambda: {"facebook": ["11:30", "20:30"], "pinterest": ["13:00", "21:00"]}
    )
    max_per_day: dict[str, int] = field(default_factory=lambda: {"facebook": 2, "pinterest": 2})
    min_lead_minutes: int = 15

    auto_approve: bool = False
    utm_campaign: str = "content_robot"
    webhook_secret: str = "doi-chuoi-bi-mat-nay"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    repo_url: str = "https://github.com/Bachthutruong/doppelherz-workflow"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "robot.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.media_dir, self.outbox_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(env_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or ROOT / ".env")
    s = Settings(
        wp_base_url=_env("WP_BASE_URL", "https://doppelherz.vn").rstrip("/"),
        data_dir=Path(_env("DATA_DIR", str(ROOT / "data"))),
        publish_mode=_env("PUBLISH_MODE", "dry_run"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        claude_model=_env("CLAUDE_MODEL", "claude-opus-5-5"),
        claude_effort=_env("CLAUDE_EFFORT", "medium"),
        ai_review=_env_bool("AI_REVIEW", True),
        fb_page_id=_env("FB_PAGE_ID"),
        fb_page_token=_env("FB_PAGE_TOKEN"),
        fb_graph_version=_env("FB_GRAPH_VERSION", "v27.0"),
        pinterest_token=_env("PINTEREST_TOKEN"),
        pinterest_api_base=_env("PINTEREST_API_BASE", "https://api.pinterest.com/v5").rstrip("/"),
        pinterest_boards=json.loads(_env("PINTEREST_BOARDS", "{}") or "{}"),
        auto_approve=_env_bool("AUTO_APPROVE", False),
        webhook_secret=_env("WEBHOOK_SECRET", "doi-chuoi-bi-mat-nay"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        repo_url=_env("REPO_URL", "https://github.com/Bachthutruong/doppelherz-workflow"),
    )
    if _env("SLOTS_FACEBOOK"):
        s.slots["facebook"] = [x.strip() for x in _env("SLOTS_FACEBOOK").split(",")]
    if _env("SLOTS_PINTEREST"):
        s.slots["pinterest"] = [x.strip() for x in _env("SLOTS_PINTEREST").split(",")]
    s.ensure_dirs()
    return s
