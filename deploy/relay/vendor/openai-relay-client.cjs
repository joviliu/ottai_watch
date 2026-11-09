'use strict';
const crypto=require('node:crypto');
const {RelayError,signClientRequest}=require('./openai-relay-core.cjs');
const OPENAI='https://api.openai.com',PATHS=new Set(['/v1/responses','/v1/audio/transcriptions']),MAX_REQUEST=18*1024*1024;
const SERVICE=/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/,REQUEST=/^(?:[a-f0-9]{64}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})$/;
function createRelayFetch(options={}){
 const origin=options.origin||'http://127.0.0.1:18769',serviceId=options.serviceId,secret=options.secret,direct=options.fetchImpl||fetch,clock=options.clock||Date.now;
 let parsed;try{parsed=new URL(origin);}catch{throw new Error('Relay requires a loopback origin.');}
 if(parsed.protocol!=='http:'||!['127.0.0.1','[::1]'].includes(parsed.hostname)||parsed.username||parsed.password||!['','/'].includes(parsed.pathname)||parsed.search||parsed.hash||!SERVICE.test(serviceId||'')||typeof secret!=='string'||secret.length<32||secret.length>512||typeof direct!=='function')throw new Error('Relay client configuration is invalid.');
 async function send(method,route,body,contentType,signal,requestId){
  if(!REQUEST.test(requestId))throw new RelayError(400,'relay_request_id','Relay request identifier is invalid.');
  const timestamp=String(clock()),nonce=crypto.randomBytes(16).toString('hex');
  const headers={'Content-Type':contentType,'X-Relay-Service':serviceId,'X-Relay-Timestamp':timestamp,'X-Relay-Nonce':nonce,'X-Relay-Request-Id':requestId,'X-Relay-Signature':signClientRequest(secret,method,route,serviceId,contentType,timestamp,nonce,requestId,body)};
  let response;try{response=await direct(parsed.origin+route,{method,redirect:'error',credentials:'omit',headers,...(method==='POST'?{body}:{}),signal:signal||AbortSignal.timeout(method==='GET'?5000:90000)});}catch{throw new RelayError(503,'relay_unavailable','OpenAI relay connection failed.');}
  if(response.status>=300&&response.status<400){await response.body?.cancel().catch(()=>{});throw new RelayError(502,'relay_redirect','Relay redirects are not allowed.');}
  return response;
 }
 async function relayFetch(input,init={}){
  if(typeof input!=='string'||!input.startsWith(OPENAI)||!PATHS.has(input.slice(OPENAI.length))||!init||typeof init!=='object'||Array.isArray(init)||init.method!=='POST'||init.redirect!==undefined&&init.redirect!=='error'||Object.keys(init).some(k=>!['method','headers','body','signal','redirect'].includes(k)))throw new RelayError(400,'relay_route','Relay supports only the two fixed OpenAI POST routes.');
  const route=input.slice(OPENAI.length),headers=new Headers(init.headers);
  if([...headers.keys()].some(k=>!['content-type','authorization','x-relay-request-id'].includes(k)))throw new RelayError(400,'relay_headers','Relay request headers are not supported.');
  if(route==='/v1/responses'&&typeof init.body!=='string'||route==='/v1/audio/transcriptions'&&!(init.body instanceof FormData)&&!Buffer.isBuffer(init.body)&&!(init.body instanceof Uint8Array))throw new RelayError(400,'relay_body','Relay request body is not supported.');
  if(typeof init.body==='string'&&Buffer.byteLength(init.body)>MAX_REQUEST||Buffer.isBuffer(init.body)&&init.body.length>MAX_REQUEST)throw new RelayError(413,'relay_body_limit','Relay request is too large.');
  // Only the content type survives. The OpenAI credential is injected exclusively on SG.
  const contentType=headers.get('content-type'),request=new Request(OPENAI+route,{method:'POST',headers:contentType?{'Content-Type':contentType}:{},body:init.body});
  const body=Buffer.from(await request.arrayBuffer());if(!body.length||body.length>MAX_REQUEST)throw new RelayError(413,'relay_body_limit','Relay request is too large.');
  const requestId=headers.get('x-relay-request-id')||(typeof options.requestId==='function'?options.requestId(input,init):options.requestId)||crypto.randomUUID();
  return send('POST',route,body,request.headers.get('content-type'),init.signal,requestId);
 }
 relayFetch.status=async()=>{
  const response=await send('GET','/v1/status',Buffer.alloc(0),'application/json',undefined,crypto.randomUUID());
  const chunks=[];let size=0;for await(const chunk of response.body||[]){size+=chunk.length;if(size>4096)throw new RelayError(502,'relay_status','Relay status response is invalid.');chunks.push(Buffer.from(chunk));}const bytes=Buffer.concat(chunks,size);
  let value;try{value=JSON.parse(bytes.toString('utf8'));}catch{throw new RelayError(502,'relay_status','Relay status response is invalid.');}
  if(!response.ok)throw new RelayError(response.status,'relay_status','Relay status is unavailable.');return value;
 };
 return relayFetch;
}
function createRelayFetchFromEnv(options={}){return createRelayFetch({origin:process.env.OPENAI_RELAY_URL||'http://127.0.0.1:18769',serviceId:process.env.OPENAI_RELAY_SERVICE_ID,secret:process.env.OPENAI_RELAY_CLIENT_SECRET,...options});}
module.exports={createRelayFetch,createRelayFetchFromEnv,SERVICE,REQUEST,MAX_REQUEST};
