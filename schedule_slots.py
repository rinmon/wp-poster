"""
WordPress 予約投稿の枠（api_poster / reschedule_posts で共有）。

5:00〜24:00・1時間刻み固定。24:00 は翌暦日 00:00:00 として表現する。
1日あたり最大20枠（5,6,…,23時の正時＋翌0:00）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

# 同一暦日内の最初・最後の「時」枠（24:00 は slot_to_datetime の days_after=1 で表す）
SCHEDULE_FIRST_HOUR = 5
SCHEDULE_LAST_HOUR_SAME_CALENDAR_DAY = 23


def schedule_slots_for_day():
    """
    1日分の枠を (hour, minute, days_after_day0) で返す。
    days_after_day0 は day0（その日 0:00）からの日付オフセット。
    最後の (0, 0, 1) は翌日 0:00 = 当日 24:00 相当の枠。
    """
    slots = []
    for h in range(SCHEDULE_FIRST_HOUR, SCHEDULE_LAST_HOUR_SAME_CALENDAR_DAY + 1):
        slots.append((h, 0, 0))
    slots.append((0, 0, 1))
    return slots


def slot_to_datetime(day0: datetime, hour: int, minute: int, days_after_day0: int) -> datetime:
    """day0 をその日 0:00 に正規化したうえで、枠の絶対時刻を返す。"""
    base = day0.replace(hour=0, minute=0, second=0, microsecond=0)
    base = base + timedelta(days=days_after_day0)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def is_valid_schedule_slot(hour: int, minute: int) -> bool:
    """--hour / --minute 指定が枠に合致するか。hour=24 は翌 0:00 枠（24:00、分は0のみ）。"""
    if not (0 <= minute <= 59):
        return False
    if hour == 24:
        return minute == 0
    return SCHEDULE_FIRST_HOUR <= hour <= SCHEDULE_LAST_HOUR_SAME_CALENDAR_DAY


def ceil_to_next_schedule_slot(dt: datetime) -> datetime:
    """
    dt より後の最初の予約枠（厳密に > dt）。
    当日に該当がなければ翌日の最初の枠（5:00）。
    """
    dt = dt.replace(second=0, microsecond=0)
    day0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    for hour, minute, dadd in schedule_slots_for_day():
        cand = slot_to_datetime(day0, hour, minute, dadd)
        if cand > dt:
            return cand
    next_day0 = day0 + timedelta(days=1)
    h0, m0, d0 = schedule_slots_for_day()[0]
    return slot_to_datetime(next_day0, h0, m0, d0)


def iter_schedule_slots_from(dt: datetime):
    """dt より後の予約枠を時系列で無限に yield（再配置・フォールバック用）。"""
    t = ceil_to_next_schedule_slot(dt)
    while True:
        yield t
        day0 = t.replace(hour=0, minute=0, second=0, microsecond=0)
        nxt = None
        for hour, minute, dadd in schedule_slots_for_day():
            cand = slot_to_datetime(day0, hour, minute, dadd)
            if cand > t:
                nxt = cand
                break
        if nxt is not None:
            t = nxt
        else:
            nd = day0 + timedelta(days=1)
            h0, m0, d0 = schedule_slots_for_day()[0]
            t = slot_to_datetime(nd, h0, m0, d0)
