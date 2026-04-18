"""
WordPress 予約投稿の枠（api_poster / reschedule_posts で共有）。

6:00〜23:00・30分刻み固定。1日あたり最大35枠（23:30 はなし）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

# 枠の範囲（23:00 を最終枠とする）
SCHEDULE_FIRST_HOUR = 6
SCHEDULE_LAST_HOUR = 23


def schedule_slots_for_day():
    """1日分の (hour, minute) を時系列で返す（6:00 … 22:30, 23:00）。"""
    slots = []
    for h in range(SCHEDULE_FIRST_HOUR, SCHEDULE_LAST_HOUR):
        for m in (0, 30):
            slots.append((h, m))
    slots.append((SCHEDULE_LAST_HOUR, 0))
    return slots


def is_valid_schedule_slot(hour: int, minute: int) -> bool:
    """--hour / --minute 指定が枠に合致するか。"""
    if hour < SCHEDULE_FIRST_HOUR or hour > SCHEDULE_LAST_HOUR:
        return False
    if minute not in (0, 30):
        return False
    if hour == SCHEDULE_LAST_HOUR and minute != 0:
        return False
    return True


def ceil_to_next_schedule_slot(dt: datetime) -> datetime:
    """
    dt より後の最初の予約枠（厳密に > dt）。
    当日に該当がなければ翌日 6:00。
    """
    dt = dt.replace(second=0, microsecond=0)
    day0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    for h, m in schedule_slots_for_day():
        cand = day0.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand > dt:
            return cand
    next_day = day0 + timedelta(days=1)
    return next_day.replace(
        hour=SCHEDULE_FIRST_HOUR, minute=0, second=0, microsecond=0
    )


def iter_schedule_slots_from(dt: datetime):
    """dt より後の予約枠を時系列で無限に yield（再配置・フォールバック用）。"""
    t = ceil_to_next_schedule_slot(dt)
    while True:
        yield t
        day0 = t.replace(hour=0, minute=0, second=0, microsecond=0)
        nxt = None
        for h, m in schedule_slots_for_day():
            cand = day0.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand > t:
                nxt = cand
                break
        if nxt is not None:
            t = nxt
        else:
            nd = day0 + timedelta(days=1)
            t = nd.replace(
                hour=SCHEDULE_FIRST_HOUR, minute=0, second=0, microsecond=0
            )
