# -*- coding: utf-8 -*-
"""把数据同事提供的『武汉 13 区县 + 30 景点』并入站点主数据。

做两件事（可重复执行，已并入则跳过）：
  1) 在 data/city_bbox.json 末尾追加「武汉」条目：13 个区县的 bbox 并集、
     13 区县气候均值（作为城市级气候兜底值）、简介与推荐天数；
  2) 在 data/travel_spots.json 末尾追加「武汉」景点分组：按景点 type 归到
     travel_engine 的四个标准卡片区（文化地标 / 城市海滩 / 海岛活动 / 亲子乐园）。

不修改任何已有城市的数据，只做追加；写入格式与现有文件保持一致（4 空格缩进、
数组单行、CRLF 行尾）。
"""
from __future__ import annotations

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
WH_DIR = os.path.join(DATA_DIR, "wuhan")

CITY_FILE = os.path.join(DATA_DIR, "city_bbox.json")
SPOTS_FILE = os.path.join(DATA_DIR, "travel_spots.json")
DISTRICTS_FILE = os.path.join(WH_DIR, "districts.json")
WH_SPOTS_FILE = os.path.join(WH_DIR, "spots.json")

CITY = "武汉"
SEASONS = ("spring", "summer", "autumn", "winter")

# 景点 type ->（站点卡片分类名, 天气提示）
TYPE_MAP = {
    "indoor": ("博物馆", "室内恒温，雨天与高温时段首选；仍需留意闭馆日与预约"),
    "elevated_view": ("都市地标", "登高远眺，能见度低或雷雨大风时建议改期"),
    "temple": ("宗教建筑", "庭院多为室外，雨天带伞，注意殿内礼佛礼仪"),
    "street_semi_outdoor": ("城市街区", "街区有店招与骑楼可遮雨，雨天仍可慢逛"),
    "waterside_open": ("城市湖泊", "临水开阔、风大，夏季正午暴晒，备防晒与薄外套"),
    "city_park": ("城市花园", "城市公园，适合晨晚散步，正午注意遮阳补水"),
    "mountain_forest": ("山林休闲", "山林遮阴较好，雨后路滑，穿防滑鞋"),
    "flower": ("花海庄园", "花期受气温影响，赏花宜清晨或傍晚光线柔和时"),
    "theme_park": ("亲子乐园", "多为户外项目，雨天部分停开，出行前确认园区公告"),
}

INTRO = (
    "长江与汉江交汇的江城，黄鹤楼、湖北省博物馆、东湖与汉口江滩串起三镇风光；"
    "春秋温和宜游，夏季湿热、梅雨与“秋老虎”是主要天气风险。"
)


def load(path):
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def j(obj):
    """JSON 字符串字面量（中文不转义）"""
    return json.dumps(obj, ensure_ascii=False)


def city_record(districts):
    """由 13 个区县聚合出城市级记录"""
    bboxes = []
    for name, d in districts.items():
        if name.startswith("_"):
            continue
        boxes = [float(x) for x in d["bbox"].split(",")]
        bboxes.append(boxes)
    min_lon = min(b[0] for b in bboxes)
    min_lat = min(b[1] for b in bboxes)
    max_lon = max(b[2] for b in bboxes)
    max_lat = max(b[3] for b in bboxes)

    climate = {}
    for season in SEASONS:
        vals = [d["climate"][season] for name, d in districts.items()
                if not name.startswith("_") and season in d.get("climate", {})]
        if not vals:
            continue
        tmp = round(sum(v[0] for v in vals) / len(vals), 1)
        pre = round(sum(v[1] for v in vals) / len(vals), 1)
        climate[season] = [tmp, pre]

    return {
        "country": "中国",
        "region": "湖北",
        "scope": "domestic",
        "bbox": "%.2f,%.2f,%.2f,%.2f" % (min_lon, min_lat, max_lon, max_lat),
        "intro": INTRO,
        "fit_tags": ["历史人文", "江湖景观", "赏花", "博物馆", "美食"],
        "recommend_days": 3,
        "best_season": "3–5月、9–11月（春秋温和；6–7月梅雨、7–8月湿热高温、9月常有“秋老虎”）",
        "climate": climate,
    }


def city_block(rec):
    lines = ['    "%s": {' % CITY]
    lines.append('        "country": %s,' % j(rec["country"]))
    lines.append('        "region": %s,' % j(rec["region"]))
    lines.append('        "scope": %s,' % j(rec["scope"]))
    lines.append('        "bbox": %s,' % j(rec["bbox"]))
    lines.append('        "intro": %s,' % j(rec["intro"]))
    lines.append('        "fit_tags": [%s],' % ", ".join(j(t) for t in rec["fit_tags"]))
    lines.append('        "recommend_days": %d,' % rec["recommend_days"])
    lines.append('        "best_season": %s,' % j(rec["best_season"]))
    climate = ", ".join('"%s": [%s, %s]' % (k, v[0], v[1]) for k, v in rec["climate"].items())
    lines.append('        "climate": {%s}' % climate)
    lines.append("    }")
    return "\r\n".join(lines)


def spot_groups(spots):
    """按 type 归组，输出 分类 -> [景点] 结构（保持文件原有顺序）"""
    groups = {}
    for s in spots:
        cat, tip = TYPE_MAP.get(s.get("type"), ("文化地标", "按天气情况灵活安排"))
        desc = (s.get("notes") or "").strip()
        if s.get("district") and s["district"] not in desc:
            desc = (desc + "· " if desc else "") + "位于%s" % s["district"]
        item = {
            "name": s["name"],
            "desc": desc or "%s，%s" % (s.get("exposure", "景点"), tip),
            "weather_tip": tip,
            "lat": s["lat"],
            "lon": s["lon"],
        }
        groups.setdefault(cat, []).append(item)
    return groups


def spots_block(groups):
    lines = ['    "%s": {' % CITY]
    cats = list(groups.items())
    for ci, (cat, items) in enumerate(cats):
        lines.append('        "%s": [' % cat)
        for si, s in enumerate(items):
            lines.append("            {")
            lines.append('                "name": %s,' % j(s["name"]))
            lines.append('                "desc": %s,' % j(s["desc"]))
            lines.append('                "weather_tip": %s,' % j(s["weather_tip"]))
            lines.append('                "lat": %s,' % s["lat"])
            lines.append('                "lon": %s' % s["lon"])
            lines.append("            }" + ("," if si < len(items) - 1 else ""))
        lines.append("        ]" + ("," if ci < len(cats) - 1 else ""))
    lines.append("    }")
    return "\r\n".join(lines)


def append_entry(path, block, key):
    """在 JSON 文件末尾追加一个条目（保持原文件其余字节不变）"""
    with open(path, "r", encoding="utf-8", newline="") as fp:
        text = fp.read()
    if '"%s"' % key in text:
        print("  [skip] %s 已存在 %s" % (os.path.basename(path), key))
        return False
    body = text.rstrip()
    assert body.endswith("}"), body[-10:]
    body = body[:-1].rstrip()
    new_text = body + ",\r\n" + block + "\r\n}"
    with open(path, "w", encoding="utf-8", newline="") as fp:
        fp.write(new_text)
    print("  [ok] %s += %s" % (os.path.basename(path), key))
    return True


def main():
    districts = load(DISTRICTS_FILE)
    wh_spots = load(WH_SPOTS_FILE)["spots"]

    rec = city_record(districts)
    print("武汉 bbox = %s, 气候 = %s" % (rec["bbox"], rec["climate"]))
    append_entry(CITY_FILE, city_block(rec), CITY)

    groups = spot_groups(wh_spots)
    print("武汉 景点分组 = %s" % {k: len(v) for k, v in groups.items()})
    append_entry(SPOTS_FILE, spots_block(groups), CITY)

    # 自检：合并后仍能正常解析
    city_map = load(CITY_FILE)
    spot_map = load(SPOTS_FILE)
    assert CITY in city_map and CITY in spot_map
    print("共 %d 个目的地；武汉景点 %d 个"
          % (len(city_map), sum(len(v) for v in spot_map[CITY].values())))


if __name__ == "__main__":
    main()
