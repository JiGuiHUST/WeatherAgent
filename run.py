# -*- coding: utf-8 -*-
"""程序启动入口：flask run 主文件
路由：/ 目的地气候规划, /strategy 单城攻略,
      /route 行程气象助手,
      /qa 气象问答, /science 气象研学课堂+素材导出, /export/<kind>
"""
import os
import logging
import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, g, send_file, abort, jsonify,
)

from config import (
    HOST, PORT, DEBUG, SECRET_KEY,
    TEMPLATE_DIR, STATIC_DIR, LOG_DIR, PREFERENCES, SEASON_MONTH,
    CITY_BBOX_FILE, TRAVEL_SPOTS_FILE, LLM_ENABLED,
)
from utils.common import validate_form, parse_time_input, data_today_str, DATA_YEAR
from utils.i18n import translate, normalize
from utils.visual import weather_icon, comfort_icon, prob_color, prob_level
from services.travel_engine import generate_strategy, _load_json
from services import weather_api
from services.forecast_service import build_route_forecast
from services.landscape_engine import predict_for_route
from services.itinerary_planner import plan as plan_itinerary
from services.qa_engine import answer as qa_answer, example_questions
from services.science_engine import (
    companion_push, build_handbook, build_observation_record,
    build_question_bank, build_diagram,
)

# ===================== 日志配置 =====================
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("run")

CROWD_OPTIONS = ["free", "family", "photo", "study"]


def _crowd_labels(lang):
    m = {
        "free": ("自由行", "Independent"),
        "family": ("亲子游", "Family"),
        "photo": ("摄影游", "Photography"),
        "study": ("研学游", "Study tour"),
    }
    return [(k, (m[k][0] if lang != "en" else m[k][1])) for k in CROWD_OPTIONS]


def _temp_cls(tmp):
    if tmp is None:
        return ""
    if tmp >= 30:
        return "hot"
    if tmp >= 25:
        return "warm"
    return "cool"


def create_app():
    app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

    # ---- Jinja 全局 / 过滤器 ----
    app.jinja_env.globals["t"] = lambda key: translate(key, getattr(g, "lang", "zh"))
    app.jinja_env.globals["weather_icon"] = weather_icon
    app.jinja_env.globals["comfort_icon"] = comfort_icon
    app.jinja_env.globals["prob_color"] = prob_color
    app.jinja_env.globals["prob_level"] = lambda p: prob_level(p, getattr(g, "lang", "zh"))
    app.jinja_env.filters["temp_cls"] = _temp_cls

    # ---- 语言处理 ----
    @app.before_request
    def _set_lang():
        lang = request.args.get("lang")
        if lang in ("zh", "en"):
            session["lang"] = lang
        g.lang = normalize(session.get("lang", "zh"))

    @app.context_processor
    def _inject():
        return {"lang": g.lang, "other_lang": "en" if g.lang == "zh" else "zh", "data_year": DATA_YEAR}

    # ---------- 目的地气候规划 ----------
    @app.route("/")
    def index():
        return render_template("index.html", preferences=PREFERENCES)

    # ---------- 单城攻略 ----------
    @app.route("/strategy", methods=["GET", "POST"])
    def strategy():
        if request.method == "GET":
            return redirect(url_for("index"))
        destination = request.form.get("destination", "")
        preference = request.form.get("preference", "")
        time_input = request.form.get("time_input", "")
        ok, err = validate_form(destination, preference, time_input, PREFERENCES)
        if not ok:
            return render_template("error.html", code="401", message="输入有误", detail=err), 401
        ctx = generate_strategy(destination, preference, time_input)
        if ctx is None:
            from services.travel_engine import _city_bbox
            available = list(_city_bbox().keys())
            detail = f"暂未收录「{destination}」"
            if available:
                detail += f"，可用城市（共 {len(available)} 个）：{', '.join(available[:12])}"
                if len(available) > 12:
                    detail += f" 等 {len(available)} 座城市"
                detail += "；也可输入国家名（如：泰国、越南、Singapore、Thailand）自动匹配该国热门城市"
            return render_template(
                "error.html", code="404", message="未找到目的地", detail=detail
            ), 404
        logger.info("生成攻略: %s | %s | %s", destination, preference, time_input)
        return render_template("strategy.html", **ctx)

    # ---------- 景点列表（按城市）----------
    @app.route("/spots/<path:city>")
    def spots_by_city(city):
        """返回某城市所有景点的扁平列表，供前端『选景点』对话框渲染复选框。
        数据来源：data/travel_spots.json  结构 {city: {category: [spot]}} -> [{category, name, desc, weather_tip, lat, lon}]
        """
        import json as _json
        spots_data = _load_json(TRAVEL_SPOTS_FILE)
        city_key = city.strip()
        # 模糊匹配（与 resolve_city 思路一致，避免 URL 编码差异）
        if city_key not in spots_data:
            for k in spots_data:
                if city_key in k or k in city_key:
                    city_key = k
                    break
        city_cats = spots_data.get(city_key, {})
        flat = []
        for cat, spots_list in city_cats.items():
            for s in spots_list or []:
                if "lat" not in s or "lon" not in s:
                    continue
                flat.append({
                    "city": city_key,
                    "category": cat,
                    "name": s.get("name", ""),
                    "desc": s.get("desc", ""),
                    "weather_tip": s.get("weather_tip", ""),
                    "lat": s.get("lat"),
                    "lon": s.get("lon"),
                })
        return jsonify({"ok": True, "city": city_key, "spots": flat})

    # ---------- 行程气象助手 ----------
    @app.route("/route", methods=["GET", "POST"])
    def route():
        import json as _json
        cities_all = list(_load_json(CITY_BBOX_FILE).keys())
        lang = g.lang
        if request.method == "GET":
            return render_template("route.html", cities=cities_all, crowds=_crowd_labels(lang),
                                   selected=[], start="", days=2, crowd="free",
                                   selected_spots_json="[]")

        cities = request.form.getlist("cities")
        start = (request.form.get("start") or "").strip()
        days = request.form.get("days", "2")
        crowd = request.form.get("crowd", "free")
        if not cities:
            return render_template("error.html", code="401", message="请至少选择一个城市",
                                   detail="请在途经城市中至少勾选一项"), 401
        try:
            days = max(1, min(5, int(days)))
        except ValueError:
            days = 2

        # 解析前端『选景点』对话框回传的景点列表（JSON 字符串）
        selected_spots = []
        raw_spots = (request.form.get("selected_spots") or "").strip()
        if raw_spots:
            try:
                selected_spots = _json.loads(raw_spots)
                if not isinstance(selected_spots, list):
                    selected_spots = []
            except (_json.JSONDecodeError, ValueError) as e:
                logger.warning("selected_spots 解析失败: %s", e)
                selected_spots = []
        # 只保留与本次勾选城市匹配的景点，避免脏数据
        sel_cities = set(cities)
        selected_spots = [s for s in selected_spots if s.get("city") in sel_cities]

        rf = build_route_forecast(cities, start or data_today_str(), days, lang,
                                  selected_spots=selected_spots)
        start_dt, _ = parse_time_input(start or data_today_str(), SEASON_MONTH)
        landscapes = predict_for_route([s["city"] for s in rf["segments"]], start_dt, lang)

        # 行程部分延后异步生成：存参数到 session 并生成 token，前端加载完主线段后
        # 调 /route_itinerary_async?token=xxx 拉取，避免用户等 LLM 缓慢响应
        import uuid
        token = uuid.uuid4().hex[:12]
        session["route"] = {
            "cities": [s["city"] for s in rf["segments"]],
            "start": start, "days": days, "crowd": crowd,
            "lang": lang,
            "token": token,
            "itin_pending": True,  # 表示尚未生成，需要异步端点去生成
            "selected_spots": selected_spots,  # 供 /route_spots_async 复用
        }

        result = {**rf, "landscapes": landscapes,
                  "itinerary": None,  # 行程暂空，前端展示骨架屏
                  "itin_token": token,
                  "selected_spots_json": _json.dumps(selected_spots, ensure_ascii=False)}

        return render_template("route.html", cities=cities_all, crowds=_crowd_labels(lang),
                               selected=cities, start=start, days=days, crowd=crowd, result=result,
                               llm_enabled=LLM_ENABLED,
                               selected_spots_json=_json.dumps(selected_spots, ensure_ascii=False))

    # ---------- 景点级预报异步端点（配合 /route 结果页渲染）----------
    @app.route("/route_spots_async")
    def route_spots_async():
        """根据 session 中保存的 selected_spots 重新生成景点级精确预报。
        若 session 已带 spot_cache 且未 force，直接返回缓存。
        """
        lang = g.lang
        rd = session.get("route") or {}
        token = request.args.get("token", "")
        force = request.args.get("force", "") == "1" or bool(request.args.get("_", ""))
        if not rd or rd.get("token") != token:
            return jsonify({"ok": False, "error": "session_expired"}), 400

        if force:
            rd.pop("spot_cache", None)

        if rd.get("spot_cache") is not None:
            return jsonify({"ok": True, **rd["spot_cache"]})

        spots = rd.get("selected_spots") or []
        if not spots:
            payload = {"spots": []}
            rd["spot_cache"] = payload
            session["route"] = rd
            return jsonify({"ok": True, **payload})

        try:
            start_dt, _ = parse_time_input(rd.get("start") or data_today_str(), SEASON_MONTH)
        except Exception as e:
            logger.warning("景点异步：日期解析失败 %s", e)
            return jsonify({"ok": False, "error": "date_parse_failed"}), 500

        from services.forecast_service import build_spot_forecasts
        try:
            spot_forecasts = build_spot_forecasts(spots, start_dt, int(rd.get("days", 1)), lang)
        except Exception as e:
            logger.warning("景点异步：景点级预报生成失败 %s", e)
            return jsonify({"ok": False, "error": "spots_build_failed"}), 500

        payload = {"spots": spot_forecasts}
        rd["spot_cache"] = payload
        session["route"] = rd
        return jsonify({"ok": True, **payload})

    # ---------- 行程异步生成端点（配合 /route 骨架屏）----------
    @app.route("/route_itinerary_async")
    def route_itinerary_async():
        lang = g.lang
        rd = session.get("route") or {}
        token = request.args.get("token", "")
        force = request.args.get("force", "") == "1" or bool(request.args.get("_", ""))
        if not rd or rd.get("token") != token or not rd.get("cities"):
            return jsonify({"ok": False, "error": "session_expired"}), 400

        # 强制重新生成：清缓存
        if force:
            rd.pop("itin_ready", None)
            rd.pop("itin_cache", None)
            rd["itin_pending"] = True

        # 已生成且未 force → 直接返回
        if rd.get("itin_ready") and rd.get("itin_cache") is not None:
            return jsonify({"ok": True, **rd["itin_cache"]})

        try:
            rf = build_route_forecast(rd["cities"], rd.get("start") or data_today_str(),
                                      int(rd.get("days", 1)), lang)
        except Exception as e:
            logger.warning("行程异步：路线重建失败 %s", e)
            return jsonify({"ok": False, "error": "route_build_failed"}), 500

        try:
            itin = plan_itinerary(rf, rd.get("crowd", "free"), lang)
        except Exception as e:
            logger.warning("行程异步：行程生成异常 %s", e)
            return jsonify({"ok": False, "error": "itinerary_failed"}), 500

        payload = {
            "days": itin["days"],
            "road_risk": itin["road_risk"],
            "crowd": itin["crowd"],
            "source": itin["source"],
        }
        rd["itin_ready"] = True
        rd["itin_cache"] = payload
        rd["itin_pending"] = False
        session["route"] = rd
        return jsonify({"ok": True, **payload})

    # ---------- 双语气象问答 ----------
    @app.route("/qa", methods=["GET", "POST"])
    def qa():
        lang = g.lang
        history = session.get("qa_history", [])
        if request.method == "POST":
            q = request.form.get("question", "").strip()
            if q:
                w = _weather_for_qa(lang)
                res = qa_answer(q, w, lang)
                history.append({"q": q, "a": res["answer"], "anim": res["anim"],
                                "source": res.get("source", "")})
                history = history[-12:]
                session["qa_history"] = history
        return render_template("qa.html", history=history,
                               examples=example_questions(lang),
                               live_case=_weather_for_qa(lang),
                               llm_enabled=LLM_ENABLED)

    # ---------- 气象研学课堂 + 导出 ----------
    @app.route("/science")
    def science():
        lang = g.lang
        rf, landscapes, _ = _route_from_session(lang)
        push = companion_push(rf, lang) if rf else []
        diagram_path = build_diagram(lang)
        diagram_url = ("/static/weather_img/" + os.path.basename(diagram_path)) if diagram_path else None
        return render_template("science.html", push=push, diagram_url=diagram_url)

    # ---------- 出行安全指南 ----------
    @app.route("/safety")
    def safety():
        return render_template("safety.html")

    @app.route("/export/<kind>")
    def export(kind):
        lang = g.lang
        rf, landscapes, _ = _route_from_session(lang)
        if not rf:
            return redirect(url_for("route"))
        if kind == "handbook":
            text = build_handbook(rf, landscapes, lang)
            return _send_text(text, "weather_handbook.md")
        if kind == "record":
            return _send_text(build_observation_record(rf, lang), "observation_record.md")
        if kind == "bank":
            return _send_text(build_question_bank(lang), "quiz_bank.md")
        if kind == "diagram":
            path = build_diagram(lang)
            if path and os.path.exists(path):
                return send_file(path, as_attachment=True, download_name="weather_diagram.png")
            abort(404)
        abort(404)

    # ---------- 错误处理 ----------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code="404", message="页面走丢了", detail="你访问的页面不存在。"), 404

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template("error.html", code="401", message="请求未授权", detail="请检查输入或重新从首页进入。"), 401

    @app.errorhandler(413)
    def too_large(e):
        return render_template("error.html", code="413", message="请求过大", detail="提交内容超过限制。"), 413

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("服务器内部错误: %s", e)
        return render_template("error.html", code="500", message="服务器开小差了", detail="气象接口或渲染异常，请稍后重试。"), 500

    return app


def _send_text(text, filename):
    import io
    buf = io.BytesIO(text.encode("utf-8"))
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="text/markdown")


def _route_from_session(lang):
    """从会话还原路线预报（天气调用有缓存，低成本）。返回 (route_forecast, landscapes, start_dt) 或 (None, [], None)"""
    rd = session.get("route")
    if not rd:
        return None, [], None
    try:
        rf = build_route_forecast(rd["cities"], rd["start"] or data_today_str(),
                                  rd.get("days", 1), lang)
        start_dt, _ = parse_time_input(rd["start"] or data_today_str(), SEASON_MONTH)
        landscapes = predict_for_route([s["city"] for s in rf["segments"]], start_dt, lang)
        return rf, landscapes, start_dt
    except Exception as e:
        logger.warning("会话路线重建失败: %s", e)
        return None, [], None


def _weather_for_qa(lang):
    """构造 QA 实景案例所需的当日天气。优先用会话路线首城首日。"""
    rd = session.get("route")
    city_map = _load_json(CITY_BBOX_FILE)
    from services.travel_engine import resolve_city, _mock_weather
    from services.forecast_service import _derive_wind, _derive_visibility

    if rd and rd.get("cities"):
        city = resolve_city(rd["cities"][0]) or rd["cities"][0]
        start = rd.get("start") or data_today_str()
    else:
        city = "芽庄"
        start = data_today_str()

    info = city_map.get(city)
    if not info:
        return {"city": city}
    start_dt, season = parse_time_input(start, SEASON_MONTH)
    summary = weather_api.get_weather_summary(start_dt, info["bbox"])
    if summary is None:
        summary = _mock_weather(info, season)
    tmp = summary.get("avg_tmp")
    pre = summary.get("total_pre") or 0
    rh = summary.get("avg_rh") or 78
    wind = _derive_wind(pre, 14)
    vis = _derive_visibility(pre, rh, 14)
    return {"city": city, "tmp": tmp, "pre": pre, "rh": rh, "wind": wind,
            "vis": vis, "season": season}


app = create_app()


if __name__ == "__main__":
    logger.info("==== 气象旅行攻略启动 %s ====", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    app.run(host=HOST, port=PORT, debug=DEBUG)
