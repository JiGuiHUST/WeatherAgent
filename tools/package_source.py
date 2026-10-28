"""Package deliverable source while refusing to include local credentials."""
import subprocess,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root).decode('utf8').split('\0')
files=[p for p in files if p and (root/p).is_file()]
keys=[]
for env in (root/'.env',root/'.env.weathercn.local'):
    if env.exists():
        for line in env.read_text(encoding='utf8').splitlines():
            if line.startswith(('OPENAI_API_KEY=','WEATHERCN_OPENAPI_KEY=')):
                key=line.partition('=')[2].strip().strip('\"').strip("'").encode()
                if key:keys.append(key)
for name in files:
    if name.startswith('.env') and name!='.env.example' or '.venv' in Path(name).parts or 'sessions' in Path(name).parts:
        raise SystemExit('Refusing private runtime data: '+name)
    if any(key in (root/name).read_bytes() for key in keys):
        raise SystemExit('Refusing file containing API credential: '+name)
out=root.parent/'WeatherAgent_文旅应用交付.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for name in files:z.write(root/name,'WeatherAgent/'+name)
    z.write(root.parent/'启动.bat','启动.bat')
print(f'Source package: {len(files)+1} files, {out.stat().st_size} bytes. Credentials excluded.')
