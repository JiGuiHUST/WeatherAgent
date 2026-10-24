# -*- coding: utf-8 -*-
"""中英双语国际化（i18n）。
translate(key, lang) -> str；默认中文。
lang 取值："zh" / "en"。
"""

_STRINGS = {
    # 导航
    "nav.brand": {"zh": "气象旅行攻略", "en": "Weather Travel Guide"},
    "nav.home": {"zh": "目的地气候规划", "en": "Destination Climate"},
    "nav.route": {"zh": "行程气象助手", "en": "Travel Weather Assistant"},
    "nav.qa": {"zh": "气象问答", "en": "Weather Q&A"},
    "nav.science": {"zh": "气象研学课堂", "en": "Weather Study"},
    "nav.safety": {"zh": "出行安全指南", "en": "Travel Safety Guide"},
    "nav.lang": {"zh": "EN", "en": "中文"},

    # 通用
    "common.back": {"zh": "返回", "en": "Back"},
    "common.submit": {"zh": "生成", "en": "Generate"},
    "common.reset": {"zh": "重置", "en": "Reset"},
    "common.loading": {"zh": "生成中…", "en": "Loading…"},
    "common.source": {"zh": "数据来源", "en": "Source"},
    "common.updated": {"zh": "更新于", "en": "Updated"},

    # 路线页
    "route.title": {"zh": "行程气象助手", "en": "Travel Weather Assistant"},
    "route.subtitle": {"zh": "一键导入行程，整合沿途多国逐时气象总览", "en": "Import your route, get a coherent hourly weather overview across borders"},
    "route.cities": {"zh": "途经城市（可多选）", "en": "Cities along route (multi-select)"},
    "route.start_date": {"zh": "出发日期", "en": "Start date"},
    "route.days_each": {"zh": "每城停留天数", "en": "Days per city"},
    "route.crowd": {"zh": "出行人群", "en": "Traveler type"},
    "route.crowd.free": {"zh": "自由行", "en": "Independent"},
    "route.crowd.family": {"zh": "亲子游", "en": "Family"},
    "route.crowd.photo": {"zh": "摄影游", "en": "Photography"},
    "route.crowd.study": {"zh": "研学游", "en": "Study tour"},
    "route.forecast": {"zh": "整程连贯逐时气象总览", "en": "Coherent hourly weather overview"},
    "route.landscape": {"zh": "特色景观观赏概率预判", "en": "Featured landscape viewing probability"},
    "route.itinerary": {"zh": "分人群智能行程规划", "en": "Crowd-aware itinerary"},
    "route.itin.source.llm": {"zh": "AI 生成", "en": "AI generated"},
    "route.itin.source.rule": {"zh": "规则建议", "en": "Rule-based"},
    "route.itin.source.mixed": {"zh": "AI+规则", "en": "AI + rule"},
    "route.itin.source.tip.llm": {"zh": "建议由 AI 依据当日气象动态生成，时间点+景点+取舍更详尽",
                                  "en": "AI dynamically generated using the day's weather, with slots/spots/trade-offs"},
    "route.itin.source.tip.rule": {"zh": "AI 接口不可用，已使用规则建议（较为精简）",
                                  "en": "AI unavailable, using rule-based suggestions (condensed)"},
    "route.itin.source.tip.mixed": {"zh": "部分城市 AI 生成，部分城市规则回退",
                                   "en": "Some cities by AI, others by rule fallback"},
    "route.itin.loading": {"zh": "AI 正在规划详细时间线（调用大模型，通常需要 10-30 秒）…",
                          "en": "AI is drafting detailed timelines (LLM call, usually 10-30s)…"},
    "route.itin.loading.fallback": {"zh": "同时正在准备规则版精简建议兜底…",
                                    "en": "Preparing rule-based fallback in parallel…"},
    "route.itin.error": {"zh": "AI 规划失败，已切换为规则版精简建议",
                        "en": "AI plan failed, switched to rule-based condensed suggestions"},
    "route.itin.error.session": {"zh": "会话已过期，请重新提交行程表单",
                                "en": "Session expired, please re-submit the route form"},
    "route.itin.refresh": {"zh": "重新生成", "en": "Regenerate"},
    "route.itin.retry": {"zh": "点击重试", "en": "Click to retry"},
    "route.hour": {"zh": "时间", "en": "Time"},
    "route.tmp": {"zh": "温度℃", "en": "Temp℃"},
    "route.pre": {"zh": "降水mm", "en": "Precip mm"},
    "route.wind": {"zh": "风力级", "en": "Wind"},
    "route.vis": {"zh": "能见度km", "en": "Vis km"},
    "route.comfort": {"zh": "体感", "en": "Comfort"},

    # 景点选择 & 景点级预报
    "route.spots.btn_tip": {"zh": "选择该城市景点，按景点经纬度匹配精确预报",
                            "en": "Pick spots in this city for precise point forecasts"},
    "route.spots.tip": {"zh": "勾选城市后点击右侧 📍 按钮挑选景点，结果页将按景点经纬度逐日生成精确预报（异步加载，不影响主表渲染）",
                        "en": "Check a city then click the 📍 button to pick spots; the result page will fetch point-level daily forecasts asynchronously"},
    "route.spots.modal_title": {"zh": "选择景点", "en": "Select spots"},
    "route.spots.modal_tip": {"zh": "可多选，景点经纬度用于调用 0.25° 格点气象接口获取精确预报",
                              "en": "Multi-select; spot lat/lon drives 0.25°-grid point forecast calls"},
    "route.spots.loading": {"zh": "景点列表加载中…", "en": "Loading spots…"},
    "route.spots.empty": {"zh": "该城市暂未收录景点", "en": "No spots recorded for this city yet"},
    "route.spots.select_all": {"zh": "全选", "en": "Select all"},
    "route.spots.select_none": {"zh": "清空", "en": "Clear"},
    "route.spots.selected_count": {"zh": "已选", "en": "Selected"},
    "route.spots.forecast_title": {"zh": "已选景点精确预报", "en": "Spot-level precise forecast"},
    "route.spots.loading_forecast": {"zh": "正在按景点经纬度逐日获取精确预报（每个景点 1 次格点调用，可能 5-15 秒）…",
                                     "en": "Fetching point-level daily forecasts by spot lat/lon (one grid call per spot, may take 5-15s)…"},
    "route.spots.loading_forecast_tip": {"zh": "API 不可达时自动降级为城市气候均值",
                                         "en": "Falls back to city climate averages when API unreachable"},
    "route.spots.error": {"zh": "景点预报加载失败", "en": "Spot forecast failed to load"},
    "route.spots.error_session": {"zh": "会话已过期，请重新提交行程表单", "en": "Session expired, please re-submit the route form"},
    "route.spots.best_hours": {"zh": "最佳时段", "en": "Best hours"},
    "route.spots.weather_tip": {"zh": "景点天气建议", "en": "Spot weather tip"},
    "route.spots.no_data": {"zh": "未选择任何景点，跳过精确预报", "en": "No spots selected — skipping spot forecasts"},

    # 问答页
    "qa.title": {"zh": "气象问答", "en": "Weather Q&A"},
    "qa.subtitle": {"zh": "提问东南亚专属气象现象，结合路线实况讲解", "en": "Ask about SE-Asia weather phenomena, explained with live route data"},
    "qa.placeholder": {"zh": "例如：为什么东南亚午后常下对流雨？ / Why convective rain in afternoon?",
    "en": "e.g. Why convective rain in afternoon? / 为什么午后常下对流雨？"},
    "qa.ask": {"zh": "提问", "en": "Ask"},
    "qa.example": {"zh": "示例问题", "en": "Example questions"},
    "qa.live_case": {"zh": "实景案例（路线当日实况）", "en": "Live case (route weather today)"},

    # 科普页
    "sci.title": {"zh": "气象研学课堂", "en": "Weather Study"},
    "sci.subtitle": {"zh": "沿线伴随式知识推送 + 研学素材导出", "en": "Companion knowledge push + study material export"},
    "sci.push": {"zh": "今日实景知识点", "en": "Today's field knowledge"},
    "sci.export": {"zh": "研学素材导出", "en": "Study material export"},
    "sci.handbook": {"zh": "双语研学手册", "en": "Bilingual handbook"},
    "sci.record": {"zh": "户外观测记录表", "en": "Observation record"},
    "sci.bank": {"zh": "气象科普题库", "en": "Quiz bank"},
    "sci.diagram": {"zh": "简易气象示意图", "en": "Weather diagram"},

    # 景观
    "land.prob": {"zh": "观赏概率", "en": "Viewing prob"},
    "land.window": {"zh": "最佳拍摄时段", "en": "Best shoot window"},
    "land.risk": {"zh": "拍摄安全风险", "en": "Safety risk"},
    "land.principle": {"zh": "气象原理", "en": "Meteorological principle"},
    "land.none": {"zh": "该路线暂无匹配的特色景观点位", "en": "No featured landscape points matched this route"},

    # 出行安全指南页
    "safety.title": {"zh": "出行安全指南", "en": "Travel Safety Guide"},
    "safety.subtitle": {"zh": "气象、交通、健康、证件、跨境、应急 六维一体防范手册",
                       "en": "Six-dimensional handbook: weather, transit, health, documents, border, emergency"},
    "safety.weather": {"zh": "气象安全", "en": "Weather safety"},
    "safety.transit": {"zh": "交通出行", "en": "Transit safety"},
    "safety.health": {"zh": "健康防护", "en": "Health protection"},
    "safety.docs": {"zh": "证件财物", "en": "Documents & valuables"},
    "safety.border": {"zh": "跨境手续", "en": "Border formalities"},
    "safety.emergency": {"zh": "应急救援", "en": "Emergency response"},
    "safety.disclaimer": {"zh": "本指南仅作参考，具体出行请以目的国官方公告、气象部门最新预警及使领馆提示为准。",
                         "en": "For reference only — always defer to official notices, weather authority warnings, and embassy advisories of your destination."},

    # 安全指南 - 特殊人群
    "safety.special": {"zh": "特殊人群出行须知", "en": "Special Traveler Guidelines"},
    "safety.special.sub": {"zh": "儿童、老人、孕妇等特殊人群需格外关注健康与安全",
                           "en": "Children, elderly, and pregnant travelers need extra health and safety attention"},
    "safety.children": {"zh": "儿童出行", "en": "Children"},
    "safety.elderly": {"zh": "老年人出行", "en": "Elderly"},
    "safety.pregnant": {"zh": "孕妇出行", "en": "Pregnant Travelers"},

    # 安全指南 - 紧急救援中心
    "safety.emergency.hotline": {"zh": "紧急联系热线", "en": "Emergency Hotlines"},
    "safety.emergency.consular": {"zh": "中国领事保护", "en": "China Consular Protection"},
    "safety.emergency.insurance": {"zh": "旅行保险建议", "en": "Travel Insurance"},
    "safety.emergency.copy": {"zh": "一键复制", "en": "Copy All"},
    "safety.emergency.copied": {"zh": "已复制到剪贴板", "en": "Copied to clipboard"},

    # 安全指南 - 东南亚特色活动
    "safety.activity": {"zh": "东南亚特色活动安全", "en": "Southeast Asia Activity Safety"},
    "safety.activity.sub": {"zh": "海岛、丛林、游船等特色活动的安全防范要点",
                           "en": "Safety tips for island, jungle, and boat activities"},
    "safety.notes": {"zh": "安全要点", "en": "Safety Notes"},
    "safety.firstaid": {"zh": "急救处理", "en": "First Aid"},

    # 活动类型
    "safety.act.island": {"zh": "海岛跳岛游", "en": "Island Hopping"},
    "safety.act.snorkel": {"zh": "浮潜与潜水", "en": "Snorkeling & Diving"},
    "safety.act.jungle": {"zh": "丛林徒步", "en": "Jungle Trekking"},
    "safety.act.boat": {"zh": "游船与漂流", "en": "Boat & Rafting"},
    "safety.act.temple": {"zh": "寺庙参观", "en": "Temple Visiting"},
    "safety.act.market": {"zh": "夜市与集市", "en": "Night Market & Bazaar"},

    # 安全指南 - 国家应急电话
    "safety.country.th": {"zh": "泰国", "en": "Thailand"},
    "safety.country.vn": {"zh": "越南", "en": "Vietnam"},
    "safety.country.my": {"zh": "马来西亚", "en": "Malaysia"},
    "safety.country.sg": {"zh": "新加坡", "en": "Singapore"},
    "safety.country.kh": {"zh": "柬埔寨", "en": "Cambodia"},
    "safety.country.la": {"zh": "老挝", "en": "Laos"},
    "safety.country.id": {"zh": "印度尼西亚", "en": "Indonesia"},
    "safety.country.ph": {"zh": "菲律宾", "en": "Philippines"},
    "safety.country.mm": {"zh": "缅甸", "en": "Myanmar"},
    "safety.country.bn": {"zh": "文莱", "en": "Brunei"},

    # 安全指南 - 新增强化内容
    "safety.weather.monsoon": {"zh": "季风与台风季", "en": "Monsoon & Typhoon Season"},
    "safety.weather.monsoon.hint": {
        "zh": "东南亚每年 5-11 月为雨季/台风季，出行前请查看 GOWFS 3 小时预报及台风路径，台风影响区域建议调整行程或改签",
        "en": "SE-Asia rainy/typhoon season runs May–Nov; check GOWFS 3-hour forecasts and typhoon tracks; consider rerouting if a storm is near"},
    "safety.weather.haze": {"zh": "雾霾与空气质量", "en": "Haze & Air Quality"},
    "safety.weather.haze.hint": {
        "zh": "旱季（2-4 月）马来、印尼等地可能出现烟霾，敏感人群建议佩戴 N95 口罩，减少长时间户外运动",
        "en": "Haze may affect Malaysia/Indonesia in Feb–Apr; sensitive groups should wear N95 masks and limit prolonged outdoor activity"},
    "safety.weather.uv": {"zh": "紫外线与高温", "en": "UV & Heat"},
    "safety.weather.uv.hint": {
        "zh": "东南亚紫外线指数常年 8-11（极高），SPF50+ PA++++ 防晒霜每 2 小时补涂，搭配遮阳帽与墨镜",
        "en": "UV index typically 8–11 (very high); reapply SPF50+ PA++++ every 2h, use a wide-brim hat and UV-blocking sunglasses"},

    "safety.emergency.export": {"zh": "导出紧急信息", "en": "Export Emergency Info"},
    "safety.emergency.card": {"zh": "应急联络卡", "en": "Emergency Contact Card"},
    "safety.checklist": {"zh": "出行准备清单", "en": "Pre-Trip Checklist"},
    "safety.checklist.sub": {
        "zh": "出发前逐项核对，确保证件、药品、应急物资齐全",
        "en": "Tick off before departure — documents, medications, and emergency supplies"},
    "safety.checklist.doc": {"zh": "证件资料", "en": "Documents"},
    "safety.checklist.med": {"zh": "药品物资", "en": "Medication"},
    "safety.checklist.finance": {"zh": "财务资金", "en": "Finance"},
    "safety.checklist.comms": {"zh": "通讯联络", "en": "Communication"},
    "safety.checklist.safety": {"zh": "安全防护", "en": "Safety Gear"},
    "safety.checklist.emergency": {"zh": "应急信息", "en": "Emergency Info"},

    "safety.country.weather": {"zh": "气候与天气提示", "en": "Climate & Weather Tips"},
    "safety.country.best_time": {"zh": "最佳出行季", "en": "Best Travel Season"},

    # 首页
    "home.brand": {"zh": "风雨智游", "en": "Weather Voyager"},
    "home.engine_ready": {"zh": "AI 气象引擎已就绪", "en": "AI weather engine ready"},
    "home.hero_desc": {"zh": "输入目的地、偏好与出行时间，结合实况 / 预报格点，生成穿搭、避雨、景点适配的专属攻略。",
                       "en": "Enter your destination, preferences, and travel dates — we combine live observations and forecast grids to generate tailored guides for outfits, rain avoidance, and landmark plans."},
    "home.destination": {"zh": "目的地", "en": "Destination"},
    "home.destination_placeholder": {"zh": "国家或城市，如：芽庄 / 下龙湾 / 吴哥 / 巴厘岛",
                                     "en": "Country or city, e.g. Nha Trang / Ha Long / Angkor / Bali"},
    "home.destination_tip": {"zh": "已收录 34 个目的地：国内（武汉）＋ 国外 10 国 33 城，全部在二级菜单中直接选择",
                              "en": "34 destinations: Wuhan (domestic) + 33 cities in 10 Southeast Asian countries, all selectable from the two-level menu"},
    "home.preference": {"zh": "旅行偏好", "en": "Travel preference"},
    "home.time": {"zh": "季节 / 出行时间", "en": "Season / Travel date"},
    "home.time_placeholder": {"zh": "示例：春季 / 20240101 / 202401010200",
                               "en": "e.g. Spring / 20240101 / 202401010200"},
    "home.time_tip": {"zh": "可输入季节文字，或 8 位日期(YYYYMMDD)，或精确到 12 位(YYYYMMDDHHMM)。气象数据来自 {{ data_year }} 年存档，输入的日期会自动映射到 {{ data_year }} 年同期。",
                      "en": "Enter a season name, 8-digit date (YYYYMMDD), or precise 12-digit datetime (YYYYMMDDHHMM). Weather data is archived from {{ data_year }}; your input will auto-map to the {{ data_year }} equivalent."},
    "home.start": {"zh": "开始查看", "en": "Start Planning"},
    "home.feature_route_desc": {"zh": "多国逐时 · 景观概率 · 人群行程", "en": "Multi-country hourly · Landscape odds · Crowd-aware itinerary"},
    "home.feature_qa_desc": {"zh": "真实 LLM · 中英问答 · 实景案例", "en": "Real LLM · Bilingual Q&A · Live cases"},
    "home.feature_science_desc": {"zh": "伴随科普 · 研学素材导出", "en": "Companion science · Study material export"},

    # 目的地二级菜单
    "nav.trip": {"zh": "行程规划", "en": "Trip Planner"},
    "dest.two_level": {"zh": "二级菜单", "en": "Two-level menu"},
    "dest.pick": {"zh": "选择目的地（国内 / 国外）", "en": "Choose a destination (domestic / overseas)"},
    "dest.level1": {"zh": "一级 · 国内 / 国外", "en": "Level 1 · Domestic / Overseas"},
    "dest.level2": {"zh": "二级 · 城市", "en": "Level 2 · City"},
    "dest.required": {"zh": "请先在二级菜单中选择目的地城市", "en": "Please pick a city from the menu first"},

    # 行程规划工具（trip_tool）
    "trip.title": {"zh": "行程规划工具 · 武汉", "en": "Trip Planner · Wuhan"},
    "trip.subtitle": {"zh": "输入日期，按当天逐时天气排景点顺序：时间窗 + 交通耗时由求解器计算，结果可复现。",
                      "en": "Enter a date and get Wuhan sights ordered by that day's hourly weather; time windows and travel time are solved, reproducible."},
    "trip.date": {"zh": "出行日期", "en": "Travel date"},
    "trip.max_spots": {"zh": "最多景点数", "en": "Max stops"},
    "trip.transport": {"zh": "交通方式", "en": "Transport"},
    "trip.transport.mixed": {"zh": "自动（步行 / 打车取快）", "en": "Auto (walk or taxi)"},
    "trip.transport.walk": {"zh": "只步行", "en": "Walk only"},
    "trip.transport.drive": {"zh": "只打车", "en": "Taxi only"},
    "trip.submit": {"zh": "生成行程", "en": "Plan my day"},
    "trip.tip": {"zh": "逐时天气取 Open-Meteo；景点与开放时间来自 data/wuhan，出行前请以官方公告为准。",
                 "en": "Hourly weather from Open-Meteo; sights and opening hours from data/wuhan — check official notices before you go."},
    "trip.planning": {"zh": "正在规划行程…", "en": "Planning your day…"},
    "trip.failed": {"zh": "规划失败", "en": "Planning failed"},
    "trip.solver": {"zh": "求解器", "en": "Solver"},
    "trip.stops": {"zh": "景点", "en": "Stops"},
    "trip.dropped": {"zh": "未安排", "en": "Not scheduled"},
    "trip.no_rain": {"zh": "全天无降水", "en": "No rain all day"},
    "trip.rain": {"zh": "降雨", "en": "Rain"},
    "trip.feels": {"zh": "体感最高", "en": "Feels like max"},
    "trip.total": {"zh": "合计交通", "en": "Travel total"},
    "trip.navigate": {"zh": "导航", "en": "Navigate"},
    "trip.warn": {"zh": "提示", "en": "Notes"},
    "trip.err_empty": {"zh": "请选择日期", "en": "Please pick a date"},
    "qa.source.tool": {"zh": "行程工具", "en": "Trip tool"},
}


def available_langs():
    return ["zh", "en"]


def normalize(lang):
    return lang if lang in ("zh", "en") else "zh"


def translate(key, lang="zh"):
    lang = normalize(lang)
    entry = _STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("zh", key))


def t_pairs():
    """返回 (key, {zh,en}) 全量，供需要枚举的场景使用"""
    return _STRINGS.items()
