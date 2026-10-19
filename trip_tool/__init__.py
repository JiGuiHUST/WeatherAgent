# -*- coding: utf-8 -*-
"""trip_tool —— 给智能体调用的「按日期规划武汉行程」工具。

最小用法：
    from trip_tool import plan_trip
    plan_trip("2026-10-25")                    # 只要一个日期

智能体用法：
    from trip_tool import TOOLS, dispatch
    client.chat.completions.create(..., tools=TOOLS)
    result = dispatch("plan_trip", tool_call.arguments)

换数据/换模型/换求解器：见 hooks.py 与 README.md。
"""
from . import hooks
from .contract import LIST_SPOTS, PLAN_TRIP, TOOLS, dispatch, validate
from .planner import plan, plan_trip, summary_text

__version__ = "1.0.0"

__all__ = [
    "plan", "plan_trip", "summary_text",
    "dispatch", "validate", "TOOLS", "PLAN_TRIP", "LIST_SPOTS",
    "hooks", "__version__",
]
