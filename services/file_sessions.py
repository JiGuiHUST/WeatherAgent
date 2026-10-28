"""Server-side sessions keep route data and chat histories out of cookies."""
import json
import os
import secrets
import threading
import time
from pathlib import Path
from flask.sessions import SessionInterface, SessionMixin
from itsdangerous import URLSafeSerializer, BadSignature
from werkzeug.datastructures import CallbackDict

class Session(CallbackDict,SessionMixin):
    def __init__(self,data=None,sid=None):
        super().__init__(data or {},lambda obj:setattr(obj,"modified",True))
        self.sid=sid or secrets.token_hex(24)
        self.modified=False

class FileSessions(SessionInterface):
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock()
    def open_session(self,app,request):
        try:
            sid=URLSafeSerializer(app.secret_key,salt="sessions").loads(request.cookies.get("weather_session",""))
            if not isinstance(sid,str) or len(sid)!=48 or any(c not in "0123456789abcdef" for c in sid): raise ValueError()
            record=json.loads((self.root/(sid+".json")).read_text(encoding="utf8"))
            if time.time()-record["updated"]>7*86400: raise ValueError()
            return Session(record["data"],sid)
        except (BadSignature,ValueError,KeyError,OSError): return Session()
    def save_session(self,app,session,response):
        if not session: return
        path=self.root/(session.sid+".json")
        with self.lock:
            temporary=path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"updated":time.time(),"data":dict(session)},ensure_ascii=False),encoding="utf8")
            os.replace(temporary,path)
        response.set_cookie("weather_session",URLSafeSerializer(app.secret_key,salt="sessions").dumps(session.sid),
                            httponly=True,samesite="Lax",secure=app.config.get("SESSION_COOKIE_SECURE",False),max_age=7*86400)
