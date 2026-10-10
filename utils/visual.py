# -*- coding: utf-8 -*-
"""视觉辅助：天气/体感图标映射、概率配色等，供 Jinja 模板调用。"""


def weather_icon(tag):
    """气象标签 -> Bootstrap Icons 类名"""
    m = {
        "高温多雨": "bi-cloud-rain-heavy-fill",
        "高温少雨": "bi-thermometer-sun",
        "高温伴阵雨": "bi-cloud-sun-rain-fill",
        "温和多雨": "bi-cloud-rain-fill",
        "温和少雨": "bi-sun-fill",
        "温和伴阵雨": "bi-cloud-drizzle-fill",
        "清凉多雨": "bi-cloud-rain-fill",
        "清凉伴阵雨": "bi-cloud-rain-fill",
        "清凉干燥": "bi-snow",
        "气象待定": "bi-cloud-sun",
    }
    return m.get(tag, "bi-cloud-sun-fill")


def comfort_icon(comfort):
    """体感标签 -> 图标"""
    m = {
        "舒适": "bi-emoji-smile-fill", "Pleasant": "bi-emoji-smile-fill",
        "温热": "bi-thermometer-half", "Warm": "bi-thermometer-half",
        "炎热": "bi-thermometer-high", "Hot": "bi-thermometer-high",
        "多雨": "bi-umbrella-fill", "Rainy": "bi-umbrella-fill",
        "风大": "bi-wind", "Windy": "bi-wind",
        "凉爽": "bi-snow2", "Cool": "bi-snow2",
    }
    return m.get(comfort, "bi-dash-circle")


def prob_color(p):
    """0-100 -> 颜色"""
    if p is None:
        return "#6c757d"
    if p >= 75:
        return "#27ae60"
    if p >= 50:
        return "#f39c12"
    if p >= 30:
        return "#e67e22"
    return "#c0392b"


def prob_level(p, lang="zh"):
    if p is None:
        return "—" if lang == "en" else "—"
    if p >= 75:
        return "High" if lang == "en" else "高"
    if p >= 50:
        return "Medium" if lang == "en" else "中"
    if p >= 30:
        return "Low" if lang == "en" else "偏低"
    return "Unlikely" if lang == "en" else "不宜"
