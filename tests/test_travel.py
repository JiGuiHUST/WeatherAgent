import copy
import datetime as dt
import unittest
from unittest.mock import patch
from services.live_weather import WeatherUnavailable,fetch
from trip_tool import hooks
from trip_tool.contract import dispatch,validate
from trip_tool.planner_core import build_window,rain_exposure
from trip_tool.routing import StraightLineMatrix
from trip_tool.weather import InjectedProvider
from trip_tool.selftest import _hours
from trip_tool.scoring import TemplateScorer
from trip_tool.solver import OrtoolsSolver,GreedySolver
from utils.common import parse_time_input,to_data_year

class WindowTests(unittest.TestCase):
    def setUp(self):
        self.spot={'type':'indoor','open_hours':{'periods':[{'days':'Mon-Sun','open':'09:00','close':'17:00','last_entry':'16:00'}]}}
        self.tpl={'sensitivity':{}}
    def window(self,hours,stay=120):
        return build_window(self.spot,self.tpl,hours,3,540,1230,stay)['windows']
    def test_stay_cannot_cross_close(self):
        self.assertEqual(self.window([{'hour':16}]),[])
    def test_stay_cannot_cross_weather_end(self):
        self.assertEqual(self.window([{'hour':9}]),[])
    def test_last_entry_is_not_close(self):
        wins=self.window([{'hour':h} for h in range(9,17)],90)
        self.assertEqual(wins[0][1],930) # 15:30 arrival -> 17:00 departure
    def test_unknown_hours_not_all_day(self):
        self.spot['open_hours']['periods']=[]
        self.assertEqual(self.window(_hours()),[])
    def test_closed_weekday(self):
        self.spot['open_hours']['periods'][0]['days']='Tue-Sun'
        self.assertEqual(build_window(self.spot,self.tpl,_hours(),0,540,1230,120)['windows'],[])
    def test_thunder_disjoint_windows(self):
        self.spot['type']='city_park'
        rows=_hours(precip_hours=())
        for row in rows:
            if 12<=row['hour']<14: row['thunder']=True
        wins=self.window(rows,60)
        self.assertEqual([(a,b) for a,b,_ in wins],[(540,660),(840,960)])
    def test_missing_risk_excludes_outdoor(self):
        self.spot['type']='city_park'
        self.assertEqual(self.window([{'hour':h} for h in range(24)]),[])
    def test_rain_exposure_full_stay(self):
        stops=[dict(type='city_park',arrive='12:30',leave='14:15')]
        self.assertEqual(rain_exposure(stops,_hours()),75)
    def test_missing_factor_not_full_score(self):
        score,hits=TemplateScorer().score({},dict(sensitivity={'thunder':dict(weight=3,bad='true')}),{})
        self.assertLess(score,100)
        self.assertEqual(hits[0]['verdict'],'unknown')

class ValidationTests(unittest.TestCase):
    def test_date_preserved(self):
        d,_=parse_time_input('2026-10-29',{})
        self.assertEqual(d.year,2026)
        self.assertEqual(to_data_year(dt.datetime(2024,2,29)).day,29)
    def test_invalid_dates_rejected(self):
        for date in ['2026-02-30','2026/10/29','2026-10-29evil']:
            self.assertFalse(validate({'date':date})[0])
    def test_invalid_ranges(self):
        for r in [{'max_spots':99},{'days':0},{'max_radius_km':float('nan')},{'start':{'time':'25:90'}},{'start':{'time':'18:00'},'end_by':'09:00'}]:
            self.assertFalse(validate(r)[0],r)
    def test_list_shape(self):
        self.assertFalse(validate({'selected_spots':'hubei_museum'})[0])
        self.assertFalse(validate({'weather':{'hours':[{'hour':0}]*24}})[0])
    def test_invalid_argument_objects(self):
        self.assertFalse(dispatch('plan_trip',[])['ok'])
    def test_out_of_forecast_range(self):
        with self.assertRaises(WeatherUnavailable):fetch(30.55,114.33,'2099-01-01')

class SolverTests(unittest.TestCase):
    def problem(self):
        return dict(n=2,mins=[[0,15],[15,0]],stay=[0,120],windows={1:[(600,600,90),(800,800,90)]},day_start=540,day_end=720,max_spots=1)
    def test_open_route_finishes_service(self):
        p=self.problem();p['windows']={1:[(600,600,90)]}
        for solver in [OrtoolsSolver(),GreedySolver()]:
            route,_=solver.solve(p)
            self.assertEqual(route,[(1,600)]) # No forced return to start at 735.
    def test_must_visit_cannot_be_dropped(self):
        p=self.problem();p['windows']={1:[(650,650,90)]};p['must_nodes']=[1]
        self.assertEqual(OrtoolsSolver().solve(p)[0],[])

class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from run import app
        cls.app=app
    def setUp(self):
        hooks.set_matrix_provider(StraightLineMatrix())
        hooks.set_weather_provider(InjectedProvider(_hours()))
        self.client=self.app.test_client()
    def tearDown(self): hooks.reset()
    def test_main_pages(self):
        for p in ['/','/trip','/destinations','/route','/safety','/api/travel/catalog','/api/trip/tools']:
            self.assertEqual(self.client.get(p).status_code,200,p)
    def test_qa_partial_weather_does_not_break_page(self):
        data=dict(hours=_hours()[19:],label='合成测试',source='test')
        with patch('services.live_weather.fetch',return_value=data):
            response=self.client.get('/qa')
        self.assertEqual(response.status_code,200)
        self.assertIn('未覆盖全天',response.text)
    def test_qa_can_open_during_weather_outage(self):
        with patch('services.live_weather.fetch',side_effect=WeatherUnavailable('测试不可用')):
            response=self.client.get('/qa')
        self.assertEqual(response.status_code,200)
        self.assertIn('天气暂不可用',response.text)
    def test_real_endpoint_rejects_injection(self):
        self.assertEqual(self.client.post('/api/travel/plan',json={'weather':{'hours':_hours()}}).status_code,400)
    def test_plan_save_restore_and_export(self):
        r=self.client.post('/api/travel/plan',json={'date':'2026-10-29','max_spots':3})
        self.assertEqual(r.status_code,200,r.json)
        plan=r.json;pid=plan['id']
        self.assertEqual(self.client.get('/api/travel/plans/'+pid).json['id'],pid)
        exported=self.client.get('/api/travel/plans/'+pid+'/export')
        self.assertEqual(exported.status_code,200)
        self.assertIn('人工模拟',exported.text)
        self.assertEqual(self.client.get('/api/travel/plans/'+pid+'/export?format=json').status_code,200)
        self.assertLess(len(r.headers.get('Set-Cookie','')),300)
        self.assertEqual(self.app.test_client().get('/api/travel/plans/'+pid).status_code,400)
    def test_scenario_is_marked(self):
        r=self.client.post('/api/travel/plan',json={'date':'2026-10-29','max_spots':3}).json
        result=self.client.post('/api/travel/scenario',json={'id':r['id'],'from':13,'to':17,'rain':3})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['days'][0]['evidence']['mode'],'simulation')
        self.assertIn('不是真实预报',result.json['scenario_label'])
    def test_cross_origin_writes_rejected(self):
        r=self.client.post('/api/travel/plan',json={},headers={'Origin':'https://example.com'})
        self.assertEqual(r.status_code,403)
    def test_weather_outage_no_climate_substitution(self):
        hooks.set_weather_provider(None)
        with patch('trip_tool.planner_core.fetch',side_effect=WeatherUnavailable('service offline')):
            r=dispatch('plan_trip',{'date':'2026-10-29'})
            self.assertFalse(r['ok'])
            self.assertNotIn('days',r)
    def test_required_spot_rejected_if_unknown(self):
        self.assertFalse(dispatch('plan_trip',{'date':'2026-10-29','must_visit':['not-real']})['ok'])
    def test_no_dangerous_stays(self):
        r=dispatch('plan_trip',{'date':'2026-10-29','max_spots':4})
        self.assertTrue(r['ok'],r)
        for d in r['days']:
            for s in d['stops']:
                if s['type']!='indoor':
                    self.assertTrue(all(x.get('precip',0)<2.5 and x.get('thunder') is False for x in s['weather_during_stay']))

if __name__=='__main__':unittest.main()
