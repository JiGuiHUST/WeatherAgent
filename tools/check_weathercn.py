r"""Probe licensed Huafeng APIs; activate only after a successful live check.

Run: .venv\Scripts\python.exe -X utf8 tools/check_weathercn.py --activate
Credentials are read from the ignored local env file, never command arguments.
"""
from pathlib import Path
import argparse
import datetime as dt
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def activate():
    path=ROOT/'.env.weathercn.local'
    original=path.read_text(encoding='utf8') if path.exists() else ''
    lines=[line for line in original.splitlines() if not line.startswith(('WEATHERCN_ENABLED=','WEATHER_PROVIDER='))]
    lines+=['WEATHERCN_ENABLED=1','WEATHER_PROVIDER=auto']
    temporary=path.with_suffix('.local.tmp')
    temporary.write_text('\n'.join(lines)+'\n',encoding='utf8')
    temporary.replace(path)

def main():
    parser=argparse.ArgumentParser(description='华风爱科真实权限检查，不输出密钥或定位响应。')
    parser.add_argument('--activate',action='store_true')
    args=parser.parse_args()
    from services.weathercn_provider import Client,WeatherCNError,readiness
    from services.live_weather import today
    try:
        # A full tomorrow tests usability rather than a truncated remaining day.
        data=Client().fetch(30.5506,114.3366,(today()+dt.timedelta(days=1)).isoformat(),refresh=True)
        report=readiness(data)
        report['full_day']=len(data['hours'])==24
        report['source']=data['source']
        report['alerts_count']=len(data['alerts'])
        report['activation_passed']=bool(report['full_day'] and report['ready_for_outdoor'])
        if args.activate and report['activation_passed']:
            activate()
            report['activation']='已写入本机配置，重启服务后生效'
        else:report['activation']='未修改激活状态'
        path=ROOT/'docs'/'weathercn_permission_check.json'
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report['activation_passed'] else 2
    except WeatherCNError as exc:
        print('权限检查未通过：'+str(exc))
        print('未激活华风爱科，当前服务的数据源保持原配置。')
        return 2

if __name__=='__main__':sys.exit(main())
