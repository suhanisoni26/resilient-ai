from fastapi.testclient import TestClient
import main

def test_contract(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',str(tmp_path/'test.db'))
    monkeypatch.setattr(main,'KEYS',['a','b'])
    monkeypatch.setattr(main,'SIM',True)
    def fake(msgs,failures):
        if '*' in failures: raise main.HTTPException(503,'all providers unavailable')
        return 'test reply',dict(resolution_source='LIVE_INFERENCE',model=main.MODEL,input_tokens=5,output_tokens=2,key_id='key_2' if failures else 'key_1',fallback_attempts=int(bool(failures)))
    monkeypatch.setattr(main,'infer',fake)
    with TestClient(main.app) as c:
        assert c.get('/health').status_code==200
        assert c.get('/sessions/missing/messages').status_code==404
        assert c.post('/chat',json={'session_id':'s','message':' '}).status_code==422
        assert c.post('/chat',json={'session_id':'s','message':'hello'},headers={'X-Simulate-Failure':'*=429'}).status_code==503
        assert c.get('/sessions/s/messages').status_code==404
        r=c.post('/chat',json={'session_id':'s','message':'hello'},headers={'X-Simulate-Failure':'key_1=429'})
        assert r.json()['metadata']['key_id']=='key_2'
        assert len(c.get('/sessions/s/messages').json()['messages'])==2
