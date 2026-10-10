# -*- coding: utf-8 -*-
"""模块2.2 / 2.3：沿线伴随式气象研学课堂 + 中英双语研学素材导出。
"""
import os
import json
import logging
import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

from config import WEATHER_IMG_DIR

for _f in ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]:
    try:
        matplotlib.rcParams["font.sans-serif"] = [_f]
        matplotlib.rcParams["axes.unicode_minus"] = False
        break
    except Exception:
        pass

logger = logging.getLogger("science_engine")

_KB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge_base.json")

_MOUNTAIN = {"河内", "清迈"}
_COAST = {"芽庄", "岘港", "普吉岛", "胡志明"}


def _load_kb():
    with open(_KB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _pick_knowledge(kb, tmp, pre, rh, wind, vis, city):
    """根据当日气象挑选最贴切的科普知识点 key"""
    if pre and pre >= 25 and (wind or 0) >= 5:
        return "typhoon"
    if vis and vis <= 6 and (rh or 0) < 75 and pre and pre < 3:
        return "haze_burning"
    if pre and pre >= 5:
        return "convective_rain"
    if (vis and vis <= 5) or ((rh or 0) >= 90 and city in _MOUNTAIN):
        return "mountain_inversion"
    if (tmp or 0) >= 28:
        return "monsoon"
    if city in _COAST:
        return "sea_breeze"
    return "monsoon"


def companion_push(route_forecast, lang="zh"):
    """对路线逐日推送伴随式实景知识点（中英双语）

    优先调用 LLM 基于当日实况动态生成；LLM 未配置或失败时，
    回退到 knowledge_base.json 模板（按气象要素挑选主题）。
    """
    from services.forecast_service import _derive_wind, _derive_visibility
    from services.llm_client import generate_science_topic
    kb = _load_kb()
    items = []
    for seg in route_forecast.get("segments", []):
        city = seg["city"]
        for d in seg["days"]:
            tmp = d.get("avg_tmp")
            pre = d.get("total_pre") or 0
            # 取该日首行派生湿度/风/能见度
            row = (d.get("rows") or [{}])[0]
            rh = row.get("rh")
            wind = row.get("wind") or _derive_wind(pre, 12)
            vis = row.get("vis") or _derive_visibility(pre, rh or 78, 12)

            # 1) 优先 LLM 动态生成（缓存键：城市+日期+关键气象值，避免页面刷新重复调用）
            cache_key = (city, d["date"], tmp, pre, vis, lang)
            cached = _SCIENCE_CACHE.get(cache_key)
            if cached is None:
                weather = {
                    "tmp": tmp, "pre": pre, "rh": rh,
                    "wind": wind, "vis": vis, "season": d.get("tag"),
                    "date": d["date"],
                }
                try:
                    cached = generate_science_topic(city, weather, lang)
                except Exception as e:
                    logger.warning("LLM 科普异常(城市=%s 日期=%s): %s", city, d["date"], e)
                    cached = None
                if cached is not None:
                    _SCIENCE_CACHE[cache_key] = cached
                    if len(_SCIENCE_CACHE) > _SCIENCE_CACHE_MAX:
                        # 简单 FIFO：丢弃最早的键
                        _SCIENCE_CACHE.pop(next(iter(_SCIENCE_CACHE)))

            if cached is not None:
                items.append({
                    "city": city,
                    "date": d["date"],
                    "reason": _reason("llm_generated", tmp, pre, vis, lang),
                    "title": cached["title_zh"] if lang != "en" else cached["title_en"],
                    "title_en": cached["title_en"],
                    "title_zh": cached["title_zh"],
                    "text": cached["text_zh"] if lang != "en" else cached["text_en"],
                    "text_en": cached["text_en"],
                    "text_zh": cached["text_zh"],
                    "tip": cached["tip_zh"] if lang != "en" else cached["tip_en"],
                    "source": "llm",
                })
                continue

            # 2) 回退：knowledge_base.json 模板
            key = _pick_knowledge(kb, tmp, pre, rh, wind, vis, city)
            kp = kb.get(key, {})
            items.append({
                "city": city,
                "date": d["date"],
                "reason": _reason(key, tmp, pre, vis, lang),
                "title": kp.get("title", {"zh": key, "en": key}).get(lang, key),
                "title_en": kp.get("title", {}).get("en", key),
                "title_zh": kp.get("title", {}).get("zh", key),
                "text": kp.get("text", {}).get(lang, ""),
                "text_en": kp.get("text", {}).get("en", ""),
                "text_zh": kp.get("text", {}).get("zh", ""),
                "tip": kp.get("tip", {}).get(lang, ""),
                "source": "kb",
            })
    return items


# 进程内缓存：键=(city, date, tmp, pre, vis, lang)，值=LLM 解析后的 dict
_SCIENCE_CACHE = {}
_SCIENCE_CACHE_MAX = 64


def _reason(key, tmp, pre, vis, lang):
    zhs = {
        "convective_rain": f"当日降水约{pre}mm，触发对流雨讲解",
        "mountain_inversion": f"能见度约{vis}km，触发山地逆温/晨雾讲解",
        "monsoon": f"气温约{tmp}℃，触发热带季风讲解",
        "typhoon": "强风强雨，触发台风讲解",
        "haze_burning": f"能见度低约{vis}km且偏干，触发烧山雾霾讲解",
        "sea_breeze": "沿海点位，触发海陆风讲解",
        "llm_generated": f"AI 基于当日实况({tmp}℃·{pre}mm·{vis}km)动态生成",
    }
    ens = {
        "convective_rain": f"~{pre}mm rain triggers convective-rain explain",
        "mountain_inversion": f"~{vis}km vis triggers inversion/fog explain",
        "monsoon": f"~{tmp}°C triggers monsoon explain",
        "typhoon": "strong wind/rain triggers typhoon explain",
        "haze_burning": f"low vis ~{vis}km & dry triggers haze explain",
        "sea_breeze": "coastal point triggers sea-breeze explain",
        "llm_generated": f"AI generated from live weather ({tmp}C · {pre}mm · {vis}km)",
    }
    return (zhs if lang != "en" else ens).get(key, "")


# ----------------------------- 研学素材导出 -----------------------------
def build_handbook(route_forecast, landscapes, lang="zh"):
    L = lang
    title = "跨境气象研学手册" if L != "en" else "Cross-border Weather Study Handbook"
    lines = [f"# {title}", ""]
    lines.append(f"> {'生成时间' if L != 'en' else 'Generated'}: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"## {'一、行程连贯气象总览' if L != 'en' else '1. Coherent route weather overview'}")
    for seg in route_forecast.get("segments", []):
        lines.append(f"\n### {seg['city']} ({seg['country']})")
        for d in seg["days"]:
            lines.append(f"- {d['date']} ({d['weekday']}): {'均温' if L!='en' else 'avg'} {d['avg_tmp']}℃ / "
                         f"{'降水' if L!='en' else 'precip'} {d['total_pre']}mm ({d['source']})")

    if landscapes:
        lines.append(f"\n## {'二、特色景观观赏概率' if L != 'en' else '2. Featured landscape probability'}")
        for l in landscapes:
            lines.append(f"- **{l['name']}** ({l['city']}): {'概率' if L!='en' else 'prob'} {l['prob']}% "
                         f"({l['prob_label']}) · {'窗口' if L!='en' else 'window'} {l['window']}")
            lines.append(f"  - {l['principle'] if L!='en' else l['principle_en']}")

    # 科普
    push = companion_push(route_forecast, L)
    if push:
        lines.append(f"\n## {'三、沿线实景知识点' if L != 'en' else '3. Field knowledge along route'}")
        for it in push:
            lines.append(f"\n### {it['city']} · {it['date']} — {it['title']}")
            lines.append(it["text"])

    lines.append(f"\n## {'四、户外观测提示' if L != 'en' else '4. Field observation tips'}")
    lines.append("- " + ("携带温湿度计/风速仪/雨量筒；每2小时记录一次。" if L != "en" else "Bring thermo-hygrometer, anemometer, rain gauge; log every 2 hours."))
    lines.append("- " + ("雨天远离河道与陡坡；高温及时补水避暑。" if L != "en" else "Stay off riverbanks/slopes in rain; hydrate and avoid heat."))
    return "\n".join(lines)


def build_observation_record(route_forecast, lang="zh"):
    L = lang
    head = "户外气象观测记录表" if L != "en" else "Field Weather Observation Record"
    cols = ["日期 Date", "地点 Location", "时间 Time", "温度℃ Temp", "降水mm Precip", "湿度% RH", "风力 Wind", "能见度km Vis", "云状 Cloud", "备注 Notes"]
    lines = [f"# {head}", "", "| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for seg in route_forecast.get("segments", []):
        for d in seg["days"]:
            for r in (d.get("rows") or [])[:4]:  # 每日取4个代表时次
                lines.append("| " + " | ".join([
                    d["date"], seg["city"], str(r.get("time", "")),
                    str(r.get("tmp", "")), str(r.get("pre", "")), str(r.get("rh", "")),
                    str(r.get("wind", "")), str(r.get("vis", "")), "", "",
                ]) + " |")
    return "\n".join(lines)


def build_question_bank(lang="zh"):
    L = lang
    title = "气象科普题库" if L != "en" else "Weather Science Quiz Bank"
    qa = [
        ("对流雨通常发生在一天中的哪个时段？为什么？",
         "What time of day does convective rain usually occur and why?",
         "午后至傍晚；地表被太阳强辐射加热，暖湿空气上升凝结成积雨云。",
         "Afternoon/evening; solar heating lifts warm moist air into cumulonimbus."),
        ("山地逆温为何容易形成晨雾？",
         "Why does mountain inversion favor morning fog?",
         "夜间冷空气下沉聚集谷底形成逆温，水汽饱和凝结成雾。",
         "Cold air drains into valleys forming inversion; moisture saturates into fog."),
        ("中南半岛雨季主要由什么季风带来？",
         "Which monsoon brings the wet season to Indochina?",
         "西南季风（5-10月）。",
         "The southwest monsoon (May–Oct)."),
        ("台风形成需要哪些基本条件？",
         "What conditions are needed for typhoon formation?",
         "高海温(≥26.5℃)、低垂直风切变、足够的地转偏向力。",
         "Warm SST (≥26.5°C), low vertical wind shear, sufficient Coriolis force."),
        ("跨境烧山雾霾的主要成分及危害？",
         "Main component and harm of cross-border burning haze?",
         "PM2.5；降低能见度、刺激呼吸道、加剧心血管疾病。",
         "PM2.5; reduces visibility, irritates airways, worsens cardiovascular disease."),
    ]
    lines = [f"# {title}", ""]
    for i, (qz, qe, az, ae) in enumerate(qa, 1):
        q = qz if L != "en" else qe
        a = az if L != "en" else ae
        lines.append(f"## {i}. {q}")
        lines.append(f"- {'参考答案' if L != 'en' else 'Answer'}: {a}")
        lines.append("")
    return "\n".join(lines)


def build_diagram(lang="zh"):
    """简易气象示意图：对流雨形成示意"""
    import hashlib
    try:
        fig, ax = plt.subplots(figsize=(7, 5), dpi=110)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")
        # 地表
        ax.add_patch(Rectangle((0, 0), 10, 1.2, color="#f4a460"))
        # 海洋/水汽
        ax.text(1.2, 0.6, ("水汽蒸发" if lang != "en" else "Evaporation"), fontsize=9, color="#1f78b4")
        # 上升气流
        ax.add_patch(FancyArrowPatch((2, 1.2), (4, 7), arrowstyle="-|>", mutation_scale=22, color="#e67e22", lw=2))
        ax.text(4.2, 4.2, ("上升气流" if lang != "en" else "Updraft"), fontsize=9, color="#e67e22")
        # 积雨云
        ax.add_patch(plt.Circle((5, 7.5), 1.4, color="#95a5a6", alpha=0.8))
        ax.add_patch(plt.Circle((6.2, 7.8), 1.1, color="#7f8c8d", alpha=0.8))
        ax.text(5.2, 7.5, ("积雨云" if lang != "en" else "Cumulonimbus"), fontsize=9, color="white", ha="center")
        # 降水
        ax.add_patch(FancyArrowPatch((6, 6.4), (6, 1.4), arrowstyle="-|>", mutation_scale=18, color="#3498db", lw=2))
        ax.text(6.2, 3.5, ("对流雨" if lang != "en" else "Convective rain"), fontsize=9, color="#3498db")
        # 下沉气流
        ax.add_patch(FancyArrowPatch((8, 6.5), (8, 1.4), arrowstyle="-|>", mutation_scale=18, color="#7f8c8d", lw=1.5))
        ax.text(8.1, 4.0, ("下沉气流" if lang != "en" else "Downdraft"), fontsize=9, color="#555")
        # 太阳
        ax.add_patch(plt.Circle((1.2, 9), 0.4, color="#f1c40f"))
        ax.text(0.4, 9.6, ("太阳加热" if lang != "en" else "Solar heating"), fontsize=9, color="#c0392b")
        ax.set_title(("对流雨形成示意图" if lang != "en" else "Convective Rain Formation"), fontsize=12)
        fig.tight_layout()
        key = hashlib.md5(b"convective").hexdigest()[:6]
        path = os.path.join(WEATHER_IMG_DIR, f"diagram_{key}.png")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path
    except Exception as e:
        logger.warning("示意图生成失败: %s", e)
        plt.close("all")
        return None
