"""Xếp lịch đăng: mỗi kênh có khung giờ vàng và số bài tối đa mỗi ngày (giờ Việt Nam)."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def next_slot(channel: str, taken: list[datetime], now: datetime, slots: dict[str, list[str]],
              max_per_day: dict[str, int], tz: str = "Asia/Ho_Chi_Minh", min_lead_minutes: int = 15,
              horizon_days: int = 30) -> datetime:
    """Trả về khung giờ trống sớm nhất (có múi giờ) sau `now + min_lead`.

    Facebook chỉ cho hẹn giờ trong khoảng 10 phút – 30 ngày, nên mặc định lead 15 phút, tối đa 30 ngày.
    """
    zone = ZoneInfo(tz)
    now = now.astimezone(zone)
    earliest = now + timedelta(minutes=min_lead_minutes)
    taken_local = [t.astimezone(zone) for t in taken]
    times = sorted(slots.get(channel, ["09:00"]))
    cap = max_per_day.get(channel, 2)
    for day in range(horizon_days):
        date = (now + timedelta(days=day)).date()
        used_today = sum(1 for t in taken_local if t.date() == date)
        if used_today >= cap:
            continue
        for hhmm in times:
            h, m = map(int, hhmm.split(":"))
            cand = datetime(date.year, date.month, date.day, h, m, tzinfo=zone)
            if cand < earliest or any(abs((cand - t).total_seconds()) < 60 for t in taken_local):
                continue
            return cand
    raise RuntimeError(f"Không còn khung giờ trống cho {channel} trong {horizon_days} ngày")
