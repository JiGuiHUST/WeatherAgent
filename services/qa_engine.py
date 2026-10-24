# -*- coding: utf-8 -*-
"""模块2.1：中英交互式气象智能问答。
优先调用真实 LLM（OpenAI 兼容接口，见 services/llm_client.py），
LLM 未配置或调用失败时回退到关键词问答，保证页面始终可用。
"""
import datetime
import json
import os
import re
import logging

from config import LLM_ENABLED
from services import llm_client
from services.forecast_service import _derive_wind, _derive_visibility

logger = logging.getLogger("qa_engine")

_QA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "qa_knowledge.json")

_ANIM = {
    "convective_rain": "anim-rain",
    "monsoon": "anim-wind",
    "typhoon": "anim-storm",
    "haze": "anim-haze",
    "fog": "anim-fog",
    "general": None,
}


def _load():
    with open(_QA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _detect_topic(question):
    """轻量关键词检测，用于选择演示动图（与问答来源无关）"""
    q = (question or "").lower()
    mapping = {
        "convective_rain": ["对流雨", "午后下雨", "阵雨", "convective", "afternoon rain", "thunderstorm"],
        "monsoon": ["季风", "雨季", "旱季", "monsoon", "wet season", "dry season"],
        "typhoon": ["台风", "风暴", "typhoon", "cyclone", "storm"],
        "haze": ["雾霾", "烧山", "pm2.5", "能见度低", "haze", "burning", "smoke"],
        "fog": ["雾", "晨雾", "能见度", "fog", "mist"],
    }
    best, best_score = "general", 0
    for topic, kws in mapping.items():
        s = sum(len(k) for k in kws if k.lower() in q)
        if s > best_score:
            best, best_score = topic, s
    return best


def answer(question, weather, lang="zh"):
    """
    :param question: 用户提问文本
    :param weather: {city, tmp, pre, rh, season, wind, vis}
    :return: {topic, source, answer, anim}
    """
    topic = _detect_topic(question)
    anim = _ANIM.get(topic)

    # 0) 行程类问题：直接调用 trip_tool（不依赖大模型，结果可复现）
    trip = _try_trip_tool(question, lang)
    if trip:
        return {"topic": "trip", "source": "tool", "answer": trip, "anim": anim}

    # 1) 优先真实 LLM（带 trip_tool 工具调用能力）
    llm_text = None
    if LLM_ENABLED:
        llm_text, _ = llm_client.ask_with_tools(question, weather, lang)
        if not llm_text:
            llm_text = llm_client.ask(question, weather, lang)
    if llm_text:
        return {"topic": topic, "source": "llm", "answer": llm_text, "anim": anim}

    # 2) 回退关键词问答
    logger.info("使用关键词问答回退")
    return {"topic": topic, "source": "keyword", "answer": _keyword_answer(question, weather, lang), "anim": anim}


# ===================== 行程工具接入（意图识别 + 结果转述）=====================
_TRIP_HINT = ("行程", "路线", "规划", "安排", "怎么玩", "玩一天", "一日游", "两日游",
              "itinerary", "plan", "route", "schedule")
_TRIP_CITY_HINT = ("武汉", "wuhan", "黄鹤楼", "东湖", "楚河汉街", "户部巷", "昙华林", "归元寺")


def _extract_date(text):
    """从提问里抽 YYYY-MM-DD；支持 2026-10-25 / 2026/10/25 / 2026年10月25日 / 10月25日"""
    m = re.search(r"(20\d{2})\s*[-/年\.]\s*(\d{1,2})\s*[-/月\.]\s*(\d{1,2})", text or "")
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text or "")
        if not m:
            return None
        y, mo, d = datetime.date.today().year, int(m.group(1)), int(m.group(2))
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _wants_wuhan_trip(question):
    q = (question or "").lower()
    return any(k in q for k in _TRIP_CITY_HINT) and any(k in q for k in _TRIP_HINT)


def _format_trip_plan(plan, lang):
    """把 trip_tool 的结果转成一段可直接展示的回答"""
    if not plan or not plan.get("ok"):
        return None
    days = plan.get("days") or []
    solver = plan.get("solver", "—")
    if lang == "en":
        lines = ["Planned with the trip tool (solver: %s, %d ms)." % (solver, plan.get("elapsed_ms", 0))]
        for day in days:
            w = day.get("weather", {})
            rain = ("rain %s-%sh" % (w.get("rain_start"), (w.get("rain_end") or 0) + 1)
                    if w.get("rain_start") is not None else "no rain")
            lines.append("%s %s · %s, feels-like max %s℃" % (day["date"], day["weekday"], rain, w.get("feels_max")))
            for s in day.get("stops") or []:
                lines.append("  %d. %s–%s %s (%d min, fit %d) — %s"
                             % (s["seq"], s["arrive"], s["leave"], s["name"],
                                s.get("stay_min", 0), s.get("suitability", 0), s.get("reason", "")))
            t = day.get("totals") or {}
            lines.append("  total %s min / %s km, ends %s"
                         % (t.get("travel_min"), t.get("travel_km"), t.get("end_time")))
        return "\n".join(lines)

    summary = (plan.get("summary_text") or "").strip()
    head = "已调用行程工具（求解器 %s，%d ms）：" % (solver, plan.get("elapsed_ms", 0))
    tail = ""
    if plan.get("warnings"):
        tail = "\n提示：" + "；".join(plan["warnings"])
    return head + "\n" + (summary or "（未生成可行路线）") + tail


def _try_trip_tool(question, lang="zh"):
    if not _wants_wuhan_trip(question):
        return None
    try:
        from trip_tool import plan_trip
    except Exception as e:
        logger.warning("trip_tool 不可用: %s", e)
        return None
    date = _extract_date(question) or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    max_spots = 4
    m = re.search(r"(\d)\s*个?景点", question or "")
    if m:
        max_spots = max(2, min(6, int(m.group(1))))
    try:
        plan = plan_trip(date, max_spots=max_spots)
    except Exception as e:
        logger.warning("trip_tool 规划失败: %s", e)
        return None
    return _format_trip_plan(plan, lang)


def _keyword_answer(question, weather, lang="zh"):
    kb = _load()
    q = (question or "").lower()
    best, best_score = "general", 0
    for tpc, entry in kb.items():
        s = 0
        for kw in entry.get("keywords", []):
            if kw.lower() in q:
                s += len(kw)
        if s > best_score:
            best, best_score = tpc, s
    entry = kb[best]

    w = dict(weather or {})
    city = w.get("city") or ("芽庄" if lang != "en" else "Nha Trang")
    tmp = w.get("tmp") if w.get("tmp") is not None else 27
    pre = w.get("pre") if w.get("pre") is not None else 3
    rh = w.get("rh") or 78
    season = w.get("season") or ("当前季节" if lang != "en" else "current season")
    wind = w.get("wind") if w.get("wind") is not None else _derive_wind(pre, 14)
    vis = w.get("vis") if w.get("vis") is not None else _derive_visibility(pre, rh, 14)

    tmpl = entry["answer"][lang if lang in entry["answer"] else "zh"]
    advice_text = entry.get("advice", {}).get(lang) or entry.get("advice", {}).get("zh", "")
    return tmpl.format(city=city, tmp=tmp, pre=pre, wind=wind, vis=vis, season=season, advice=advice_text)


def example_questions(lang="zh"):
    if lang == "en":
        return [
            "Plan my Wuhan day trip tomorrow, avoiding the rain",
            "Why convective rain in the afternoon?",
            "What causes the dry/wet monsoon seasons?",
            "How does cross-border burning haze form?",
            "Why morning fog in mountain valleys?",
            "When do South China Sea typhoons strike?",
        ]
    return [
        "帮我规划明天的武汉一日游，避开下雨时段",
        "为什么东南亚午后常下对流雨？",
        "季风是怎么形成的？",
        "跨境烧山雾霾是怎么形成的？",
        "山谷为什么容易起晨雾？",
        "南海台风一般在什么季节出现？",
    ]
