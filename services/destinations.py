# -*- coding: utf-8 -*-
"""目的地清单：把 data/city_bbox.json 里的城市按「国内 / 国外」两级分组。

数据约定（与 data/city_bbox.json 一致）：
  · 国外城市：沿用原有字段 country（国家名，如「越南」）
  · 国内城市：由 tools/integrate_wuhan_data.py 并入，额外带 scope="domestic"
    与 region（省级行政区，如「湖北」）

对外只暴露三个函数：
  menu(lang)        → 首页二级菜单用的两级结构
  city_groups(lang) → 行程页按「国内 · 中国 / 国外 · 越南 …」分组的城市清单
  all_cities()      → 全部城市名（按展示顺序，国内在前）
"""
from __future__ import annotations

import json
import os

from config import CITY_BBOX_FILE

COUNTRY_EN = {
    "中国": "China",
    "越南": "Vietnam",
    "泰国": "Thailand",
    "柬埔寨": "Cambodia",
    "老挝": "Laos",
    "马来西亚": "Malaysia",
    "新加坡": "Singapore",
    "印度尼西亚": "Indonesia",
    "菲律宾": "Philippines",
    "缅甸": "Myanmar",
    "文莱": "Brunei",
    "湖北": "Hubei",
}

_MAP = None


def city_map():
    global _MAP
    if _MAP is None:
        with open(CITY_BBOX_FILE, "r", encoding="utf-8") as fp:
            _MAP = json.load(fp)
    return _MAP


def is_domestic(record):
    return record.get("scope") == "domestic" or record.get("country") == "中国"


def _country_label(country, lang):
    if lang == "en":
        return COUNTRY_EN.get(country, country)
    return country


def menu(lang="zh"):
    """两级菜单结构：

    {
      "domestic": [{"country": "中国", "region": "湖北", "label": "中国 · 湖北",
                    "label_en": "China · Hubei", "cities": ["武汉"], "scope": "domestic"}],
      "foreign":  [{"country": "越南", "label": "越南", "cities": ["芽庄", ...]}, ...]
    }
    """
    data = city_map()
    domestic, foreign = {}, {}
    for city, rec in data.items():
        if is_domestic(rec):
            key = (rec.get("country", "中国"), rec.get("region", ""))
            domestic.setdefault(key, []).append(city)
        else:
            foreign.setdefault(rec.get("country", "其他"), []).append(city)

    def _entry(key, cities, scope, region=""):
        country = key if isinstance(key, str) else key[0]
        if region:
            label = "%s · %s" % (country, region)
            label_en = "%s · %s" % (_country_label(country, "en"), COUNTRY_EN.get(region, region))
        else:
            label, label_en = _country_label(country, "zh"), _country_label(country, "en")
        return {
            "country": country,
            "region": region,
            "label": label,
            "label_en": label_en,
            "cities": cities,
            "scope": scope,
        }

    dom = [_entry(k, v, "domestic", region=k[1]) for k, v in domestic.items()]
    for_ = [_entry(k, v, "foreign") for k, v in foreign.items()]
    return {"domestic": dom, "foreign": for_}


def city_groups(lang="zh"):
    """行程页分组：国内一行、每个国家一行，组内保持原 JSON 顺序。"""
    m = menu(lang)
    groups = []
    dom_prefix = "Domestic · " if lang == "en" else "国内 · "
    for_prefix = "Overseas · " if lang == "en" else "国外 · "
    for e in m["domestic"]:
        groups.append({
            "label": dom_prefix + (e["label_en"] if lang == "en" else e["label"]),
            "scope": "domestic",
            "cities": e["cities"],
        })
    for e in m["foreign"]:
        groups.append({
            "label": for_prefix + (e["label_en"] if lang == "en" else e["label"]),
            "scope": "foreign",
            "cities": e["cities"],
        })
    return groups


def all_cities():
    """国内在前，其余按数据顺序。"""
    m = menu()
    cities = []
    for e in m["domestic"]:
        cities.extend(e["cities"])
    for e in m["foreign"]:
        cities.extend(e["cities"])
    return cities
