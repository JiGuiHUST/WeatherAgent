"""Opening, last-entry and departure are separate constraints, in local minutes."""
from __future__ import annotations

_WD = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def weekday_set(expr):
    result = set()
    for part in str(expr).split(","):
        if "-" in part:
            a, b = [s.strip() for s in part.split("-", 1)]
            if a in _WD and b in _WD:
                result.update(i % 7 for i in range(_WD[a], _WD[b] + (7 if _WD[b] < _WD[a] else 0) + 1))
        elif part.strip() in _WD:
            result.add(_WD[part.strip()])
    return result


def minutes(text):
    h, m = map(int, str(text).split(":"))
    if not 0 <= h <= 24 or not 0 <= m < 60 or h == 24 and m != 0:
        raise ValueError("无效时间")
    return h * 60 + m


def periods(spot, weekday):
    raw = (spot.get("open_hours") or {}).get("periods") or []
    if not raw:
        return None
    result = []
    for p in raw:
        days = weekday_set(p.get("days", "Mon-Sun"))
        if days and weekday not in days:
            continue
        try:
            start, end = minutes(p["open"]), minutes(p["close"])
            if end <= start:
                end += 1440
            last = minutes(p["last_entry"]) if p.get("last_entry") else end
            result.append((start, end, last))
        except (KeyError, ValueError, TypeError):
            continue
    return result


def parse_periods(spot, weekday):
    result = periods(spot, weekday)
    return [(a, b) for a, b, last in result] if result is not None else None
