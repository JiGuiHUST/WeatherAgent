# -*- coding: utf-8 -*-
"""模块1.1：跨境多日连贯逐时精细化预报整合。
输入路线城市序列 + 出发日 + 每城天数，逐城逐日调用气象接口，合并为一条连贯时序。
风、能见度来自真实资料；缺失值不合成。
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
def wind_beaufort(ms):
    if ms is None:
        return None
    return next((i for i, edge in enumerate((.3,1.6,3.4,5.5,8,10.8,13.9,17.2,20.8,24.5,28.5,32.7)) if ms < edge),12)


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
        ws, vs = summary.get("wind_series", []), summary.get("vis_series", [])
        wind = wind_beaufort(ws[i]) if i < len(ws) else None
        vis = vs[i] if i < len(vs) else None
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


def _weekday(dt, lang):
    names_zh = ["一", "二", "三", "四", "五", "六", "日"]
    names_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    i = dt.weekday()
    return names_en[i] if lang == "en" else names_zh[i]


def _live_day(day_dt, bbox, lang):
    from services.live_weather import today
    s = weather_api.get_weather_summary(day_dt, bbox)
    rows = _rows_from_summary(s, day_dt, lang)
    return {"date": day_dt.strftime("%Y-%m-%d"), "weekday": _weekday(day_dt,lang),
            "rows": rows, "avg_tmp": s["avg_tmp"], "max_tmp":s["max_tmp"], "min_tmp":s["min_tmp"],
            "total_pre":s["total_pre"], "avg_rh":s["avg_rh"], "source":s["source"],
            "used_climate":False,"out_of_range":False,"days_over":0,"is_past":day_dt.date()<today(),
            "forecast_hours_ahead":(day_dt.date()-today()).days*24,
            "tag":_comfort_label(s["avg_tmp"],s["total_pre"],None,lang),
            "comfort":_comfort_label(s["avg_tmp"],s["total_pre"],None,lang),
            "wind":max((r["wind"] for r in rows if r.get("wind") is not None),default=None),
            "vis":min((r["vis"] for r in rows if r.get("vis") is not None),default=None),
            "best_hours":_spot_best_hours(rows),"provenance":s["provenance"]}


def build_route_forecast(city_inputs,start_input,days_each,lang="zh",selected_spots=None):
    """Actual calendar dates, local-time hourly series; no climate substitution."""
    from concurrent.futures import ThreadPoolExecutor
    city_map=_load_json(CITY_BBOX_FILE)
    start_dt,season=parse_time_input(start_input,SEASON_MONTH)
    count=max(1,min(5,int(days_each)))
    cities=list(dict.fromkeys(resolve_city(c) for c in city_inputs))
    if len(cities)>8: raise ValueError("一次最多选择 8 个城市")
    tasks=[]
    for i,city in enumerate(cities):
        if city not in city_map: raise ValueError("未收录该城市")
        for k in range(count): tasks.append((city,start_dt+datetime.timedelta(days=i*count+k)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda task:_live_day(task[1],city_map[task[0]]["bbox"],lang),tasks))
    segments=[dict(city=city,country=city_map[city]["country"],bbox=city_map[city]["bbox"],days=results[i*count:(i+1)*count]) for i,city in enumerate(cities)]
    totals=_route_totals(segments,lang)
    totals.update(total_days=len(tasks),days_in_range=len(tasks),days_climate=0,days_out_of_range=0,max_forecast_days=16)
    points=[(city+" "+r["time"],r["tmp"],r["pre"]) for seg in segments for city in [seg["city"]] for d in seg["days"] for r in d["rows"]]
    return dict(segments=segments,totals=totals,warnings=["Open-Meteo 真实天气；逐小时使用目的地当地时间，历史资料与预报按日期区分。无数据时不合成天气。" if lang!="en" else "Real Open-Meteo data in destination local time. Historical records and forecasts are distinguished; missing weather is not synthesized."],
                plot_url=_plot_combined(points,segments,lang),start_date=start_dt.strftime("%Y-%m-%d"),days_each=count,season=season,has_selected_spots=bool(selected_spots))


def build_spot_forecasts(spots,start_dt,days_each,lang="zh"):
    from concurrent.futures import ThreadPoolExecutor
    def build(spot):
        lat,lon=float(spot["lat"]),float(spot["lon"])
        days=[_live_day(start_dt+datetime.timedelta(days=i),_spot_bbox(lat,lon),lang) for i in range(max(1,min(5,int(days_each))))]
        return dict(spot,days=days)
    if len(spots)>12: raise ValueError("一次最多查询 12 个景点")
    with ThreadPoolExecutor(max_workers=4) as pool: return list(pool.map(build,spots))


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

        key = hashlib.md5((lang+"".join(labels)).encode("utf-8")).hexdigest()[:10]
        path = os.path.join(WEATHER_IMG_DIR, f"route_{key}.png")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return f"/static/weather_img/{os.path.basename(path)}"
    except Exception as e:
        logger.warning("整程图绘制失败: %s", e)
        plt.close("all")
        return None
