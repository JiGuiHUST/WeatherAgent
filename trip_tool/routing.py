# -*- coding: utf-8 -*-
"""路网耗时矩阵。默认用开源 OSRM；拿不到就用球面距离估算，绝不阻塞规划。

预留接口
--------
    class MyMatrix:
        def matrix(self, points, transport) -> (mins[][], km[][], modes[][])
        # points: [{"lat":..,"lon":..,"name":..}, ...]（WGS84）
        # transport: "walk" | "drive" | "mixed"
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.request

logger = logging.getLogger("trip_tool.routing")

OSRM_BASE = "https://routing.openstreetmap.de"
WALK_KMH = 4.5
DRIVE_KMH = 22.0
DRIVE_OVERHEAD_MIN = 8   # 叫车/停车/找入口
DETOUR_FACTOR = 1.35     # 直线距离 → 实际路程的经验系数


def haversine_km(lat1, lon1, lat2, lon2):
    import math
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class MatrixProvider:
    def matrix(self, points, transport="mixed"):
        raise NotImplementedError


class OsrmMatrix(MatrixProvider):
    def __init__(self, cache_dir=None, timeout=20):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cache_dir = cache_dir or os.path.join(here, "data", "wuhan", ".cache")
        self.timeout = timeout

    def _cache_path(self, profile, pts):
        key = profile + "|" + "|".join("%.4f,%.4f" % (p["lat"], p["lon"]) for p in pts)
        return os.path.join(self.cache_dir, "mx_%s.json" % hashlib.md5(key.encode()).hexdigest()[:16])

    def _table(self, pts, profile):
        cached = self._cache_path(profile, pts)
        try:
            with open(cached, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d["km"], d["min"]
        except (OSError, KeyError):
            pass

        path = "foot" if profile == "foot" else "driving"
        coords = ";".join("%.6f,%.6f" % (p["lon"], p["lat"]) for p in pts)
        url = "%s/routed-%s/table/v1/%s/%s?annotations=duration,distance" % (
            OSRM_BASE, profile, path, coords)
        req = urllib.request.Request(url, headers={"User-Agent": "weathertrip/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            d = json.load(resp)
        n = len(pts)
        km = [[(d["distances"][i][j] or 0) / 1000.0 for j in range(n)] for i in range(n)]
        mins = [[int(round((d["durations"][i][j] or 0) / 60.0)) for j in range(n)] for i in range(n)]
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(cached, "w", encoding="utf-8") as f:
                json.dump({"km": km, "min": mins}, f, ensure_ascii=False)
        except OSError as e:
            logger.warning("矩阵缓存写入失败: %s", e)
        return km, mins

    def matrix(self, points, transport="mixed"):
        n = len(points)
        if transport == "walk":
            km, mins = self._table(points, "foot")
            return mins, km, [["walk"] * n for _ in range(n)]
        if transport == "drive":
            km, mins = self._table(points, "car")
            return mins, km, [["drive"] * n for _ in range(n)]

        km_w, min_w = self._table(points, "foot")
        km_d, min_d = self._table(points, "car")
        km = [[0.0] * n for _ in range(n)]
        mins = [[0] * n for _ in range(n)]
        modes = [["walk"] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                cw, cd = min_w[i][j], min_d[i][j] + DRIVE_OVERHEAD_MIN
                if cw <= cd:
                    mins[i][j], km[i][j], modes[i][j] = cw, km_w[i][j], "walk"
                else:
                    mins[i][j], km[i][j], modes[i][j] = cd, km_d[i][j], "drive"
        return mins, km, modes


class StraightLineMatrix(MatrixProvider):
    """兜底：球面距离 × 1.35 系数。完全离线，但步行估算会偏乐观。"""

    def matrix(self, points, transport="mixed"):
        n = len(points)
        kmh = WALK_KMH if transport == "walk" else DRIVE_KMH
        km = [[0.0] * n for _ in range(n)]
        mins = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                d = haversine_km(points[i]["lat"], points[i]["lon"],
                                 points[j]["lat"], points[j]["lon"]) * DETOUR_FACTOR
                km[i][j] = round(d, 2)
                mins[i][j] = int(round(d / kmh * 60))
        mode = "walk" if transport == "walk" else "drive"
        return mins, km, [[mode] * n for _ in range(n)]


def with_fallback(provider, points, transport, warnings):
    """先试 provider，失败就退到直线估算，并在 warnings 里留痕。"""
    try:
        return provider.matrix(points, transport)
    except Exception as e:
        logger.warning("路网矩阵失败，降级为直线估算: %s", e)
        warnings.append("路网服务不可用（%s），本次耗时按直线距离估算，仅供参考。" % type(e).__name__)
        return StraightLineMatrix().matrix(points, transport)


DEFAULT_MATRIX = OsrmMatrix()
