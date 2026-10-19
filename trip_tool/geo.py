# -*- coding: utf-8 -*-
"""坐标系与导航深链。

项目约定：data/wuhan/*.json 全部是 WGS84；高德/腾讯需要 GCJ-02，必须转换。
"""
from __future__ import annotations

import math
from urllib.parse import quote

_AXIS = 6378245.0
_EE = 0.00669342162296594323
_PI = math.pi


def _tlat(x, y):
    r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * _PI) + 20 * math.sin(2 * x * _PI)) * 2 / 3
    r += (20 * math.sin(y * _PI) + 40 * math.sin(y / 3 * _PI)) * 2 / 3
    r += (160 * math.sin(y / 12 * _PI) + 320 * math.sin(y * _PI / 30)) * 2 / 3
    return r


def _tlng(x, y):
    r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * _PI) + 20 * math.sin(2 * x * _PI)) * 2 / 3
    r += (20 * math.sin(x * _PI) + 40 * math.sin(x / 3 * _PI)) * 2 / 3
    r += (150 * math.sin(x / 12 * _PI) + 300 * math.sin(x / 30 * _PI)) * 2 / 3
    return r


def wgs2gcj(lon, lat):
    dlat, dlng = _tlat(lon - 105, lat - 35), _tlng(lon - 105, lat - 35)
    rad = lat / 180.0 * _PI
    magic = 1 - _EE * math.sin(rad) ** 2
    sq = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_AXIS * (1 - _EE)) / (magic * sq) * _PI)
    dlng = (dlng * 180.0) / (_AXIS / sq * math.cos(rad) * _PI)
    return lon + dlng, lat + dlat


def gcj2wgs(lon, lat):
    wlon, wlat = lon, lat
    for _ in range(6):
        glon, glat = wgs2gcj(wlon, wlat)
        wlon += lon - glon
        wlat += lat - glat
    return wlon, wlat


def amap_nav_url(lon, lat, name="", mode="walk"):
    """高德 URI 深链（无需 key，手机点开即逐向导航）。入参 WGS84，内部转 GCJ-02。"""
    glon, glat = wgs2gcj(lon, lat)
    m = {"walk": "walk", "drive": "car", "transit": "bus", "bus": "bus", "ride": "ride"}.get(mode, "walk")
    payload = "%.6f,%.6f" % (glon, glat) + (("," + quote(str(name))) if name else "")
    return ("https://uri.amap.com/navigation?to=" + payload
            + "&mode=" + m + "&policy=1&src=weathertrip&coordinate=gaode&callnative=1")


def amap_marker_url(lon, lat, name=""):
    glon, glat = wgs2gcj(lon, lat)
    payload = "%.6f,%.6f" % (glon, glat) + (("," + quote(str(name))) if name else "")
    return "https://uri.amap.com/marker?position=" + payload + "&coordinate=gaode&src=weathertrip"
