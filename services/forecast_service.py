# -*- coding: utf-8 -*-
"""模块1.1：跨境多日连贯逐时精细化预报整合。
输入路线城市序列 + 出发日 + 每城天数，逐城逐日调用气象接口，合并为一条连贯时序。
风/能见度：API 未直接提供时，依据降水与湿度派生（标注估算），体感综合评分。
"""
import os
import math
import hashlib
import logging
import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from config import CITY_BBOX_FILE, WEATHER_IMG_DIR
from services import weather_api
from services.travel_engine import _load_json, resolve_city
from utils.common import parse_time_input, parse_bbox, DATA_YEAR
from config import SEASON_MONTH

logger = logging.getLogger("forecast_service")

for _f in ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]:
    try:
        matplotlib.rcParams["font.sans-serif"] = [_f]
        matplotlib.rcParams["axes.unicode_minus"] = False
        break
    except Exception:
        pass


# ----------------------------- 派生量 -----------------------------
def _derive_wind(total_pre, hour):
    """由降水估算风力等级（API 无风场时的近似）"""
    base = 2
    rain_factor = min(4, total_pre / 5.0)
    # 午后对流更强
    diurnal = 1.0 if 12 <= hour <= 18 else 0.5
    return round(min(8, base + rain_factor + diurnal), 0)


def _derive_visibility(total_pre, rh, hour):
    """能见度(km)：降水/高湿降低"""
    vis = 20.0
    vis -= min(12, total_pre * 0.6)
    if rh and rh > 85:
        vis -= (rh - 85) * 0.5
    if 4 <= hour <= 7 and rh and rh > 80:  # 晨雾
        vis -= 4
    return round(max(1.0, vis), 1)


def _comfort_label(tmp, pre, wind, lang):
    """体感标签"""
    if tmp is None:
        return "—" if lang == "en" else "—"
    if pre and pre >= 5:
        return "Rainy" if lang == "en" else "多雨"
    if tmp >= 31:
        return "Hot" if lang == "en" else "炎热"
    if tmp >= 28:
        return "Warm" if lang == "en" else "温热"
    if tmp <= 15:
        return "Cool" if lang == "en" else "凉爽"
    if wind and wind >= 5:
        return "Windy" if lang == "en" else "风大"
    return "Pleasant" if lang == "en" else "舒适"


def _synthesize_hourly(avg_tmp, total_pre, avg_rh, date, lang):
    """气候默认值兜底时，按日变化合成 24 小时序列"""
    rows = []
    amp = 3.0  # 日较差半幅
    for h in range(24):
        tmp = round(avg_tmp + amp * math.sin((h - 9) * math.pi / 12), 1)
        # 午后集中降水
        if total_pre > 0:
            pre = round(total_pre * (0.12 if 13 <= h <= 18 else 0.04), 1)
        else:
            pre = 0.0
        rh = int((avg_rh or 75) + 8 * math.cos((h - 3) * math.pi / 12))
        rh = max(40, min(98, rh))
        wind = _derive_wind(total_pre, h)
        vis = _derive_visibility(total_pre, rh, h)
        rows.append({
            "time": f"{date.strftime('%m-%d')} {h:02d}:00",
            "hour": h,
            "tmp": tmp, "pre": pre, "rh": rh, "wind": wind, "vis": vis,
            "comfort": _comfort_label(tmp, pre, wind, lang),
        })
    return rows


def _rows_from_summary(summary, date, lang):
    """从真实接口时间序列构造逐时行（按 API 给出的 times）"""
    times = summary.get("times", [])
    tmp_s = summary.get("tmp_series", [])
    pre_s = summary.get("pre_series", [])
    rh_s = summary.get("rh_series", [])
    n = min(len(times), len(tmp_s)) if tmp_s else 0
    rows = []
    total_pre = summary.get("total_pre", 0) or 0
    for i in range(n):
        t = times[i]
        # 时间可能是 "202401010200" 或 "2024-01-01 02:00" 等
        hh = _extract_hour(t)
        tmp = tmp_s[i]
        pre = pre_s[i] if i < len(pre_s) else 0
        rh = rh_s[i] if i < len(rh_s) else (summary.get("avg_rh") or 75)
        wind = _derive_wind(pre or 0, hh if hh is not None else 12)
        vis = _derive_visibility(pre or 0, rh, hh if hh is not None else 12)
        rows.append({
            "time": _fmt_time(t, date),
            "hour": hh,
            "tmp": tmp, "pre": pre, "rh": int(rh) if rh is not None else None,
            "wind": wind, "vis": vis,
            "comfort": _comfort_label(tmp, pre, wind, lang),
        })
    return rows


def _extract_hour(t):
    if not isinstance(t, str):
        return None
    digits = "".join(ch for ch in t if ch.isdigit())
    if len(digits) >= 10:  # YYYYMMDDHH...
        return int(digits[8:10])
    if ":" in t:
        return int(t.split(":")[0][-2:])
    return None


def _fmt_time(t, date):
    hh = _extract_hour(t)
    if hh is None:
        return str(t)
    return f"{date.strftime('%m-%d')} {hh:02d}:00"


# ----------------------------- 景点级精确预报 -----------------------------
def _spot_bbox(lat, lon, pad=0.05):
    """以 (lat, lon) 为中心构造 ~10km 见方的小 bbox 字符串。"""
    return f"{lon - pad},{lat - pad},{lon + pad},{lat + pad}"


def _spot_best_hours(rows):
    """从逐时行中挑出体感"舒适"且无显著降水的最佳时段，返回文案。"""
    if not rows:
        return ""
    candidates = [r for r in rows
                  if r.get("comfort") in ("Pleasant", "舒适")
                  and (r.get("pre") or 0) < 1
                  and r.get("hour") is not None]
    if not candidates:
        # 退而求其次：取降水量最小时段
        candidates = sorted(rows, key=lambda r: (r.get("pre") or 99, abs((r.get("hour") or 12) - 10)))
        candidates = candidates[:1]
    hours = sorted({r["hour"] for r in candidates if r.get("hour") is not None})
    if not hours:
        return ""
    def _fmt(h):
        return f"{h:02d}:00"
    if len(hours) == 1:
        return _fmt(hours[0])
    # 合并连续小时为区间
    ranges, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h == prev + 1:
            prev = h
        else:
            ranges.append((start, prev))
            start = prev = h
    ranges.append((start, prev))
    return " / ".join(_fmt(s) if s == e else f"{_fmt(s)}-{_fmt(e)}" for s, e in ranges)


def build_spot_forecasts(spots, start_dt, days_each, lang="zh"):
    """为指定景点列表逐日获取精确预报。

    :param spots: list of dict，每个元素形如
                  {"city": "芽庄", "name": "芽庄海滩", "lat": 12.24, "lon": 109.19,
                   "category": "城市海滩", "desc": "...", "weather_tip": "..."}
    :param start_dt: 行程起始 datetime（已映射到 DATA_YEAR）
    :param days_each: 每城停留天数（与主行程保持一致）
    :param lang: "zh" / "en"
    :return: list of dict，每个景点一条
            [{city, name, lat, lon, category, desc, weather_tip, days: [...]}]
    """
    from services.weather_api import check_forecast_availability, nearest_run_time
    from utils.common import to_data_year, data_today
    from services.travel_engine import _mock_weather, _city_bbox

    city_map = _city_bbox()
    trip_run_time = nearest_run_time(data_today())
    today = data_today()
    season = None  # 由首城推导；这里行程级用不上

    results = []
    for spot in spots or []:
        lat = spot.get("lat")
        lon = spot.get("lon")
        if lat is None or lon is None:
            continue
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            continue

        city = spot.get("city") or ""
        bbox_str = _spot_bbox(lat_f, lon_f)
        # 用景点所在城市找气候兜底信息
        city_info = city_map.get(city, {})
        spot_days = []
        cursor = start_dt
        for _ in range(max(1, int(days_each or 1))):
            day_dt = cursor
            fc_info = check_forecast_availability(day_dt, trip_run_time)
            summary = weather_api.get_weather_summary(day_dt, bbox_str)
            used_climate = False
            if summary is None:
                # 用景点所在城市的气候默认值兜底
                _, season_local = parse_time_input(day_dt.strftime("%Y%m%d"), SEASON_MONTH)
                season = season_local or season
                summary = _mock_weather(city_info or {"climate": {}}, season_local or "春季")
                used_climate = True

            avg_tmp = summary.get("avg_tmp")
            total_pre = summary.get("total_pre") or 0
            # 沿用整程的逐时合成 / 提取函数
            if summary.get("times"):
                rows = _rows_from_summary(summary, day_dt, lang)
                if not rows:
                    rows = _synthesize_hourly(avg_tmp, total_pre, summary.get("avg_rh"), day_dt, lang)
            else:
                rows = _synthesize_hourly(avg_tmp, total_pre, summary.get("avg_rh"), day_dt, lang)

            # 体感标签取一个具有代表性的（取白天 09-18 小时区间的众数）
            day_rows = [r for r in rows if r.get("hour") is not None and 9 <= r["hour"] <= 18] or rows
            comfort = day_rows[0]["comfort"] if day_rows else ""

            # 与城市 days 字段保持一致：source 文案、时效字段对齐
            day_source = summary.get("source")
            if used_climate and not day_source:
                day_source = "气候默认值"
            spot_days.append({
                "date": day_dt.strftime("%Y-%m-%d"),
                "weekday": _weekday(day_dt, lang),
                "avg_tmp": avg_tmp,
                "max_tmp": summary.get("max_tmp"),
                "min_tmp": summary.get("min_tmp"),
                "total_pre": round(total_pre, 1),
                "avg_rh": summary.get("avg_rh"),
                "wind": _derive_wind(total_pre, 12),
                "vis": _derive_visibility(total_pre, summary.get("avg_rh") or 78, 12),
                "comfort": comfort,
                "source": day_source,  # "实况" / "预报" / "气候默认值"
                "used_climate": used_climate,
                "forecast_hours_ahead": fc_info["hours_ahead"],
                "is_past": fc_info["is_past"],
                "out_of_range": fc_info["days_over"] > 0,
                "days_over": fc_info["days_over"],
                "best_hours": _spot_best_hours(rows),
            })
            cursor += datetime.timedelta(days=1)

        results.append({
            "city": city,
            "name": spot.get("name") or "",
            "lat": lat_f,
            "lon": lon_f,
            "category": spot.get("category") or "",
            "desc": spot.get("desc") or "",
            "weather_tip": spot.get("weather_tip") or "",
            "days": spot_days,
        })
    return results


# ----------------------------- 主流程 -----------------------------
def build_route_forecast(city_inputs, start_input, days_each, lang="zh", selected_spots=None):
    """
    构建整程连贯逐时气象总览。

    跨境行程若超过 GOWFS 168h 预报时效（7 天）：
      · 超出部分自动使用该城市季节气候默认值
      · 返回 warnings 字段，列出哪些天使用了气候值及原因

    时效判定规则（关键）：
      · 用"今天"的最近 GOWFS 起报时次（trip_run_time：08 / 20 时）作为统一基准
      · 这样 8/17 出发，8/18 起的预报时效基于 8/17 的起报判断
      · 第 8 天起（T+8 天）会正确标记为"超时效"，即使 2024 年同期实况已归档，
        真实出行当天也拿不到对应 GOWFS 预报

    :param selected_spots: 可选，用户在前端通过景点选择对话框勾选的景点列表。
                          元素形如 {"city","name","lat","lon","category","desc","weather_tip"}。
                          传入时会在返回结果中追加 `spot_forecasts` 字段（按景点逐日精确预报）。
    """
    from services.weather_api import (
        check_forecast_availability, MAX_FORECAST_DAYS, nearest_run_time
    )
    from utils.common import to_data_year, data_today

    city_map = _load_json(CITY_BBOX_FILE)
    start_dt, season = parse_time_input(start_input, SEASON_MONTH)

    days_each = max(1, int(days_each or 1))
    segments = []
    cursor = start_dt
    all_points = []  # (label, tmp) for combined plot

    # ===== 行程级共享：基于"今天"的最近起报时次（不是行程首日起报）=====
    trip_run_time = nearest_run_time(data_today())

    # 时效统计
    total_days = 0
    days_in_range = 0      # 有实况/预报（在时效内）
    days_climate = 0       # 使用气候默认值
    days_out_of_range = 0  # 超出预报时效
    first_over_limit = None
    warnings = []          # 用于前端展示的警告列表
    align_notes = set()

    for raw in city_inputs:
        city = resolve_city(raw)
        if not city or city not in city_map:
            continue
        info = city_map[city]
        seg_days = []
        for _d in range(days_each):
            day_dt = cursor
            total_days += 1
            # 判断时效：统一使用 trip_run_time（而不是 day_dt 自己的 run_time）
            fc_info = check_forecast_availability(day_dt, trip_run_time)

            summary = weather_api.get_weather_summary(day_dt, info["bbox"])
            used_climate = False
            out_of_range = fc_info["days_over"] > 0

            if summary is None:
                # 兜底：构造一个最小 summary（气候默认值）
                from services.travel_engine import _mock_weather
                summary = _mock_weather(info, season)
                used_climate = True
                days_climate += 1

            # 超时效：以行程首日 run_time 起算超过 168h（即便有实况存档也要警示真实场景拿不到预报）
            if out_of_range:
                days_out_of_range += 1
                if first_over_limit is None:
                    first_over_limit = {
                        "city": city,
                        "date": day_dt.strftime("%Y-%m-%d"),
                        "days_over": fc_info["days_over"],
                        "run_time": trip_run_time.strftime("%Y-%m-%d %H:%M"),
                        "max_target": (trip_run_time + datetime.timedelta(hours=MAX_FORECAST_DAYS * 24)).strftime("%Y-%m-%d %H:%M"),
                    }
            if not used_climate:
                days_in_range += 1
                if summary.get("warn_observation_align"):
                    align_notes.add(summary["warn_observation_align"])

            if summary.get("times"):
                rows = _rows_from_summary(summary, day_dt, lang)
                if not rows:
                    rows = _synthesize_hourly(summary["avg_tmp"], summary["total_pre"], summary.get("avg_rh"), day_dt, lang)
            else:
                rows = _synthesize_hourly(summary["avg_tmp"], summary["total_pre"], summary.get("avg_rh"), day_dt, lang)

            # 逐时总览展示当天所有可用的格点时次：
            #   · 实况格点：每 6 小时一个时次（02 / 08 / 14 / 20）
            #   · 预报格点：08/20 时起报，时效 3-168h
            # 不再固定从 08:00 起，保留 API 返回的全部当日时次

            # 在每一天数据上携带"数据来源/时效标记"
            day_source = summary.get("source")
            if used_climate and not day_source:
                day_source = "气候值"  # 明确标记是气候默认值
            seg_days.append({
                "date": day_dt.strftime("%Y-%m-%d"),
                "weekday": _weekday(day_dt, lang),
                "rows": rows,
                "avg_tmp": summary.get("avg_tmp"),
                "total_pre": round(summary.get("total_pre") or 0, 1),
                "source": day_source,
                "used_climate": used_climate,
                "forecast_hours_ahead": fc_info["hours_ahead"],
                "out_of_range": fc_info["days_over"] > 0,
                "days_over": fc_info["days_over"],
            })
            for r in rows:
                all_points.append((f"{city} {r['time']}", r["tmp"], r["pre"]))
            cursor += datetime.timedelta(days=1)
        if seg_days:
            segments.append({
                "city": city,
                "country": info["country"],
                "bbox": info["bbox"],
                "days": seg_days,
            })

    # ===== 提前计算 totals 扩展项（供 warnings 文案引用）=====
    totals = _route_totals(segments, lang)
    trip_max_target = trip_run_time + datetime.timedelta(hours=MAX_FORECAST_DAYS * 24)
    totals.update({
        "total_days": total_days,
        "days_in_range": days_in_range,
        "days_climate": days_climate,
        "days_out_of_range": days_out_of_range,
        "max_forecast_days": MAX_FORECAST_DAYS,
        "trip_run_time": trip_run_time.strftime("%Y-%m-%d %H:%M"),
        "trip_max_target": trip_max_target.strftime("%Y-%m-%d %H:%M"),
    })

    # 组装 warnings（供模板渲染的人类可读文案）
    # 说明：days_out_of_range（超时效天数）≠ days_climate（兜底气候值天数），
    #       因为即便超时效，DATA_YEAR 同期的 CRA40 实况存档仍可提供参考值。
    days_oor_with_climate = min(days_climate, days_out_of_range)
    days_oor_with_archive = days_out_of_range - days_oor_with_climate
    days_pure_climate_fallback = days_climate - days_oor_with_climate
    archive_label = f"CRA40 {DATA_YEAR}同期实况存档"

    if lang == "en":
        archive_label_en = f"CRA40 {DATA_YEAR} same-period observation archive"
        if days_out_of_range > 0:
            parts = []
            if days_oor_with_archive:
                parts.append(
                    f"{days_oor_with_archive} day(s) referenced "
                    f"{archive_label_en} (display only; no live GOWFS forecast available on your real travel day)"
                )
            if days_oor_with_climate:
                parts.append(f"{days_oor_with_climate} day(s) used seasonal climate averages because APIs unreachable")
            warnings.append(
                f"⚠️ Exceeded GOWFS max forecast range ({MAX_FORECAST_DAYS} days from trip run "
                f"{totals['trip_run_time']} ~ {totals['trip_max_target']}): "
                + "; ".join(parts) + "."
            )
        if first_over_limit:
            warnings.append(
                f"First out-of-range day: {first_over_limit['city']} {first_over_limit['date']} "
                f"(+{first_over_limit['days_over']}d over limit)."
            )
        if days_pure_climate_fallback > 0:
            warnings.append(
                f"{days_pure_climate_fallback} additional day(s) *within* forecast range fell back to seasonal climate averages "
                f"because observation/forecast APIs unreachable — graceful degradation as designed."
            )
        for note in align_notes:
            warnings.append("ℹ️ Observation hours aligned (CRA40 publishes every 6h: 02/08/14/20).")
    else:
        if days_out_of_range > 0:
            parts = []
            if days_oor_with_archive:
                parts.append(f"{days_oor_with_archive}天展示采用{archive_label}（真实出行当日无法获取对应 GOWFS 预报，仅供参考）")
            if days_oor_with_climate:
                parts.append(f"{days_oor_with_climate}天因接口不可达改用该城市季节气候均值")
            warnings.append(
                f"⚠️ 已超出 GOWFS 预报最大时效（行程起报 {totals['trip_run_time']} 起算 {MAX_FORECAST_DAYS} 天，"
                f"最多至 {totals['trip_max_target']}）："
                + "；".join(parts) + "。"
            )
        if first_over_limit:
            warnings.append(
                f"超时效起始：{first_over_limit['city']} {first_over_limit['date']}（超出 {first_over_limit['days_over']} 天）。"
            )
        if days_pure_climate_fallback > 0:
            warnings.append(
                f"另有 {days_pure_climate_fallback} 天（在预报时效内）因实况/预报接口暂不可达，"
                f"自动降级为该城市季节气候均值，属正常兜底机制。"
            )
        for note in align_notes:
            warnings.append("ℹ️ " + note)
    plot_url = _plot_combined(all_points, segments, lang)
    result = {
        "segments": segments,
        "totals": totals,
        "warnings": warnings,
        "plot_url": plot_url,
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "days_each": days_each,
        "season": season,
        # 景点级精确预报由 /route_spots_async 异步生成（避免阻塞主线段渲染）；
        # 这里保留 selected_spots 引用以便模板判断是否显示骨架屏。
        "has_selected_spots": bool(selected_spots),
    }
    return result


def _weekday(dt, lang):
    names_zh = ["一", "二", "三", "四", "五", "六", "日"]
    names_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    i = dt.weekday()
    return names_en[i] if lang == "en" else names_zh[i]


def _route_totals(segments, lang):
    rainy = hot = pleasant = 0
    for seg in segments:
        for d in seg["days"]:
            for r in d["rows"]:
                if r["pre"] and r["pre"] >= 5:
                    rainy += 1
                if r["tmp"] is not None and r["tmp"] >= 31:
                    hot += 1
                if r["comfort"] in ("Pleasant", "舒适"):
                    pleasant += 1
    return {
        "rainy_hours": rainy,
        "hot_hours": hot,
        "pleasant_hours": pleasant,
    }


def _plot_combined(points, segments, lang):
    """整程温度/降水连贯时间线图

    优化点：
      · 所有城市（含首城/末城）都在图中标注，首城不会被漏掉
      · 城市段用淡色背景区分，城市名在段中央顶部带圆角背景框
      · x 轴显示"MM-DD HH:MM"完整日期时间，不只是时间
    """
    if not points:
        return None
    try:
        labels = [p[0] for p in points]
        tmps = [p[1] if p[1] is not None else np.nan for p in points]
        pres = [p[2] if p[2] is not None else 0 for p in points]
        x = np.arange(len(labels))

        fig, ax1 = plt.subplots(figsize=(14, 5.5), dpi=110)
        ax1.plot(x, tmps, color="#e74c3c", marker="o", markersize=2.5, linewidth=1.4, label="TMP℃",
                 zorder=3)
        ax1.set_ylabel("温度 ℃" if lang != "en" else "Temp ℃", color="#e74c3c")
        ax1.tick_params(axis="y", labelcolor="#e74c3c")
        ax1.set_ylim(bottom=min(np.nanmin(tmps) - 2, 0))

        # ---- 城市分段：计算每段 [start, end) ----
        city_bounds = []
        idx = 0
        for seg in segments:
            n = sum(len(d["rows"]) for d in seg["days"])
            city_bounds.append((idx, idx + n, seg["city"]))
            idx += n

        # 城市段淡色背景 + 分界竖线 + 城市名标注
        band_colors = ["#e3f2fd", "#fff3e0", "#f3e5f5", "#e8f5e9", "#fce4ec",
                       "#e0f7fa", "#fffde7", "#f1f8e9"]
        for i, (start, end, city) in enumerate(city_bounds):
            bg = band_colors[i % len(band_colors)]
            ax1.axvspan(start - 0.5, end - 0.5, alpha=0.35, color=bg, zorder=0)
            if start > 0:
                ax1.axvline(start - 0.5, color="#888", linestyle="--", linewidth=0.8, zorder=1)
            mid = (start + end - 1) / 2.0
            ax1.text(mid, 1.02, city, transform=ax1.get_xaxis_transform(),
                     fontsize=9, ha="center", va="bottom",
                     bbox=dict(boxstyle="round,pad=0.3", facecolor=bg,
                               edgecolor="#666", alpha=0.9, linewidth=0.8))

        # 降水柱
        ax2 = ax1.twinx()
        ax2.bar(x, pres, alpha=0.35, color="#3498db", label="PRE mm", zorder=2, width=0.8)
        ax2.set_ylabel("降水 mm" if lang != "en" else "Precip mm", color="#3498db")
        ax2.tick_params(axis="y", labelcolor="#3498db")

        # x 轴：显示日期 + 时间（MM-DD HH:MM）
        step = max(1, len(labels) // 14)
        tick_idx = list(range(0, len(labels), step))
        tick_labels = []
        for i in tick_idx:
            parts = labels[i].split(" ", 1)
            tick_labels.append(parts[1] if len(parts) > 1 else labels[i][-11:])
        ax1.set_xticks([x[i] for i in tick_idx])
        ax1.set_xticklabels(tick_labels, rotation=45, fontsize=7, ha="right")

        title = "整程连贯气象时间线" if lang != "en" else "Coherent Route Weather Timeline"
        ax1.set_title(title, fontsize=13, pad=28)
        ax1.set_xlim(-0.5, len(labels) - 0.5)
        ax1.grid(axis="y", alpha=0.2, zorder=0)
        fig.tight_layout()

        key = hashlib.md5(("".join(labels)).encode("utf-8")).hexdigest()[:10]
        path = os.path.join(WEATHER_IMG_DIR, f"route_{key}.png")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return f"/static/weather_img/{os.path.basename(path)}"
    except Exception as e:
        logger.warning("整程图绘制失败: %s", e)
        plt.close("all")
        return None
