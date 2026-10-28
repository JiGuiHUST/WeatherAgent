"""Focused live refresh acceptance; sanitized output, never logs credentials."""
import datetime as dt
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run import app
from services.live_weather import today

def main():
    client=app.test_client();results=[]
    cases=[(1,30.5506,114.3366),(0,30.5506,114.3366),(2,30.5506,114.3366),
           (1,30.619,114.252),(1,30.5289,114.317),(1,30.5797,114.2857)]
    for offset,lat,lon in cases:
        started=time.monotonic();date=(today()+dt.timedelta(days=offset)).isoformat()
        response=client.get('/api/travel/weather',query_string=dict(date=date,lat=lat,lon=lon,refresh=1))
        data=response.get_json() or {}
        passed=response.status_code==200 and bool(data.get('hours')) and data.get('national_source_verified') is True
        result=dict(date=date,point=dict(lat=lat,lon=lon),status=response.status_code,passed=passed,
                    hours=len(data.get('hours',[])),source=data.get('source'),national_source_verified=data.get('national_source_verified'),
                    error=data.get('error'),seconds=round(time.monotonic()-started,2))
        results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    # Repeat refresh of one point: should remain usable and share a fresh response.
    for _ in range(3):
        response=client.get('/api/travel/weather',query_string=dict(date=(today()+dt.timedelta(days=1)).isoformat(),refresh=1))
        data=response.get_json() or {}
        results.append(dict(name='repeat refresh',passed=response.status_code==200,status=response.status_code,cached=data.get('cached'),error=data.get('error')))
    path=Path(__file__).resolve().parents[1]/'docs'/'weathercn_refresh_acceptance.json'
    path.write_text(json.dumps(dict(checked_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),results=results),ensure_ascii=False,indent=2),encoding='utf8')
    print('Refresh checks:',sum(r['passed'] for r in results),'/',len(results))
    return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':sys.exit(main())
