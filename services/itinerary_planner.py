# -*- coding: utf-8 -*-
"""模块1.3：分人群气象驱动智能行程规划。
依据整程逐时预报 + 出行人群，生成每日早/中/晚行程建议，规避台风暴雨雾霾，标注边境道路雨雾滑坡风险，
亲子高温推荐室内避暑、雨天替换户外，摄影依据景观窗口调整，研学预留气象观测时间。

LLM 接入：优先按城市批量调用 LLM 生成多日行程（参考 qa_engine 模式），
LLM 未配置/调用失败/解析异常时回退到下面的规则行程，保证页面始终可用。
"""
import logging

from services import llm_client
from services.travel_engine import judge_weather, _load_json, resolve_city
from config import TRAVEL_SPOTS_FILE

logger = logging.getLogger("itinerary_planner")

# 城市对应的边境/山区道路风险备注（中英）
_ROAD_RISK = {
    "河内": {"zh": "北部山区边境公路雨雾易滑坡，能见度低谨慎夜行。", "en": "Northern mountain border roads prone to landslide in rain/fog; avoid night driving."},
    "清迈": {"zh": "山区弯道多雨雾湿滑，泰北边境段注意落石。", "en": "Mountain curves are slippery in rain/fog; watch falling rocks on northern routes."},
    "岘港": {"zh": "海云岭段雨季多雾能见度低，铁路沿海段注意晚点。", "en": "Hai Van Pass is foggy in wet season; coastal rail may be delayed."},
    "芽庄": {"zh": "沿海1号公路雨季偶有积水，跳岛船班受风浪影响。", "en": "Coastal Hwy 1 may flood in wet season; island ferry services depend on sea state."},
    "普吉岛": {"zh": "雨季山路湿滑，海岛跳船受风浪与季风涌浪影响。", "en": "Mountain roads slippery in wet season; island hopping depends on swell and wind."},
    "胡志明": {"zh": "雨季城市内涝频发，航班受对流影响易延误。", "en": "Urban flooding common in wet season; flights may be delayed by convection."},
    "曼谷": {"zh": "雨季市区短时内涝，地铁/天铁影响小但路面拥堵。", "en": "Brief urban flooding in wet season; transit mostly unaffected but roads congested."},
}


def _spots_of(city):
    data = _load_json(TRAVEL_SPOTS_FILE)
    return data.get(city, {})


def _pick(city, category, idx=0):
    cats = _spots_of(city)
    spots = cats.get(category, [])
    if spots:
        return spots[idx % len(spots)]["name"]
    return None


def _bilingual(zh, en, lang):
    return zh if lang != "en" else en


def plan(route_forecast, crowd, lang="zh"):
    """
    :param route_forecast: build_route_forecast() 的返回值
    :param crowd: free/family/photo/study
    :return: {days, road_risk, crowd, source} 其中 source 标识建议来源
             ('llm' / 'rule' / 'mixed')，供前端展示；
             days 每个元素含 schedule:[{time,title,detail}], notes 字段。
    """
    segments = route_forecast.get("segments", [])
    plan_days = []
    sources = []  # 每座城市的来源 'llm' or 'rule'

    for seg in segments:
        city = seg["city"]
        days_data = [{
            "city": city,
            "country": seg["country"],
            "date": d["date"],
            "weekday": d["weekday"],
            "avg_tmp": d["avg_tmp"],
            "total_pre": d["total_pre"],
            "tag": judge_weather(d["avg_tmp"], d["total_pre"]),
            "source": d["source"],
        } for d in seg["days"]]

        if city == "武汉":
            from trip_tool.contract import dispatch
            for d in days_data:
                result = dispatch("plan_trip", {"date":d["date"],"max_spots":4})
                if result.get("ok"):
                    sch = [{"time":s["arrive"]+"–"+s["leave"],"title":s["name"],"detail":s["reason"]} for s in result["days"][0]["stops"]]
                    notes = "；".join(result["warnings"][:5]) or "出发前更新预报并确认景区公告和预约。"
                else:
                    sch=[];notes=result.get("error","暂未生成可行行程")
                plan_days.append(dict(d,schedule=sch,notes=notes))
            sources.append("tool")
            continue

        # 优先按城市批量调 LLM
        llm_plans = llm_client.generate_itinerary(city, days_data, crowd, lang)
        if llm_plans is not None and len(llm_plans) == len(days_data):
            sources.append("llm")
            for d, p in zip(days_data, llm_plans):
                merged = {**d, **p}
                merged["notes"] = "AI 行程灵感：景点开放、预约与交通尚未校验；请核实后采用。" + (merged.get("notes") or "")
                # notes 兜底：LLM 偶尔会漏，用规则补
                if not merged.get("notes"):
                    merged["notes"] = _route_plan_for_day(d, crowd, lang)["notes"]
                plan_days.append(merged)
            logger.info("城市=%s 使用 LLM 生成 %d 天行程", city, len(days_data))
        else:
            sources.append("rule")
            for d in days_data:
                plan_days.append(_route_plan_for_day(d, crowd, lang))
            logger.info("城市=%s 使用规则回退生成 %d 天行程", city, len(days_data))

    road_risk = _collect_road_risk(segments, lang)
    if sources and all(s == "tool" for s in sources):
        source = "tool"
    elif all(s == "llm" for s in sources):
        source = "llm"
    elif all(s == "rule" for s in sources):
        source = "rule"
    else:
        source = "mixed"
    return {"days": plan_days, "road_risk": road_risk, "crowd": crowd, "source": source}


def _route_plan_for_day(day, crowd, lang):
    """规则回退版：返回 day dict（含 schedule:[{time,title,detail}], notes）
    与 LLM 新格式保持一致，便于模板统一渲染。
    """
    pre = day["total_pre"] or 0
    tmp = day["avg_tmp"]
    rainy = pre >= 10
    hot = (tmp or 0) >= 30
    city = day["city"]

    # 按分人群函数取回 (morning_title, afternoon_title, evening_title, notes_text)
    if crowd == "free":
        m, a, e, notes_text = _free_plan(city, day["tag"], rainy, hot, lang)
    elif crowd == "family":
        m, a, e, notes_text = _family_plan(city, day["tag"], rainy, hot, lang)
    elif crowd == "photo":
        m, a, e, notes_text = _photo_plan(city, day["tag"], rainy, hot, lang)
    elif crowd == "study":
        m, a, e, notes_text = _study_plan(city, day["tag"], rainy, hot, lang)
    else:
        g = _bilingual("常规观光", "Sightseeing", lang)
        m, a, e, notes_text = g, g, g, g

    # 三段式标题 → 规则版 schedule（比 LLM 简洁但结构一致）
    if lang != "en":
        detail_m = (f"天气：{day['tag']}。建议晨间光线/人流最适合，带雨伞和饮水；打车约 15 分钟，先玩此段。"
                    if not rainy and not hot else
                    (f"降水≥{pre:.0f}mm，晨间若雨势小可短时户外，否则改室内。" if rainy
                     else f"最高{tmp}℃炎热，晨间户外先逛以避正午毒日。"))
        detail_a = f"核心时段：12-16 点。{('降水≥10mm 替换室内为主；' if rainy else '')}{('≥30℃ 正午避开户外，优先空调场所；' if hot else '')}途中含午餐。"
        detail_e = "傍晚气温回落，适合夜景、海滨或夜市；注意返程末班车时间，餐饮后留余裕。"
    else:
        detail_m = (f"Weather: {day['tag']}. Morning is best for light and crowds; bring umbrella and water; taxi ~15 min, start here."
                    if not rainy and not hot else
                    (f"Precip {pre:.0f}mm; keep morning short if light rain, else indoor." if rainy
                     else f"Hot high {tmp}C; start outdoor early to avoid midday sun."))
        detail_a = f"Core 12-16. {'Swap to mostly indoor (precip≥10mm); ' if rainy else ''}{'Avoid outdoor at noon (≥30C), prefer AC; ' if hot else ''}includes lunch."
        detail_e = "Evening cools down, good for night view, seaside or night market; note last transit, leave buffer after dinner."

    return {
        **day,
        "schedule": [
            {"time": "08:00-11:00", "title": m, "detail": detail_m},
            {"time": "12:00-16:00", "title": a, "detail": detail_a},
            {"time": "17:00-21:00", "title": e, "detail": detail_e},
        ],
        "notes": notes_text,
    }


def _free_plan(city, tag, rainy, hot, lang):
    risk = _bilingual(
        f"避开台风/持续暴雨与烧山雾霾时段；{_ROAD_RISK.get(city, _ROAD_RISK['河内'])['zh']}",
        f"Avoid typhoon/heavy rain and burning haze; {_ROAD_RISK.get(city, _ROAD_RISK['河内'])['en']}",
        lang)
    if rainy:
        m = _bilingual("上午雨小安排户外，午后转室内", "Outdoor in the morning (less rain), indoor afternoon", lang)
    elif hot:
        m = _bilingual("上午户外游览，正午避暑", "Outdoor sightseeing in the morning; avoid midday heat", lang)
    else:
        m = _bilingual("全天适宜户外，自由探索", "Full day suits outdoor exploration", lang)
    a = _pick(city, "文化地标") or _bilingual("城区地标", "City landmarks", lang)
    e = _bilingual("夜市/海滨漫步", "Night market / seaside walk", lang)
    return m, a, e, risk


def _family_plan(city, tag, rainy, hot, lang):
    indoor = _pick(city, "亲子乐园") or _bilingual("室内展馆", "Indoor venues", lang)
    outdoor = _pick(city, "城市海滩") or _bilingual("海滨", "Seaside", lang)
    med = _bilingual(
        "随身备防暑药、止泻药、儿童防晒；暴雨留意就近避险点(商场/医院)。",
        "Carry heatstroke/diarrhea meds and child sun protection; note nearby shelter (mall/hospital) in storms.",
        lang)
    if hot:
        m = _bilingual(f"上午前往室内避暑：{indoor}", f"Morning indoor cooling: {indoor}", lang)
        a = _bilingual("午后高温建议室内展馆/动物园", "Hot afternoon: indoor venues / zoo", lang)
        e = outdoor if not rainy else indoor
    elif rainy:
        m = indoor
        a = _bilingual("雨天替换户外为室内", "Swap outdoor for indoor in rain", lang)
        e = _bilingual("商场亲子区/室内餐饮", "Mall family zone / indoor dining", lang)
    else:
        m = outdoor
        a = _pick(city, "亲子乐园") or outdoor
        e = _bilingual("亲子乐园傍晚场", "Family park evening session", lang)
    return m, a, e, med


def _photo_plan(city, tag, rainy, hot, lang):
    fog_note = _bilingual("晨雾时段适合拍摄山雾与水面倒影", "Morning fog is great for mountain mist and reflections", lang)
    sunset_note = _bilingual("傍晚晚霞窗口前就位，注意日落方位", "Arrive before sunset glow window; mind sunset azimuth", lang)
    if rainy:
        m = _bilingual("雨后通透与水洼倒影拍摄", "Shoot clarity after rain and puddle reflections", lang)
    else:
        m = fog_note if city in ("河内", "清迈") else _bilingual("日出黄金时段拍摄", "Sunrise golden-hour shooting", lang)
    a = _bilingual("正午强光休息，记录对流程云", "Rest in harsh midday light; capture convective clouds", lang)
    e = sunset_note
    notes = _bilingual("平衡拍摄体验与出行安全，雷雨停止登高/出海。", "Balance shooting and safety; stop climbing/sea trips in thunderstorms.", lang)
    return m, a, e, notes


def _study_plan(city, tag, rainy, hot, lang):
    geo = _bilingual(
        "优先匹配特色地貌点位，预留气象实地观测(温/湿/风记录)时间。",
        "Prioritize geo-landmarks; reserve field weather-observation time (temp/humidity/wind).",
        lang)
    m = _pick(city, "文化地标") or _bilingual("地貌/人文观测点", "Geo/cultural observation point", lang)
    if rainy:
        a = _bilingual("观测对流雨过程，记录降水强度变化", "Observe convective rain, log rainfall intensity changes", lang)
    elif hot:
        a = _bilingual("观测海陆风/午后对流云发展", "Observe sea breeze and afternoon convective cloud growth", lang)
    else:
        a = _bilingual("实地温湿风观测与样方记录", "Field temp/humidity/wind observation and quadrat logging", lang)
    e = _bilingual("整理观测数据，讨论成因", "Compile data and discuss formation", lang)
    return m, a, e, geo


def _collect_road_risk(segments, lang):
    out = []
    for seg in segments:
        city = seg["city"]
        risk = _ROAD_RISK.get(city)
        if risk:
            out.append({"city": city, "text": risk["zh"] if lang != "en" else risk["en"]})
    return out
