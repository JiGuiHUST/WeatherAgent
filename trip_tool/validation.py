"""Validate all untrusted planning inputs before network or solver work."""
import datetime as dt
import math
from .opening import minutes

def validate(req):
    if not isinstance(req,dict): return False,"参数必须是 JSON 对象"
    try:
        if req.get("date"):
            if len(str(req["date"]))!=10: raise ValueError("date 必须为 YYYY-MM-DD")
            dt.date.fromisoformat(req["date"])
        for key,lo,hi in (("days",1,5),("max_spots",1,8),("suit_min",0,100),("rel_band",0,100),("buffer_min",0,60)):
            if key in req and (isinstance(req[key],bool) or int(req[key])!=float(req[key]) or not lo<=int(req[key])<=hi):
                raise ValueError(f"{key} 必须为 {lo}–{hi} 的整数")
        if req.get("transport","mixed") not in ("walk","drive","mixed"): raise ValueError("交通方式无效")
        for key in ("selected_spots","must_visit","avoid","districts","preferences"):
            if key in req and (not isinstance(req[key],list) or len(req[key])>60 or any(not isinstance(x,str) or len(x)>120 for x in req[key])):
                raise ValueError(key+" 必须是字符串数组")
        start=req.get("start") or {}
        if not isinstance(start,dict): raise ValueError("start 必须是起点对象")
        for key,lo,hi in (("lat",29.8,31.5),("lon",113.5,115.3)):
            if key in start and (not math.isfinite(float(start[key])) or not lo<=float(start[key])<=hi):
                raise ValueError("起点坐标必须位于武汉周边")
        if not isinstance(start.get("name",""),str) or len(start.get("name",""))>120: raise ValueError("起点名称无效")
        a,b=minutes(start.get("time","09:00")),minutes(req.get("end_by","20:30"))
        if not 0<=a<b<=1440: raise ValueError("结束时间必须晚于出发时间")
        radius=float(req.get("max_radius_km",30))
        if not math.isfinite(radius) or not 1<=radius<=100: raise ValueError("半径必须为 1–100 公里")
        if "weather" in req:
            rows=req["weather"].get("hours") if isinstance(req["weather"],dict) else None
            if not isinstance(rows,list) or len(rows)!=24 or {r.get("hour") for r in rows if isinstance(r,dict)}!=set(range(24)):
                raise ValueError("注入天气必须包含完整且不重复的 0–23 时记录")
            for r in rows:
                for key in ("tmp","apparent_temp","precip","wind10_speed","wind_gusts","visibility","uv_index","precip_prob"):
                    if r.get(key) is not None and (isinstance(r[key],bool) or not isinstance(r[key],(int,float)) or not math.isfinite(float(r[key]))): raise ValueError("天气数值无效")
                if r.get("thunder") is not None and not isinstance(r["thunder"],bool): raise ValueError("雷暴字段应为布尔或缺失")
    except (ValueError,TypeError,AttributeError) as e:
        return False,str(e) or "参数无效"
    return True,None
