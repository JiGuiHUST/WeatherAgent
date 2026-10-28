# -*- coding: utf-8 -*-
"""模块1.2：东南亚特色景观观赏概率 AI 预判。

气象加权打分模型：依据温度、降水、湿度、派生风力，输出观赏概率、最佳拍摄时段、
安全风险与中英双语气象原理。

景观类型：
  日出日落类：sunset, sunrise, sunset_convection_cloud, fire_cloud, haze_dusk
  云海雾景类：morning_fog, sea_fog, radiation_fog, mountain_sea_of_cloud, coastal_fog, river_fog
  光学虹彩类：waterfall_rainbow, sea_rainbow, spray_rainbow  # 彩虹/浪花
  冰晶光学类：circumzenithal_arc, brocken_spectre, sun_corona, moon_corona, cloud_iridescence
  对流风暴类：cumulonimbus, tropical_lightning, waterspout, roll_cloud, orographic_rain, convective_rain_curtain
  夜光/天文类：stargazing, bioluminescence_sea, moon_corona（同上）, twilight_glow, blue_hour
  其他光学：tyndall_effect, mirage, banner_cloud
"""
import os
import logging

from services import weather_api
from services.travel_engine import _load_json

logger = logging.getLogger("landscape_engine")

_LANDSCAPES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landscapes.json")


def _load_landscapes():
    return _load_json(_LANDSCAPES_FILE)


def _clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))


def _wind(s):
    """派生风力（与 forecast_service 估算口径一致）"""
    from services.forecast_service import wind_beaufort
    values = [v for v in s.get("wind_series",[]) if v is not None]
    return wind_beaufort(max(values)) if values else 0


# ============================= 基础评分函数 =============================

def _sunset_score(s):
    """通用日落：晴少云 + 湿度 50-75% 最佳，降水大幅削弱"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 80
    score -= min(55, pre * 5)
    if 55 <= rh <= 75:
        score += 10
    elif rh > 88:
        score -= 20
    elif rh < 35:
        score -= 12
    if wind >= 5:
        score -= 15
    return _clamp(score)


def _sunrise_score(s):
    """通用日出：薄雾 80-95 RH 加分，大风扣分"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 78
    score -= min(55, pre * 5)
    if 80 <= rh <= 95:
        score += 12
    elif rh > 95:
        score -= 15
    if wind >= 5:
        score -= 15
    return _clamp(score)


def _dive_score(s):
    """潜水/海水能见度：少雨少风高晴，返回 (score, vis_km)"""
    pre = s.get("total_pre") or 0
    wind = _wind(s)
    rh = s.get("avg_rh") or 70
    vis = max(1, 20 - pre * 0.6 - wind * 1.5 - max(0, (rh - 80)) * 0.3)
    score = vis / 20.0 * 100
    return _clamp(score), round(vis, 1)


def _fog_score(s):
    """通用晨雾：RH>=85 且风小加分，降水反而减弱雾"""
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    score = 30
    if rh >= 85:
        score += (rh - 85) * 2.5
    if wind <= 2:
        score += 25
    elif wind >= 4:
        score -= 20
    score -= min(30, pre * 3)
    return _clamp(score)


def _star_score(s):
    """观星：少雨、低湿、少云、风适中"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 85
    score -= min(50, pre * 4)
    if rh > 80:
        score -= 25
    if wind >= 5:
        score -= 15
    return _clamp(score)


# ============================= 云海雾景 =============================

def _sea_fog_score(s):
    """平流海雾：需要海水-空气温差（RH>=88 且有轻风、微降水）"""
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    score = 28
    if rh >= 88:
        score += (rh - 88) * 3
    if 1.5 <= wind <= 3:
        score += 18
    elif wind >= 5:
        score -= 30
    score += min(15, pre * 1.5)  # 轻微降水后水汽足
    return _clamp(score)


def _radiation_fog_score(s):
    """辐射雾（稻田/陆地）：晴夜、RH高、微风；降水反而降低辐射冷却"""
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    score = 35
    if rh >= 85:
        score += (rh - 85) * 2
    if wind <= 2:
        score += 22
    if pre >= 10:
        score -= 25  # 降水后云层厚，冷却不足
    return _clamp(score)


def _mountain_sea_of_cloud_score(s):
    """山地云海：雨后+高湿+风适中"""
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    score = 30
    if rh >= 90:
        score += (rh - 90) * 2.5
    score += min(30, pre * 2.2)  # 雨后次日云海概率极高
    if 2 <= wind <= 4:
        score += 15
    elif wind >= 6:
        score -= 25
    return _clamp(score)


def _coastal_fog_score(s):
    """海岸平流海蚀雾：湿空气过冷水域，RH极高+轻风"""
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    score = 25
    if rh >= 92:
        score += (rh - 92) * 3.5
    if 1.5 <= wind <= 3.5:
        score += 16
    elif wind >= 5:
        score -= 25
    score -= min(20, pre * 2)
    return _clamp(score)


def _river_fog_score(s):
    """江河晨雾：河流水汽+辐射冷却，RH高+无风少雨"""
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    score = 32
    if rh >= 88:
        score += (rh - 88) * 2.8
    if wind <= 2.5:
        score += 18
    if pre >= 8:
        score -= 22
    return _clamp(score)


# ============================= 日落云系变体 =============================

def _sunset_convection_cloud_score(s):
    """对流云晚霞：需要午后有降雨（发展对流云）+ 傍晚降水结束"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 55
    if 5 <= pre <= 30:
        score += 25  # 午后对流发展但已收尾
    elif pre > 40:
        score -= 20  # 雨太大太阳难露出
    if 65 <= rh <= 85:
        score += 8
    if wind >= 5:
        score -= 12
    return _clamp(score)


def _fire_cloud_score(s):
    """火烧云：中低层云量多但不遮蔽，空气通透度适中"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 60
    if 3 <= pre <= 25:
        score += 20
    elif pre == 0:
        score -= 15  # 万里无云没有火烧云对象
    elif pre > 30:
        score -= 20
    if 70 <= rh <= 88:
        score += 8
    if wind >= 5:
        score -= 10
    return _clamp(score)


def _haze_dusk_score(s):
    """水乡暮霭：湿地河网，RH高+极微风+少量降水"""
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    score = 55
    if 82 <= rh <= 96:
        score += (rh - 82) * 2
    if wind <= 2:
        score += 15
    score += min(10, pre * 1.2)  # 轻降水增强水汽
    return _clamp(score)


# ============================= 彩虹类 =============================

def _rainbow_base(s, needs_wave_spray=False):
    """通用彩虹：有降水但局部天晴、太阳角度合适"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 40
    if 3 <= pre <= 25:
        score += 30
    elif pre > 30:
        score -= 10  # 全天雨，放晴难
    elif pre == 0:
        score -= 20  # 无雨无虹
    if 60 <= rh <= 82:
        score += 10
    if needs_wave_spray:
        # 需要海浪浪花（风力中等偏大，3-5级）
        if 3 <= wind <= 5:
            score += 12
        elif wind < 2 or wind > 6:
            score -= 15
    else:
        if wind >= 5:
            score -= 10
    return _clamp(score)


# ============================= 冰晶/光学/大气光学类 =============================

def _corona_score(s, is_moon=False):
    """日华/月华：薄中高云 + 少降水，云中小水滴衍射"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 45
    if 2 <= pre <= 12:
        score += 18
    elif pre > 20:
        score -= 25
    if 70 <= rh <= 90:
        score += 12
    if wind >= 5:
        score -= 12
    if is_moon:
        score -= 3  # 月华概率略低于日华
    return _clamp(score)


def _cloud_iridescence_score(s):
    """虹彩幞状云（七彩祥云）：热带对流旺盛，幞状云顶薄云"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    tmp = s.get("avg_tmp") or 28
    score = 48
    if 5 <= pre <= 20:
        score += 22  # 午后对流产生幞状云
    elif pre >= 25:
        score -= 20
    if tmp >= 28:
        score += 8  # 高温对流强
    if 65 <= rh <= 85:
        score += 8
    return _clamp(score)


def _circumzenithal_arc_score(s):
    """环天顶弧：高空薄卷云 + 太阳高度<32度 + 低湿晴朗"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 38
    if 0 <= pre <= 5:
        score += 12  # 晴朗为主（允许极少降水，代表卷云活跃）
    elif pre > 10:
        score -= 30
    if 40 <= rh <= 65:
        score += 18  # 干燥高空板状冰晶
    else:
        score -= 10
    if wind >= 6:
        score -= 12
    return _clamp(score)  # 罕见现象，最高分不高


def _brocken_spectre_score(s):
    """宝光/布罗肯幽灵：云海+朝阳低角度+人在山顶"""
    # 核心需求：云海+晨雾+少雨+高湿
    soc = _mountain_sea_of_cloud_score(s)
    # 云海要足够好，人站在太阳和雾之间
    soc = 0.7 * soc + 0.3 * _fog_score(s)
    # 降水过多遮挡
    pre = s.get("total_pre") or 0
    if pre >= 20:
        soc -= 20
    return _clamp(soc - 5)  # 宝光比云海更难形成


def _tyndall_effect_score(s):
    """丁达尔光：轻雾/轻霾+空气悬溶胶+阳光低角度"""
    rh = s.get("avg_rh") or 60
    pre = s.get("total_pre") or 0
    wind = _wind(s)
    score = 50
    if 78 <= rh <= 92:
        score += 15  # 薄雾悬溶胶
    elif rh > 95:
        score -= 18
    elif rh < 60:
        score -= 15
    if 1.5 <= wind <= 3:
        score += 8
    if 0 <= pre <= 8:
        score += 5
    elif pre > 15:
        score -= 22
    return _clamp(score)


def _mirage_score(s):
    """海市蜃楼（海滋/护城河）：近地面逆温+晴静清晨+高湿不降雨"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 42
    if pre == 0:
        score += 18
    elif pre > 5:
        score -= 40
    if 82 <= rh <= 96:
        score += 18
    if wind <= 2:
        score += 12
    return _clamp(score)


def _banner_cloud_score(s):
    """山巅旗云：强风越过山顶+背风侧有凝结"""
    wind = _wind(s)
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    score = 40
    if wind >= 4:
        score += (wind - 4) * 6
    else:
        score -= 25
    if 70 <= rh <= 88:
        score += 15
    score += min(10, pre * 1)
    return _clamp(score)


def _twilight_glow_score(s):
    """薄暮华光：日落后民用暮光，少云+城市灯光叠加"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    score = 68
    if 0 <= pre <= 8:
        score += 10
    elif pre >= 20:
        score -= 22
    if 65 <= rh <= 85:
        score += 8
    return _clamp(score)


def _blue_hour_score(s):
    """蓝调时刻：日出前日落后，少降水+空气通透"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    score = 70
    if pre == 0:
        score += 12
    elif pre > 10:
        score -= 25
    if 55 <= rh <= 78:
        score += 8
    return _clamp(score)


def _bioluminescence_score(s):
    """生物荧光海（蓝眼泪）：暗夜+新月附近+少风+少云+水温适宜"""
    pre = s.get("total_pre") or 0
    wind = _wind(s)
    rh = s.get("avg_rh") or 60
    tmp = s.get("avg_tmp") or 28
    score = 48
    if pre == 0:
        score += 12
    elif pre > 5:
        score -= 25
    if wind <= 2:
        score += 10
    elif wind >= 4:
        score -= 18
    if 26 <= tmp <= 30:
        score += 8
    if rh > 85:
        score -= 8  # 高湿伴云，光污染大
    return _clamp(score)


# ============================= 对流风暴类（观赏性 & 风险）=============================

def _cumulonimbus_score(s):
    """积雨云（午后）：高温+有降雨代表对流发展"""
    pre = s.get("total_pre") or 0
    tmp = s.get("avg_tmp") or 28
    score = 42
    if pre >= 8:
        score += min(35, pre * 2.2)
    if tmp >= 30:
        score += 12
    return _clamp(score)


def _tropical_lightning_score(s):
    """夜间热带闪电：降雨强度较大+热带夜间对流"""
    pre = s.get("total_pre") or 0
    tmp = s.get("avg_tmp") or 28
    score = 38
    if 10 <= pre <= 40:
        score += 35
    elif pre > 50:
        score -= 20  # 雨太大，云内闪电多但看不清
    if tmp >= 28:
        score += 10
    return _clamp(score)


def _waterspout_score(s):
    """海龙卷：暖海+积雨云+中尺度涡旋"""
    pre = s.get("total_pre") or 0
    tmp = s.get("avg_tmp") or 28
    wind = _wind(s)
    score = 30  # 罕见
    if 8 <= pre <= 28:
        score += 30
    if tmp >= 29:
        score += 12
    if 3 <= wind <= 5:
        score += 10
    return _clamp(score)


def _roll_cloud_score(s):
    """台风外围滚轴云：大风+降水+锋面过境，罕见前兆"""
    pre = s.get("total_pre") or 0
    wind = _wind(s)
    score = 28  # 罕见
    if 6 <= wind <= 8:
        score += (wind - 6) * 10
    elif wind < 4:
        score -= 25
    if 10 <= pre <= 35:
        score += 25
    return _clamp(score)


def _orographic_rain_score(s):
    """地形雨：一定降水+高湿+中等风力抬升"""
    pre = s.get("total_pre") or 0
    rh = s.get("avg_rh") or 60
    wind = _wind(s)
    score = 45
    if 8 <= pre <= 40:
        score += 30
    elif pre > 50:
        score -= 10  # 太大就不是"景"而是灾
    if 80 <= rh <= 95:
        score += 12
    if 3 <= wind <= 5:
        score += 10
    return _clamp(score)


def _convective_rain_curtain_score(s):
    """对流雨幕（分界线雨）：局地对流，中等降水+高温"""
    pre = s.get("total_pre") or 0
    tmp = s.get("avg_tmp") or 28
    score = 48
    if 5 <= pre <= 20:
        score += 28
    elif pre > 30:
        score -= 15
    if tmp >= 30:
        score += 10
    return _clamp(score)


# ============================= 风险标签 =============================

# 高风险景观类型：观赏时需要强警示
_DANGER_TYPES = {"waterspout", "roll_cloud", "tropical_lightning", "cumulonimbus",
                 "convective_rain_curtain", "orographic_rain"}


def _risk_label(s, ltype, lang):
    pre = s.get("total_pre") or 0
    wind = _wind(s)

    # 危险性极高的景观（即使能拍到，也必须警告）
    if ltype == "waterspout":
        return "海龙卷属于危险天气现象，仅允许远距离观赏，切勿靠近海边或乘船出海追逐" if lang != "en" \
            else "Waterspout is a DANGEROUS weather system. Observe from far inland ONLY — never approach seashore or chase by boat."
    if ltype == "roll_cloud":
        return "滚轴云预示台风/强飑线将至，立即终止户外行程，转移至坚固建筑内" if lang != "en" \
            else "Roll cloud signals incoming typhoon/squall. Cancel outdoor activities immediately and shelter in sturdy buildings."
    if ltype == "tropical_lightning":
        return "雷暴期间进入坚固建筑内避险，远离开阔地、水边和孤立树木，暂停户外拍摄" if lang != "en" \
            else "Shelter inside a sturdy building during thunderstorms; stay away from water, open ground and isolated trees."

    if pre >= 15 or wind >= 6:
        if ltype in ("cumulonimbus", "orographic_rain", "convective_rain_curtain"):
            return "强对流天气伴随短时强降水、雷电，山区谨防山洪、滑坡，尽量避免登山" if lang != "en" \
                else "Severe convection with heavy short rain & lightning. Avoid mountains — flash flood / landslide risk."
        return "大风/暴雨风险，不宜户外拍摄" if lang != "en" else "Strong wind/heavy rain risk — avoid outdoor shooting"
    if wind >= 4:
        return "风力较大，注意器材稳固与防风" if lang != "en" else "Moderate wind — secure gear against gusts"
    if pre >= 5:
        return "有阵雨，备好防雨罩" if lang != "en" else "Showers possible — bring rain cover"
    return "气象条件良好，可正常拍摄" if lang != "en" else "Favorable conditions — safe to shoot"


# ============================= 主入口 =============================

_TYPE_SCORERS = {
    # 基础 5 类
    "sunset": _sunset_score,
    "sunrise": _sunrise_score,
    "dive_visibility": _dive_score,
    "morning_fog": _fog_score,
    "stargazing": _star_score,
    # 云海雾景
    "sea_fog": _sea_fog_score,
    "radiation_fog": _radiation_fog_score,
    "mountain_sea_of_cloud": _mountain_sea_of_cloud_score,
    "coastal_fog": _coastal_fog_score,
    "river_fog": _river_fog_score,
    # 日落云系
    "sunset_convection_cloud": _sunset_convection_cloud_score,
    "fire_cloud": _fire_cloud_score,
    "haze_dusk": _haze_dusk_score,
    # 彩虹/浪花
    "waterfall_rainbow": lambda s: _rainbow_base(s, needs_wave_spray=False),
    "sea_rainbow": lambda s: _rainbow_base(s, needs_wave_spray=True),
    "spray_rainbow": lambda s: _rainbow_base(s, needs_wave_spray=True),
    # 华光
    "sun_corona": lambda s: _corona_score(s, is_moon=False),
    "moon_corona": lambda s: _corona_score(s, is_moon=True),
    # 冰晶光学
    "circumzenithal_arc": _circumzenithal_arc_score,
    "brocken_spectre": _brocken_spectre_score,
    "cloud_iridescence": _cloud_iridescence_score,
    # 其他光学
    "tyndall_effect": _tyndall_effect_score,
    "mirage": _mirage_score,
    "banner_cloud": _banner_cloud_score,
    "twilight_glow": _twilight_glow_score,
    "blue_hour": _blue_hour_score,
    # 生物荧光
    "bioluminescence_sea": _bioluminescence_score,
    # 对流风暴
    "cumulonimbus": _cumulonimbus_score,
    "tropical_lightning": _tropical_lightning_score,
    "waterspout": _waterspout_score,
    "roll_cloud": _roll_cloud_score,
    "orographic_rain": _orographic_rain_score,
    "convective_rain_curtain": _convective_rain_curtain_score,
}


def predict_for_route(route_cities, start_dt, lang="zh", dates=None):
    """
    对路线涉及城市的特色景观点位打分。
    :return: list[{name, city, type, prob, prob_label, window, vis_km, risk_label,
                  principle, principle_en, danger}]
    """
    from services.travel_engine import _city_bbox  # 延迟导入避免循环
    city_map = _city_bbox()
    landscapes = _load_landscapes()
    results = []

    for name, land in landscapes.items():
        city = land["city"]
        if city not in route_cities:
            continue
        info = city_map.get(city)
        if not info:
            continue
        summary = weather_api.get_weather_summary((dates or {}).get(city,start_dt), info["bbox"])
        if summary is None:
            from services.travel_engine import _mock_weather
            summary = _mock_weather(info, _season_of(start_dt))

        ltype = land["type"]
        scorer = _TYPE_SCORERS.get(ltype)
        vis = None
        if scorer is None:
            prob = 50  # 兜底：未知类型中立
        else:
            out = scorer(summary)
            if isinstance(out, tuple):
                prob, vis = out
            else:
                prob = out

        danger = ltype in _DANGER_TYPES
        results.append({
            "name": name,
            "city": city,
            "type": ltype,
            "danger": danger,
            "prob": int(prob),
            "prob_label": _prob_label(prob, lang),
            "window": land["best_window"],
            "vis_km": vis,
            "risk_label": _risk_label(summary, ltype, lang),
            "principle": land["principle"]["zh"],
            "principle_en": land["principle"]["en"],
        })
    return results


def _prob_label(score, lang):
    if score >= 75:
        return "高" if lang != "en" else "High"
    if score >= 50:
        return "中" if lang != "en" else "Medium"
    if score >= 30:
        return "偏低" if lang != "en" else "Low"
    return "不宜" if lang != "en" else "Unlikely"


def _season_of(dt):
    m = dt.month
    if m in (3, 4, 5):
        return "春季"
    if m in (6, 7, 8):
        return "夏季"
    if m in (9, 10, 11):
        return "秋季"
    return "冬季"
