# -*- coding: utf-8 -*-
"""工具契约：给智能体/HTTP 的入参定义、校验与分发。

只暴露两个工具：
    plan_trip   输入一个日期 → 输出按天气优化的游览顺序
    list_spots  查有哪些景点（让模型在规划前先"看得见"数据）
"""
from __future__ import annotations

import datetime as _dt

from . import planner

PLAN_TRIP = {
    "type": "function",
    "function": {
        "name": "plan_trip",
        "description": (
            "根据日期和武汉的实时天气预报，规划当天（或多天）的景点游览顺序。"
            "输入一个日期即可：工具会自己取当天逐时天气、判断每个景点适不适合去、"
            "再排出「先去哪、后去哪」的时间线，并给出每段交通耗时与手机导航链接。"
            "当用户问「X 月 X 日来武汉怎么玩」「明天去哪」「下雨天适合去哪」时调用。"
            "不要自己编造景点顺序或时间，一律调用本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "出行日期 YYYY-MM-DD。用户说「明天/下周六/11月中旬」时由你换算成具体日期。",
                },
                "days": {"type": "integer", "minimum": 1, "maximum": 5, "default": 1,
                         "description": "连续规划几天，默认 1。"},
                "start": {
                    "type": "object",
                    "description": "起点。用户没提就省略，默认武汉市中心（洪山广场）。",
                    "properties": {
                        "name": {"type": "string"},
                        "lat": {"type": "number", "description": "纬度 WGS84"},
                        "lon": {"type": "number", "description": "经度 WGS84"},
                        "time": {"type": "string", "description": "出发时间 HH:MM，默认 09:00"},
                    },
                },
                "end_by": {"type": "string", "default": "20:30",
                           "description": "当天最晚结束时间 HH:MM"},
                "transport": {"type": "string", "enum": ["walk", "drive", "mixed"], "default": "mixed",
                              "description": "walk 只步行 / drive 只打车 / mixed 每段自动取更快的"},
                "preferences": {"type": "array", "items": {"type": "string"},
                                "description": "偏好，如 历史人文 / 湖景 / 博物馆 / 赏花 / 亲子 / 拍照"},
                "must_visit": {"type": "array", "items": {"type": "string"},
                               "description": "必去景点（id 或中文名）"},
                "avoid": {"type": "array", "items": {"type": "string"},
                          "description": "排除的景点（id 或中文名）"},
                "districts": {"type": "array", "items": {"type": "string"},
                              "description": "限定行政区，如 ['武昌区']"},
                "max_spots": {"type": "integer", "minimum": 1, "maximum": 8, "default": 4,
                              "description": "一天最多几个景点"},
                "max_radius_km": {"type": "number", "default": 30,
                                  "description": "候选景点距起点的最大直线距离（公里）"},
                "suit_min": {"type": "integer", "default": 60,
                             "description": "调参：适宜度绝对下限，越低越不挑天气"},
                "rel_band": {"type": "integer", "default": 10,
                             "description": "调参：只接受接近当日最佳的时次，越小越挑时段"},
                "weather": {"type": "object",
                            "description": "仅测试：注入逐时天气（hours 数组）以离线复现"},
            },
            "required": ["date"],
        },
    },
}

LIST_SPOTS = {
    "type": "function",
    "function": {
        "name": "list_spots",
        "description": "列出武汉可选景点（id、名称、类型、室内外、所属区、建议停留时长）。"
                       "用于规划前确认有哪些景点，或回答「武汉有什么好玩的」。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "关键词，匹配名称/备注/类型"},
                "district": {"type": "string", "description": "行政区，如 武昌区"},
                "type": {"type": "string", "description": "类型，如 indoor / elevated_view / waterside_view"},
                "limit": {"type": "integer", "default": 30},
            },
        },
    },
}

TOOLS = [PLAN_TRIP, LIST_SPOTS]


def validate(request):
    """返回 (ok, error_message)。只挡明显调不通的输入，不做过度限制。"""
    if request is None:
        return True, None
    if not isinstance(request, dict):
        return False, "参数必须是 JSON 对象"
    d = request.get("date")
    if d:
        try:
            _dt.date.fromisoformat(str(d)[:10])
        except ValueError:
            return False, "date 必须是 YYYY-MM-DD 格式，收到 %r" % d
    for key in ("days", "max_spots", "suit_min", "rel_band"):
        if request.get(key) is not None:
            try:
                int(request[key])
            except (TypeError, ValueError):
                return False, "%s 必须是整数" % key
    st = request.get("start")
    if st is not None and not isinstance(st, dict):
        return False, "start 必须是对象 {name, lat, lon, time}"
    return True, None


def dispatch(name, arguments=None):
    """智能体统一入口。arguments 允许是 dict 或 JSON 字符串。"""
    import json

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError as e:
            return {"ok": False, "error": "arguments 不是合法 JSON: %s" % e}
    arguments = dict(arguments or {})

    if name == "plan_trip":
        ok, err = validate(arguments)
        if not ok:
            return {"ok": False, "error": err}
        try:
            return planner.plan(arguments)
        except Exception as e:
            import logging
            logging.getLogger("trip_tool").exception("plan_trip 失败")
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}

    if name == "list_spots":
        return _list_spots(arguments)

    return {"ok": False, "error": "未知工具: %s（可用：%s）"
                                  % (name, ", ".join(t["function"]["name"] for t in TOOLS))}


def _list_spots(args):
    from . import datasource, hooks
    src = hooks.get("spot_source")
    spots = src.load_spots() if src else datasource.load(args.get("data_dir"))[0]

    kw = (args.get("keyword") or "").strip()
    dist = (args.get("district") or "").strip()
    typ = (args.get("type") or "").strip()
    limit = int(args.get("limit") or 30)

    out = []
    for sid, s in spots.items():
        if dist and s.get("district") != dist:
            continue
        if typ and s.get("type") != typ:
            continue
        if kw:
            blob = " ".join([s.get("name", ""), s.get("type", ""),
                             s.get("notes") or "", s.get("exposure") or ""])
            if kw not in blob:
                continue
        out.append({
            "id": sid, "name": s.get("name"), "type": s.get("type"),
            "exposure": s.get("exposure"), "district": s.get("district"),
            "duration_h": (s.get("features") or {}).get("typical_duration_h"),
            "open_text": ((s.get("open_hours") or {}).get("text") or "")[:60],
        })
        if len(out) >= limit:
            break
    return {"ok": True, "count": len(out), "spots": out}
