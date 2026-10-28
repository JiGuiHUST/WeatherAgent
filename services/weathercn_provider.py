"""Huafeng WeatherCN OpenAPI adapter. Server-only credentials, no location cache.

Docs: https://platform.weathercn.com/doc/index.html
Live activation is separate from adapter tests and requires the user's licensed key.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
import re
import threading
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'data'/'.weathercn_cache'
QUOTA=ROOT/'data'/'.weathercn_quota.json'
LOCK=threading.RLock()
NETWORK=threading.Lock()
FETCH_LOCKS=[threading.RLock() for _ in range(32)]
LAST=0.0
BASE='https://openapi.weathercn.com'
CST=dt.timezone(dt.timedelta(hours=8))

class WeatherCNError(ValueError):
    pass

def number(value):
    return float(value) if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else None

def quantity(value,kind):
    if not isinstance(value,dict):return None
    v=number(value.get('Value'))
    if v is None:return None
    unit=str(value.get('Unit','')).strip().lower().replace('°','')
    conversions={'temperature':{'c':lambda x:x,'f':lambda x:(x-32)*5/9},
                 'speed':{'m/s':lambda x:x,'km/h':lambda x:x/3.6,'kmh':lambda x:x/3.6,'mi/h':lambda x:x*.44704,'mph':lambda x:x*.44704},
                 'rain':{'mm':lambda x:x,'in':lambda x:x*25.4},
                 'distance':{'km':lambda x:x,'m':lambda x:x/1000,'mi':lambda x:x*1.609344}}
    convert=conversions[kind].get(unit)
    return round(convert(v),3) if convert else None

def normalize_hour(raw,country='CN'):
    when=dt.datetime.fromisoformat(str(raw.get('DateTime','')).replace('Z','+00:00'))
    if when.tzinfo is None:raise WeatherCNError('华风爱科返回的预报时间缺少时区')
    local=raw.get('LocalSource') or {}
    sid=local.get('Id',local.get('id'))
    if country=='CN' and str(sid)!='7':
        raise WeatherCNError(f"所查日期 {when:%Y-%m-%d %H:%M} 的预报来源未通过核验（需 LocalSource.Id=7），暂无法提供该日可靠天气，请稍后刷新。")
    wc=str(local.get('WeatherCode','')).strip()
    icon=raw.get('WeatherIcon')
    # Keep provider codes separate from the WMO display code used by this UI.
    wmo=None; thunder=None
    if country=='CN' and wc:
        if wc in ('04','05'):wmo=95;thunder=True
        elif wc=='00':wmo=0;thunder=False
        elif wc=='01':wmo=2;thunder=False
        elif wc=='02':wmo=3;thunder=False
        elif wc in ('18','32','49','57','58'):wmo=45;thunder=False
        elif wc in ('03','07','08','09','10','11','12','21','22','23','24','25','301'):wmo=61;thunder=False
        elif wc in ('06','13','14','15','16','17','19','26','27','28','302'):wmo=71;thunder=False
    elif isinstance(icon,int):
        thunder=icon in (15,16,17,41,42)
        wmo=95 if thunder else 0 if icon in (1,2,33,34) else 3
    rain=quantity(raw.get('TotalLiquid') or raw.get('Rain'),'rain')
    if rain is None and raw.get('HasPrecipitation') is False:rain=0.0
    return dict(hour=when.hour,time=when.isoformat(),tmp=quantity(raw.get('Temperature'),'temperature'),
                apparent_temp=quantity(raw.get('RealFeelTemperature'),'temperature'),
                precip=rain,precip_prob=number(raw.get('PrecipitationProbability')),
                wind10_speed=quantity((raw.get('Wind') or {}).get('Speed'),'speed'),
                wind_gusts=quantity((raw.get('WindGust') or {}).get('Speed'),'speed'),
                visibility=quantity(raw.get('Visibility'),'distance'),rh=number(raw.get('RelativeHumidity')),
                uv_index=number(raw.get('UVIndex')),thunder=thunder,code=wmo,aqi=None,
                provider_weather_code=wc,provider_icon=icon,provider_source_id=sid,
                provider_phrase=raw.get('IconPhrase'),wind_level_code=local.get('WindLevelCode'))

def normalize_alerts(raw):
    if not isinstance(raw,list):raise WeatherCNError('华风爱科预警响应格式不符')
    output=[]
    for alert in raw:
        if not isinstance(alert,dict):continue
        desc=alert.get('Description') or {}
        for area in alert.get('Area') or [{}]:
            last=area.get('LastAction') or {}
            output.append(dict(title=desc.get('Localized') or alert.get('Type') or '气象预警',level=alert.get('Level') or alert.get('AlarmLevel'),
                               source=alert.get('Source') or '华风爱科预警接口',area=area.get('Name'),start=area.get('StartTime'),end=area.get('EndTime'),
                               text=last.get('Text') or area.get('Text') or last.get('Summary') or '',
                               link=alert.get('Link') or alert.get('MobileLink')))
    return output

class Client:
    def __init__(self,key=None,auth_mode=None):
        from config import WEATHERCN_OPENAPI_KEY
        self.key=key or WEATHERCN_OPENAPI_KEY
        if not self.key:raise WeatherCNError('尚未配置华风爱科 OpenAPI Key，请先完成注册认证并申请接口权限')
        self.auth_mode=auth_mode or os.getenv('WEATHERCN_AUTH_MODE','header')
        if self.auth_mode not in ('header','query'):raise WeatherCNError('华风爱科鉴权方式配置无效')

    def get(self,path,params=None):
        global LAST
        # Requests are serialized and capped locally; no parallel account scraping.
        with NETWORK:
            delay=.26-(time.monotonic()-LAST)
            if delay>0:time.sleep(delay)
            with LOCK:
                date=dt.datetime.now(CST).date().isoformat()
                try:record=json.loads(QUOTA.read_text(encoding='utf8'))
                except (OSError,ValueError):record={}
                used=record.get('used',0) if record.get('date')==date else 0
                limit=min(500,max(1,int(os.getenv('WEATHERCN_DAILY_LIMIT','450'))))
                if used>=limit:raise WeatherCNError('本机华风爱科调用预算已用完；不会自动购买额度，请查看控制台或等待额度重置')
                QUOTA.parent.mkdir(exist_ok=True)
                QUOTA.write_text(json.dumps(dict(date=date,used=used+1)),encoding='utf8')
            LAST=time.monotonic()
            params=dict(params or {})
            headers={'Accept-Encoding':'gzip,deflate','User-Agent':'Weatherwise/2.1'}
            if self.auth_mode=='query':params['apikey']=self.key
            else:headers['X-Gw-API-Key']=self.key
            try:
                # The gateway currently ignores X-Gw-API-Key for this test key.
                # Officially documented query auth is supported, entirely server-side.
                # Never log response.request.url or propagate requests exceptions.
                response=requests.get(BASE+path,params=params,headers=headers,timeout=(5,18),allow_redirects=False)
            except requests.RequestException:
                raise WeatherCNError('华风爱科网络连接暂不可用') from None
        status=response.status_code
        if status in (401,403):raise WeatherCNError(f'华风爱科 HTTP {status}：请核对认证、Key有效期、当前接口权限及当日额度')
        if status==429:raise WeatherCNError('华风爱科请求限频，请稍后重试')
        if status!=200:raise WeatherCNError(f'华风爱科 HTTP {status}：接口暂不可用')
        try:data=response.json()
        except ValueError:raise WeatherCNError('华风爱科返回了非 JSON 响应') from None
        return data,response.headers

    def location(self,lat,lon):
        # Location data must not be cached or hardcoded per provider dev standard.
        data,_=self.get('/locations/v1/cities/geoposition/search.json',dict(q=f'{lat:.3f},{lon:.3f}',language='zh-cn'))
        if not isinstance(data,dict) or not data.get('Key'):raise WeatherCNError('定位接口未返回可用 Location Key')
        return data

    def fetch(self,lat,lon,date,refresh=False):
        # Coalesce simultaneous refreshes from chart / planner / double clicks.
        requested_at=time.time()
        slot=int(hashlib.sha256(f'{lat:.3f}|{lon:.3f}|{date}'.encode()).hexdigest()[:8],16)%len(FETCH_LOCKS)
        with FETCH_LOCKS[slot]:
            return self._fetch(lat,lon,date,refresh,requested_at)

    def _fetch(self,lat,lon,date,refresh,requested_at):
        from services.live_weather import now,today
        target=dt.date.fromisoformat(date)
        if target<today():raise WeatherCNError('当前华风爱科标准预报适配器不提供历史回放，请使用已获授权的历史产品或明确切换数据源')
        span=int(os.getenv('WEATHERCN_FORECAST_HOURS','72'))
        if span not in (24,72):raise WeatherCNError('标准试用仅配置 24 或 72 小时；更长时效需单独申请')
        if target>today()+dt.timedelta(days=span//24):raise WeatherCNError('所选日期超过已配置的华风爱科逐小时预报时效')
        digest=hashlib.sha256(f'v2|{lat:.3f}|{lon:.3f}|{date}|{span}|{self.key}'.encode()).hexdigest()[:24]
        cache=CACHE/(digest+'.json')
        try:
            record=json.loads(cache.read_text(encoding='utf8'))
            fresh=dt.datetime.fromisoformat(record['weather']['fetched_at']).timestamp()>=requested_at-3
            if record['valid_until']>time.time() and (not refresh or fresh):
                return dict(record['weather'],cached=True)
        except (OSError,ValueError,KeyError,TypeError):pass
        location=self.location(lat,lon)
        key=location['Key']
        if not re.fullmatch(r'[A-Za-z0-9_-]+',str(key)):raise WeatherCNError('Location Key 格式无效')
        country=(location.get('Country') or {}).get('ID')
        if not country:raise WeatherCNError('定位响应缺少国家代码，无法核验国内预报来源')
        raw,headers=self.get(f'/forecasts/v1/hourly/{span}hour/{key}.json',dict(language='zh-cn',details='true',metric='true'))
        if not isinstance(raw,list):raise WeatherCNError('逐小时接口响应格式不符，请确认开通正确产品')
        # Validate the requested local day, not every row in the 72-hour envelope.
        # The real API can omit LocalSource on the trailing day; that must not
        # invalidate a fully verified tomorrow. Never borrow another row's source.
        selected_raw=[r for r in raw if isinstance(r,dict) and str(r.get('DateTime',''))[:10]==date]
        try:rows=sorted([normalize_hour(r,country) for r in selected_raw],key=lambda r:r['time'])
        except (ValueError,TypeError) as exc:
            if isinstance(exc,WeatherCNError):raise
            raise WeatherCNError('逐小时预报时间或字段格式无效') from None
        selected=[r for r in rows if r['time'][:10]==date]
        if not selected:raise WeatherCNError('所选日期不在当前 Key 返回的逐小时预报覆盖范围内，请缩短出行日期或申请更长时效')
        if len({r['hour'] for r in selected})!=len(selected):raise WeatherCNError('逐时记录存在重复小时，暂不生成该日行程')
        if not any(r['tmp'] is not None for r in selected):raise WeatherCNError('预报温度缺失或单位不受支持')
        alerts=[];alerts_status='available';alerts_error='';alert_headers={}
        try:
            alert_raw,alert_headers=self.get(f'/alerts/v1/{key}.json',dict(language='zh-cn',details='true'))
            alerts=normalize_alerts(alert_raw)
        except WeatherCNError as exc:
            alerts_status='unavailable';alerts_error=str(exc)
        data=dict(hours=selected,source='华风爱科',source_url='https://platform.weathercn.com/',mode='forecast',
                  label='实时预报 · 华风爱科',target_date=date,fetched_at=now().isoformat(timespec='seconds'),
                  timezone=(location.get('TimeZone') or {}).get('Name','Asia/Shanghai'),
                  coordinates=dict(lat=lat,lon=lon),spatial_scope='区域代表点预报',
                  units=dict(tmp='°C',precip='mm/h',wind10_speed='m/s',visibility='km'),
                  missing=[k for k in ('apparent_temp','precip','wind10_speed','wind_gusts','visibility','uv_index','rh','aqi') if all(r.get(k) is None for r in selected)],
                  partial_day=len(selected)<24,coverage_start=rows[0]['time'] if rows else None,coverage_end=rows[-1]['time'] if rows else None,
                  alerts=alerts,alerts_status=alerts_status,alerts_error=alerts_error,cached=False,
                  national_source_verified=country=='CN' and all(str(r.get('provider_source_id'))=='7' for r in selected))
        # Alerts may expire sooner than the forecast; refresh the combined view then.
        expiry=time.time()+1800
        for response_headers in (headers,alert_headers):
            try:
                if response_headers.get('Expires'):expiry=min(expiry,parsedate_to_datetime(response_headers['Expires']).timestamp())
                control=response_headers.get('Cache-Control','').lower()
                if 'no-store' in control or 'no-cache' in control:expiry=time.time()
                match=re.search(r'(?:^|,)\s*max-age=(\d+)',control)
                if match:expiry=min(expiry,time.time()+int(match[1]))
            except (ValueError,TypeError,OverflowError):pass
        # Cache normalized weather, never Location response / Location Key / API key.
        try:
            CACHE.mkdir(parents=True,exist_ok=True)
            with LOCK:
                temporary=cache.with_suffix('.tmp')
                temporary.write_text(json.dumps(dict(valid_until=expiry,weather=data),ensure_ascii=False),encoding='utf8')
                os.replace(temporary,cache)
        except OSError:pass
        return data

def readiness(data):
    required=('tmp','apparent_temp','precip','wind10_speed','thunder')
    missing={k:sum(r.get(k) is None for r in data['hours']) for k in required}
    return dict(ready_for_outdoor=bool(data.get('national_source_verified') and data.get('alerts_status')=='available' and all(v==0 for v in missing.values())),missing_required_counts=missing,
                hours=len(data['hours']),national_source_verified=data.get('national_source_verified'),alerts_status=data.get('alerts_status'))
