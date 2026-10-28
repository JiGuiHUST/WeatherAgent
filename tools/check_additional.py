import sys,json,datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run import app
from services.live_weather import fetch,today,provider_status,WeatherUnavailable
from werkzeug.datastructures import MultiDict
c=app.test_client();out=[]
for path in ['/destinations?lang=en','/route?lang=en','/qa?lang=en','/science?lang=en','/safety?lang=en']:
    r=c.get(path);out.append(dict(name=path,passed=r.status_code==200,status=r.status_code))
date=(today()+dt.timedelta(days=1)).isoformat()
r=c.post('/route',data=MultiDict([('cities','武汉'),('cities','河内'),('start',date),('days','1'),('crowd','free')]))
out.append(dict(name='two-city real forecast',passed=r.status_code==200 and '武汉' in r.text and '河内' in r.text,status=r.status_code))
if provider_status()['active']=='weathercn':
    try:fetch(30.5506,114.3366,'2024-10-29');rejected=False
    except WeatherUnavailable as exc:rejected='历史' in str(exc)
    out.append(dict(name='unlicensed history explicitly rejected',passed=rejected,mode='not supported by current Huafeng adapter'))
else:
    h=fetch(30.5506,114.3366,'2024-10-29')
    out.append(dict(name='historical date preserved',passed=h['mode']=='historical' and h['target_date']=='2024-10-29' and len(h['hours'])>=23,mode=h['mode']))
Path('docs/additional_acceptance.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if all(x['passed'] for x in out) else 1)
