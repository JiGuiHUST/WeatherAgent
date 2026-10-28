"""Synthetic adapter tests, explicitly not proof of real Huafeng permissions."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

from services import weathercn_provider as hf
from services.live_weather import today
from trip_tool.planner_core import day_brief,_reason

def hour(date,h=9):
    return dict(DateTime=f'{date}T{h:02}:00:00+08:00',Temperature={'Value':20,'Unit':'C'},
                RealFeelTemperature={'Value':21,'Unit':'C'},TotalLiquid={'Value':1,'Unit':'mm'},
                Wind={'Speed':{'Value':18,'Unit':'km/h'}},LocalSource={'Id':7,'WeatherCode':'07'})

class NormalizeTests(unittest.TestCase):
    def test_metric_normalization(self):
        row=hf.normalize_hour(hour('2026-10-29'))
        self.assertEqual((row['wind10_speed'],row['precip'],row['code'],row['thunder']),(5,1,61,False))
    def test_imperial_normalization(self):
        self.assertEqual(hf.quantity({'Value':68,'Unit':'F'},'temperature'),20)
        self.assertEqual(hf.quantity({'Value':1,'Unit':'in'},'rain'),25.4)
        self.assertAlmostEqual(hf.quantity({'Value':1,'Unit':'mi'},'distance'),1.609,places=3)
    def test_unknown_units_stay_missing(self):
        self.assertIsNone(hf.quantity({'Value':3,'Unit':'level'},'speed'))
        self.assertIsNone(hf.quantity({'Value':float('nan'),'Unit':'C'},'temperature'))
    def test_wrong_domestic_source_rejected(self):
        raw=hour('2026-10-29');raw['LocalSource']['Id']=1
        with self.assertRaises(hf.WeatherCNError):hf.normalize_hour(raw)
    def test_lowercase_source_id(self):
        raw=hour('2026-10-29');raw['LocalSource']['id']=raw['LocalSource'].pop('Id')
        self.assertEqual(hf.normalize_hour(raw)['provider_source_id'],7)
    def test_code_not_interpreted_as_wmo(self):
        raw=hour('2026-10-29');raw['LocalSource']['WeatherCode']='04'
        self.assertTrue(hf.normalize_hour(raw)['thunder'])
        raw['LocalSource']['WeatherCode']='unrecognized'
        self.assertIsNone(hf.normalize_hour(raw)['thunder'])
        self.assertIsNone(hf.normalize_hour(raw)['code'])
    def test_probability_does_not_replace_rain_amount(self):
        raw=hour('2026-10-29');raw.pop('TotalLiquid');raw['PrecipitationProbability']=20
        self.assertIsNone(hf.normalize_hour(raw)['precip'])
        raw['HasPrecipitation']=False
        self.assertEqual(hf.normalize_hour(raw)['precip'],0)
    def test_timezone_required(self):
        raw=hour('2026-10-29');raw['DateTime']='2026-10-29T09:00:00'
        with self.assertRaises(hf.WeatherCNError):hf.normalize_hour(raw)
    def test_missing_rain_never_becomes_dry_summary(self):
        rows=[hf.normalize_hour(hour('2026-10-29',h)) for h in range(24)]
        rows[4]['precip']=None
        self.assertIsNone(day_brief(rows,'synthetic')['precip_total_mm'])
        self.assertIn('不完整',_reason({'type':'indoor'},rows,[]))
    def test_science_prompt_preserves_date_and_forecast_source(self):
        from services.llm_client import _build_science_user
        for lang in ('zh','en'):
            text=_build_science_user('武汉',dict(date='2026-10-29',source='华风爱科',mode='forecast',tmp=17.5),lang)
            self.assertIn('2026-10-29',text);self.assertIn('华风爱科',text)
            self.assertIn('forecast',text);self.assertNotIn('当日实况',text)
    def test_alert_details_preserved(self):
        result=hf.normalize_alerts([dict(Description={'Localized':'暴雨预警'},Source='test',Area=[dict(Name='武汉',StartTime='2026-10-29T08:00:00+08:00',EndTime='2026-10-29T20:00:00+08:00',LastAction={'Text':'注意避险'})])])
        self.assertEqual(result[0]['text'],'注意避险')
        self.assertEqual(hf.normalize_alerts([]),[])

class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patch_cache=patch.object(hf,'CACHE',self.root/'cache');self.patch_cache.start()
        self.patch_quota=patch.object(hf,'QUOTA',self.root/'quota.json');self.patch_quota.start()
        self.addCleanup(self.patch_cache.stop);self.addCleanup(self.patch_quota.stop);self.addCleanup(self.temp.cleanup)
        self.client=hf.Client(key='SYNTHETIC_TEST_KEY',auth_mode='header')
        self.date=(today()+dt.timedelta(days=1)).isoformat()
    def results(self):
        return [({'Key':'synthetic_location','Country':{'ID':'CN'},'TimeZone':{'Name':'Asia/Shanghai'}},{}),
                ([hour(self.date,h) for h in range(24)],{}),([], {})]
    def test_no_location_or_secret_in_cache(self):
        with patch.object(self.client,'get',side_effect=self.results()) as get:
            result=self.client.fetch(30.5506,114.3366,self.date)
            self.assertTrue(hf.readiness(result)['ready_for_outdoor'])
            self.assertEqual(get.call_args_list[0].args[1]['q'],'30.551,114.337')
        text=''.join(f.read_text() for f in (self.root/'cache').glob('*.json'))
        self.assertNotIn('synthetic_location',text);self.assertNotIn('SYNTHETIC_TEST_KEY',text)
        with patch.object(self.client,'get',side_effect=AssertionError('should use weather cache')):
            self.assertTrue(self.client.fetch(30.5506,114.3366,self.date)['cached'])
    def test_missing_extended_fields_blocks_activation(self):
        responses=self.results();responses[1][0][3].pop('RealFeelTemperature')
        with patch.object(self.client,'get',side_effect=responses):data=self.client.fetch(30.55,114.33,self.date)
        self.assertFalse(hf.readiness(data)['ready_for_outdoor'])
    def test_other_day_missing_source_does_not_break_requested_day(self):
        responses=self.results()
        bad=hour((dt.date.fromisoformat(self.date)+dt.timedelta(days=2)).isoformat(),20)
        bad['LocalSource']=None
        responses[1][0].append(bad)
        with patch.object(self.client,'get',side_effect=responses):data=self.client.fetch(30.55,114.33,self.date)
        self.assertEqual(len(data['hours']),24)
        self.assertTrue(data['national_source_verified'])
    def test_requested_day_missing_source_still_rejected(self):
        responses=self.results();responses[1][0][5]['LocalSource']=None
        with patch.object(self.client,'get',side_effect=responses):
            with self.assertRaises(hf.WeatherCNError):self.client.fetch(30.55,114.33,self.date)
    def test_concurrent_refresh_uses_one_upstream_transaction(self):
        from concurrent.futures import ThreadPoolExecutor
        with patch.object(self.client,'get',side_effect=self.results()) as get:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:self.client.fetch(30.55,114.33,self.date,refresh=True),range(4)))
        self.assertEqual(get.call_count,3)
        self.assertEqual(sum(not r['cached'] for r in results),1)
    def test_unlicensed_alerts_blocks_activation(self):
        responses=self.results()[:2]+[hf.WeatherCNError('HTTP 403')]
        with patch.object(self.client,'get',side_effect=responses):data=self.client.fetch(30.55,114.33,self.date)
        self.assertEqual(data['alerts_status'],'unavailable')
        self.assertFalse(hf.readiness(data)['ready_for_outdoor'])
    def test_headers_not_query_auth(self):
        reply=Mock(status_code=200,headers={});reply.json.return_value=[]
        with patch.object(hf.requests,'get',return_value=reply) as get:
            self.client.get('/test',{'language':'zh-cn'})
        self.assertNotIn(self.client.key,get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs['headers']['X-Gw-API-Key'],self.client.key)
        self.assertNotIn('apikey',get.call_args.kwargs['params'])
    def test_daily_budget_stops_before_network(self):
        hf.QUOTA.write_text(json.dumps(dict(date=today().isoformat(),used=500)))
        with patch.object(hf.requests,'get') as get:
            with self.assertRaises(hf.WeatherCNError):self.client.get('/test')
            get.assert_not_called()
    def test_documented_query_auth_compatibility(self):
        self.client.auth_mode='query'
        reply=Mock(status_code=200,headers={});reply.json.return_value=[]
        with patch.object(hf.requests,'get',return_value=reply) as get:self.client.get('/test')
        self.assertEqual(get.call_args.kwargs['params']['apikey'],self.client.key)
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
    def test_expired_alerts_not_served_from_weather_cache(self):
        responses=self.results();responses[2]=([] ,{'Cache-Control':'no-cache'})
        with patch.object(self.client,'get',side_effect=responses):self.client.fetch(30.55,114.33,self.date)
        with patch.object(self.client,'get',side_effect=self.results()) as get:
            self.assertFalse(self.client.fetch(30.55,114.33,self.date)['cached'])
            self.assertEqual(get.call_count,3)
    def test_permissions_error_redacted(self):
        reply=Mock(status_code=403,headers={})
        with patch.object(hf.requests,'get',return_value=reply):
            with self.assertRaises(hf.WeatherCNError) as error:self.client.get('/test')
        self.assertNotIn(self.client.key,str(error.exception))
    def test_history_no_network(self):
        with patch.object(self.client,'get') as get:
            with self.assertRaises(hf.WeatherCNError):self.client.fetch(30.55,114.33,'2000-01-01')
            get.assert_not_called()

if __name__=='__main__':unittest.main()
