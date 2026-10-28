"""Local WSGI entrypoint: python serve.py. Debug/reloader are disabled."""
from waitress import serve
from run import app
from config import HOST,PORT
if __name__=="__main__":
    print(f"Weatherwise ready: http://{HOST}:{PORT}",flush=True)
    serve(app,host=HOST,port=PORT,threads=8,channel_timeout=120,max_request_body_size=4*1024*1024)
