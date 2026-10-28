# -*- coding: utf-8 -*-
"""LLM 客户端：调用 OpenAI 兼容的 /chat/completions 接口。
凭据来自 config（.env / 环境变量）。未配置或调用失败时返回 None，
由 qa_engine 回退到关键词问答、由 itinerary_planner 回退到规则行程，保证页面始终可用。
"""
import json
import logging
import re
import requests

from config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
    LLM_TIMEOUT, LLM_MAX_TOKENS, LLM_ENABLED,
)

logger = logging.getLogger("llm_client")


def _clean(text):
    """去除 Qwen3 等思考模型的 <think>...</think> 推理段，仅保留最终回答"""
    if not text:
        return text
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # 残留未闭合的 <think> 起
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()

_SYSTEM_PROMPT = (
    "你是面向武汉及跨境文旅的气象科普与出行助手。"
    "严格区分实时预报、历史回放、人工模拟；无数据不能编造。不能承诺景点预约成功。"
    "工具报错必须如实说明，不得用自己编写的时间线替代失败的工具结果。"
    "请基于提供的『路线当日实况数据』回答用户问题，回答需准确、简洁、实用，"
    "尽量包含成因解释与一句话出行建议。"
    "务必使用与用户提问相同的语言回复（中文提问用中文，英文提问用英文）。"
    "引用实况时使用给定数值；若问题与气象/旅行无关，礼貌引导回气象与旅行话题。"
)


def _build_context(weather, lang):
    w = weather or {}
    from services.live_weather import today
    label = str(w.get("source") or "天气来源未确认")
    parts = [f"{label}: {w.get('city', '—')}"]
    parts += ["今天（北京时间）="+today().isoformat(), "目标日期="+str(w.get("date", "未指定"))]
    if w.get("itinerary"):
        parts.append("已验证行程："+w["itinerary"])
    if w.get("evidence"):
        parts.append("数据依据："+json.dumps(w["evidence"],ensure_ascii=False))
    if w.get("tmp") is not None:
        parts.append(f"温度/Temperature {w['tmp']}℃")
    if w.get("pre") is not None:
        parts.append(f"降水/Precip {w['pre']}mm")
    if w.get("rh") is not None:
        parts.append(f"湿度/Humidity {w['rh']}%")
    if w.get("wind") is not None:
        parts.append(f"风力/Wind {w['wind']}级")
    if w.get("vis") is not None:
        parts.append(f"能见度/Visibility {w['vis']}km")
    if w.get("season"):
        parts.append(f"季节/Season {w['season']}")
    return "；".join(parts) if lang != "en" else " | ".join(parts)


def ask(question, weather, lang="zh"):
    """调用 LLM，成功返回文本，失败/未配置返回 None。"""
    if not LLM_ENABLED:
        return None
    try:
        context = _build_context(weather, lang)
        user_msg = f"{context}\n\n{'用户问题' if lang != 'en' else 'Question'}: {question}"
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.6,
                "max_tokens": LLM_MAX_TOKENS,
                "stream": False,
                **({"thinking": {"type": "disabled"}} if "deepseek.com" in LLM_BASE_URL else {}),
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content")
        return _clean(content) or None
    except Exception as e:
        logger.warning("LLM 调用失败，将回退关键词问答: %s", e)
        return None


# ===================== 工具调用（trip_tool 接入智能体）=====================
def _trip_tools():
    """延迟导入 trip_tool 的工具定义；缺失时返回 None（主站仍可用）。"""
    try:
        from trip_tool import TOOLS
        return TOOLS
    except Exception as e:  # pragma: no cover - 取决于部署环境
        logger.warning("trip_tool 工具定义不可用，问答退化为纯文本: %s", e)
        return None


def _dispatch_tool(name, arguments):
    try:
        from trip_tool import dispatch
    except Exception as e:
        return {"ok": False, "error": "trip_tool 不可用: %s" % e}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
        args.pop("data_dir", None)
        args.pop("weather", None)
        return dispatch(name, args)
    except Exception as e:
        logger.warning("工具 %s 执行失败: %s", name, e)
        return {"ok": False, "error": "工具执行失败: %s" % e}


def ask_with_tools(question, weather, lang="zh", max_rounds=3):
    """带 function-calling 的问答：模型可调用 trip_tool 的 plan_trip / list_spots。

    返回 (text, used_tools)；未配置 / 调用失败返回 (None, False)。
    """
    tools = _trip_tools()
    if not LLM_ENABLED or not tools:
        return None, False
    try:
        context = _build_context(weather, lang)
        system = _SYSTEM_PROMPT
        if lang != "en":
            system += ("你可以调用 plan_trip 工具，按日期排武汉景点顺序（天气→约束→求解）。"
                       "用户要求「规划行程/路线/一天怎么玩」且涉及武汉时，先调用工具再基于工具结果回答；"
                       "不要编造景点顺序与时间。")
        else:
            system += (" You can call the plan_trip tool to order Wuhan sights by date "
                       "(weather -> constraints -> solver). When the user asks for an itinerary "
                       "in Wuhan, call the tool first and answer from its result; never invent times.")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{context}\n\n{'用户问题' if lang != 'en' else 'Question'}: {question}"},
        ]
        used = False
        for _ in range(max_rounds):
            resp = requests.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.4,
                    "max_tokens": LLM_MAX_TOKENS,
                    "stream": False,
                **({"thinking": {"type": "disabled"}} if "deepseek.com" in LLM_BASE_URL else {}),
                },
                timeout=LLM_TIMEOUT,
            )
            resp.raise_for_status()
            choices = (resp.json().get("choices") or [])
            if not choices:
                return None, used
            msg = choices[0].get("message") or {}
            calls = msg.get("tool_calls") or []
            if not calls:
                text = _clean(msg.get("content"))
                return (text or None), used
            used = True
            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": calls,
            })
            for call in calls:
                fn = (call.get("function") or {})
                result = _dispatch_tool(fn.get("name"), fn.get("arguments"))
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result, ensure_ascii=False)[:6000],
                })
        return None, used
    except Exception as e:
        logger.warning("LLM 工具调用失败，将回退: %s", e)
        return None, False


# ===================== 行程规划专用 =====================
_CROWD_LABEL = {
    "free":   ("自由行",   "Independent"),
    "family": ("亲子游",   "Family"),
    "photo":  ("摄影游",   "Photography"),
    "study":  ("研学游",   "Study tour"),
}

_ITINERARY_SYSTEM_ZH = (
    "你是面向东南亚跨境旅行的智能行程规划助手。"
    "请基于给定城市的多日气象实况/预报数据与出行人群，为每天生成『精确时间点 + 具体景点 + 原因说明』的详细时间线。"
    "参考示例（芽庄亲子游·32℃ 晴·正午毒日·傍晚有晚霞）：\n"
    "  07:00-08:00｜芽庄大教堂晨拍｜教堂 7 点开门、清晨光线柔人少，避开正午暴晒，拍照 40-60 分钟；中午闭馆只能早去。市区打车到缆车码头约 15-20 分钟。\n"
    "  08:30｜抵达珍珠岛缆车站，坐跨海缆车上岛（12 分钟）｜赶早班缆车避开排队。\n"
    "  09:00-15:30｜珍珠岛室内水上乐园避暑｜正午最毒，优先室内/有遮阳滑道，18:00 关门不要太晚；放弃高山飞车/机动游戏/动物园/海洋馆以保证核心体验；岛上简餐。\n"
    "  17:20-18:10｜摩天轮看晚霞｜日落前半小时登舱，高空看海湾日落是珍珠岛精华；看完缆车返回市区。\n"
    "严格要求：\n"
    "1. 每天 3-5 条日程条目，每条格式：『HH:MM-HH:MM｜标题｜详细说明』。说明必须包含：时间原因（开门/闭馆/光影/排队）、气象适配（避暑/避雨/防风/避晒）、交通/时间预估、取舍建议（『放弃 XX，保证 YY』），不要空话；\n"
    "2. 时段从 06:30 左右开始到 22:00 前后结束，按人流/光线/气象合理排布；早餐/午餐/晚餐可作为单独条目或嵌入说明；\n"
    "3. 降水≥10mm 的日子：90% 以上条目必须是室内或遮雨场所（商场、博物馆、室内乐园、Spa、咖啡馆），明确说明『避免去 XX 户外』；\n"
    "4. 平均气温≥30℃ 的日子：11:00-16:00 必须安排室内/避暑/水上项目，明确提示『正午不要户外』；\n"
    "5. 风力≥6 级的日子：禁止乘船/出海/高处景点，替换为内陆；\n"
    "6. 同一城市相邻两天内容差异≥60%（第二天换另一片区、另一种主题），禁止复制粘贴；\n"
    "7. 每条还需给出 1 条当日单独的 notes 简短提醒（1-2 句），只讲当天最强风险（防暑药/雨具/排队/防晒/防坑）。\n"
    "8. 输出严格 JSON，不输出任何解释、Markdown、代码块或额外文字。\n"
    "JSON 结构：长度等于输入天数的数组，每个元素 { \"schedule\": [ {\"time\":\"HH:MM-HH:MM\",\"title\":\"...\",\"detail\":\"...\"}, ... ], \"notes\": \"...\" }。"
)

_ITINERARY_SYSTEM_EN = (
    "You are a smart itinerary planner for Southeast Asia cross-border travel. "
    "Based on multi-day weather data, traveler type and city, produce a detailed timeline "
    "with precise time slots + concrete spots + weather-driven reasons per day. "
    "Example reference (Nha Trang family · 32C sunny · harsh midday sun · sunset glow):\n"
    "  07:00-08:00 | Nha Trang Cathedral morning shoot | Doors open at 07:00, soft light & few people; avoid 12:00+ heat, shoot 40-60 min. Cathedral closes at noon - only morning works. Taxi to cable car terminal ~15-20 min.\n"
    "  08:30 | Arrive Vinpearl cable car, ride across bay (12 min) | Take the earliest cable car to skip queues.\n"
    "  09:00-15:30 | Vinpearl indoor water park escape heat | Midday sun is worst - prioritize indoor/shaded slides. Park closes 18:00, don't stay late. SKIP alpine coaster / dry rides / zoo / aquarium to fit; eat light on island.\n"
    "  17:20-18:10 | Ferris wheel sunset viewing | Queue 30 min before sunset; bay sunset view is Vinpearl's highlight; cable car back downtown after.\n"
    "Strict rules:\n"
    "1. 3-5 schedule items per day, each format: 'HH:MM-HH:MM | title | detail'. Detail MUST include: timing reason (opening/closing/light/queues), weather adaptation (cool/rain/wind/sun protection), transit estimate, trade-offs ('skip X to make Y happen');\n"
    "2. Span ~06:30 to ~22:00, ordered by crowds / light / weather; breakfast/lunch/dinner may be standalone items or embedded;\n"
    "3. Precip >=10mm: >=90% items must be indoor or covered (malls, museums, indoor parks, spa, cafes), explicitly say 'avoid X outdoor';\n"
    "4. Avg temp >=30C: 11:00-16:00 MUST be indoor / AC / water activities, explicitly warn 'no outdoor during midday';\n"
    "5. Wind >=6 Bft: no boat / sea trips / high-altitude spots, swap to inland;\n"
    "6. Adjacent days in same city must differ >=60% (next day different district / theme), NO copy-paste;\n"
    "7. Extra 'notes' field per day: 1-2 short sentences on the day's TOP risk (heat meds / rain gear / queues / sun protection / scams);\n"
    "8. Output STRICTLY valid JSON. No explanations. No markdown. No code fences. No extra text.\n"
    "JSON shape: array of length == input days. Each element: { \"schedule\": [ {\"time\":\"HH:MM-HH:MM\",\"title\":\"...\",\"detail\":\"...\"}, ... ], \"notes\": \"...\" }."
)


def _build_itinerary_user(city, days_data, crowd, lang):
    crowd_str = _CROWD_LABEL.get(crowd, _CROWD_LABEL["free"])
    crowd_label = crowd_str[0] if lang != "en" else crowd_str[1]
    if lang != "en":
        lines = [f"Day{i+1} ({d['date']} {d['weekday']}): 平均温度 {d['avg_tmp']}℃, 降水 {d['total_pre']}mm, 天气 {d['tag']}"
                 for i, d in enumerate(days_data)]
        weather_text = "\n".join(lines)
        return (f"城市: {city}\n人群类型: {crowd_label}\n气象数据:\n{weather_text}\n\n"
                f"请生成 {len(days_data)} 天的 JSON 行程数组，仅输出 JSON。")
    lines = [f"Day{i+1} ({d['date']} {d['weekday']}): avg {d['avg_tmp']}C, precip {d['total_pre']}mm, {d['tag']}"
             for i, d in enumerate(days_data)]
    weather_text = "\n".join(lines)
    return (f"City: {city}\nCrowd: {crowd_label}\nWeather:\n{weather_text}\n\n"
            f"Generate a JSON array for {len(days_data)} days. Output JSON only.")


def _parse_itinerary_json(text, expected_len):
    """解析 LLM 返回的 JSON 数组（新版 schedule 格式，兼容旧 morning/afternoon/evening 格式）。

    返回格式统一为 list[dict]，每个元素包含：
      - schedule: list[{time, title, detail}]  新格式；若 LLM 返回旧三段式，则转换为 3 条 schedule
      - notes: str
    失败/空字段返回 None 触发规则回退。
    """
    if not text:
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
    arr = None
    try:
        arr = json.loads(raw)
    except Exception:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                arr = json.loads(m.group(0))
            except Exception:
                arr = None
    if not isinstance(arr, list) or len(arr) < expected_len:
        return None
    plans = []
    for item in arr[:expected_len]:
        if not isinstance(item, dict):
            return None
        notes = str(item.get("notes", "") or "").strip()
        # 1) 新格式：schedule 数组
        schedule = item.get("schedule")
        if isinstance(schedule, list) and schedule:
            sch_items = []
            for s in schedule:
                if not isinstance(s, dict):
                    return None
                t = str(s.get("time", "") or "").strip()
                title = str(s.get("title", "") or "").strip()
                detail = str(s.get("detail", "") or "").strip()
                if not t or not title:
                    return None
                sch_items.append({"time": t, "title": title, "detail": detail})
            if not sch_items:
                return None
            plans.append({"schedule": sch_items, "notes": notes})
            continue
        # 2) 旧格式兼容：morning / afternoon / evening → 3 条 schedule
        morning = str(item.get("morning", "") or "").strip()
        afternoon = str(item.get("afternoon", "") or "").strip()
        evening = str(item.get("evening", "") or "").strip()
        if not (morning and afternoon and evening):
            return None
        plans.append({
            "schedule": [
                {"time": "08:00-11:00", "title": morning,   "detail": ""},
                {"time": "12:00-16:00", "title": afternoon, "detail": ""},
                {"time": "17:00-21:00", "title": evening,   "detail": ""},
            ],
            "notes": notes,
        })
    if len(plans) != expected_len:
        return None
    return plans


def generate_itinerary(city, days_data, crowd, lang="zh"):
    """按城市批量调用 LLM 生成多日行程建议。

    :param city: 城市名
    :param days_data: [{date, weekday, avg_tmp, total_pre, tag, source}, ...]
    :param crowd: free / family / photo / study
    :param lang: zh / en
    :return: list[{schedule:[{time,title,detail}], notes}] 长度等于 days_data；失败/未配置返回 None
    """
    if not LLM_ENABLED or not days_data:
        return None
    try:
        system_prompt = _ITINERARY_SYSTEM_ZH if lang != "en" else _ITINERARY_SYSTEM_EN
        user_msg = _build_itinerary_user(city, days_data, crowd, lang)
        # 新格式需要更多 token，按天数动态放大
        tok_per_day = 900
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.75,
                "max_tokens": max(LLM_MAX_TOKENS, tok_per_day * len(days_data)),
                "stream": False,
                **({"thinking": {"type": "disabled"}} if "deepseek.com" in LLM_BASE_URL else {}),
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content")
        content = _clean(content)
        plans = _parse_itinerary_json(content, len(days_data))
        if plans is None:
            logger.warning("LLM 行程 JSON 解析失败(城市=%s)，回退规则: %s", city, (content or "")[:300])
        return plans
    except Exception as e:
        logger.warning("LLM 行程生成失败(城市=%s)，回退规则: %s", city, e)
        return None


# ===================== 气象研学课堂专用 =====================
_SCIENCE_SYSTEM_ZH = (
    "你是面向文旅出行的气象科普作家。"
    "以给定日期、地点与数据来源为准。预报不能称为实况；不能从凉爽等体感标签推断季节，不得凭温度臆测春季。"
    "缺失要素不能编造，也不能仅由温湿度断言已经出现雾、台风或其他现象；只能解释相关原理及观察条件。"
    "基于提供的『城市 + 当日实况数据』，挑选最贴切的气象主题（如热带季风、海陆风、对流雨、山地逆温/晨雾、"
    "跨境烧山雾霾、南海台风、城市热岛、厄尔尼诺等），撰写一段 80-120 字的成因讲解，并附一句出行建议。"
    "讲解必须：①引用给定的温度/降水/能见度等数值；②科学准确；③通俗易懂。"
    "严格输出 JSON，不要任何解释、Markdown 或代码块。"
    "JSON 结构：{\"title_zh\":\"...\",\"text_zh\":\"...\",\"tip_zh\":\"...\","
    "\"title_en\":\"...\",\"text_en\":\"...\",\"tip_en\":\"...\"}。"
)

_SCIENCE_SYSTEM_EN = (
    "You are a weather-science writer for tourism. Use the supplied date, location and source. "
    "Forecast is not observation. Never infer season from temperature or a comfort label. "
    "Do not invent missing values or assert fog or other unobserved phenomena from temperature and humidity alone. "
    "Based on the given city and live weather, pick the most relevant meteorological topic "
    "(e.g. tropical monsoon, sea-land breeze, convective rain, mountain inversion/fog, "
    "cross-border burning haze, South China Sea typhoon, urban heat island, El Nino) "
    "and write an 80-120 word explanation of its cause plus a one-sentence travel tip. "
    "The explanation MUST: (1) cite the given temperature/precip/visibility values; "
    "(2) be scientifically accurate; (3) be plain and readable. "
    "Output STRICTLY valid JSON. No explanations, no markdown, no code fences. "
    "JSON shape: {\"title_zh\":\"...\",\"text_zh\":\"...\",\"tip_zh\":\"...\","
    "\"title_en\":\"...\",\"text_en\":\"...\",\"tip_en\":\"...\"}."
)


def _build_science_user(city, weather, lang):
    """构造科普请求的用户消息：城市 + 当日实况数值"""
    w = weather or {}
    if lang != "en":
        parts = [f"城市: {city}",f"日期: {w.get('date') or '未指定'}",f"数据来源: {w.get('source') or '未确认'}",f"资料类型: {w.get('mode') or '天气资料，非已证实的现场观测'}"]
        if w.get("tmp") is not None:
            parts.append(f"平均温度 {w['tmp']}℃")
        if w.get("pre") is not None:
            parts.append(f"降水量 {w['pre']}mm")
        if w.get("rh") is not None:
            parts.append(f"湿度 {w['rh']}%")
        if w.get("wind") is not None:
            parts.append(f"风力 {w['wind']}级")
        if w.get("vis") is not None:
            parts.append(f"能见度 {w['vis']}km")
        if w.get("season"):
            parts.append(f"季节 {w['season']}")
        return "所选日期天气资料：\n" + "；".join(parts) + "\n\n请生成中英双语科普 JSON。"
    parts = [f"City: {city}",f"Date: {w.get('date') or 'unspecified'}",f"Source: {w.get('source') or 'unconfirmed'}",f"Data type: {w.get('mode') or 'weather data, not verified onsite observations'}"]
    if w.get("tmp") is not None:
        parts.append(f"Avg temp {w['tmp']}C")
    if w.get("pre") is not None:
        parts.append(f"Precip {w['pre']}mm")
    if w.get("rh") is not None:
        parts.append(f"Humidity {w['rh']}%")
    if w.get("wind") is not None:
        parts.append(f"Wind {w['wind']} Bft")
    if w.get("vis") is not None:
        parts.append(f"Visibility {w['vis']}km")
    if w.get("season"):
        parts.append(f"Season {w['season']}")
    return "Weather for the selected date:\n" + " | ".join(parts) + "\n\nGenerate bilingual science JSON."


def _parse_science_json(text):
    """解析 LLM 返回的科普 JSON。失败返回 None 触发 knowledge_base 回退。"""
    if not text:
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    # 字段完整性校验：至少要有中英 title 与 text
    required = ["title_zh", "text_zh", "title_en", "text_en"]
    if not all(obj.get(k) for k in required):
        return None
    # 文本长度兜底：避免 LLM 输出过短
    if len(obj["text_zh"]) < 20 or len(obj["text_en"]) < 20:
        return None
    return {
        "title_zh": str(obj["title_zh"]).strip(),
        "text_zh": str(obj["text_zh"]).strip(),
        "tip_zh": str(obj.get("tip_zh", "")).strip(),
        "title_en": str(obj["title_en"]).strip(),
        "text_en": str(obj["text_en"]).strip(),
        "tip_en": str(obj.get("tip_en", "")).strip(),
    }


def generate_science_topic(city, weather, lang="zh"):
    """根据当日实况调用 LLM 生成中英双语气象科普知识点。
    :param city: 城市名
    :param weather: {tmp, pre, rh, wind, vis, season} 部分字段可缺
    :param lang: zh / en （决定系统提示词语言）
    :return: {title_zh, text_zh, tip_zh, title_en, text_en, tip_en}；失败/未配置返回 None
    """
    if not LLM_ENABLED:
        return None
    try:
        system_prompt = _SCIENCE_SYSTEM_ZH if lang != "en" else _SCIENCE_SYSTEM_EN
        user_msg = _build_science_user(city, weather, lang)
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.7,
                "max_tokens": LLM_MAX_TOKENS,
                "stream": False,
                **({"thinking": {"type": "disabled"}} if "deepseek.com" in LLM_BASE_URL else {}),
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content")
        content = _clean(content)
        parsed = _parse_science_json(content)
        if parsed is None:
            logger.warning("LLM 科普 JSON 解析失败(城市=%s 日期=%s): %s",
                           city, weather.get("date", "?"), (content or "")[:300])
        return parsed
    except Exception as e:
        logger.warning("LLM 科普生成失败(城市=%s)，回退知识库: %s", city, e)
        return None
