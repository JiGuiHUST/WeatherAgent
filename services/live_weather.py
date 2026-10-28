"""Real weather only. Shared by the travel dashboard and legacy pages."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import threading
from pathlib import Path

import requests

CST = dt.timezone(dt.timedelta(hours=8))
CACHE = Path(__file__).resolve().parents[1] / "data" / ".weather_cache"
LOCK = threading.Lock()
FIELDS = {
    "tmp": "temperature_2m", "rh": "relative_humidity_2m",
    "apparent_temp": "apparent_temperature", "precip": "precipitation",
    "precip_prob": "precipitation_probability", "wind10_speed": "wind_speed_10m",
    "wind_gusts": "wind_gusts_10m", "visibility": "visibility",
    "uv_index": "uv_index", "code": "weather_code",
}


def now():
    return dt.datetime.now(CST)


def today():
    return now().date()


class WeatherUnavailable(ValueError):
    pass


def _fetch_open_meteo(lat, lon, date, *, refresh=False):
    """One local day. Never synthesize missing observations or forecasts."""
    target = dt.date.fromisoformat(date)
    delta = (target - today()).days
    if target.year < 1940 or delta > 15:
        raise WeatherUnavailable("请选择过去的有效日期，或未来 15 天内的日期；超出预报范围不能生成真实行程。")
    mode = "forecast" if delta >= -5 else "historical"
    # Archive models do not provide precipitation probability / UV / visibility.
    fields = {k: v for k, v in FIELDS.items() if mode == "forecast" or k not in ("precip_prob", "visibility", "uv_index")}
    key = hashlib.sha256(f"v3|{lat:.3f}|{lon:.3f}|{date}|{mode}".encode()).hexdigest()[:24]
    path = CACHE / (key + ".json")
    if not refresh:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (now() - dt.datetime.fromisoformat(data["fetched_at"])).total_seconds() < 1800:
                data["cached"] = True
                return data
        except (OSError, ValueError, KeyError):
            pass
    url = "https://api.open-meteo.com/v1/forecast" if mode == "forecast" else "https://archive-api.open-meteo.com/v1/archive"
    params = dict(latitude=round(lat, 4), longitude=round(lon, 4), hourly=",".join(fields.values()),
                  start_date=date, end_date=date, timezone="auto", wind_speed_unit="ms")
    try:
        response = requests.get(url, params=params, timeout=(5, 18))
        response.raise_for_status()
        raw = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WeatherUnavailable("真实天气服务暂不可用，请稍后重试；系统不会使用气候均值替代当前预报。") from exc
    hourly = raw.get("hourly") or {}
    rows = []
    for i, time in enumerate(hourly.get("time") or []):
        if not time.startswith(date):
            continue
        row = {"hour": int(time[11:13]), "time": time}
        for name, var in fields.items():
            values = hourly.get(var) or []
            value = values[i] if i < len(values) else None
            row[name] = value if value is None or isinstance(value, (int, float)) and math.isfinite(value) else None
        if row.get("visibility") is not None:
            row["visibility"] = round(row["visibility"] / 1000, 2)
        row["thunder"] = row["code"] in (95, 96, 99) if row.get("code") is not None else None
        row["aqi"] = None
        row["precip_prob"] = row.get("precip_prob")
        rows.append(row)
    if len(rows) < 23 or not any(r.get("tmp") is not None for r in rows):
        raise WeatherUnavailable("该日期真实天气数据不完整，无法可靠规划。历史数据通常需要数日才能完整归档。")
    data = dict(hours=rows, source="Open-Meteo", source_url="https://open-meteo.com/en/docs",
                mode=mode, label="实时预报" if mode == "forecast" and delta >= 0 else "历史天气回放",
                target_date=date, fetched_at=now().isoformat(timespec="seconds"),
                timezone=raw.get("timezone", "Asia/Shanghai"),
                utc_offset_seconds=raw.get("utc_offset_seconds", 28800),
                coordinates={"lat": lat, "lon": lon}, spatial_scope="区域代表点预报",
                units={"tmp": "°C", "precip": "mm/h", "wind10_speed": "m/s", "visibility": "km"},
                missing=[k for k in ("precip_prob", "visibility", "uv_index", "aqi") if all(r.get(k) is None for r in rows)],
                cached=False)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with LOCK:
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, path)
    except OSError:
        pass
    return data


def provider_status():
    from config import WEATHER_PROVIDER,WEATHERCN_OPENAPI_KEY,WEATHERCN_ENABLED
    selected='weathercn' if WEATHER_PROVIDER=='weathercn' or WEATHER_PROVIDER=='auto' and WEATHERCN_ENABLED and WEATHERCN_OPENAPI_KEY else 'open-meteo'
    return dict(preferred='华风爱科',active=selected,weathercn_key_configured=bool(WEATHERCN_OPENAPI_KEY),
                weathercn_enabled=WEATHERCN_ENABLED,weathercn_status='已激活' if selected=='weathercn' else '待注册认证、Key与真实权限验证')


def fetch(lat,lon,date,*,refresh=False):
    from config import WEATHER_PROVIDER
    if WEATHER_PROVIDER not in ('auto','weathercn','open-meteo'):
        raise WeatherUnavailable('WEATHER_PROVIDER 配置无效')
    if provider_status()['active']=='weathercn':
        from services.weathercn_provider import Client,WeatherCNError
        try:return Client().fetch(lat,lon,date,refresh=refresh)
        except WeatherCNError as exc:raise WeatherUnavailable(str(exc)) from None
    return _fetch_open_meteo(lat,lon,date,refresh=refresh)


def summary(target_dt, bbox):
    coords = [float(x) for x in bbox.split(",")]
    data = fetch((coords[1] + coords[3]) / 2, (coords[0] + coords[2]) / 2, target_dt.date().isoformat())
    rows = data["hours"]
    if len(rows)!=24 or any(r.get('precip') is None for r in rows):
        raise WeatherUnavailable('所选日期的全天降水数据不完整；请在文旅工作台查看实际覆盖时段，或选择完整覆盖的日期。')
    values = lambda key: [r[key] for r in rows if r.get(key) is not None]
    temps, rain, humid = values("tmp"), values("precip"), values("rh")
    return dict(source=data["label"] + (" · Open-Meteo" if data['source']=='Open-Meteo' else ''), times=[r["time"] for r in rows],
                tmp_series=[r.get("tmp") for r in rows], pre_series=[r.get("precip") for r in rows],
                rh_series=[r.get("rh") for r in rows], wind_series=[r.get("wind10_speed") for r in rows],
                vis_series=[r.get("visibility") for r in rows], avg_tmp=round(sum(temps)/len(temps), 1),
                max_tmp=max(temps), min_tmp=min(temps), total_pre=round(sum(rain), 1),
                avg_rh=round(sum(humid)/len(humid)) if humid else None,
                update_time=data["fetched_at"], provenance={k: v for k, v in data.items() if k != "hours"},
                warn_out_of_range=False, warn_observation_align="数据为当地时区；风速与能见度直接来自天气源。",
                _grid=None, _lats=None, _lons=None)
