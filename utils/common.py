# -*- coding: utf-8 -*-
"""通用工具函数：时间格式化、参数校验、bbox解析"""
import re
from datetime import datetime, timedelta

# 气象接口仅提供该年的实况 / 预报数据；任何用于获取与展示气象数据的日期
# 都会被映射到这一年（保留月、日、时、分）。
DATA_YEAR = 2024


def to_data_year(dt):
    """把任意 datetime 的年份强制替换为 DATA_YEAR（保留月日时分）。

    用于把"当前时间"或用户输入的日期映射到接口实际拥有数据的年份。
    2 月 29 日在非闰年会回退到 2 月 28 日，避免非法日期。
    """
    if dt is None:
        return None
    try:
        return dt.replace(year=DATA_YEAR)
    except ValueError:
        # 处理闰日 -> 非闰年的 2/29
        if dt.month == 2 and dt.day == 29:
            return dt.replace(year=DATA_YEAR, day=28)
        raise


def data_today():
    """返回映射到 DATA_YEAR 的"今天"（保留当前月日时分）。"""
    return to_data_year(datetime.now())


def data_today_str(fmt="%Y%m%d"):
    """返回 DATA_YEAR 今天日期字符串，默认 YYYYMMDD。"""
    return data_today().strftime(fmt)


def parse_time_input(raw, seasons_map):
    """
    解析用户输入的时间/季节：
      - 12位 YYYYMMDDHHMM  -> 直接使用
      - 8位  YYYYMMDD      -> 补 0200
      - 季节(春/夏/秋/冬)   -> 当年对应月份中旬日期 0200
    所有结果都会被映射到 DATA_YEAR（接口实际年份），保证气象数据可获取。
    返回 (dt对象, season_label)
    """
    raw = (raw or "").strip()
    if not raw:
        today = datetime.now()
        dt = today.replace(hour=2, minute=0, second=0, microsecond=0)
        return to_data_year(dt), _month_to_season(today.month)

    # 12位 YYYYMMDDHHMM
    m = re.fullmatch(r"\d{12}", raw)
    if m:
        dt = datetime.strptime(raw, "%Y%m%d%H%M")
        return to_data_year(dt), _month_to_season(dt.month)

    # 8位
    m = re.fullmatch(r"\d{8}", raw)
    if m:
        dt = datetime.strptime(raw + "0200", "%Y%m%d%H%M")
        return to_data_year(dt), _month_to_season(dt.month)

    # 季节关键字
    for season, month in seasons_map.items():
        if season in raw:
            dt = datetime(DATA_YEAR, month, 15, 2, 0)
            return dt, season

    # 兜底
    today = datetime.now()
    dt = today.replace(hour=2, minute=0, second=0, microsecond=0)
    return to_data_year(dt), _month_to_season(today.month)


def _month_to_season(month):
    if month in (3, 4, 5):
        return "春季"
    if month in (6, 7, 8):
        return "夏季"
    if month in (9, 10, 11):
        return "秋季"
    return "冬季"


def fmt_14(dt):
    return dt.strftime("%Y%m%d%H%M")


def fmt_display(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def nearest_run_time(dt):
    """预报起报时间：仅 08 / 20 时。向前取最近的合法起报时间。"""
    base = dt.replace(hour=8, minute=0, second=0, microsecond=0)
    if dt.hour >= 20:
        base = dt.replace(hour=20, minute=0, second=0, microsecond=0)
    elif dt.hour < 8:
        base = (dt - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    return base


def parse_bbox(bbox_str):
    """'109.1,12.1,109.3,12.3' -> (min_lon, min_lat, max_lon, max_lat) float 元组"""
    parts = [float(x) for x in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError(f"bbox 长度异常: {bbox_str}")
    return tuple(parts)


def validate_form(destination, preference, time_input, allowed_prefs):
    """表单基础校验，返回 (ok, err_msg)"""
    if not destination or not destination.strip():
        return False, "请输入目的地"
    if preference not in allowed_prefs:
        return False, "请选择有效的旅行偏好"
    if time_input and not re.fullmatch(r"[\u4e00-\u9fa5\d]+", time_input.strip()):
        return False, "时间/季节输入仅支持数字或季节文字"
    return True, ""
