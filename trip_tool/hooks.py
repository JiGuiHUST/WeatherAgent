# -*- coding: utf-8 -*-
"""扩展点注册表（预留接口）。

这个模块是给「以后要换实现」准备的：数据源、天气源、评分函数、路网、求解器
全部通过这里插拔，**不需要改 trip_tool 里的任何其他文件**。

用法：
    from trip_tool import hooks
    hooks.set_weather_provider(my_provider)      # 换成气象局数据
    hooks.set_scorer(my_learned_scorer)          # 换成训练出来的模型
"""
from __future__ import annotations

_SLOTS = {
    "spot_source": None,      # datasource.SpotSource
    "weather_provider": None,  # weather.WeatherProvider
    "scorer": None,           # scoring.Scorer
    "matrix_provider": None,  # routing.MatrixProvider
    "solver": None,           # solver.Solver
    "clock": None,            # 可注入的"今天"，便于测试与回放
}


def set_spot_source(obj):
    _SLOTS["spot_source"] = obj


def set_weather_provider(obj):
    _SLOTS["weather_provider"] = obj


def set_scorer(obj):
    _SLOTS["scorer"] = obj


def set_matrix_provider(obj):
    _SLOTS["matrix_provider"] = obj


def set_solver(obj):
    _SLOTS["solver"] = obj


def set_clock(fn):
    """fn() -> datetime.date，用于固定"今天"。"""
    _SLOTS["clock"] = fn


def get(name):
    return _SLOTS.get(name)


def reset():
    for k in _SLOTS:
        _SLOTS[k] = None
