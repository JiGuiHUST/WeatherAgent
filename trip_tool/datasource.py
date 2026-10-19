# -*- coding: utf-8 -*-
"""景点数据源：读 data/wuhan/*.json；数据缺失时自动降级到内置示例集。

预留接口（关键）
----------------
任何实现了下面四个方法的对象都可以替换默认数据源：

    class MySource:
        def load_spots(self) -> dict[str, dict]     # 景点，键是 id
        def load_type_templates(self) -> dict       # 景点类型 -> 气象敏感性
        def load_districts(self) -> dict            # 行政区（取气候兜底值用）
        def describe(self) -> dict                  # 自述：数据版本/来源/缺什么

字段契约
--------
spot（景点）至少要这些键：
    id / name / lat / lon / type
可选但强烈建议：
    district / exposure / features.typical_duration_h / open_hours{periods,closed}
    / best_months / sensitivity_overrides / rainy_alternative / notes


type_template（类型模板）：
    {"sensitivity": {因子名: {"weight": 0-3, "good": "...", "bad": "...", "basis": "..."}}}
    因子名取值见 scoring.FACTORS。
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("trip_tool.datasource")

# 允许用环境变量指定数据目录，便于测试"数据缺失"分支
DATA_DIR_ENV = "TRIP_TOOL_DATA_DIR"


def default_data_dir():
    env = os.environ.get(DATA_DIR_ENV)
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "data", "wuhan")


# ---------------------------------------------------------------- 内置兜底
# 注意：这是"数据文件缺失时也能跑通链路"的保底数据，不是正式景点库。
# 坐标是 WGS84 近似值，仅供演示；一旦 data/wuhan/spots.json 存在就完全不会用到。
_BOOTSTRAP_SPOTS = [
    ("huanghelou", "黄鹤楼", 30.5471, 114.2970, "elevated_view", "室外为主", 90, "08:30", "17:20"),
    ("hubei_museum", "湖北省博物馆", 30.5637, 114.3597, "indoor", "室内", 180, "09:00", "16:00"),
    ("tanhualin", "昙华林", 30.5537, 114.3080, "street_semi_outdoor", "半室外", 120, "09:00", "20:00"),
    ("chuhe_hanjie", "楚河汉街", 30.5586, 114.3312, "street_semi_outdoor", "半室外", 120, "10:00", "21:00"),
    ("wuda", "武汉大学", 30.5368, 114.3604, "flower", "室外", 120, "08:00", "18:00"),
    ("guiyuan_temple", "归元寺", 30.5520, 114.2630, "temple", "室外为主", 60, "08:00", "17:00"),
    ("jianghanguan", "江汉关博物馆", 30.5780, 114.2867, "indoor", "室内", 60, "09:00", "17:00"),
    ("donghu_moshan", "东湖磨山景区", 30.5430, 114.4220, "mountain_forest", "室外", 150, "09:30", "17:00"),
]


def _bootstrap_source_meta():
    return {"kind": "bootstrap", "note": "正式数据文件不存在，使用内置示例景点（仅保证链路可跑）"}


def bootstrap_spots():
    spots = {}
    for (sid, name, lat, lon, typ, expo, dur, op, cl) in _BOOTSTRAP_SPOTS:
        spots[sid] = {
            "id": sid, "name": name, "district": "武昌区", "zone": None,
            "lat": lat, "lon": lon,
            "coord_source": "内置示例（WGS84 近似，仅供缺数据时演示）",
            "type": typ, "exposure": expo,
            "features": {"typical_duration_h": dur / 60.0},
            "open_hours": {
                "text": "内置示例，请以正式数据为准",
                "periods": [{"days": "Mon-Sun", "open": op, "close": cl}],
                "closed": [], "reservation": "", "source": "bootstrap",
                "checked": "", "confidence": "低",
            },
            "sensitivity_overrides": {}, "photo_opportunities": [],
            "best_months": list(range(1, 13)), "rainy_alternative": [],
            "notes": "内置示例景点",
        }
    return spots


# ---------------------------------------------------------------- 文件数据源
class JsonFileSource:
    """从 <data_dir>/spots.json 等文件读取。缺文件时逐项降级。"""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or default_data_dir()
        self._cache = {}
        self.missing = []

    def _read(self, name):
        if name in self._cache:
            return self._cache[name]
        path = os.path.join(self.data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("数据文件不可用 %s: %s", path, e)
            self.missing.append(name)
            data = None
        self._cache[name] = data
        return data

    def load_spots(self):
        raw = self._read("spots.json")
        if isinstance(raw, dict) and isinstance(raw.get("spots"), list):
            return {s["id"]: s for s in raw["spots"] if s.get("id")}
        if isinstance(raw, list):
            return {s["id"]: s for s in raw if s.get("id")}
        return {}

    def load_type_templates(self):
        raw = self._read("spot_type_templates.json")
        if isinstance(raw, dict) and isinstance(raw.get("templates"), dict):
            return {"templates": raw["templates"],
                    "factors": raw.get("factors", {}),
                    "meta": raw.get("meta", {})}
        return {"templates": {}, "factors": {}, "meta": {}}

    def load_districts(self):
        raw = self._read("districts.json")
        if isinstance(raw, dict):
            return {k: v for k, v in raw.items() if not k.startswith("_")}
        return {}

    def describe(self):
        return {"kind": "json", "data_dir": self.data_dir, "missing": list(self.missing)}


# ---------------------------------------------------------------- 统一入口
def load(data_dir=None):
    """返回 (spots, templates, districts, meta)。任何一层缺失都不会抛异常。"""
    src = JsonFileSource(data_dir)
    spots = src.load_spots()
    meta = {"source": src.describe(), "warnings": []}

    if not spots:
        spots = bootstrap_spots()
        meta["source"] = {"kind": "bootstrap", "data_dir": src.data_dir,
                          "missing": list(src.missing)}
        meta["warnings"].append(
            "未找到可用的景点数据（data/wuhan/spots.json），已降级为内置示例景点；"
            "请放入正式数据，工具会自动切换。")

    tpl = src.load_type_templates()
    if not tpl["templates"]:
        meta["warnings"].append(
            "未找到景点类型的气象敏感性模板（spot_type_templates.json），"
            "所有景点将按「对天气不敏感」处理，排序会忽略天气。")

    districts = src.load_districts()
    if not districts:
        meta["warnings"].append("未找到 districts.json，气候兜底与行政区筛选不可用。")

    return spots, tpl, districts, meta
