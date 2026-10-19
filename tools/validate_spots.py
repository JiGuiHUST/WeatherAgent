# -*- coding: utf-8 -*-
"""校验武汉景点数据（data/wuhan/spots.json、districts.json）的格式与取值。

用法：python tools/validate_spots.py
检查项：必填字段、id 唯一、坐标落在武汉市范围、行政区与功能区合法、type 对应已有模板、
覆盖项里的因子名合法、权重取值、开放时间来源与核对日期、备选景点 id 存在。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data", "wuhan")

# 武汉市行政区大致外包框（WGS84），用于发现坐标填错或误用 GCJ-02 之外的明显错误
WUHAN_BBOX = {"lat": (29.95, 31.40), "lon": (113.68, 115.10)}

REQUIRED = ["id", "name", "district", "lat", "lon", "coord_source", "type",
            "exposure", "features", "open_hours", "best_months"]
EXPOSURES = {"室内", "半室外", "室外为主", "室外"}
CONFIDENCE = re.compile(r"^(高|中|低)")
EXTRA_FACTORS = {"bloom_stage"}  # 非气象直读的模型输出因子


def _load(name):
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def validate():
    tpl = _load("spot_type_templates.json")
    data = _load("spots.json")
    districts = _load("districts.json")
    district_names = {k for k in districts if not k.startswith("_")}
    zones = set(districts.get("_meta", {}).get("functional_zones", {}))
    factors = set(tpl["factors"]) | EXTRA_FACTORS
    templates = tpl["templates"]
    spots = data.get("spots", [])
    ids = [s.get("id") for s in spots]
    errors, warnings = [], []

    for t_key, t in templates.items():
        for f, cfg in t.get("sensitivity", {}).items():
            if f not in factors:
                errors.append(f"模板 {t_key}: 未知因子 {f}")
            if cfg.get("weight") not in (0, 1, 2, 3):
                errors.append(f"模板 {t_key}.{f}: weight 须为 0–3")
            if cfg.get("basis") and cfg["basis"] not in tpl["basis"]:
                errors.append(f"模板 {t_key}.{f}: basis '{cfg['basis']}' 不在 basis 列表")

    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append(f"重复 id: {sorted(dup)}")

    for s in spots:
        sid = s.get("id", "<无id>")
        for k in REQUIRED:
            if k not in s:
                errors.append(f"{sid}: 缺少字段 {k}")
        lat, lon = s.get("lat"), s.get("lon")
        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            errors.append(f"{sid}: lat/lon 须为数值")
        elif not (WUHAN_BBOX["lat"][0] <= lat <= WUHAN_BBOX["lat"][1]
                  and WUHAN_BBOX["lon"][0] <= lon <= WUHAN_BBOX["lon"][1]):
            errors.append(f"{sid}: 坐标 ({lat},{lon}) 不在武汉市范围")
        if s.get("district") not in district_names:
            errors.append(f"{sid}: district '{s.get('district')}' 不是 districts.json 中的行政区")
        if s.get("zone") is not None and s["zone"] not in zones:
            errors.append(f"{sid}: zone '{s['zone']}' 不在 functional_zones 列表")
        if s.get("type") not in templates:
            errors.append(f"{sid}: type '{s.get('type')}' 没有对应模板")
        if s.get("exposure") not in EXPOSURES:
            errors.append(f"{sid}: exposure 须为 {sorted(EXPOSURES)}")
        for f, cfg in (s.get("sensitivity_overrides") or {}).items():
            if f not in factors:
                errors.append(f"{sid}: 覆盖项未知因子 {f}")
            if "weight" in cfg and cfg["weight"] not in (0, 1, 2, 3):
                errors.append(f"{sid}.{f}: weight 须为 0–3")
        oh = s.get("open_hours") or {}
        for k in ("text", "source", "checked", "confidence"):
            if not oh.get(k):
                errors.append(f"{sid}: open_hours 缺少 {k}")
        if oh.get("confidence") and not CONFIDENCE.match(oh["confidence"]):
            errors.append(f"{sid}: open_hours.confidence 须以 高/中/低 开头")
        for p in oh.get("periods", []):
            for k in ("open", "close"):
                if not re.fullmatch(r"\d{2}:\d{2}", p.get(k, "")):
                    errors.append(f"{sid}: periods.{k} 须为 HH:MM")
        if not oh.get("periods"):
            warnings.append(f"{sid}: open_hours.periods 为空（开放时段未知）")
        months = s.get("best_months") or []
        if not all(isinstance(m, int) and 1 <= m <= 12 for m in months):
            errors.append(f"{sid}: best_months 须为 1–12 的整数")
        for alt in s.get("rainy_alternative", []):
            if alt not in ids:
                errors.append(f"{sid}: rainy_alternative 引用了不存在的 id '{alt}'")
        if str(oh.get("confidence", "")).startswith("低"):
            warnings.append(f"{sid}: 开放时间可信度低，需人工核实")

    for name in district_names:
        listed = set(districts[name].get("spots", []))
        actual = {s["id"] for s in spots if s.get("district") == name}
        if listed != actual:
            errors.append(f"districts.json {name}.spots 与 spots.json 不一致：多 {sorted(listed - actual)} 少 {sorted(actual - listed)}")

    return spots, errors, warnings


if __name__ == "__main__":
    spots, errors, warnings = validate()
    for w in warnings:
        print("[警告]", w)
    for e in errors:
        print("[错误]", e)
    print(f"共 {len(spots)} 个景点，{len(errors)} 个错误，{len(warnings)} 个警告")
    sys.exit(1 if errors else 0)
