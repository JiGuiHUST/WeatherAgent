# -*- coding: utf-8 -*-
"""逐时天气源。字段名与「气象敏感性模板」的因子名**完全一致**，避免两套命名。

规范记录（HourRecord）：
    {"hour": 9, "tmp": 20.6,
     "precip": 0.3,            # mm/h
     "precip_prob": 95,        # %
     "apparent_temp": 20.6,    # ℃
     "wind10_speed": 1.83,     # m/s
     "wind_gusts": 3.5,        # m/s
     "visibility": 2.26,       # km
     "uv_index": 0.5,
     "thunder": False,
     "aqi": 45}                # 可为 None

预留接口
--------
    class MyWeather:
        def hourly(self, lat, lon, date_iso) -> list[HourRecord]
        def describe(self) -> dict
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request

logger = logging.getLogger("trip_tool.weather")

THUNDER_CODES = {95, 96, 99}

_OM_VARS = ("temperature_2m,apparent_temperature,precipitation,precipitation_probability,"
            "wind_speed_10m,wind_gusts_10m,visibility,uv_index,weather_code,pm2_5")

# HJ 633-2012 的 PM2.5 断点（用逐时瞬时值近似 24h 均值，仅作排序参考）
_PM25_BP = [(0, 0), (35, 50), (75, 100), (115, 150), (150, 200), (250, 300), (350, 400), (500, 500)]


def _iaqi_pm25(v):
    if v is None:
        return None
    v = max(0.0, min(500.0, float(v)))
    for (c0, i0), (c1, i1) in zip(_PM25_BP, _PM25_BP[1:]):
        if c0 <= v <= c1 and c1 > c0:
            return int(round(i0 + (i1 - i0) * (v - c0) / (c1 - c0)))
    return 500


class WeatherProvider:
    def hourly(self, lat, lon, date_iso):
        raise NotImplementedError

    def describe(self):
        return {"kind": type(self).__name__}


class OpenMeteoProvider(WeatherProvider):
    """免费、无需 key、国内可直连。带 30 分钟磁盘缓存。"""

    def __init__(self, cache_dir=None, ttl=1800, timeout=15, tz="Asia/Shanghai"):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cache_dir = cache_dir or os.path.join(here, "data", "wuhan", ".cache")
        self.ttl = ttl
        self.timeout = timeout
        self.tz = tz

    def _cache_path(self, lat, lon, date_iso):
        return os.path.join(self.cache_dir, "wx_%.3f_%.3f_%s.json" % (lat, lon, date_iso))

    def _read(self, path):
        try:
            if time.time() - os.path.getmtime(path) > self.ttl:
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return None

    def hourly(self, lat, lon, date_iso):
        path = self._cache_path(lat, lon, date_iso)
        cached = self._read(path)
        if cached is not None:
            return cached

        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": "%.4f" % lat, "longitude": "%.4f" % lon,
            "hourly": _OM_VARS, "forecast_days": 16,
            "timezone": self.tz, "wind_speed_unit": "ms",
        })
        req = urllib.request.Request(url, headers={"User-Agent": "weathertrip/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = json.load(resp)

        h = raw.get("hourly") or {}
        times = h.get("time") or []
        rows = []
        for i, t in enumerate(times):
            if not t.startswith(date_iso):
                continue
            code = (h.get("weather_code") or [None] * len(times))[i]
            pm25 = (h.get("pm2_5") or [None] * len(times))[i]
            rows.append({
                "hour": int(t[11:13]),
                "tmp": (h.get("temperature_2m") or [None] * len(times))[i],
                "precip": (h.get("precipitation") or [0] * len(times))[i],
                "precip_prob": (h.get("precipitation_probability") or [None] * len(times))[i],
                "apparent_temp": (h.get("apparent_temperature") or [None] * len(times))[i],
                "wind10_speed": (h.get("wind_speed_10m") or [None] * len(times))[i],
                "wind_gusts": (h.get("wind_gusts_10m") or [None] * len(times))[i],
                "visibility": ((h.get("visibility") or [None] * len(times))[i] or 0) / 1000.0,
                "uv_index": (h.get("uv_index") or [None] * len(times))[i],
                "thunder": (code in THUNDER_CODES) if code is not None else None,
                "aqi": _iaqi_pm25(pm25),
            })
        if not rows:
            raise ValueError("Open-Meteo 未返回 %s 的数据（可能超出 16 天预报范围）" % date_iso)

        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
        except OSError as e:
            logger.warning("天气缓存写入失败: %s", e)
        return rows

    def describe(self):
        return {"kind": "open-meteo", "unit_wind": "m/s", "cache_ttl_s": self.ttl}


class InjectedProvider(WeatherProvider):
    """离线/回放/单测用：直接把逐时数据塞进来。"""

    def __init__(self, rows, label="injected"):
        self.rows = list(rows or [])
        self.label = label

    def hourly(self, lat, lon, date_iso):
        if not self.rows:
            raise ValueError("InjectedProvider 没有数据")
        return self.rows

    def describe(self):
        return {"kind": self.label, "hours": len(self.rows)}


class ClimatologyProvider(WeatherProvider):
    """最终兜底：用行政区季节气候值合成一条平滑的逐时曲线（明确标注 source）。"""

    def __init__(self, districts, fallback_tmp=20.0, fallback_precip_month=80.0):
        self.districts = districts or {}
        self.fallback_tmp = fallback_tmp
        self.fallback_precip_month = fallback_precip_month
        self.used = 0

    def _nearest_climate(self, lat, lon):
        best, bestd = None, 1e18
        for name, d in self.districts.items():
            c = d.get("center") or {}
            if not c.get("lat"):
                continue
            dd = (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2
            if dd < bestd:
                best, bestd = d, dd
        return best

    def hourly(self, lat, lon, date_iso):
        self.used += 1
        import math
        month = int(date_iso[5:7])
        season = {3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer",
                  9: "autumn", 10: "autumn", 11: "autumn"}.get(month, "winter")
        d = self._nearest_climate(lat, lon) or {}
        t_mean, p_month = ((d.get("climate") or {}).get(season)
                           or [self.fallback_tmp, self.fallback_precip_month])
        per_hour = float(p_month) / 30.0 / 24.0
        rows = []
        for hh in range(24):
            t = round(t_mean + 3 * math.sin((hh - 9) * math.pi / 12), 1)
            rows.append({
                "hour": hh, "tmp": t, "precip": round(per_hour, 3),
                "precip_prob": int(min(95, per_hour * 30)),
                "apparent_temp": t, "wind10_speed": 2.0, "wind_gusts": 3.5,
                "visibility": 12.0, "uv_index": 3.0, "thunder": False, "aqi": None,
            })
        return rows

    def describe(self):
        return {"kind": "climatology", "used": self.used}
