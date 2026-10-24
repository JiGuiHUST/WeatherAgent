# -*- coding: utf-8 -*-
"""攻略生成引擎：城市映射、天气判定、偏好筛选、出行建议生成"""
import json
import logging
import datetime

from config import (
    CITY_BBOX_FILE, TRAVEL_SPOTS_FILE, SEASON_MONTH,
    PREFERENCE_CATEGORY_PRIORITY,
)
from utils.common import parse_time_input, fmt_display
from services import weather_api
from services.plot_service import plot_weather

logger = logging.getLogger("travel_engine")

_CITY_BBOX = None
_TRAVEL_SPOTS = None


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _city_bbox():
    global _CITY_BBOX
    if _CITY_BBOX is None:
        _CITY_BBOX = _load_json(CITY_BBOX_FILE)
    return _CITY_BBOX


def _travel_spots():
    global _TRAVEL_SPOTS
    if _TRAVEL_SPOTS is None:
        _TRAVEL_SPOTS = _load_json(TRAVEL_SPOTS_FILE)
    return _TRAVEL_SPOTS


# 国家名 → 首选城市映射（支持中文/英文国家名）
_COUNTRY_CITY_MAP = {
    # 中文国家名
    "越南": "河内", "泰国": "曼谷", "柬埔寨": "暹粒", "老挝": "琅勃拉邦",
    "马来西亚": "吉隆坡", "新加坡": "新加坡", "印度尼西亚": "巴厘岛",
    "菲律宾": "长滩岛", "缅甸": "仰光", "文莱": "斯里巴加湾",
    # 国内
    "中国": "武汉", "湖北省": "武汉", "湖北": "武汉",
    # 英文国家名
    "vietnam": "河内", "thailand": "曼谷", "cambodia": "暹粒", "laos": "琅勃拉邦",
    "malaysia": "吉隆坡", "singapore": "新加坡", "indonesia": "巴厘岛",
    "philippines": "长滩岛", "myanmar": "仰光", "brunei": "斯里巴加湾",
    "china": "武汉", "wuhan": "武汉",
}


def resolve_city(destination):
    """目的地模糊匹配城市字典键，支持：
    1. 城市名精确匹配
    2. 城市名包含/被包含的模糊匹配
    3. 国家名（中/英）自动映射到该国首选城市
    """
    city_map = _city_bbox()
    dest = destination.strip()
    if dest in city_map:
        return dest
    # 国家名匹配
    country_key = dest.lower() if any(c.isascii() for c in dest) else dest
    mapped = _COUNTRY_CITY_MAP.get(country_key) or _COUNTRY_CITY_MAP.get(dest)
    if mapped and mapped in city_map:
        return mapped
    # 模糊匹配
    for k in city_map:
        if dest in k or k in dest:
            return k
    return None


def _mock_weather(city_info, season_label):
    """API 不可达时的气候默认值兜底"""
    season_map = {"春季": "spring", "夏季": "summer", "秋季": "autumn", "冬季": "winter"}
    key = season_map.get(season_label, "spring")
    tmp, pre = city_info.get("climate", {}).get(key, [26, 30])
    # 在均值上做轻微随机化，避免一成不变
    now = datetime.datetime.now()
    seed = (now.hour + now.minute) % 5
    avg_tmp = round(tmp + (seed - 2) * 0.4, 1)
    return {
        "source": "气候默认值",
        "times": [],
        "tmp_series": [avg_tmp],
        "pre_series": [pre / 3.0],
        "rh_series": [78],
        "avg_tmp": avg_tmp,
        "max_tmp": round(avg_tmp + 3.5, 1),
        "min_tmp": round(avg_tmp - 3.0, 1),
        "total_pre": round(pre / 3.0, 1),
        "avg_rh": 78,
        "update_time": fmt_display(now),
        "_res_json": None,
        "_grid": None,
        "_lats": None,
        "_lons": None,
    }


def judge_weather(avg_tmp, total_pre):
    """生成气象标签"""
    if avg_tmp is None:
        return "气象待定"
    hot = avg_tmp >= 28
    warm = 20 <= avg_tmp < 28
    rainy = total_pre >= 15
    mid_rain = 5 <= total_pre < 15
    if hot and rainy:
        return "高温多雨"
    if hot and not mid_rain and not rainy:
        return "高温少雨"
    if hot and mid_rain:
        return "高温伴阵雨"
    if warm and rainy:
        return "温和多雨"
    if warm and not mid_rain and not rainy:
        return "温和少雨"
    if warm and mid_rain:
        return "温和伴阵雨"
    if not warm and not hot and rainy:
        return "清凉多雨"
    if not warm and not hot and mid_rain:
        return "清凉伴阵雨"
    return "清凉干燥"


def build_weather_advice(tag, avg_tmp, total_pre):
    """根据气象标签生成穿搭 / 避雨 / 最佳游玩时段建议"""
    # 穿搭
    if avg_tmp is None:
        clothing = "建议按出行季节常规穿搭准备。"
    elif avg_tmp >= 28:
        clothing = "高温天气：速干短袖、短裤、防晒帽、墨镜，备防晒霜。"
    elif avg_tmp >= 22:
        clothing = "温暖舒适：短袖 + 薄外套，早晚加一件长袖。"
    elif avg_tmp >= 15:
        clothing = "天气凉爽：长袖衬衫 + 薄夹克，备一件防风衣。"
    else:
        clothing = "天气偏凉：抓绒 / 卫衣 + 外套，山区可加薄羽绒。"

    # 避雨
    if total_pre is None:
        rain_tip = "降水信息不足，建议出行随身带折叠伞。"
    elif total_pre >= 15:
        rain_tip = "累计降水较大：建议替换室内景点（博物馆、水族馆、商场），室外行程安排雨衣雨具。"
    elif total_pre >= 5:
        rain_tip = "有阵雨：随身带伞，室外行程预留弹性，可灵活切换室内备选。"
    else:
        rain_tip = "降水稀少：适合户外活动，仍建议备一把折叠伞以防局部阵雨。"

    # 最佳时段
    if avg_tmp is not None and avg_tmp >= 28:
        best_hours = "高温：避开 11:00-15:00 正午烈日，最佳游玩时段为 07:00-10:00 与 16:00-19:00，傍晚海边最舒适。"
    elif total_pre is not None and total_pre >= 15:
        best_hours = "多雨：上午雨势通常较小，建议将户外景点安排在上午，下午转入室内场馆。"
    elif avg_tmp is not None and avg_tmp < 15:
        best_hours = "凉爽：全天适宜，正午阳光时段最舒适，早晚温差大注意加衣。"
    else:
        best_hours = "天气整体适宜：上午 09:00-11:00、下午 15:00-18:00 体感最佳，可全程户外。"

    return {"clothing": clothing, "rain_tip": rain_tip, "best_hours": best_hours}


# 自定义景点类别 → 标准卡片区（文化地标/城市海滩/海岛活动/亲子乐园）的映射
# JSON 数据中各城使用了更具本地特色的分类名，这里按语义聚合，不强制改数据。
_CATEGORY_ALIAS = {
    # —— 文化地标 类 ——
    "文化地标": "文化地标", "历史古迹": "文化地标", "人文古迹": "文化地标", "古迹群": "文化地标",
    "皇城古迹": "文化地标", "皇家陵寝": "文化地标", "古城寺庙": "文化地标", "皇家寺庙": "文化地标",
    "宗教建筑": "文化地标", "宗教人文": "文化地标", "寺庙人文": "文化地标", "法式建筑": "文化地标",
    "老城人文": "文化地标", "都市地标": "文化地标", "城市人文": "文化地标", "古都历史": "文化地标",
    "吴哥古迹群": "文化地标", "古神庙人文": "文化地标", "特色人文体验": "文化地标",
    "联动周边": "文化地标", "本岛人文": "文化地标", "中转周边": "文化地标",
    "人文观景": "文化地标", "陆地景点": "文化地标", "陆地人文": "文化地标",
    "市井街区": "文化地标", "夜市购物": "文化地标", "城市街区": "文化地标",
    "休闲市井": "文化地标", "美食市井": "文化地标", "城市市井": "文化地标",
    "滨海湾区": "文化地标", "市井渔村": "文化地标", "人文休闲": "文化地标",
    # —— 城市海滩 类 ——
    "城市海滩": "城市海滩", "城市湖泊": "城市海滩", "核心沙滩": "城市海滩",
    "海岸沙滩": "城市海滩", "海岸海滩": "城市海滩", "环岛海滩": "城市海滩",
    "海岛沙滩": "城市海滩", "本岛海滩": "城市海滩", "南部海滩": "城市海滩",
    "法式山城": "城市海滩", "花海庄园": "城市海滩", "山地景点": "城市海滩",
    "山城云海": "城市海滩", "喀斯特海岸": "城市海滩", "观景打卡": "城市海滩",
    "山城避暑": "城市海滩", "自然景观": "城市海滩", "特色体验": "城市海滩",
    "古城慢游": "城市海滩", "城市花园": "城市海滩", "山林休闲": "城市海滩",
    "徒步观景": "城市海滩", "香江体验": "城市海滩",
    # —— 海岛活动 类 ——
    "海岛活动": "海岛活动", "跳岛出海": "海岛活动", "离岛跳岛": "海岛活动",
    "海岛游玩": "海岛活动", "海上喀斯特": "海岛活动", "游船体验": "海岛活动",
    "海上体验": "海岛活动", "喀斯特山水": "海岛活动", "河滨体验": "海岛活动",
    "度假岛屿": "海岛活动", "特色神庙": "海岛活动", "乌布人文山林": "海岛活动",
    "中转周边出海": "海岛活动", "跳岛潜水": "海岛活动", "周边短途": "海岛活动",
    "湄公河": "海岛活动",
    # —— 亲子乐园 类 ——
    "亲子乐园": "亲子乐园", "都市购物": "亲子乐园", "夜市娱乐": "亲子乐园",
    "中转集散": "亲子乐园", "美食探店": "亲子乐园", "老城漫步": "亲子乐园",
    "滨海休闲": "亲子乐园", "古城联动": "亲子乐园", "躺平海岛": "亲子乐园",
    "度假村躺平": "亲子乐园", "派对体验": "亲子乐园", "美食夜市": "亲子乐园",
    "山水喀斯特": "亲子乐园", "古遗址": "亲子乐园", "短途一日游": "亲子乐园",
    "高原避暑": "亲子乐园", "法式小镇": "亲子乐园", "花海拍照": "亲子乐园",
    "古建筑": "亲子乐园", "人文深度游": "亲子乐园", "免签海岛": "亲子乐园",
    "攀岩": "亲子乐园", "喀斯特": "亲子乐园", "世界遗产": "亲子乐园",
    "历史探索": "亲子乐园", "古城慢游": "亲子乐园", "宗教人文": "亲子乐园",
    "湄公河休闲": "亲子乐园", "南洋人文": "亲子乐园", "多元人文": "亲子乐园",
    "梯田人文": "亲子乐园", "冲浪": "亲子乐园", "婚礼蜜月": "亲子乐园",
    "白沙滩海岛": "亲子乐园", "海上玩乐": "亲子乐园", "落日体验": "亲子乐园",
    "跳岛中转": "亲子乐园", "潜水浮潜": "亲子乐园", "历史遗迹": "亲子乐园",
    "浮潜度假": "亲子乐园", "潜水考证": "亲子乐园", "人字沙滩": "亲子乐园",
    "海岛浮潜": "亲子乐园", "亲子旅行": "亲子乐园", "都市观光": "亲子乐园",
}


def _map_category(custom_key):
    """把数据文件中的自定义类别名映射到 4 个标准卡片区；找不到则默认归入"文化地标"。"""
    return _CATEGORY_ALIAS.get(custom_key, "文化地标")


def filter_spots(spots_data, city, preference, weather_tag, total_pre):
    """
    按偏好排序四大分类，并根据天气动态调整 spot 的 weather_tip：
      - 高温/少雨：突出傍晚 / 户外推荐
      - 多雨：海岛 / 户外 spot 标记"今日降水偏大，建议确认或改室内"
    兼容 JSON 中的任意自定义类别键：通过 _CATEGORY_ALIAS 映射到四个标准卡片区。
    """
    category_order = PREFERENCE_CATEGORY_PRIORITY.get(preference, ["文化地标", "城市海滩", "海岛活动", "亲子乐园"])
    city_spots = spots_data.get(city, {})
    rainy = total_pre is not None and total_pre >= 15
    hot = "高温" in weather_tag

    # 预聚合：把各城自定义类别的 spots 按标准类别合并
    buckets = {"文化地标": [], "城市海滩": [], "海岛活动": [], "亲子乐园": []}
    for custom_key, spots_list in city_spots.items():
        std_cat = _map_category(custom_key)
        for s in spots_list:
            # 保留原始类别名用于 UI 提示（不影响排序）
            buckets[std_cat].append((custom_key, s))

    icon_map = {
        "城市海滩": "🏖️", "文化地标": "🏯", "海岛活动": "⛵", "亲子乐园": "🎠"
    }

    result = []
    for std_cat in category_order:
        bucket = buckets.get(std_cat, [])
        items = []
        for (custom_key, s) in bucket:
            tip = s.get("weather_tip", "")
            extra = ""
            if std_cat == "海岛活动" and rainy:
                extra = "【今日降水偏大，跳岛易停航，建议改室内或确认船班】"
            elif std_cat == "城市海滩" and rainy:
                extra = "【近岸浪大，注意红旗警示】"
            elif hot and std_cat in ("文化地标", "城市海滩"):
                extra = "【高温建议傍晚前往】"
            elif std_cat in ("亲子乐园", "文化地标") and rainy and "室内" in (s.get("desc", "") + tip):
                extra = "【含室内场馆，雨天适宜】"
            items.append({
                "name": s["name"],
                "desc": s["desc"],
                "weather_tip": (tip + " " + extra).strip(),
            })
        # 卡片标题：若标准类别与原始类别名不同，用更"本地化"的名字（保留排序）
        display_name = std_cat
        if bucket:
            first_custom = bucket[0][0]
            # 如果数据中自定义名更短，显示为"标准（本地名）"
            if first_custom != std_cat and len(bucket) <= 2:
                display_name = f"{std_cat} · {first_custom}"
        result.append({
            "name": display_name,
            "icon": icon_map.get(std_cat, "📍"),
            "spots": items,
        })
    # 国内城市（如武汉）没有"海岛活动"这类分区，空卡片不展示
    return [c for c in result if c["spots"]]


def generate_strategy(destination, preference, time_input):
    """主入口：生成完整攻略上下文，供 strategy.html 渲染"""
    city_map = _city_bbox()
    spots_data = _travel_spots()

    city = resolve_city(destination)
    if not city:
        return None

    city_info = city_map[city]
    target_dt, season_label = parse_time_input(time_input, SEASON_MONTH)

    # 取天气
    summary = weather_api.get_weather_summary(target_dt, city_info["bbox"])
    if summary is None:
        summary = _mock_weather(city_info, season_label)

    avg_tmp = summary.get("avg_tmp")
    total_pre = summary.get("total_pre")
    weather_tag = judge_weather(avg_tmp, total_pre)
    advice = build_weather_advice(weather_tag, avg_tmp, total_pre)

    # 绘图（仅真实数据时）
    tmp_url = pre_url = None
    if summary.get("_grid"):
        try:
            tmp_url, pre_url = plot_weather(city, summary["_grid"], summary["_lats"], summary["_lons"], avg_tmp)
        except Exception as e:
            logger.warning("绘图失败: %s", e)

    categories = filter_spots(spots_data, city, preference, weather_tag, total_pre)

    return {
        "destination": city,
        "country": city_info["country"],
        "city_intro": city_info["intro"],
        "fit_tags": city_info["fit_tags"],
        "preference": preference,
        "time_input": time_input or target_dt.strftime("%Y%m%d%H%M"),
        "season_label": season_label,
        "recommend_days": city_info["recommend_days"],
        "best_season": city_info["best_season"],
        "weather": {
            "source": summary["source"],
            "avg_tmp": avg_tmp,
            "max_tmp": summary.get("max_tmp"),
            "min_tmp": summary.get("min_tmp"),
            "total_pre": total_pre,
            "tag": weather_tag,
            "update_time": summary["update_time"],
            "times": summary.get("times", []),
            "tmp_series": summary.get("tmp_series", []),
            "pre_series": summary.get("pre_series", []),
            # 时效与对齐提示（新增）
            "warn_out_of_range": summary.get("warn_out_of_range", False),
            "warn_observation_align": summary.get("warn_observation_align", ""),
            "forecast_availability": summary.get("forecast_availability"),
            "used_climate_fallback": summary.get("source") == "气候默认值",
        },
        "weather_advice": advice,
        "categories": categories,
        "plot_tmp": tmp_url,
        "plot_pre": pre_url,
    }
