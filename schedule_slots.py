"""
WordPress 予約投稿の枠（api_poster / reschedule_posts で共有）。

0:00〜22:00・2時間刻み正時で固定（0,2,4,…,22）。1日あたり最大12枠。
日付をまたぐ「24:00」枠は置かない（深夜0:00の予約は「翌日0:00」枠を使う）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

# 同一暦日: 0,2,4,…,22 時 正時
SCHEDULE_HOURS_SAME_DAY = tuple(range(0, 24, 2))  # (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22)

# --hour として解釈可能な整数（上記と同じ）
SCHEDULE_HOURS_CLI = SCHEDULE_HOURS_SAME_DAY


def schedule_slots_for_day():
    """
    1日分の枠を (hour, minute, days_after_day0) で返す。
    days_after_day0 は day0（その日 0:00）からの日付オフセット（本定義では常に 0 のみ）。
    """
    return [(h, 0, 0) for h in SCHEDULE_HOURS_SAME_DAY]


def slot_to_datetime(day0: datetime, hour: int, minute: int, days_after_day0: int) -> datetime:
    """day0 をその日 0:00 に正規化したうえで、枠の絶対時刻を返す。"""
    base = day0.replace(hour=0, minute=0, second=0, microsecond=0)
    base = base + timedelta(days=days_after_day0)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def is_valid_schedule_slot(hour: int, minute: int) -> bool:
    """--hour / --minute 指定が枠に合致するか。0,2,…,22 の正時のみ（分は0）。"""
    if not (0 <= minute <= 59):
        return False
    if hour in SCHEDULE_HOURS_SAME_DAY:
        return minute == 0
    return False


def ceil_to_next_schedule_slot(dt: datetime) -> datetime:
    """
    dt より後の最初の予約枠（厳密に > dt）。
    当日に該当がなければ翌日の最初の枠（0:00）。
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
