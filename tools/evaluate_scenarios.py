"""Reproducible, explicitly synthetic comparison. Baseline is not travel advice."""
import copy,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trip_tool import hooks,datasource,opening,routing
from trip_tool.contract import dispatch
from trip_tool.selftest import _hours
from trip_tool.planner_core import _stay_minutes,rain_exposure,DEFAULT_START,risk_reason,interval_rows

def baseline(rows):
    spots=datasource.load()[0]
    remaining={sid:s for sid,s in spots.items() if (s.get('open_hours') or {}).get('periods') and not str(s['open_hours'].get('confidence','')).startswith('低')
               and routing.haversine_km(DEFAULT_START['lat'],DEFAULT_START['lon'],s['lat'],s['lon'])<=30
               and (s.get('type')!='flower' or 10 in s.get('best_months',[]))}
    point,clock,stops=DEFAULT_START,540,[]
    while remaining and len(stops)<4:
        options=[]
        for sid,s in remaining.items():
            travel=routing.StraightLineMatrix().matrix([point,s],'mixed')[0][0][1]+10
            stay=_stay_minutes(s)
            for start,end,last in opening.periods(s,3) or []:
                a=max(start,clock+travel)
                if a<=last and a+stay<=min(end,1230):options.append((travel,a,sid,stay))
        if not options:break
        travel,a,sid,stay=min(options)
        s=remaining.pop(sid)
        stops.append(dict(s,arrive=f'{a//60:02}:{a%60:02}',leave=f'{(a+stay)//60:02}:{(a+stay)%60:02}'))
        point,clock=s,a+stay
    return stops

cases=[]
for label,a,b,rain in [('晴天',0,0,0),('上午雨',8,12,3),('午后雨',13,17,3),('全天雨',8,21,3),('傍晚雨',17,21,3),('小雨',10,16,.7)]:
    rows=_hours(precip_hours=())
    for r in rows:
        if a<=r['hour']<b:r.update(precip=rain,precip_prob=95)
    cases.append((label,rows))
for label,key,value in [('高温','apparent_temp',39),('大风','wind10_speed',12),('雷暴','thunder',True),('雷暴缺失','thunder',None)]:
    rows=_hours(precip_hours=())
    for r in rows:
        if 12<=r['hour']<16:r[key]=value
    cases.append((label,rows))
hooks.set_matrix_provider(routing.StraightLineMatrix())
output=[]
for name,rows in cases:
    r=dispatch('plan_trip',dict(date='2026-10-29',max_spots=4,weather={'hours':rows}))
    old=baseline(rows)
    new=[s for d in r.get('days',[]) for s in d['stops']]
    output.append(dict(case=name,mode='synthetic_simulation',baseline_stops=len(old),optimized_stops=len(new),
                       baseline_rain_min=rain_exposure(old,rows),optimized_rain_min=rain_exposure(new,rows) if new else '',
                       status='feasible' if r.get('ok') else 'no_safe_plan',error=r.get('error','')))
hooks.reset()
root=Path(__file__).resolve().parents[1]/'docs';root.mkdir(exist_ok=True)
with (root/'scenario_evaluation.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
(root/'scenario_evaluation.json').write_text(json.dumps(dict(note='人工模拟，非实测效果；同一景点库、起点、时间、直线矩阵与停留时长。基线为距离优先且满足开放时间，忽略天气；用于评估，不作为出行建议。',cases=output),ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(output,ensure_ascii=False,indent=2))
