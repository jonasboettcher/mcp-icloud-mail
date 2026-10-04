"""Verify the actual patched server refuses invoice creation at MCP dispatch."""
import os
from pathlib import Path
import subprocess
import time

import httpx

from lexware_gateway.patch_backend import ALLOWED

def test_backend_tool_surface():
    root=Path('.lexware-runtime')
    assert (root/'dist/server.js').exists()
    env=dict(os.environ,PORT='8082',__PORT='8082',LEXWARE_API_KEY='test-only',
        LEXWARE_API_BASE_URL='http://127.0.0.1:9',MCP_AUTH_TOKEN='test-only-'+'x'*40,
        LEXWARE_ENABLE_DRAFTS='true',LEXWARE_ENABLE_FINALIZE='false',LEXWARE_ENABLE_URL_UPLOAD='false')
    env.pop('OAUTH_ISSUER',None)
    env.pop('LEXWARE_READ_ONLY',None)
    p=subprocess.Popen(['node','--require',str((Path(__file__).parents[1]/'loopback.cjs').resolve()),'dist/server.js'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url='http://127.0.0.1:8082',trust_env=False) as c:
            for _ in range(100):
                try:
                    if c.get('/status').status_code==200: break
                except httpx.HTTPError: pass
                time.sleep(.1)
            else: raise AssertionError('Backend failed to start')
            headers={'Authorization':'Bearer '+env['MCP_AUTH_TOKEN'],'Accept':'application/json, text/event-stream'}
            def rpc(method,params=None):
                return c.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}})
            assert c.post('/mcp',json={}).status_code==401
            result=rpc('tools/list')
            assert result.status_code==200,result.text
            import json
            if result.headers.get('content-type','').startswith('text/event-stream'):
                data=json.loads(next(line[6:] for line in result.text.splitlines() if line.startswith('data: ')))
            else: data=result.json()
            names={x['name'] for x in data['result']['tools']}
            assert names==ALLOWED,(names,ALLOWED)
            denied=rpc('tools/call',{'name':'create-draft-invoice','arguments':{}})
            assert 'error' in denied.text or 'Unknown tool' in denied.text,denied.text
    finally:
        p.terminate()
        p.wait(timeout=10)
