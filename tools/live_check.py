"""Live end-to-end acceptance against real providers; no credentials are printed."""
import sys,json,datetime as dt,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run import app
from services.live_weather import today
from services import llm_client

results=[]
def record(name,passed,detail=""):
    results.append(dict(name=name,passed=bool(passed),detail=detail))
    print(('PASS ' if passed else 'FAIL ')+name+' '+str(detail),flush=True)

c=app.test_client()
date=(today()+dt.timedelta(days=1)).isoformat()
for path in ['/','/destinations','/route','/trip','/safety','/qa','/science','/api/travel/health']:
    r=c.get(path);record('GET '+path,r.status_code==200,str(r.status_code))
r=c.get('/api/travel/weather?date='+date)
record('real hourly weather',r.status_code==200 and len(r.json.get('hours',[]))>=23,r.json.get('source') if r.is_json else r.status_code)
r=c.post('/api/travel/plan',json=dict(date=date,max_spots=4))
plan=r.json
record('real plan',r.status_code==200 and plan.get('ok'),dict(error=plan.get('error'),routing=[d['routing_source'] for d in plan.get('days',[])]))
if plan.get('ok'):
    pid=plan['id']
    for suffix in ['', '/export','/export?format=json']:
        r=c.get('/api/travel/plans/'+pid+suffix);record('saved plan '+suffix,r.status_code==200,str(r.status_code))
    r=c.post('/api/travel/replan',json={'id':pid});record('refresh real weather and replan',r.status_code==200 and r.json.get('ok'),r.json.get('error','comparison available'))
    r=c.post('/api/travel/scenario',json={'id':pid,'from':13,'to':17,'rain':3})
    record('explicit rain scenario',r.status_code==200 and 'scenario_label' in r.json,r.json.get('comparison',r.json.get('error')))
    r=c.post('/api/travel/chat',json={'id':pid,'question':'请根据已验证的行程解释这样安排的天气原因，简要回答，不要重新调用规划工具。'})
    record('real model explanation',r.status_code==200 and r.json.get('source')=='deepseek-flash',r.json.get('source'))
    record('science from saved workspace plan',c.get('/science').status_code==200)

r=c.post('/strategy',data=dict(destination='武汉',preference='首次旅行',time_input=date))
record('destination strategy real weather',r.status_code==200,str(r.status_code))
r=c.post('/route',data=dict(cities='武汉',start=date,days='1',crowd='study',selected_spots='[]'))
record('legacy route real weather',r.status_code==200,str(r.status_code))
with c.session_transaction() as s: token=(s.get('route') or {}).get('token')
if token:
    r=c.get('/route_itinerary_async?token='+token)
    record('async itinerary',r.status_code==200 and r.json.get('ok'),r.json.get('source') if r.is_json else r.status_code)
for kind in ['handbook','record','bank','diagram']:
    r=c.get('/export/'+kind);record('export '+kind,r.status_code==200 and len(r.data)>20,dict(status=r.status_code,bytes=len(r.data)))
    if kind=='handbook': record('handbook includes actual route and weather','武汉' in r.text and date in r.text,r.text[:180])
text,used=llm_client.ask_with_tools('请调用 list_spots 工具列出武汉的两个室内景点，然后回答名称，不要规划行程。',{'city':'武汉','date':date,'source':'工具查询'},'zh')
record('DeepSeek actual function calling',bool(text) and used,dict(used_tools=used,answer=(text or '')[:250]))
r=c.post('/qa',data={'question':'请用两句话解释为什么下雨时室内活动更适合旅行。'})
record('legacy bilingual QA',r.status_code==200,str(r.status_code))
out=Path(__file__).resolve().parents[1]/'docs'/'live_acceptance.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(dict(date=str(today()),results=results),ensure_ascii=False,indent=2),encoding='utf8')
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
