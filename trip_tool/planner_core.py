"""Real weather constrained planning. Every stop is checked for its whole stay."""
from __future__ import annotations
import datetime as dt
import time
from services.live_weather import fetch, now, today
from . import datasource, hooks, opening, routing, scoring
from .geo import amap_nav_url
from .solver import pick_solver

SUIT_MIN, REL_BAND = 55, 30
DEFAULT_START = {"name":"洪山广场","lat":30.5506,"lon":114.3366,"time":"09:00"}

def _hm(text, default):
    return opening.minutes(text) if text else default

def _stay_minutes(spot):
    return max(30,round(float((spot.get("features") or {}).get("typical_duration_h") or 1.5)*60))

def score_hour(spot, template, hour, scorer=None):
    return (scorer or hooks.get("scorer") or scoring.DEFAULT_SCORER).score(spot,template,hour)

def risk_reason(spot,row):
    if spot.get("type")=="indoor": return None
    if any(row.get(k) is None for k in ("precip","apparent_temp","wind10_speed","thunder")):
        return "关键天气字段缺失，无法确认户外适宜性"
    if row.get("thunder"): return "雷暴时段暂停户外活动"
    if (row.get("precip") or 0)>=2.5: return "降雨较强，转为室内活动"
    if (row.get("wind_gusts") or 0)>=17.2: return "强阵风，不安排户外活动"
    if (row.get("wind10_speed") or 0)>=10.8 or (row.get("apparent_temp") or 0)>=38:
        return "大风或体感高温，不安排户外活动"
    if spot.get("type") in ("elevated_view","waterside_open") and (row.get("wind10_speed") or 0)>=8:
        return "临水或登高区域风速偏大"
    return None

def interval_rows(hours,start,end):
    return [r for r in hours if r["hour"]*60<end and (r["hour"]+1)*60>start]

def build_window(spot,template,hours,weekday,day_start,day_end,stay,suit_min=SUIT_MIN,rel_band=REL_BAND,scorer=None):
    periods=opening.periods(spot,weekday)
    if periods is None: return dict(windows=[],peak=0,closed=False,note="开放时间未知，未纳入可执行行程")
    if not periods: return dict(windows=[],peak=0,closed=True,note="当日闭馆")
    scores={r["hour"]:score_hour(spot,template,r,scorer)[0] for r in hours}
    good={r["hour"] for r in hours if not risk_reason(spot,r) and scores[r["hour"]]>=suit_min}
    runs=[]
    for h in sorted(good):
        if runs and h==runs[-1][-1]+1: runs[-1].append(h)
        else: runs.append([h])
    wins=[]
    for run in runs:
        for a,close,last in periods:
            lo=max(a,run[0]*60,day_start)
            hi=min(close-stay,(run[-1]+1)*60-stay,day_end-stay,last)
            if lo<=hi: wins.append((lo,hi,min(scores[h] for h in run)))
    return dict(windows=wins,peak=max(scores.values(),default=0),closed=False,
                note="全程停留满足开放与天气约束" if wins else "开放时间与完整适宜停留时段无重叠")

def day_peak(spot,template,hours,scorer=None):
    return max([(score_hour(spot,template,r,scorer)[0],r["hour"]) for r in hours if 8<=r["hour"]<=20],default=(0,None))

def resolve_weather(lat,lon,date_iso,districts,warnings,injected=None):
    if injected: return injected,"injected"
    provider=hooks.get("weather_provider")
    if provider: return provider.hourly(lat,lon,date_iso),provider.describe().get("kind","custom")
    data=fetch(lat,lon,date_iso)
    return data["hours"],data["label"]

def day_brief(hours,source):
    rain=[r["hour"] for r in hours if (r.get("precip") or 0)>=.5]
    feels=[r["apparent_temp"] for r in hours if r.get("apparent_temp") is not None]
    complete=len(hours)==24 and all(r.get('precip') is not None for r in hours)
    return dict(source=source,precip_total_mm=round(sum(r['precip'] for r in hours),1) if complete else None,
                partial_day=not complete,
                rain_start=min(rain) if rain else None,rain_end=max(rain) if rain else None,
                feels_max=max(feels) if feels else None,thunder=any(r.get("thunder") for r in hours))

def _resolve_ids(items,spots):
    result,unknown=[],[]
    for item in items or []:
        sid=item if item in spots else next((k for k,s in spots.items() if s["name"]==item),None)
        (result if sid else unknown).append(sid or item)
    return result,unknown

def _reason(spot,rows,hits):
    rain=max((r['precip'] for r in rows if r.get('precip') is not None),default=None)
    temps=[r["apparent_temp"] for r in rows if r.get("apparent_temp") is not None]
    text=f"停留全程最大降水 {rain:g} mm/h" if rain is not None and all(r.get('precip') is not None for r in rows) else '停留时段降水量数据不完整'
    if temps: text+=f"，体感 {min(temps):g}–{max(temps):g}°C"
    text+="；室内场馆可避雨" if spot.get("type")=="indoor" else "；完整停留时段通过户外天气约束"
    if any(h["verdict"]=="unknown" for h in hits): text+="；部分非关键因子缺失，适宜指数已扣分"
    return text

def plan(request=None,**kwargs):
    return plan_request(dict(request or {},**kwargs))

def plan_trip(date,**kwargs):
    return plan(dict(date=date,**kwargs))

def plan_request(req):
    from .contract import validate
    valid,error=validate(req)
    if not valid: return dict(ok=False,error=error)
    started=time.monotonic()
    date=dt.date.fromisoformat(req.get("date") or today().isoformat())
    warnings,days,visited=[],[],set()
    source=hooks.get("spot_source")
    if source:
        spots,templates,districts=source.load_spots(),source.load_type_templates(),source.load_districts()
        meta=dict(source=source.describe(),warnings=[])
    else: spots,templates,districts,meta=datasource.load(req.get("data_dir"))
    warnings.extend(meta["warnings"])
    if meta["source"].get("kind")=="bootstrap" and not hooks.get("weather_provider"):
        return dict(ok=False,error="正式景点数据缺失，不能生成真实行程。")
    start=dict(DEFAULT_START,**(req.get("start") or {}))
    start["lat"],start["lon"]=float(start["lat"]),float(start["lon"])
    day_start,day_end=_hm(start.get("time"),540),_hm(req.get("end_by"),1230)
    must,unknown=_resolve_ids(req.get("must_visit"),spots)
    if unknown: return dict(ok=False,error="未识别必去景点："+"、".join(unknown))
    avoid,_=_resolve_ids(req.get("avoid"),spots)
    selected,unknown_selected=_resolve_ids(req.get("selected_spots"),spots)
    if unknown_selected: return dict(ok=False,error="未识别候选景点："+"、".join(unknown_selected))
    solver=pick_solver(hooks.get("solver"))
    max_spots,rejected=int(req.get("max_spots",4)),[]
    for offset in range(int(req.get("days",1))):
        current=date+dt.timedelta(days=offset)
        dstr=current.isoformat()
        injected=(req.get("weather") or {}).get("hours")
        provider=hooks.get("weather_provider")
        if injected or provider:
            hours,label=resolve_weather(start["lat"],start["lon"],dstr,districts,warnings,injected)
            evidence=dict(source=label,label="人工模拟 / 测试注入",mode="simulation",target_date=dstr,
                          fetched_at=now().isoformat(),spatial_scope="区域代表点",timezone="Asia/Shanghai")
        else:
            evidence=fetch(start["lat"],start["lon"],dstr,refresh=bool(req.get("refresh")))
            hours=evidence["hours"]
            evidence={k:v for k,v in evidence.items() if k!="hours"}
            if evidence.get('source')=='华风爱科':
                if evidence.get('alerts_status')!='available':
                    return dict(ok=False,error='华风爱科预警接口尚未验证可用，暂不生成可执行行程。请开通天气预警权限。')
                warnings.append('华风爱科预警为查询时发布状态，不能代表未来出行时段没有风险；出发前请刷新。')
                for alert in evidence.get('alerts',[]):
                    try:
                        a=dt.datetime.fromisoformat(str(alert.get('start')).replace('Z','+00:00')).date()
                        b=dt.datetime.fromisoformat(str(alert.get('end')).replace('Z','+00:00')).date()
                        relevant=a<=current<=b
                    except (ValueError,TypeError):relevant=True
                    if relevant:return dict(ok=False,error='当地存在官方气象预警：'+str(alert.get('title') or '气象预警')+'。暂缓自动行程规划，请查看预警与景区公告。')
        effective_start=day_start
        if current==today() and not injected and not provider:
            effective_start=max(day_start,now().hour*60+now().minute+20)
        if effective_start>=day_end: return dict(ok=False,error="今天可用时间已结束，请选择明天或调整结束时间。")
        pool=[]
        for sid,s in spots.items():
            if sid in avoid or sid in visited or selected and sid not in selected and sid not in must: continue
            if req.get("districts") and s.get("district") not in req["districts"] and sid not in must: continue
            distance=routing.haversine_km(start["lat"],start["lon"],s["lat"],s["lon"])
            if distance>float(req.get("max_radius_km",30)) and sid not in must: continue
            if str((s.get("open_hours") or {}).get("confidence","")).startswith("低"):
                rejected.append(dict(spot_id=sid,name=s["name"],why="开放时间可信度低，待核实后纳入规划")); continue
            if s.get("best_months") and current.month not in s["best_months"] and s.get("type")=="flower":
                rejected.append(dict(spot_id=sid,name=s["name"],why="不在已收录观赏季节，不能保证开放或花期")); continue
            tpl=templates.get("templates",{}).get(s.get("type"))
            if tpl is None:
                rejected.append(dict(spot_id=sid,name=s["name"],why="缺少气象敏感度模板")); continue
            stay=_stay_minutes(s)
            window=build_window(s,tpl,hours,current.weekday(),effective_start,day_end,stay,int(req.get("suit_min",SUIT_MIN)))
            if not window["windows"]:
                rejected.append(dict(spot_id=sid,name=s["name"],why=window["note"])); continue
            blob=" ".join([s["name"],s.get("notes") or "",s.get("exposure","")])
            bonus=sum(12 for p in req.get("preferences",[]) if p in blob)
            pool.append((sid,s,tpl,stay,window,distance,bonus))
        unavailable=[spots[s]["name"] for s in must if s not in visited and s not in [p[0] for p in pool]]
        if unavailable: return dict(ok=False,error="必去景点当前不可行："+"、".join(unavailable),rejected=rejected)
        pool.sort(key=lambda p:(p[0] not in must,-(p[4]["peak"]+p[6]),p[5]))
        pool=pool[:24]
        if not pool: return dict(ok=False,error="没有满足开放、完整停留与天气约束的景点，请调整日期、起点或筛选。",rejected=rejected)
        nodes=[start]+[p[1] for p in pool]
        matrix_provider=hooks.get("matrix_provider") or routing.DEFAULT_MATRIX
        before=len(warnings)
        mins,km,modes=routing.with_fallback(matrix_provider,nodes,req.get("transport","mixed"),warnings)
        matrix_kind="直线距离估算" if len(warnings)>before or isinstance(matrix_provider,routing.StraightLineMatrix) else "OSRM 路网估时"
        for i in range(len(nodes)):
            for j in range(len(nodes)):
                if i!=j: mins[i][j]+=int(req.get("buffer_min",10))
        problem=dict(n=len(nodes),mins=mins,stay=[0]+[p[3] for p in pool],windows={i+1:p[4]["windows"] for i,p in enumerate(pool)},
                     day_start=effective_start,day_end=day_end,max_spots=max_spots,must_nodes=[i+1 for i,p in enumerate(pool) if p[0] in must])
        order,dropped=solver.solve(problem)
        stops,prev,departure,travel_min,travel_km=[],0,effective_start,0,0.
        for node,arrive in order:
            sid,s,tpl,stay,window,dist,bonus=pool[node-1]
            leave=arrive+stay
            rows=interval_rows(hours,arrive,leave)
            if not any(a<=arrive<=b for a,b,_ in window["windows"]) or leave>day_end or arrive<departure+mins[prev][node]:
                return dict(ok=False,error="行程未通过最终时间校验，请调整条件。")
            if len(rows)!=len(set(range(arrive//60,(leave-1)//60+1))) or any(risk_reason(s,r) for r in rows):
                return dict(ok=False,error="行程未通过完整停留天气校验。")
            leg_rows=interval_rows(hours,arrive-mins[prev][node],arrive)
            required_leg_hours=set(range((arrive-mins[prev][node])//60,(arrive-1)//60+1))
            if {r['hour'] for r in leg_rows}!=required_leg_hours or any(r.get('precip') is None or r.get('wind10_speed') is None or r.get("thunder") is not False or (r.get("precip") or 0)>=10 or (r.get('wind10_speed') or 0)>=17.2 or (r.get("wind_gusts") or 0)>=20.8 for r in leg_rows):
                return dict(ok=False,error="转场时段存在雷暴、极强降水或关键风险数据缺失，建议暂缓出发或调整出发时间。")
            scored=[score_hour(s,tpl,r) for r in rows]
            hits=[h for _,hs in scored for h in hs]
            oh=s.get("open_hours") or {}
            if not str(oh.get("confidence","")).startswith("高"):
                warnings.append(s["name"]+"开放时间可信度为"+oh.get("confidence","未知")+"，出发前请核实来源。")
            if oh.get("reservation"): warnings.append(s["name"]+"："+oh["reservation"])
            leg_min=mins[prev][node]
            stops.append(dict(seq=len(stops)+1,spot_id=sid,name=s["name"],type=s["type"],exposure=s.get("exposure"),district=s.get("district"),
                              lat=s["lat"],lon=s["lon"],arrive=f"{arrive//60:02}:{arrive%60:02}",leave=f"{leave//60:02}:{leave%60:02}",stay_min=stay,
                              suitability=min(v for v,_ in scored),reason=_reason(s,rows,hits),weather_at_arrival=rows[0],weather_during_stay=rows,
                              opening=oh,leg={"from":start["name"] if not stops else stops[-1]["name"],"km":km[prev][node],"min":leg_min,
                                  "transport":modes[prev][node],"source":matrix_kind,"nav_url":amap_nav_url(s["lon"],s["lat"],s["name"],modes[prev][node])},
                              rainy_alternatives=s.get("rainy_alternative",[])))
            travel_min+=leg_min; travel_km+=km[prev][node]
            visited.add(sid); prev,departure=node,leave
        if not stops: return dict(ok=False,error="时间不足以完成行程，建议减少必去景点或延长时间。")
        if any(s not in visited for s in must) and offset==int(req.get("days",1))-1:
            return dict(ok=False,error="必去景点无法全部安排，请减少必去项或延长时间。")
        days.append(dict(date=dstr,weekday="周"+"一二三四五六日"[current.weekday()],weather=day_brief(hours,evidence["label"]),evidence=evidence,hours=hours,
                         stops=stops,dropped=[dict(spot_id=pool[i-1][0],name=pool[i-1][1]["name"],why="时间或交通约束下未选择") for i in dropped],
                         totals=dict(spot_count=len(stops),travel_min=travel_min,travel_km=round(travel_km,1),end_time=stops[-1]["leave"],rain_exposure_min=rain_exposure(stops,hours)),routing_source=matrix_kind))
    result=dict(ok=True,city="武汉",elapsed_ms=round((time.monotonic()-started)*1000),solver=solver.name,
                data=dict(spots=len(spots),templates=len(templates.get("templates",{})),source=meta["source"]),
                request={k:v for k,v in req.items() if k!="weather"},days=days,warnings=list(dict.fromkeys(warnings)),rejected=rejected,created_at=now().isoformat(timespec="seconds"))
    result["summary_text"]=summary_text(days)
    return result

def rain_exposure(stops,hours):
    total=0
    for s in stops:
        if s.get("type")=="indoor": continue
        a,b=opening.minutes(s["arrive"]),opening.minutes(s["leave"])
        for r in interval_rows(hours,a,b):
            if (r.get("precip") or 0)>=.5: total+=max(0,min(b,(r["hour"]+1)*60)-max(a,r["hour"]*60))
    return total

def summary_text(days):
    lines=[]
    for d in days:
        lines.append(f"{d['date']} {d['weekday']} · {d['weather']['source']}")
        lines.extend(f"{s['seq']}. {s['arrive']}–{s['leave']} {s['name']} · {s['reason']}" for s in d["stops"])
        lines.append(f"交通 {d['totals']['travel_min']} 分钟 · {d['routing_source']}（含转场余量）")
    return "\n".join(lines)
