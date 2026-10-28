"""Local travel workspace API. Saved plans are scoped to the browser session."""
import copy
import datetime as dt
import json
import secrets
import logging
from flask import Blueprint,request,jsonify,session,render_template,Response
from config import LLM_ENABLED,LLM_MODEL
from services.live_weather import fetch,today,now,WeatherUnavailable,provider_status
from trip_tool import datasource,hooks
from trip_tool.contract import dispatch
from trip_tool.planner_core import rain_exposure

bp=Blueprint("travel",__name__,url_prefix="/api/travel")

def payload():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): raise ValueError("请求体必须为 JSON 对象")
    return data

def owned_plan(pid):
    data=(session.get("plans") or {}).get(pid)
    if not data: raise ValueError("行程不存在或当前浏览器会话已过期，请重新生成。")
    return copy.deepcopy(data)

def save(result):
    if result.get("ok"):
        result["id"]=secrets.token_hex(12)
        plans=dict(session.get("plans") or {})
        plans[result["id"]]=result
        session["plans"]=dict(list(plans.items())[-6:])
        if not any(d["evidence"].get("mode")=="simulation" for d in result["days"]):
            session["route"]={"cities":["武汉"],"start":result["request"]["date"],
                              "days":len(result["days"]),"crowd":"free","lang":"zh",
                              "token":secrets.token_hex(6),"selected_spots":[]}
    return result

@bp.errorhandler(ValueError)
def bad_input(exc):
    return jsonify(ok=False,error=str(exc)),400

@bp.errorhandler(WeatherUnavailable)
def weather_error(exc):
    logging.getLogger('travel.weather').warning('Weather provider unavailable: %s',str(exc))
    return jsonify(ok=False,error=str(exc),code='weather_unavailable'),503

@bp.get("catalog")
def catalog():
    spots,templates,districts,meta=datasource.load()
    out=[]
    for sid,s in spots.items():
        oh=s.get("open_hours") or {}
        plannable=bool(oh.get("periods")) and not str(oh.get("confidence","")).startswith("低")
        out.append(dict(s,id=sid,plannable=plannable,opening_status="开放时间已收录" if plannable else "开放时间待核实"))
    status=provider_status()
    horizon=2 if status['active']=='weathercn' else 15
    return jsonify(ok=True,spots=out,districts=list(districts),today=today().isoformat(),provider=status,
                   max_date=(today()+dt.timedelta(days=horizon)).isoformat(),model=LLM_MODEL,llm_enabled=LLM_ENABLED)

@bp.get("weather")
def weather():
    date=request.args.get("date",today().isoformat())
    lat=float(request.args.get("lat",30.5506));lon=float(request.args.get("lon",114.3366))
    if not 29.8<=lat<=31.5 or not 113.5<=lon<=115.3: raise ValueError("请选择武汉周边起点")
    data=fetch(lat,lon,date,refresh=request.args.get("refresh")=="1")
    return jsonify(ok=True,**data)

@bp.post("plan")
def plan():
    data=payload()
    if any(k in data for k in ("data_dir","weather")): raise ValueError("真实规划不接受测试数据或自定义数据目录")
    result=dispatch("plan_trip",data)
    return jsonify(save(result)),200 if result.get("ok") else 422

def compare(original,updated):
    changes=[]
    old={s["spot_id"]:s for d in original["days"] for s in d["stops"]}
    new={s["spot_id"]:s for d in updated.get("days",[]) for s in d["stops"]}
    for sid,s in old.items():
        if sid not in new: changes.append(dict(kind="removed",name=s["name"],text="新天气与时间约束下移出；在候选未安排原因中可查看详情"))
        elif new[sid]["arrive"]!=s["arrive"]:
            changes.append(dict(kind="moved",name=s["name"],text=s["arrive"]+" → "+new[sid]["arrive"]+"；"+new[sid]["reason"]))
    for sid,s in new.items():
        if sid not in old: changes.append(dict(kind="added",name=s["name"],text=s["reason"]))
    before=sum(rain_exposure(d["stops"],n["hours"]) for d,n in zip(original["days"],updated.get("days",[])))
    after=sum(d["totals"]["rain_exposure_min"] for d in updated.get("days",[]))
    return dict(changes=changes,before_rain_min=before,after_rain_min=after,
                label="原行程与新行程均按同一份更新天气评估；仅计景点停留，不含交通")

@bp.post("replan")
def replan():
    data=payload();original=owned_plan(data.get("id"))
    if any(d["evidence"].get("mode")=="simulation" for d in original["days"]):
        raise ValueError("请从真实行程刷新天气，模拟方案不能作为真实基线")
    req=dict(original["request"],refresh=True)
    result=dispatch("plan_trip",req)
    if result.get("ok"):
        result["comparison"]=compare(original,result)
        result["parent_id"]=original["id"]
    return jsonify(save(result)),200 if result.get("ok") else 422

@bp.post("scenario")
def scenario():
    data=payload();original=owned_plan(data.get("id"))
    if len(original["days"])!=1: raise ValueError("天气推演暂支持单日行程")
    a,b,mm=int(data.get("from",13)),int(data.get("to",17)),float(data.get("rain",3))
    if not 0<=a<b<=24 or not 0<=mm<=15: raise ValueError("推演时间或降水值无效")
    rows=copy.deepcopy(original["days"][0]["hours"])
    for r in rows:
        if a<=r["hour"]<b: r.update(precip=mm,precip_prob=95)
    req=dict(original["request"],weather={"hours":rows})
    result=dispatch("plan_trip",req)
    if result.get("ok"):
        result["comparison"]=compare(original,result)
        result["scenario_label"]=f"模拟推演：{a:02}:00–{b:02}:00 降水 {mm:g} mm/h，不是真实预报"
    return jsonify(save(result)),200 if result.get("ok") else 422

@bp.get("plans/<pid>")
def get_plan(pid):
    return jsonify(owned_plan(pid))

@bp.get("plans/<pid>/export")
def export(pid):
    result=owned_plan(pid)
    if request.args.get("format")=="json":
        return Response(json.dumps(result,ensure_ascii=False,indent=2),mimetype="application/json",
                        headers={"Content-Disposition":"attachment; filename=weather-trip.json"})
    return render_template("travel_print.html",plan=result)

@bp.post("chat")
def chat():
    data=payload();q=data.get("question","")
    if not isinstance(q,str) or not q.strip() or len(q)>1500: raise ValueError("问题需为 1–1500 字")
    context={"city":"武汉","today":today().isoformat(),"source":"尚未载入行程"}
    if data.get("id"):
        p=owned_plan(data["id"])
        d=p["days"][0]
        context.update(source=d["evidence"]["label"],date=d["date"],pre=d["weather"]["precip_total_mm"],tmp=d["weather"]["feels_max"],
                       itinerary=p["summary_text"],evidence=d["evidence"])
    from services import llm_client
    text,used=llm_client.ask_with_tools(q,context,"zh") if LLM_ENABLED else (None,False)
    if text: return jsonify(ok=True,answer=text,source=LLM_MODEL,used_tools=used)
    # Explicitly identified deterministic fallback; never invent weather.
    if data.get("id"):
        text=p["summary_text"]+"\n\n"+"；".join(p["warnings"][:4])
    else:
        text="请先选择日期并生成行程。我会根据逐时天气、开放时间和交通时间安排游览；你也可以在气象研学页面了解现象原理。"
    return jsonify(ok=True,answer=text,source="规则助手（模型暂不可用）",used_tools=False)

@bp.get("health")
def health():
    return jsonify(ok=True,date=today().isoformat(),model=LLM_MODEL,llm_configured=LLM_ENABLED,
                   weather_source=provider_status()['active'],provider=provider_status(),routing_source="OSRM / 明示的距离估算",version="2.1")
