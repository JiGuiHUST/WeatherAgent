# -*- coding: utf-8 -*-
"""气象接口封装：基于 notebook 中的实况 / 3小时预报接口。
统一对外暴露 get_weather_summary()，返回日均温度、累计降水、时间序列等。
API 不可达时自动降级返回 None，由 travel_engine 用气候默认值兜底。

接口规格（重要）：
  /api/v1/forecasts/3h  —— GOWFS 三小时预报格点
      · 起报时次：每日 08 时、20 时（北京时间）
      · 预报时效：3h ~ 168h（即 7 天）；超出范围需提示用户降级使用气候值
  /api/v1/observations  —— CRA40 实况格点
      · 分辨率：0.25° 等经纬度网格
      · 时次频率：每 6 小时一个时次（02 / 08 / 14 / 20 时）
"""
import logging
import requests
import numpy as np
from datetime import timedelta

from config import BASE_URL, HEADERS
from utils.common import parse_bbox, fmt_14, nearest_run_time, fmt_display, to_data_year
from utils.cache import weather_cache

logger = logging.getLogger("weather_api")

_VARIABLES = "TMP,PRE,RH"
_TIMEOUT = 60

# GOWFS 3h 预报最大时效（小时）与对应天数
MAX_FORECAST_HOURS = 168
MAX_FORECAST_DAYS = MAX_FORECAST_HOURS // 24  # 7 天

# CRA40 实况合法时次（每 6 小时）：02 / 08 / 14 / 20
_OBSERVATION_HOURS = (2, 8, 14, 20)


# ----------------------------- 时效校验工具 -----------------------------

def check_forecast_availability(target_dt, run_dt=None):
    """
    检查目标时间是否在 GOWFS 预报时效内（≤ 起报时间 + 168h）。

    时效基准（关键）：
      · 默认用"今天"的最近起报时间（08 / 20 时）作为 run_dt，而不是 target_dt 自己的起报时间。
      · 这样用户输入未来出行日期时，判断的是"相对于今天的预报时效"，符合真实场景：
        今天 = 8/17，用户出行 8/18 → T+1天，在 7 天预报内 ✓
        今天 = 8/17，用户出行 8/25 → T+8天，超 7 天预报 ✗（即使 2024-08-25 实况已归档，
        真实出行当天也拿不到对应 GOWFS 预报，需提示用户降级使用气候值）。

    :param target_dt: 目标 datetime（会自动映射到 DATA_YEAR）
    :param run_dt:    起报时间；None 则默认用 nearest_run_time(data_today())
    :return: dict {
        'within_range': bool,      # 是否在 3–168h 时效内
        'hours_ahead':  int,       # 起报 → 目标 的小时差（可正可负）
        'run_time':     datetime,  # 使用的起报时间
        'max_target':   datetime,  # 当前起报能覆盖的最晚时间
        'days_over':    int,       # 超出几天（0 表示未超）
        'is_past':       bool,      # 目标日是否在今天之前（历史日期，走实况）
        'limit_hours':  int,       # 最大合法时效 168
    }
    """
    from datetime import datetime
    from utils.common import data_today
    target_dt = to_data_year(target_dt) or to_data_year(datetime.now())
    if run_dt is None:
        # 关键修正：用"今天"的最近起报，而不是 target_dt 自己的起报
        run_dt = nearest_run_time(data_today())
    run_dt = to_data_year(run_dt)

    today = data_today()
    is_past = target_dt.date() < today.date()

    delta = target_dt - run_dt
    hours_ahead = int(delta.total_seconds() // 3600)
    max_target = run_dt + timedelta(hours=MAX_FORECAST_HOURS)
    over_seconds = (target_dt - max_target).total_seconds()
    days_over = int((over_seconds + 86399) // 86400) if over_seconds > 0 else 0

    return {
        "within_range": 3 <= hours_ahead <= MAX_FORECAST_HOURS,
        "hours_ahead": hours_ahead,
        "run_time": run_dt,
        "max_target": max_target,
        "days_over": days_over,
        "is_past": is_past,
        "limit_hours": MAX_FORECAST_HOURS,
        "limit_days": MAX_FORECAST_DAYS,
    }


def align_observation_hours(dt_start, dt_end):
    """
    将实况请求时间段对齐到合法的 6h 时次（02 / 08 / 14 / 20）。
    向后对齐：如果起点不在合法时次，就"向上取"最近的合法时次；终点则"向下取"。
    返回 (aligned_start, aligned_end)；若区间内无合法时次返回 (None, None)。
    """
    from datetime import datetime
    def _ceil(d):
        # 从 02/08/14/20 中取 ≥ d.hour 的最小；若都小则取下一天的 02
        h = d.hour
        for legal in _OBSERVATION_HOURS:
            if legal >= h:
                return d.replace(hour=legal, minute=0, second=0, microsecond=0)
        return (d + timedelta(days=1)).replace(hour=_OBSERVATION_HOURS[0], minute=0, second=0, microsecond=0)

    def _floor(d):
        h = d.hour
        for legal in reversed(_OBSERVATION_HOURS):
            if legal <= h:
                return d.replace(hour=legal, minute=0, second=0, microsecond=0)
        return (d - timedelta(days=1)).replace(hour=_OBSERVATION_HOURS[-1], minute=0, second=0, microsecond=0)

    s = _ceil(to_data_year(dt_start) or datetime.now())
    e = _floor(to_data_year(dt_end) or datetime.now())
    if s > e:
        return None, None
    return s, e


def get_variable_list(product="observation"):
    """获取可用变量列表"""
    url = f"{BASE_URL}/api/v1/variables"
    resp = requests.get(url, params={"product": product}, headers=HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("variables", [])


def _restore_grid(res_json):
    """一维 values -> 多维 (time, lat, lon) numpy 数组"""
    grid = {}
    for var_name, var_info in res_json["data"].items():
        arr_1d = np.array(var_info["values"], dtype=np.float32)
        grid[var_name] = arr_1d.reshape(var_info["shape"])
    return grid


def _extract_lats_lons(res_json, grid, bbox):
    """优先从响应取 lats/lons，否则按 bbox 线性插值（用于绘图的近似坐标）。"""
    try:
        var0 = list(res_json["data"].values())[0]
        lats = var0.get("lats")
        lons = var0.get("lons")
        if lats is not None and lons is not None:
            return np.array(lats), np.array(lons)
    except Exception:
        pass
    shape = grid[list(grid)[0]].shape if grid else (1, 2, 2)
    nlat = shape[1]
    nlon = shape[2]
    min_lon, min_lat, max_lon, max_lat = bbox
    lats = np.linspace(min_lat, max_lat, nlat)
    lons = np.linspace(min_lon, max_lon, nlon)
    return lats, lons


def get_observation_data(variables, time_start, time_end, bbox_str):
    """读取 CRA40 实况格点 -> (res_json, grid_data, (lats,lons))

    注意：实况接口每 6 小时一个时次（02/08/14/20），调用前请用
    align_observation_hours() 对齐 time_start / time_end。
    """
    url = f"{BASE_URL}/api/v1/observations"
    params = {
        "variables": variables,
        "time_start": time_start,
        "time_end": time_end,
        "bbox": bbox_str,
    }
    logger.info("实况请求: %s ~ %s vars=%s", time_start, time_end, variables)
    resp = requests.get(url, params=params, headers=HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    res_json = resp.json()
    grid = _restore_grid(res_json)
    lats, lons = _extract_lats_lons(res_json, grid, parse_bbox(bbox_str))
    return res_json, grid, (lats, lons)


def get_forecast_3h_data(variables, run_time, forecast_hours, bbox_str):
    """读取 GOWFS 3小时预报格点 -> (res_json, grid_data, (lats,lons))

    注意：forecast_hours 的合法范围是 3–168（单位：小时）；超出范围请先调用
    check_forecast_availability() 判断，并在前端向用户说明降级为气候默认值。
    """
    url = f"{BASE_URL}/api/v1/forecasts/3h"
    params = {
        "variables": variables,
        "run_time": run_time,
        "forecast_hours": forecast_hours,
        "bbox": bbox_str,
    }
    logger.info("预报请求: run=%s fh=%s vars=%s", run_time, forecast_hours, variables)
    resp = requests.get(url, params=params, headers=HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    res_json = resp.json()
    grid = _restore_grid(res_json)
    lats, lons = _extract_lats_lons(res_json, grid, parse_bbox(bbox_str))
    return res_json, grid, (lats, lons)


def get_weather_summary(target_dt, bbox_str):
    """
    取目标日期当天气象摘要。

    真实场景路由规则（关键）：
      1. 目标日 <= 今天（已发生/今天）    → 走 CRA40 实况接口（已归档）
      2. 今天 < 目标日 <= 今天 + 7 天     → 走 GOWFS 3h 预报接口（时效内）
      3. 目标日 > 今天 + 7 天            → 超时效，返回 None（上层用气候默认值兜底）

    返回 dict 会携带时效相关字段：
      forecast_availability:  check_forecast_availability() 的结果
      warn_out_of_range:       bool，目标日是否超出预报最大时效
      warn_observation_align:  str，实况时次对齐提示（可能为空）
      source:                  "实况" / "预报"
    """
    from datetime import datetime
    from utils.common import data_today
    cache_key = f"summary|{fmt_14(target_dt)}|{bbox_str}"
    cached = weather_cache.get(cache_key)
    if cached:
        return cached

    var_candidates = [_VARIABLES, "TMP,PRE"]

    # 时效判断（基于"今天"的最近起报）
    fc_avail = check_forecast_availability(target_dt)
    today = data_today()
    target_mapped = to_data_year(target_dt)
    is_past_or_today = target_mapped.date() <= today.date()
    warn_out_of_range = fc_avail["days_over"] > 0

    align_note = ""
    summary = None

    # ---- 1) 实况：目标日 <= 今天，按 6h 时次对齐 ----
    if is_past_or_today:
        raw_ts = target_mapped.replace(hour=0, minute=0)
        raw_te = target_mapped.replace(hour=23, minute=59)
        ts_dt, te_dt = align_observation_hours(raw_ts, raw_te)
        if ts_dt is None:
            align_note = "当日无匹配的 6h 实况时次，已跳过实况接口"
            logger.warning(align_note)
        else:
            ts = fmt_14(ts_dt)
            te = fmt_14(te_dt)
            if ts_dt != raw_ts or te_dt != raw_te:
                align_note = f"实况已对齐到时次 {ts_dt.strftime('%H:%M')}–{te_dt.strftime('%H:%M')}（接口每 6 小时一次）"
            for vs in var_candidates:
                try:
                    res_json, grid, (lats, lons) = get_observation_data(vs, ts, te, bbox_str)
                    summary = _build_summary("实况", res_json, grid, lats, lons)
                    break
                except Exception as e:
                    logger.warning("实况接口(%s)失败: %s", vs, e)

    # ---- 2) 预报：今天 < 目标日 <= 今天 + 7 天 ----
    if summary is None and fc_avail["within_range"] and not is_past_or_today:
        run_time = fmt_14(fc_avail["run_time"])
        h = fc_avail["hours_ahead"]
        # 目标日全天 3h 间隔时次（覆盖 00-23 时，共 8 个时次）
        # h 对应 day_dt（默认 02:00），目标日 0:00 ≈ h-2，目标日 23:00 ≈ h+21
        # 注意：GOWFS 3h 预报的合法时效必须是 3 的倍数（3,6,9,...,168）
        fh_start = max(3, h - 2)
        # 对齐到 3 的倍数（向上取）
        if fh_start % 3 != 0:
            fh_start = ((fh_start // 3) + 1) * 3
        fh_end = min(MAX_FORECAST_HOURS, h + 21)
        # 对齐到 3 的倍数（向下取）
        if fh_end % 3 != 0:
            fh_end = (fh_end // 3) * 3
        # 生成 3h 间隔的合法时效列表（全部为 3 的倍数）
        all_fhs = [fh for fh in range(fh_start, fh_end + 1, 3)
                   if 3 <= fh <= MAX_FORECAST_HOURS]
        # API 限制：每次最多 5 个时效 → 分批请求
        BATCH = 5
        merged_summary = None
        for vs in var_candidates:
            try:
                batch_summaries = []
                for i in range(0, len(all_fhs), BATCH):
                    batch_fhs = all_fhs[i:i + BATCH]
                    forecast_hours = ",".join(str(f) for f in batch_fhs)
                    try:
                        res_json, grid, (lats, lons) = get_forecast_3h_data(
                            vs, run_time, forecast_hours, bbox_str)
                        s = _build_summary("预报", res_json, grid, lats, lons)
                        batch_summaries.append(s)
                    except Exception as e:
                        logger.warning("预报批次(%s)失败: %s", forecast_hours, e)
                        continue
                if not batch_summaries:
                    continue
                # 合并多批次结果
                if len(batch_summaries) == 1:
                    merged_summary = batch_summaries[0]
                else:
                    merged_summary = _merge_summaries(batch_summaries, "预报")
                break
            except Exception as e:
                logger.error("预报接口(%s)失败: %s", vs, e)
        if merged_summary is not None:
            summary = merged_summary

    # ---- 3) 超时效：跳过 API 调用 ----
    if summary is None and warn_out_of_range:
        logger.info(
            "目标日 %s 超出 GOWFS 168h 时效（今日起报 %s，最多至 %s），返回 None 由上层兜底",
            fmt_14(target_mapped), fmt_14(fc_avail["run_time"]), fmt_14(fc_avail["max_target"])
        )

    if summary is None:
        # 留给上层用气候默认值兜底
        return None

    # 追加时效与对齐标记（写入缓存，供模板渲染使用）
    summary["forecast_availability"] = {
        k: (v.isoformat() if hasattr(v, "isoformat") else v)
        for k, v in fc_avail.items()
    }
    summary["warn_out_of_range"] = warn_out_of_range
    summary["warn_observation_align"] = align_note
    weather_cache.set(cache_key, summary)
    return summary


def _build_summary(source, res_json, grid, lats, lons):
    """从格点数据计算区域平均/累计时间序列"""
    times = res_json.get("times") or res_json.get("valid_times") or []
    tmp_arr = grid.get("TMP")
    pre_arr = grid.get("PRE")
    rh_arr = grid.get("RH")

    # 区域均值：对 (lat, lon) 取平均，得到逐时次序列
    tmp_series = []
    pre_series = []
    rh_series = []
    if tmp_arr is not None:
        tmp_series = np.nanmean(tmp_arr, axis=(1, 2)).tolist()
    if pre_arr is not None:
        pre_series = np.nansum(pre_arr, axis=(1, 2)).tolist()
    if rh_arr is not None:
        rh_series = np.nanmean(rh_arr, axis=(1, 2)).tolist()

    avg_tmp = float(np.nanmean(tmp_series)) if tmp_series else None
    max_tmp = float(np.nanmax(tmp_series)) if tmp_series else None
    min_tmp = float(np.nanmin(tmp_series)) if tmp_series else None
    total_pre = float(np.nansum(pre_series)) if pre_series else 0.0
    avg_rh = float(np.nanmean(rh_series)) if rh_series else None

    update_time = fmt_display(__import__("datetime").datetime.now())

    return {
        "source": source,
        "times": list(times),
        "tmp_series": [round(x, 1) if x is not None and x == x else None for x in tmp_series],
        "pre_series": [round(x, 1) if x is not None and x == x else None for x in pre_series],
        "rh_series": [round(x, 0) if x is not None and x == x else None for x in rh_series],
        "avg_tmp": round(avg_tmp, 1) if avg_tmp is not None else None,
        "max_tmp": round(max_tmp, 1) if max_tmp is not None else None,
        "min_tmp": round(min_tmp, 1) if min_tmp is not None else None,
        "total_pre": round(total_pre, 1),
        "avg_rh": round(avg_rh, 0) if avg_rh is not None else None,
        "update_time": update_time,
        "_res_json": res_json,
        "_grid": grid,
        "_lats": lats,
        "_lons": lons,
    }


def _merge_summaries(summaries, source):
    """合并多批次预报结果（每批最多 5 个时效）。
    按时间次序拼接 times / tmp_series / pre_series / rh_series，并重算统计量。"""
    merged_times, merged_tmp, merged_pre, merged_rh = [], [], [], []
    seen = set()
    for s in summaries:
        ts = s.get("times", [])
        tmp = s.get("tmp_series", [])
        pre = s.get("pre_series", [])
        rh = s.get("rh_series", [])
        for i, t in enumerate(ts):
            if t in seen:
                continue
            seen.add(t)
            merged_times.append(t)
            merged_tmp.append(tmp[i] if i < len(tmp) else None)
            merged_pre.append(pre[i] if i < len(pre) else None)
            merged_rh.append(rh[i] if i < len(rh) else None)

    # 按时间排序
    def _sort_key(t):
        digits = "".join(ch for ch in str(t) if ch.isdigit())
        return digits[:12] if len(digits) >= 12 else digits
    paired = list(zip(merged_times, merged_tmp, merged_pre, merged_rh))
    paired.sort(key=lambda x: _sort_key(x[0]))
    if paired:
        merged_times, merged_tmp, merged_pre, merged_rh = map(list, zip(*paired))

    tmp_clean = [x for x in merged_tmp if x is not None and x == x]
    avg_tmp = float(np.nanmean(tmp_clean)) if tmp_clean else None
    max_tmp = float(np.nanmax(tmp_clean)) if tmp_clean else None
    min_tmp = float(np.nanmin(tmp_clean)) if tmp_clean else None
    total_pre = float(np.nansum([x for x in merged_pre if x is not None])) if merged_pre else 0.0
    rh_clean = [x for x in merged_rh if x is not None and x == x]
    avg_rh = float(np.nanmean(rh_clean)) if rh_clean else None

    update_time = fmt_display(__import__("datetime").datetime.now())
    return {
        "source": source,
        "times": merged_times,
        "tmp_series": merged_tmp,
        "pre_series": merged_pre,
        "rh_series": merged_rh,
        "avg_tmp": round(avg_tmp, 1) if avg_tmp is not None else None,
        "max_tmp": round(max_tmp, 1) if max_tmp is not None else None,
        "min_tmp": round(min_tmp, 1) if min_tmp is not None else None,
        "total_pre": round(total_pre, 1),
        "avg_rh": round(avg_rh, 0) if avg_rh is not None else None,
        "update_time": update_time,
    }
