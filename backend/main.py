import os, sqlite3, json, time, threading
from datetime import datetime, timezone
from contextlib import contextmanager, asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints
from typing import Annotated
import litellm
from litellm.caching.caching import Cache
from dotenv import load_dotenv
load_dotenv()
KEYS=[k.strip() for k in os.getenv('LLM_API_KEYS','').split(',') if k.strip()]
MODEL=os.getenv('LLM_MODEL','gemini/gemini-2.5-flash')
DB=os.getenv('DATABASE_URL','sqlite:///./data/app.db').removeprefix('sqlite:///')
SIM=os.getenv('ENABLE_FAILURE_SIMULATION','false').lower()=='true'
DEFAULT='You are a helpful AI assistant.'
litellm.cache=Cache(type='local')
lock=threading.RLock()
@contextmanager
def db():
    os.makedirs(os.path.dirname(os.path.abspath(DB)),exist_ok=True)
    c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row
    try:
        with c: yield c
    finally: c.close()
@asynccontextmanager
async def lifespan(app):
    with db() as c:
        c.executescript('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, prompt TEXT NOT NULL); CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT, created_at TEXT NOT NULL); CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id,id);')
    yield
app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('ALLOWED_ORIGINS','http://localhost:3000').split(','),allow_methods=['GET','POST'],allow_headers=['Content-Type','X-Simulate-Failure'])
@app.exception_handler(Exception)
async def unexpected(request,exc): return JSONResponse(status_code=500,content={'detail':'internal server error'})
class Chat(BaseModel):
    session_id: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=128)]
    message: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=4000)]
    system_prompt: str|None=None
@app.get('/health')
def health():
    with db() as c: c.execute('SELECT 1')
    if len(KEYS)<2: raise HTTPException(503,'key pool not configured')
    return {'status':'ok','keys_configured':len(KEYS),'cache_enabled':True}
def history(c,s):
    return [dict(role=r['role'],content=r['content'],**({'metadata':json.loads(r['metadata'])} if r['metadata'] else {})) for r in c.execute('SELECT role,content,metadata FROM messages WHERE session_id=? ORDER BY id',(s,))]
@app.get('/sessions/{session_id}/messages')
def messages(session_id:str):
    with db() as c:
        if not c.execute('SELECT 1 FROM sessions WHERE id=?',(session_id,)).fetchone(): raise HTTPException(404,'session not found')
        return {'session_id':session_id,'messages':history(c,session_id)}
def infer(msgs, failures):
    attempts=0
    for i,key in enumerate(KEYS,1):
        kid=f'key_{i}'
        if kid in failures or '*' in failures:
            attempts+=1; continue
        try:
            response=litellm.completion(model=MODEL,messages=msgs,api_key=key,num_retries=0,timeout=25,caching=True,cache={'no-cache':True,'no-store':True} if failures else {})
            hit=bool(response._hidden_params.get('cache_hit',False))
            reply=response.choices[0].message.content
            if not reply: raise ValueError('empty reply')
            return reply,dict(resolution_source='LLM_CACHE' if hit else 'LIVE_INFERENCE',model=MODEL,input_tokens=response.usage.prompt_tokens,output_tokens=response.usage.completion_tokens,key_id=None if hit else kid,fallback_attempts=0 if hit else attempts)
        except Exception as exc:
            status=getattr(exc,'status_code',None)
            if status in (400,401,403,408,429,500,502,503,504) or isinstance(exc,(litellm.APIConnectionError,litellm.Timeout,ValueError)):
                attempts+=1; continue
            raise
    raise HTTPException(503,'all providers unavailable')
@app.post('/chat')
def chat(body:Chat,x_simulate_failure:str|None=Header(None)):
    start=time.perf_counter(); failures={}
    if SIM and x_simulate_failure:
        for item in x_simulate_failure.split(','):
            k,sep,v=item.strip().partition('=')
            if not sep or v not in ('429','500','502','503') or k not in ['*']+[f'key_{i}' for i in range(1,len(KEYS)+1)]: raise HTTPException(422,'invalid simulation header')
            failures[k]=v
    with lock:
        with db() as c:
            row=c.execute('SELECT prompt FROM sessions WHERE id=?',(body.session_id,)).fetchone()
            prompt=body.system_prompt if body.system_prompt is not None else (row['prompt'] if row else DEFAULT)
            msgs=[{'role':'system','content':prompt}]+[{k:r[k] for k in ('role','content')} for r in history(c,body.session_id)]+[{'role':'user','content':body.message}]
        reply,meta=infer(msgs,failures)
        meta['latency_ms']=int((time.perf_counter()-start)*1000)
        with db() as c:
            c.execute('INSERT INTO sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET prompt=excluded.prompt',(body.session_id,prompt))
            for role,content,m in [('user',body.message,None),('assistant',reply,json.dumps(meta))]:
                c.execute('INSERT INTO messages(session_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)',(body.session_id,role,content,m,datetime.now(timezone.utc).isoformat()))
        return {'session_id':body.session_id,'reply':reply,'metadata':meta}
