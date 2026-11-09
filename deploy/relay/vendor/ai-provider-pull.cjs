'use strict';
// Ali owns provider payloads and validation; SG only streams these two fixed API routes.
const crypto=require('node:crypto');
const {RelayError:AiReviewError,signRequest,hash}=require('./openai-relay-core.cjs');
const PROTOCOL='provider-pull-v1',MAX_REQUEST=18*1024*1024,MAX_RESPONSE=256*1024,MAX_RESULT=512*1024;
const PATHS=new Set(['/v1/responses','/v1/audio/transcriptions']);
const fail=(status,code,message='AI后台暂不可用。')=>{throw new AiReviewError(status,code,message);};
const validType=value=>value==='application/json'||typeof value==='string'&&value.length<=120&&/^multipart\/form-data; boundary=[A-Za-z0-9'()+_,./:=?-]{1,80}$/.test(value);
function createProviderPullBroker({secret,workerId,clock=Date.now,pollWaitMs=15000,onlineMs=45000}){
 if(!Number.isSafeInteger(pollWaitMs)||pollWaitMs<1||pollWaitMs>20000||!Number.isSafeInteger(onlineMs)||onlineMs<1||onlineMs>60000)throw new Error('Invalid AI worker heartbeat timing');
 const jobs=new Map(),waiters=[],nonces=new Map();let heartbeatAt=null,providerReady=false,closed=false;
 const online=()=>heartbeatAt!==null&&clock()-heartbeatAt>=0&&clock()-heartbeatAt<=onlineMs,ready=()=>!closed&&online()&&providerReady;
 function send(res,status,value){if(res.destroyed||res.writableEnded)return;const body=JSON.stringify(value);res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Content-Length':Buffer.byteLength(body),'Cache-Control':'no-store'});res.end(body);}
 function finish(job,error,response){if(!jobs.delete(job.id))return;clearTimeout(job.timer);job.signal?.removeEventListener('abort',job.abort);if(error)job.reject(error);else job.resolve(response);}
 function expire(){for(const job of jobs.values())if(clock()>=job.deadline)finish(job,new AiReviewError(503,'provider_timeout','AI识别已超时。'));}
 function lease(){expire();if(!ready()||[...jobs.values()].some(job=>job.lease))return null;for(const job of jobs.values()){job.lease=crypto.randomBytes(24).toString('hex');job.deadline=Math.min(job.deadline,clock()+85000);return job;}return null;}
 function dispatch(){while(waiters.length){const job=lease();if(!job)break;waiters.shift().resolve(job);}}
 async function forward(requestId,url,init={},context={}){
  if(!/^[a-f0-9]{64}$/.test(requestId||'')||typeof url!=='string'||!url.startsWith('https://api.openai.com/'))fail(400,'invalid_provider_request');
  const route=url.slice('https://api.openai.com'.length);if(!PATHS.has(route)||init.method!=='POST'||init.redirect!=='error'||!(typeof init.body==='string'||init.body instanceof FormData))fail(400,'invalid_provider_request');
  if(route==='/v1/responses'?typeof init.body!=='string':!(init.body instanceof FormData))fail(400,'invalid_provider_request');
  const signal=init.signal;if(signal?.aborted)fail(503,'provider_timeout');
  if(typeof init.body==='string'&&Buffer.byteLength(init.body)>MAX_REQUEST)fail(413,'media_limit');
  const headers=new Headers(init.headers),declared=headers.get('content-type');
  if(typeof init.body==='string'&&declared!=='application/json')fail(400,'invalid_provider_request');
  // The placeholder Authorization is deliberately discarded and never crosses Ali.
  const request=new Request('https://api.openai.com'+route,{method:'POST',headers:declared?{'Content-Type':declared}:{},body:init.body});
  const contentType=request.headers.get('content-type');if(!validType(contentType)||route==='/v1/audio/transcriptions'&&!contentType.startsWith('multipart/form-data; boundary='))fail(400,'invalid_provider_request');
  const body=Buffer.from(await request.arrayBuffer());
  return forwardRaw(requestId,url,body,contentType,{...context,signal});
 }
 async function forwardRaw(requestId,url,bytes,contentType,context={}){
  if(!/^[a-f0-9]{64}$/.test(requestId||'')||typeof url!=='string'||!url.startsWith('https://api.openai.com/'))fail(400,'invalid_provider_request');
  const route=url.slice('https://api.openai.com'.length);if(!PATHS.has(route)||!validType(contentType)||route==='/v1/responses'&&contentType!=='application/json'||route==='/v1/audio/transcriptions'&&!contentType.startsWith('multipart/form-data; boundary='))fail(400,'invalid_provider_request');
  if(!Buffer.isBuffer(bytes)||!bytes.length||bytes.length>MAX_REQUEST)fail(413,'media_limit');
  const signal=context.signal,body=Buffer.from(bytes);
  if(signal?.aborted)fail(503,'provider_timeout');expire();if(!ready())fail(503,'provider_unavailable');if(jobs.size>=2)fail(429,'provider_busy');
  const deadline=Math.min(clock()+85000,Number.isFinite(context.deadlineAt)?context.deadlineAt:Infinity);if(deadline<=clock())fail(503,'provider_timeout');
  return new Promise((resolve,reject)=>{
   const id=hash(requestId+'\n'+route+'\n'+hash(body)+'\n'+crypto.randomBytes(16).toString('hex'));
   const job={id,requestId,key:context.key||requestId,route,contentType,body,deadline,signal,resolve,reject};
   job.abort=()=>finish(job,new AiReviewError(503,'provider_timeout','AI识别已超时。'));
   job.timer=setTimeout(job.abort,Math.max(1,deadline-clock()));job.timer.unref?.();jobs.set(id,job);signal?.addEventListener('abort',job.abort,{once:true});if(signal?.aborted)job.abort();else dispatch();
  });
 }
 async function handle(req,res){
  const parsed=new URL(req.url,'http://localhost'),route=parsed.pathname,action=route==='/api/ai/worker/poll'?'poll':route==='/api/ai/worker/result'?'result':null;if(!action)return false;
  try{
   if(closed||!secret)fail(503,'worker_not_configured');if(req.method!=='POST')fail(405,'method_not_allowed');if(parsed.search||parsed.hash)fail(400,'invalid_input');
   if(!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type']||''))fail(415,'json_required');
   const timestamp=req.headers['x-ai-timestamp'],nonce=req.headers['x-ai-nonce'],signature=req.headers['x-ai-signature'];
   if(typeof timestamp!=='string'||!/^\d{13}$/.test(timestamp)||Math.abs(clock()-Number(timestamp))>60000||typeof nonce!=='string'||!/^[a-f0-9]{32}$/.test(nonce)||typeof signature!=='string'||!/^[a-f0-9]{64}$/.test(signature))fail(401,'invalid_signature');
   let size=0,chunks=[];for await(const chunk of req){size+=chunk.length;if(size>(action==='poll'?4096:MAX_RESULT))fail(413,'body_limit');chunks.push(chunk);}
   const raw=Buffer.concat(chunks,size).toString('utf8'),expected=signRequest(secret,timestamp,nonce,raw);if(!crypto.timingSafeEqual(Buffer.from(signature,'hex'),Buffer.from(expected,'hex')))fail(401,'invalid_signature');
   for(const [key,at]of nonces)if(clock()-at>120000)nonces.delete(key);if(nonces.has(nonce))fail(409,'request_replayed');if(nonces.size>=5000)fail(429,'busy');nonces.set(nonce,clock());
   let input;try{input=JSON.parse(raw);}catch{fail(400,'invalid_json');}
   if(!input||typeof input!=='object'||Array.isArray(input)||input.workerId!==workerId||input.action!==action||input.protocol!==PROTOCOL)fail(401,'worker_identity');expire();
   if(action==='poll'){
    if(Object.keys(input).some(k=>!['workerId','action','protocol','providerReady','capacity'].includes(k))||typeof input.providerReady!=='boolean'||![0,1].includes(input.capacity))fail(400,'invalid_input');
    heartbeatAt=clock();providerReady=input.providerReady;let assigned=input.capacity===1&&ready()?lease():null;
    if(!assigned&&input.capacity===1&&ready()){
     if(waiters.length>=2)fail(429,'busy');let waiter,timer;const aborted=()=>waiter?.resolve(null);
     assigned=await new Promise(resolve=>{waiter={resolve};waiters.push(waiter);timer=setTimeout(()=>resolve(null),pollWaitMs);timer.unref?.();req.once('aborted',aborted);res.once('close',aborted);});
     clearTimeout(timer);const index=waiters.indexOf(waiter);if(index>=0)waiters.splice(index,1);req.removeListener('aborted',aborted);res.removeListener('close',aborted);
    }
    if(!assigned){send(res,200,{job:null,serverTime:clock()});return true;}
    if(res.destroyed||res.writableEnded){finish(assigned,new AiReviewError(503,'provider_uncertain','后台连接已中断。'));return true;}
    res.writeHead(200,{'Content-Type':'application/octet-stream','Content-Length':assigned.body.length,'Cache-Control':'no-store','X-AI-Provider-Job':assigned.id,'X-AI-Provider-Lease':assigned.lease,'X-AI-Provider-Request':assigned.requestId,'X-AI-Provider-Path':assigned.route,'X-AI-Provider-Type':assigned.contentType,'X-AI-Provider-Deadline':String(assigned.deadline)});res.end(assigned.body);return true;
   }
   if(Object.keys(input).some(k=>!['workerId','action','protocol','jobId','leaseId','status','body','error'].includes(k))||!/^[a-f0-9]{64}$/.test(input.jobId||'')||!/^[a-f0-9]{48}$/.test(input.leaseId||''))fail(400,'invalid_input');
   const job=jobs.get(input.jobId);if(!job||job.lease!==input.leaseId)fail(409,'lease_expired');
   if(Object.hasOwn(input,'error')){if(input.status!==undefined||input.body!==undefined||!input.error||typeof input.error!=='object'||Object.keys(input.error).some(k=>k!=='code')||!['provider_unavailable','provider_uncertain','provider_timeout'].includes(input.error.code))fail(400,'invalid_input');finish(job,new AiReviewError(503,input.error.code));}
   else{
    if(!Number.isSafeInteger(input.status)||input.status!==200&&(input.status<400||input.status>599)||typeof input.body!=='string'||input.body.length>Math.ceil(MAX_RESPONSE/3)*4||input.body.length%4!==0)fail(400,'invalid_input');
    const body=Buffer.from(input.body,'base64');if(body.length>MAX_RESPONSE||body.toString('base64')!==input.body)fail(400,'invalid_input');
    finish(job,null,new Response(body,{status:input.status,headers:{'Content-Type':'application/json'}}));
   }
   send(res,200,{accepted:true});dispatch();return true;
  }catch(error){const safe=error instanceof AiReviewError?error:new AiReviewError(503,'worker_unavailable','AI后台暂不可用。');send(res,safe.status,{code:safe.code,message:safe.message});return true;}
 }
 function cancel(key){for(const job of jobs.values())if(job.key===key)finish(job,new AiReviewError(409,'provider_stale','完成证据已更新。'));}
 function close(){closed=true;for(const job of jobs.values())finish(job,new AiReviewError(503,'provider_unavailable'));for(const waiter of waiters.splice(0))waiter.resolve(null);}
 return {ready,forward,forwardRaw,handle,cancel,close,state:()=>({workerOnline:online(),providerReady:online()&&providerReady,pendingJobs:jobs.size})};
}
module.exports={createProviderPullBroker,PROTOCOL,MAX_REQUEST,MAX_RESPONSE,MAX_RESULT,validType};
