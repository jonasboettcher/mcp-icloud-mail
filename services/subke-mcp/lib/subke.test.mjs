import test from 'node:test';
import assert from 'node:assert/strict';
import {handleMcp,callTool,listTools} from './subke.mjs';
const env={SUBKE_API_KEY:'test-secret',SUBKE_WRITE_ENABLED:'true'};
const data=r=>JSON.parse(r.content[0].text);
test('read request uses fixed HTTPS destination and encoded query',async()=>{
 let seen; const r=await callTool('list_stock',{sku:'SKU & ?x=1'},env,async(u,o)=>{seen={u,o};return Response.json({data:[]});});
 assert.equal(r.isError,false);assert.equal(seen.u.origin,'https://tbfdscpntpwprefyrdjj.supabase.co');assert.equal(seen.u.pathname,'/functions/v1/public-api/v1/stock');assert.equal(seen.u.searchParams.get('sku'),'SKU & ?x=1');assert.equal(seen.o.headers.Authorization,'Bearer test-secret');assert.equal(seen.o.method,'GET');assert.equal(seen.o.redirect,'error');
});
test('missing key, write gate, invalid args and traversal never contact API',async()=>{
 const never=()=>{throw Error('must not fetch');};
 assert.equal(data(await callTool('list_stock',{}, {},never)).error,'not_configured');
 assert.equal(data(await callTool('announce_return',{body:{order_number:'O-1'}},{SUBKE_API_KEY:'test'},never)).error,'write_disabled');
 for(const [name,args]of [['get_order',{id:'../products'}],['list_orders',{page:0}],['list_orders',{per_page:101}],['list_orders',{from_date:'2026-02-30'}],['list_products',{url:'https://example.com'}],['update_inbound',{id:'a',body:{action:'add_items'}}]]) assert.equal(data(await callTool(name,args,env,never)).error,'invalid_arguments');
});
test('inbound write preserves idempotency and has no automatic retry',async()=>{
 let count=0,seen;const args={body:{inbound_number:'IN-1',items:[{product_id:'p1',packaging_level_id:'l1',expected_quantity:2}]},idempotency_key:'in-test-1'};
 const r=await callTool('announce_inbound',args,env,async(u,o)=>{count++;seen=o;throw Error('timeout');});
 assert.equal(count,1);assert.equal(seen.method,'POST');assert.equal(seen.headers['Idempotency-Key'],'in-test-1');assert.equal(data(r).error,'upstream_request_failed');assert.match(data(r).message,/uncertain/);
});
test('API errors and rate limits propagate with no secret exposure',async()=>{
 const r=await callTool('list_stock',{},env,async()=>Response.json({error:{message:'test-secret'}},{status:429,headers:{'retry-after':'60'}}));
 assert.equal(r.isError,true);assert.equal(data(r).retry_after,'60');assert.ok(!JSON.stringify(r).includes('test-secret'));
});
test('discovery lists all verified API tools and correct write annotations',async()=>{
 const tools=listTools();assert.equal(tools.length,21);assert.equal(tools.filter(t=>t.annotations.readOnlyHint).length,17);assert.equal(tools.find(t=>t.name==='update_inbound').annotations.destructiveHint,true);
 const req=new Request('https://local/mcp',{method:'POST',body:JSON.stringify({jsonrpc:'2.0',id:1,method:'server/discover'})});
 const response=await(await handleMcp(req,env)).json();assert.ok(response.result.supportedVersions.includes('2026-07-28'));
});
test('notifications have no response; malformed JSON gives parse error',async()=>{
 assert.equal((await handleMcp(new Request('https://local/mcp',{method:'POST',body:'{"jsonrpc":"2.0","method":"notifications/initialized"}'}),env)).status,204);
 const bad=await(await handleMcp(new Request('https://local/mcp',{method:'POST',body:'{'}),env)).json();assert.equal(bad.error.code,-32700);
});
