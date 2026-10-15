import test from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from './server.mjs';
const secret='test-only-connection-token-at-least-32-characters';
test('HTTP boundary protects tools, enforces origin and body size, and exposes health', async t => {
  const server=createApp({MCP_ACCESS_TOKEN:secret,SUBKE_WRITE_ENABLED:'true',PUBLIC_BASE_URL:'https://example.test'});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  t.after(()=>new Promise(r=>{server.closeAllConnections();server.close(r);}));
  const url=`http://127.0.0.1:${server.address().port}`;
  assert.equal((await fetch(url+'/healthz')).status,200);
  const payload={jsonrpc:'2.0',id:1,method:'tools/list'};
  const post=(headers={},body=JSON.stringify(payload))=>fetch(url+'/mcp',{method:'POST',headers:{'Content-Type':'application/json',...headers},body});
  assert.equal((await post()).status,401);
  assert.equal((await post({Authorization:'Bearer wrong-token'})).status,401);
  const auth={Authorization:`Bearer ${secret}`};
  const response=await post(auth);assert.equal(response.status,200);assert.equal((await response.json()).result.tools.length,21);
  assert.equal((await post({...auth,Origin:'https://evil.test'})).status,403);
  assert.equal((await post({...auth,Origin:'https://example.test'})).status,200);
  assert.equal((await post(auth,'x'.repeat(256001))).status,413);
  const status=await post(auth,JSON.stringify({jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'connection_status',arguments:{}}}));
  const text=JSON.stringify(await status.json());assert.ok(!text.includes(secret));assert.match(text,/configured/);
});
test('missing server credential always denies tool discovery',async t=>{
  const server=createApp({});await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>{server.closeAllConnections();server.close(r);}));
  const response=await fetch(`http://127.0.0.1:${server.address().port}/mcp`,{method:'POST',headers:{Authorization:`Bearer ${secret}`,'Content-Type':'application/json'},body:'{}'});
  assert.equal(response.status,401);
});
