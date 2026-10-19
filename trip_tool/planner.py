# -*- coding: utf-8 -*-
"""行程规划主流程：输入一个日期 → 取天气 → 算适宜度 → 排顺序 → 出行程。

对外只有两个函数：
    plan(request: dict) -> dict        智能体/HTTP 用（字段见 contract.py）
    plan_trip(date, **opts) -> dict    代码内调用（关键字参数更顺手）

依赖全部可替换，见 hooks.py。
"""
from __future__ import annotations

import datetime as _dt
import logging
import time

from . import datasource, hooks, opening, routing, scoring
from .solver import pick_solver
from .geo import amap_nav_url

logger = logging.getLogger("trip_tool.planner")

SUIT_MIN = 60          # 绝对适宜度下限
REL_BAND = 10          # 相对带宽：只接受接近当日最佳的时次（peak - REL_BAND）
DEFAULT_STAY_MIN = 90
DEFAULT_START = {"name": "武汉市中心（洪山广场）", "lat": 30.5506, "lon": 114.3366, "time": "09:00"}
PEAK_HOUR_FROM, PEAK_HOUR_TO = 8, 20

_TYPE_HINTS = {
    "indoor": "室内 博物馆 展馆 避雨 避暑",
    "elevated_view": "登高 远眺 观景 夜景",
    "waterside_open": "江滩 湖 水景 散步",
    "mountain_forest": "山 森林 徒步 自然",
    "flower": "赏花 樱花 花海 拍照",
    "city_park": "公园 绿地 休闲 亲子",
    "street_semi_outdoor": "街区 夜市 小吃 逛街 美食",
    "temple": "寺庙 人文 古建 祈福",
    "theme_park": "乐园 亲子 游乐",
}


# ---------------------------------------------------------------- 小工具
def _hm(text, default):
    try:
        h, m = [int(x) for x in str(text or "").split(":")]
        return h * 60 + m
    except ValueError:
        return default


def _today():
    clock = hooks.get("clock")
    return clock() if clock else _dt.date.today()


def _stay_minutes(spot):
    h = (spot.get("features") or {}).get("typical_duration_h")
    try:
        return int(round(float(h) * 60)) if h else DEFAULT_STAY_MIN
    except (TypeError, ValueError):
        return DEFAULT_STAY_MIN


def _resolve_ids(items, spots):
    out, unknown = [], []
    for it in items or []:
        if it in spots:
            out.append(it)
            continue
        hit = next((sid for sid, s in spots.items() if s.get("name") == it), None)
        if hit:
            out.append(hit)
        else:
            unknown.append(it)
    return out, unknown


def _pref_bonus(spot, prefs):
    """偏好匹配：命中即加分（只影响候选排序，不影响适宜度分数）。"""
    if not prefs:
        return 0
    blob = " ".join([spot.get("name", ""), spot.get("notes", "") or "",
                     spot.get("type", ""), _TYPE_HINTS.get(spot.get("type"), "")])
    hits = sum(1 for p in prefs if p and p in blob)
    return min(15, hits * 8)


# ---------------------------------------------------------------- 评分与窗口
def score_hour(spot, template, hour, scorer=None):
    return (scorer or hooks.get("scorer") or scoring.DEFAULT_SCORER).score(spot, template, hour)


def day_peak(spot, template, hours, scorer=None):
    best, best_h = -1, None
    for r in hours:
        if not (PEAK_HOUR_FROM <= r["hour"] <= PEAK_HOUR_TO):
            continue
        s, _ = score_hour(spot, template, r, scorer)
        if s > best:
            best, best_h = s, r["hour"]
    return best, best_h


def build_window(spot, template, hours, weekday, day_start, day_end, stay,
                 suit_min=SUIT_MIN, rel_band=REL_BAND, scorer=None):
    """返回 {windows: [(lo, hi, peak)], peak, closed, note}。

    规则：先取「该景点当日最佳适宜度 - rel_band」为阈值，
    找出达标的**连续**小时段（不跨低谷合并），再与开放时间求交。
    """
    opens = opening.parse_periods(spot, weekday)
    if opens == []:
        return {"windows": [], "peak": 0, "closed": True, "note": "当日闭馆"}

    scored = [(r["hour"], score_hour(spot, template, r, scorer)[0])
              for r in hours if day_start - 60 <= r["hour"] * 60 <= day_end]
    if not scored:
        return {"windows": [], "peak": 0, "closed": False, "note": "无可用时次"}

    peak_all = max(s for _, s in scored)
    thr = max(suit_min, peak_all - rel_band)
    ok = [(h, s) for h, s in scored if s >= thr]
    if not ok:
        return {"windows": [], "peak": peak_all, "closed": False,
                "note": "当日无适宜时段（峰值 %d）" % peak_all}

    runs, cur = [], [ok[0]]
    for node in ok[1:]:
        if node[0] == cur[-1][0] + 1:
            cur.append(node)
        else:
            runs.append(cur)
            cur = [node]
    runs.append(cur)

    best = max(runs, key=lambda run: sum(s for _, s in run) / len(run))
    peak = max(s for _, s in best)
    h_from, h_to = best[0][0], best[-1][0]

    wins = []
    for (a, b) in (opens if opens else [(0, 24 * 60)]):
        lo = max(a, h_from * 60, day_start)
        run_end = (h_to + 1) * 60
        hi = min(run_end, b - stay, day_end)
        if hi < lo:
            if lo <= run_end and lo + stay <= max(b, day_end):
                hi = lo      # 窗口比停留还短：允许整点到达，只要待得下
            else:
                continue
        wins.append((lo, hi, peak))
    if not wins:
        return {"windows": [], "peak": peak, "closed": False, "note": "开放时间与适宜时段无重叠"}
    return {"windows": wins, "peak": peak, "closed": False,
            "note": "适宜时段 %02d:00-%02d:00" % (h_from, h_to + 1)}


# ---------------------------------------------------------------- 候选筛选
def select_candidates(spots, templates, start, hours, *, radius=30, districts=None,
                      month=None, must=(), avoid=(), prefs=(), scorer=None):
    tpls = templates.get("templates") or {}
    picked = []
    for sid, s in spots.items():
        if sid in avoid:
            continue
        if districts and s.get("district") not in districts and sid not in must:
            continue
        d = routing.haversine_km(start["lat"], start["lon"], s["lat"], s["lon"])
        if d > radius and sid not in must:
            continue
        bm = s.get("best_months") or []
        if month and bm and month not in bm and sid not in must:
            continue
        tpl = tpls.get(s.get("type")) or scoring.FALLBACK_TEMPLATE
        peak, peak_h = day_peak(s, tpl, hours, scorer)
        picked.append({"spot": s, "template": tpl, "dist_km": round(d, 1),
                       "peak": peak, "peak_hour": peak_h, "must": sid in must,
                       "bonus": _pref_bonus(s, prefs)})

    picked.sort(key=lambda x: (not x["must"], -(x["peak"] + x["bonus"]), x["dist_km"]))
    return _diversify(picked, per_type=2)


def _diversify(pool, per_type=2):
    """同一类型最多留 per_type 个——否则按分数排会塞进四条步行街。"""
    head, tail, cnt = [], [], {}
    for p in pool:
        t = p["spot"].get("type")
        if not p["must"] and cnt.get(t, 0) >= per_type:
            tail.append(p)
            continue
        cnt[t] = cnt.get(t, 0) + 1
        head.append(p)
    return head + tail


# ---------------------------------------------------------------- 天气
def resolve_weather(lat, lon, date_iso, districts, warnings, injected=None):
    """注入 > 自定义 provider > Open-Meteo > 气候值，逐级降级并留痕。

    injected 用于离线回放与单测：直接把逐时数组塞进请求即可，结果完全可复现。
    """
    if injected:
        return injected, "injected"
    provider = hooks.get("weather_provider")
    if provider is not None:
        try:
            return provider.hourly(lat, lon, date_iso), provider.describe().get("kind", "custom")
        except Exception as e:
            warnings.append("自定义天气源失败（%s），改用默认源。" % type(e).__name__)
    try:
        from .weather import OpenMeteoProvider
        return OpenMeteoProvider().hourly(lat, lon, date_iso), "open-meteo"
    except Exception as e:
        warnings.append("实时天气获取失败（%s），已用该区季节气候值兜底。" % type(e).__name__)
        from .weather import ClimatologyProvider
        return ClimatologyProvider(districts).hourly(lat, lon, date_iso), "climatology"


def day_brief(hours, source):
    if not hours:
        return {"source": source}
    pre = [r.get("precip") or 0 for r in hours]
    rain = [r["hour"] for r in hours if (r.get("precip") or 0) >= 0.5]
    feels = [r["apparent_temp"] for r in hours if r.get("apparent_temp") is not None]
    return {
        "source": source,
        "precip_total_mm": round(sum(pre), 1),
        "precip_max_mm": round(max(pre), 1),
        "rain_start": min(rain) if rain else None,
        "rain_end": max(rain) if rain else None,
        "feels_max": round(max(feels), 1) if feels else None,
        "thunder": any(r.get("thunder") for r in hours),
    }


def _reason(spot, hour, hits):
    bits = []
    if hour.get("thunder"):
        bits.append("雷暴时段")
    if (hour.get("precip") or 0) >= 0.5:
        bits.append("降水 %.1f mm/h" % hour["precip"])
    elif (hour.get("precip_prob") or 0) >= 70:
        bits.append("降水概率 %d%%" % hour["precip_prob"])
    t = hour.get("apparent_temp")
    if t is not None and t >= 30:
        bits.append("体感 %.0f℃" % t)
    if (hour.get("wind10_speed") or 0) >= 8:
        bits.append("风速 %.1f m/s" % hour["wind10_speed"])
    if (hour.get("visibility") or 99) < 5:
        bits.append("能见度 %.1f km" % hour["visibility"])

    typ = spot.get("type")
    if typ == "indoor":
        tail = "室内场馆，恶劣天气下的稳定选择"
    elif typ == "elevated_view":
        tail = "登高远眺，能见度好时视野最佳"
    elif typ == "waterside_open":
        tail = "临水开阔，风大时体感偏冷"
    elif typ == "street_semi_outdoor":
        tail = "街区可边逛边避雨"
    elif typ == "flower":
        tail = "赏花地，花期与天气共同决定体验"
    else:
        tail = "按类型模板评估"
    return "%s；%s" % ("、".join(bits) if bits else "天气条件良好", tail)


# ---------------------------------------------------------------- 主流程
def plan(request=None, **kwargs):
    req = dict(request or {})
    req.update({k: v for k, v in kwargs.items() if v is not None})
    return plan_request(req)


def plan_trip(date, **kwargs):
    kwargs["date"] = date
    return plan_request(kwargs)


def plan_request(req):
    t0 = time.time()
    warnings = []

    date_iso = str(req.get("date") or _today().isoformat())[:10]
    try:
        d0 = _dt.date.fromisoformat(date_iso)
    except ValueError:
        return {"ok": False, "error": "date 必须是 YYYY-MM-DD，收到：%r" % req.get("date")}

    n_days = max(1, min(5, int(req.get("days") or 1)))
    transport = req.get("transport") or "mixed"
    max_spots = max(1, min(8, int(req.get("max_spots") or 4)))
    suit_min = int(req.get("suit_min") or SUIT_MIN)
    rel_band = int(req.get("rel_band") if req.get("rel_band") is not None else REL_BAND)

    start = dict(DEFAULT_START)
    start.update({k: v for k, v in (req.get("start") or {}).items() if v is not None})
    day_start = _hm(start.get("time"), 9 * 60)
    day_end = _hm(req.get("end_by"), 20 * 60 + 30)

    # ---- 数据 ----
    source = hooks.get("spot_source")
    if source is not None:
        spots = source.load_spots()
        templates = source.load_type_templates()
        districts = source.load_districts()
        meta = {"source": source.describe(), "warnings": []}
    else:
        spots, templates, districts, meta = datasource.load(req.get("data_dir"))
    warnings.extend(meta.get("warnings") or [])

    scorer = hooks.get("scorer")
    must, miss_must = _resolve_ids(req.get("must_visit"), spots)
    avoid, miss_avoid = _resolve_ids(req.get("avoid"), spots)
    if miss_must:
        warnings.append("未识别的必去景点：%s" % "、".join(miss_must))
    if miss_avoid:
        warnings.append("未识别的排除景点：%s" % "、".join(miss_avoid))

    prefs = [str(p) for p in (req.get("preferences") or [])]
    districts_filter = set(req.get("districts") or [])
    matrix = hooks.get("matrix_provider") or routing.DEFAULT_MATRIX
    solver = pick_solver(hooks.get("solver"))
    injected = (req.get("weather") or {}).get("hours")

    visited, plan_days = set(), []

    for k in range(n_days):
        dcur = d0 + _dt.timedelta(days=k)
        dstr = dcur.isoformat()
        hours, wx_source = resolve_weather(start["lat"], start["lon"], dstr, districts,
                                           warnings, injected=injected)
        brief = day_brief(hours, wx_source)

        pool = select_candidates(spots, templates, start, hours,
                                 radius=float(req.get("max_radius_km") or 30),
                                 districts=districts_filter or None, month=dcur.month,
                                 must=set(must), avoid=set(avoid), prefs=prefs, scorer=scorer)
        pool = [p for p in pool if p["spot"]["id"] not in visited]
        if not pool:
            warnings.append("%s 没有符合条件的候选景点（半径/行政区/月份/排除项过滤后）。" % dstr)
            break

        nodes = [{"lat": start["lat"], "lon": start["lon"], "name": start.get("name", "起点")}]
        stays, windows, notes = [0], {}, {}
        for p in pool[:max(max_spots * 3, 8)]:
            s = p["spot"]
            stay = _stay_minutes(s)
            w = build_window(s, p["template"], hours, dcur.weekday(), day_start, day_end, stay,
                             suit_min=suit_min, rel_band=rel_band, scorer=scorer)
            notes[s["id"]] = w["note"]
            if not w["windows"]:
                continue
            best = max(w["windows"], key=lambda x: x[2])
            nodes.append({"lat": s["lat"], "lon": s["lon"], "name": s.get("name", s["id"])})
            stays.append(stay)
            windows[len(nodes) - 1] = best
        if len(nodes) == 1:
            warnings.append("%s 没有任何景点落在可安排时段内。" % dstr)
            break

        mins, km, modes = routing.with_fallback(matrix, nodes, transport, warnings)
        order, dropped_idx = solver.solve({
            "n": len(nodes), "mins": mins, "stay": stays, "windows": windows,
            "day_start": day_start, "day_end": day_end, "max_spots": max_spots,
        })

        stops, prev, total_km, total_min = [], 0, 0.0, 0
        for seq, (i, arr) in enumerate(order, 1):
            node = nodes[i]
            sid = next((pid for pid, p in spots.items() if p.get("name") == node["name"]), None)
            spot = spots.get(sid) or {}
            hour = next((r for r in hours if r["hour"] == arr // 60), hours[0])
            tpl = (templates.get("templates") or {}).get(spot.get("type")) or scoring.FALLBACK_TEMPLATE
            sc, hits = score_hour(spot, tpl, hour, scorer)
            leg_min, leg_km, mode = mins[prev][i], km[prev][i], modes[prev][i]
            total_min += leg_min
            total_km += leg_km
            stops.append({
                "seq": seq, "spot_id": sid, "name": node["name"],
                "type": spot.get("type"), "exposure": spot.get("exposure"),
                "district": spot.get("district"),
                "arrive": "%02d:%02d" % (arr // 60, arr % 60),
                "leave": "%02d:%02d" % ((arr + stays[i]) // 60, (arr + stays[i]) % 60),
                "stay_min": stays[i], "suitability": sc,
                "weather_at_arrival": {kk: hour.get(kk) for kk in
                                       ("hour", "precip", "precip_prob", "apparent_temp",
                                        "wind10_speed", "visibility", "uv_index", "thunder")},
                "reason": _reason(spot, hour, hits),
                "leg": {"from": "起点" if seq == 1 else stops[-1]["name"],
                        "km": round(leg_km, 2), "min": leg_min, "transport": mode,
                        "nav_url": amap_nav_url(node["lon"], node["lat"], node["name"], mode)},
                "lat": node["lat"], "lon": node["lon"],
            })
            visited.add(sid)
            prev = i

        dropped = []
        for i in dropped_idx or []:
            sid = next((pid for pid, p in spots.items() if p.get("name") == nodes[i]["name"]), None)
            dropped.append({"spot_id": sid, "name": nodes[i]["name"],
                            "why": notes.get(sid) or "时间/开放时段排不下"})

        plan_days.append({
            "date": dstr, "weekday": "周" + "一二三四五六日"[dcur.weekday()],
            "weather": brief, "stops": stops, "dropped": dropped,
            "totals": {"spot_count": len(stops), "travel_km": round(total_km, 1),
                       "travel_min": total_min,
                       "end_time": stops[-1]["leave"] if stops else None},
        })

    return {
        "ok": bool(plan_days),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "city": req.get("city") or "武汉",
        "data": {"spots": len(spots), "templates": len((templates.get("templates") or {})),
                 "source": meta.get("source")},
        "solver": solver.name,
        "request": {"date": date_iso, "days": n_days, "transport": transport,
                    "max_spots": max_spots, "start": start},
        "days": plan_days,
        "warnings": warnings,
        "summary_text": summary_text(plan_days),
    }


def summary_text(plan_days):
    if not plan_days:
        return "没有生成可行行程。"
    lines = []
    for d in plan_days:
        w = d["weather"]
        head = "%s（%s）" % (d["date"], d["weekday"])
        if w.get("rain_start") is not None:
            head += "，降水 %.1f mm，%02d–%02d 时有雨" % (
                w["precip_total_mm"], w["rain_start"], (w["rain_end"] or 0) + 1)
        else:
            head += "，全天无降水"
        if w.get("feels_max") is not None:
            head += "，体感最高 %.0f℃" % w["feels_max"]
        lines.append(head + "。建议顺序：")
        for s in d["stops"]:
            lines.append("  %d. %s %s（停留 %d 分钟，适宜度 %d）：%s"
                         % (s["seq"], s["arrive"], s["name"], s["stay_min"], s["suitability"], s["reason"]))
        if d["dropped"]:
            lines.append("  未安排：%s" % "、".join(x["name"] for x in d["dropped"]))
        lines.append("  合计交通 %d 分钟 / %.1f 公里，%s 结束。"
                     % (d["totals"]["travel_min"], d["totals"]["travel_km"], d["totals"]["end_time"]))
    return "\n".join(lines)
