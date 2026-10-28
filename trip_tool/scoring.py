# -*- coding: utf-8 -*-
"""景点适宜度评分：完全由「类型模板」里的阈值驱动，代码里不含气象常识。

因子名（与 weather.HourRecord 的键一致）：
    precip precip_prob apparent_temp wind10_speed wind_gusts visibility uv_index thunder aqi

模板结构：
    {"sensitivity": {"precip": {"weight": 3, "good": "0", "bad": ">=0.5", "basis": "..."}}}

预留接口
--------
    class MyScorer:
        def score(self, spot, template, hour) -> tuple[int, list[dict]]
    # 以后想换成"训练出来的满意度模型"，实现这个接口再 hooks.set_scorer() 即可。
"""
from __future__ import annotations

import re

FACTORS = ("precip", "precip_prob", "apparent_temp", "wind10_speed", "wind_gusts",
           "visibility", "uv_index", "thunder", "aqi")

FACTOR_LABEL = {
    "precip": "降水", "precip_prob": "降水概率", "apparent_temp": "体感温度",
    "wind10_speed": "风速", "wind_gusts": "阵风", "visibility": "能见度",
    "uv_index": "紫外线", "thunder": "雷暴", "aqi": "空气质量",
}

PENALTY = {"good": 0, "ok": 4, "bad": 14}   # 再乘 weight(0-3)

_RANGE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)$")


def _norm_expr(expr):
    s = str(expr).strip().lower()
    for a, b in (("≥", ">="), ("≤", "<="), ("＞", ">"), ("＜", "<"), ("，", "|")):
        s = s.replace(a, b)
    return s.replace(" 或 ", "|").replace(" or ", "|").replace(",", "|")


def _match_one(v, token):
    token = token.strip()
    if not token:
        return False
    if token in ("true", "false"):
        return bool(v) is (token == "true")
    for op in (">=", "<=", ">", "<"):
        if token.startswith(op):
            try:
                x = float(token[len(op):])
            except ValueError:
                return False
            return {">=": v >= x, "<=": v <= x, ">": v > x, "<": v < x}[op]
    m = _RANGE.match(token)
    if m:
        return float(m.group(1)) <= v <= float(m.group(2))
    try:
        return abs(float(token) - float(v)) < 1e-9
    except (TypeError, ValueError):
        return False


def match(v, expr):
    if expr is None or v is None:
        return False
    if isinstance(v, bool):
        return any(_match_one(v, t) for t in _norm_expr(expr).split("|") if t.strip())
    try:
        v = float(v)
    except (TypeError, ValueError):
        return False
    return any(_match_one(v, t) for t in _norm_expr(expr).split("|") if t.strip())


def verdict(v, good, bad):
    """'bad' / 'good' / 'ok'。

    只写了 bad 的因子（如 thunder: bad=true）语义是「没命中 bad 就是好」，
    否则 thunder=False 会被判成"可接受"并被扣分。
    """
    if bad is not None and match(v, bad):
        return "bad"
    if good is None:
        return "good"
    return "good" if match(v, good) else "ok"


def severity(hour):
    """天气恶劣度 0-1，用于给"对天气不敏感"的场所（室内）在坏天气里加权。"""
    s = 0.0
    s = max(s, min(1.0, (hour.get("precip") or 0) / 2.0))
    s = max(s, min(1.0, (hour.get("precip_prob") or 0) / 100.0 * 0.9))
    if hour.get("thunder"):
        s = max(s, 1.0)
    t = hour.get("apparent_temp")
    if t is not None:
        if t >= 33 or t <= 3:
            s = max(s, 0.9)
        elif t >= 30 or t <= 8:
            s = max(s, 0.5)
    s = max(s, min(1.0, max(0.0, ((hour.get("wind10_speed") or 0) - 5.5) / 3.0)))
    s = max(s, min(1.0, max(0.0, ((hour.get("uv_index") or 0) - 6) / 5.0)))
    return round(s, 3)


class TemplateScorer:
    """默认评分器：模板阈值 + 权重。"""

    def score(self, spot, template, hour):
        sens = dict((template or {}).get("sensitivity") or {})
        sens.update(spot.get("sensitivity_overrides") or {})

        active = [f for f in FACTORS if (sens.get(f, {}).get("weight") or 0) > 0]
        if not active:
            # 对天气不敏感（室内等）：好天气 70 分、极端天气 100 分。
            # 下限不能低于 SUIT_MIN（60），否则数据里缺模板时所有景点都会因"无适宜时段"被丢弃。
            if not template:
                return 0, [{"factor": "template", "label": "类型模板", "verdict": "unknown", "value": None}]
            return int(round(78 + 15 * severity(hour))), []

        score, hits = 100.0, []
        for f in active:
            cfg = sens[f]
            v = hour.get(f)
            if v is None:
                score -= 8 * (cfg.get("weight") or 0)
                hits.append({"factor": f, "label": FACTOR_LABEL.get(f, f),
                             "value": None, "verdict": "unknown", "bad_threshold": cfg.get("bad")})
                continue
            w = cfg.get("weight") or 0
            vd = verdict(v, cfg.get("good"), cfg.get("bad"))
            score -= PENALTY[vd] * w
            if vd != "good":
                hits.append({"factor": f, "label": FACTOR_LABEL.get(f, f),
                             "value": v, "verdict": vd, "bad_threshold": cfg.get("bad")})
        return max(0, min(100, int(round(score)))), hits


DEFAULT_SCORER = TemplateScorer()

# 数据里没有该景点类型时使用的模板：所有因子权重 0 → 视为对天气不敏感
FALLBACK_TEMPLATE = {"sensitivity": {}}
