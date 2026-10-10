# -*- coding: utf-8 -*-
"""模块2.1：中英交互式气象智能问答。
优先调用真实 LLM（OpenAI 兼容接口，见 services/llm_client.py），
LLM 未配置或调用失败时回退到关键词问答，保证页面始终可用。
"""
import json
import os
import logging

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

    # 1) 优先真实 LLM
    llm_text = llm_client.ask(question, weather, lang)
    if llm_text:
        return {"topic": topic, "source": "llm", "answer": llm_text, "anim": anim}

    # 2) 回退关键词问答
    logger.info("使用关键词问答回退")
    return {"topic": topic, "source": "keyword", "answer": _keyword_answer(question, weather, lang), "anim": anim}


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
            "Why convective rain in the afternoon?",
            "What causes the dry/wet monsoon seasons?",
            "How does cross-border burning haze form?",
            "Why morning fog in mountain valleys?",
            "When do South China Sea typhoons strike?",
        ]
    return [
        "为什么东南亚午后常下对流雨？",
        "季风是怎么形成的？",
        "跨境烧山雾霾是怎么形成的？",
        "山谷为什么容易起晨雾？",
        "南海台风一般在什么季节出现？",
    ]
