import { operations } from './subke-tools.mjs';
const BASE_URL = 'https://tbfdscpntpwprefyrdjj.supabase.co/functions/v1/public-api';
const versions = ['2026-07-28','2025-06-18','2025-03-26','2024-11-05'];
const serverInfo = {name:'subke-mcp',version:'1.0.0'};
const statusTool = {name:'connection_status',description:'Report private API-key configuration and write access without returning the key or contacting Subke.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}};
export function listTools(){return [statusTool,...operations.map(({name,description,inputSchema,method,scope})=>({name,description:`${description} Required scope: ${scope}.`,inputSchema,annotations:{readOnlyHint:method==='GET',destructiveHint:method==='PATCH',idempotentHint:method==='GET'||name==='announce_inbound',openWorldHint:true}}))];}
function validate(v,s,p='arguments'){
 if(s.type==='object'){
  if(!v||typeof v!=='object'||Array.isArray(v))throw Error(`${p} must be an object`);
  for(const k of s.required||[])if(!Object.hasOwn(v,k))throw Error(`${p}.${k} is required`);
  if(s.minProperties&&Object.keys(v).length<s.minProperties)throw Error(`${p} is empty`);
  for(const [k,x]of Object.entries(v)){if(Object.hasOwn(s.properties||{},k))validate(x,s.properties[k],`${p}.${k}`);else if(s.additionalProperties===false)throw Error(`Unknown parameter ${p}.${k}`);}
 }else if(s.type==='array'){
  if(!Array.isArray(v)||v.length<(s.minItems||0))throw Error(`${p} must be a nonempty array`);v.forEach((x,i)=>validate(x,s.items,`${p}[${i}]`));
 }else if(s.type==='string'){
  if(typeof v!=='string'||v.length<(s.minLength||0)||v.length>(s.maxLength||Infinity))throw Error(`${p} has an invalid string length`);
  if(s.format==='date'&&(!/^\d{4}-\d{2}-\d{2}$/.test(v)||!Number.isFinite(Date.parse(v))||new Date(v).toISOString().slice(0,10)!==v))throw Error(`${p} must be a valid YYYY-MM-DD date`);
 }else if(s.type==='number'||s.type==='integer'){
  if(typeof v!=='number'||!Number.isFinite(v)||(s.type==='integer'&&!Number.isInteger(v))||v<(s.minimum??-Infinity)||v>(s.maximum??Infinity)||(s.exclusiveMinimum!==undefined&&v<=s.exclusiveMinimum))throw Error(`${p} is outside the numeric range`);
 }
 if(s.enum&&!s.enum.includes(v))throw Error(`${p} must be one of ${s.enum.join(', ')}`);
}
const result=(data,isError=false)=>({content:[{type:'text',text:JSON.stringify(data)}],isError});
export async function callTool(name,args,env,fetcher=fetch){
 const op=operations.find(o=>o.name===name);
 if(name!==statusTool.name&&!op)return result({error:'unknown_tool'},true);
 try{validate(args,name===statusTool.name?statusTool.inputSchema:op.inputSchema);}catch(e){return result({error:'invalid_arguments',message:e.message},true);}
 if(name===statusTool.name)return result({configured:!!env.SUBKE_API_KEY,write_enabled:env.SUBKE_WRITE_ENABLED==='true',api_tools:operations.length});
 if(!env.SUBKE_API_KEY)return result({error:'not_configured',message:'Configure the private runtime secret SUBKE_API_KEY.'},true);
 if(op.method!=='GET'&&env.SUBKE_WRITE_ENABLED!=='true')return result({error:'write_disabled'},true);
 if(name==='update_inbound'&&args.body.action!=='cancel'&&!args.body.items?.length)return result({error:'invalid_arguments',message:'items are required for this action'},true);
 let path=op.path;const pathParams=new Set();
 for(const match of path.matchAll(/\{([^}]+)\}/g)){
  const k=match[1];if(!/^[A-Za-z0-9_-]+$/.test(args[k]))return result({error:'invalid_arguments',message:`${k} contains invalid path characters`},true);
  pathParams.add(k);path=path.replace(match[0],encodeURIComponent(args[k]));
 }
 const url=new URL(BASE_URL+path);
 for(const[k,v]of Object.entries(args))if(!pathParams.has(k)&&k!=='body'&&k!=='idempotency_key')url.searchParams.set(k,String(v));
 const headers={Authorization:`Bearer ${env.SUBKE_API_KEY}`,Accept:'application/json'};
 if(args.body)headers['Content-Type']='application/json';
 if(args.idempotency_key)headers['Idempotency-Key']=args.idempotency_key;
 try{
  const response=await fetcher(url,{method:op.method,headers,body:args.body?JSON.stringify(args.body):undefined,redirect:'error',signal:AbortSignal.timeout(20000)});
  const raw=await response.text();if(raw.length>2000000)return result({error:'response_too_large',message:'Narrow the filters or page size.'},true);
  let data;try{data=JSON.parse(raw.split(env.SUBKE_API_KEY).join('[redacted]'));}catch{return result({error:'invalid_upstream_response',http_status:response.status},true);}
  return result({http_status:response.status,...(response.status===429?{retry_after:response.headers.get('retry-after')}:{}),response:data},!response.ok);
 }catch{return result({error:'upstream_request_failed',message:op.method==='GET'?'Subke could not be reached. Try later.':'The result is uncertain. Check Subke before retrying to avoid duplicates.'},true);}
}
export async function handleMcp(request,env,fetcher=fetch){
 if(request.method!=='POST')return new Response('Use POST for MCP JSON-RPC.',{status:405,headers:{Allow:'POST','Cache-Control':'no-store'}});
 const reply=x=>Response.json(x,{headers:{'Cache-Control':'no-store'}});let m;
 try{const raw=await request.text();if(raw.length>256000)return new Response('Request too large',{status:413});m=JSON.parse(raw);}catch{return reply({jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}});}
 if(!m||Array.isArray(m)||m.jsonrpc!=='2.0'||typeof m.method!=='string')return reply({jsonrpc:'2.0',id:m?.id??null,error:{code:-32600,message:'Invalid Request'}});
 if(!Object.hasOwn(m,'id'))return new Response(null,{status:204});
 const e={jsonrpc:'2.0',id:m.id};let r;
 switch(m.method){
 case 'server/discover':r={serverInfo,supportedVersions:versions,capabilities:{tools:{}}};break;
 case 'initialize':r={protocolVersion:versions.includes(m.params?.protocolVersion)?m.params.protocolVersion:versions[0],serverInfo,capabilities:{tools:{}}};break;
 case 'ping':r={};break;
 case 'tools/list':r={tools:listTools()};break;
 case 'tools/call':r=await callTool(m.params?.name,m.params?.arguments??{},env,fetcher);break;
 default:return reply({...e,error:{code:-32601,message:'Method not found'}});
 }return reply({...e,result:r});
}
