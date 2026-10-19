# -*- coding: utf-8 -*-
"""开放时间解析：把 spots.json 里的人类可读开放时间，折算成可用的到达窗口。

支持：
  open_hours.periods[] = {days: "Mon-Sun" / "Tue-Sun" / "Mon", open: "09:00", close: "17:00", last_entry: "16:00"}
  open_hours.closed[]  = ["周一（法定节假日除外）", ...]（中文星期，尽力解析）
  periods 为空 = 开放时间未知 → 返回 None，由上层按"全天可去 + 给警告"处理
"""
from __future__ import annotations

_WD = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
_CN_WD = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6,
          "星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3, "星期五": 4, "星期六": 5, "星期日": 6}


def weekday_set(expr):
    out = set()
    for part in str(expr).split(","):
        part = part.strip()
        if "-" in part:
            a, b = [x.strip() for x in part.split("-", 1)]
            if a in _WD and b in _WD:
                i, j = _WD[a], _WD[b]
                out |= set(range(i, j + 1)) if i <= j else set(range(i, 7)) | set(range(0, j + 1))
        elif part in _WD:
            out.add(_WD[part])
    return out


def closed_weekdays(closed):
    out = set()
    for c in closed or []:
        for cn, i in _CN_WD.items():
            if cn in str(c):
                out.add(i)
    return out


def parse_periods(spot, weekday):
    """返回 [(start_min, end_min), ...]；未知返回 None；当日闭馆返回 []。"""
    oh = spot.get("open_hours") or {}
    if weekday in closed_weekdays(oh.get("closed")):
        return []

    periods = oh.get("periods") or []
    if not periods:
        return None

    wins = []
    for p in periods:
        days = weekday_set(p.get("days") or "")
        if days and weekday not in days:
            continue
        try:
            ohh, omm = [int(x) for x in str(p.get("open", "")).split(":")]
            chh, cmm = [int(x) for x in str(p.get("close", "")).split(":")]
        except ValueError:
            continue
        start = ohh * 60 + omm
        close = chh * 60 + cmm
        if close <= start:
            close = 24 * 60
        last = p.get("last_entry")
        if last:
            try:
                lh, lm = [int(x) for x in str(last).split(":")]
                close = min(close, lh * 60 + lm)
            except ValueError:
                pass
        wins.append((start, close))
    return wins or None
