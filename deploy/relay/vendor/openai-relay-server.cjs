'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const {RelayError,hash,signClientRequest}=require('./openai-relay-core.cjs');
const {createProviderPullBroker,MAX_REQUEST,MAX_RESPONSE,validType}=require('./ai-provider-pull.cjs');
const {SERVICE,REQUEST}=require('./openai-relay-client.cjs');
const PATHS=new Set(['/v1/responses','/v1/audio/transcriptions']),CACHE_TTL=10*60000;
const fail=(status,code,message)=>{throw new RelayError(status,code,message);};
function clientsFromFile(file){
 if(!path.isAbsolute(file||''))throw new Error('A private relay client configuration is required.');
 const stat=fs.lstatSync(file),privateOwner=(stat.mode&0o077)===0&&(stat.uid===0||stat.uid===process.getuid()),serviceGroup=stat.uid===0&&stat.gid===process.getgid()&&(stat.mode&0o077)===0o040;
 if(!stat.isFile()||stat.isSymbolicLink()||stat.size>32768||!privateOwner&&!serviceGroup)throw new Error('Relay client configuration must be a private regular file.');
 try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch{throw new Error('Relay client configuration is invalid.');}
}
function normalizeClients(value){
 if(!value||typeof value!=='object'||Array.isArray(value)||!Object.keys(value).length||Object.keys(value).length>32)throw new Error('Relay clients are invalid.');
 const clients=new Map(),secrets=new Set();for(const [id,item]of Object.entries(value)){
  if(!SERVICE.test(id)||!item||typeof item!=='object'||Array.isArray(item)||Object.keys(item).some(k=>!['secret','dailyLimit'].includes(k))||typeof item.secret!=='string'||item.secret.length<32||item.secret.length>512||!Number.isSafeInteger(item.dailyLimit)||item.dailyLimit<1||item.dailyLimit>100)throw new Error('Relay client configuration is invalid.');
  if(secrets.has(item.secret))throw new Error('Relay business credentials must be independent.');secrets.add(item.secret);clients.set(id,{secret:item.secret,dailyLimit:item.dailyLimit});
 }return clients;
}
function atomic(file,value){
 const temp=file+'.tmp-'+crypto.randomBytes(8).toString('hex');let fd;
 try{fd=fs.openSync(temp,'wx',0o600);fs.writeFileSync(fd,JSON.stringify(value));fs.fsyncSync(fd);fs.closeSync(fd);fd=undefined;fs.renameSync(temp,file);const dir=fs.openSync(path.dirname(file),'r');try{fs.fsyncSync(dir);}finally{fs.closeSync(dir);}}finally{if(fd!==undefined)fs.closeSync(fd);try{fs.unlinkSync(temp);}catch{}}
}
function readBuffer(req,limit){
 const declared=req.headers['content-length'];let length=null;
 if(declared!==undefined){if(!/^\d+$/.test(declared))return Promise.reject(new RelayError(400,'relay_length','Request length is invalid.'));length=Number(declared);if(!Number.isSafeInteger(length)||length>limit)return Promise.reject(new RelayError(413,'relay_body_limit','Request body is too large.'));}
 return new Promise((resolve,reject)=>{
  const bytes=length===null?null:Buffer.alloc(length),chunks=[];let size=0,done=false;
  const finish=(error,result)=>{if(done)return;done=true;req.removeListener('data',data);req.removeListener('end',end);req.removeListener('aborted',aborted);req.removeListener('error',aborted);if(error){req.resume();reject(error);}else resolve(result);};
  const data=chunk=>{size+=chunk.length;if(size>limit||length!==null&&size>length){finish(new RelayError(413,'relay_body_limit','Request body is too large.'));return;}if(bytes)bytes.set(chunk,size-chunk.length);else chunks.push(chunk);};
  const end=()=>length!==null&&size!==length?finish(new RelayError(400,'relay_length','Request body is incomplete.')):finish(null,bytes||Buffer.concat(chunks,size));
  const aborted=()=>finish(new RelayError(400,'relay_aborted','Request was interrupted.'));
  req.on('data',data);req.once('end',end);req.once('aborted',aborted);req.once('error',aborted);
 });
}
function createOpenAiRelayServer(options={}){
 const clock=options.clock||Date.now,clients=normalizeClients(options.clients||clientsFromFile(options.clientsFile||process.env.OPENAI_RELAY_CLIENTS_FILE)),stateDir=path.resolve(options.stateDir||process.env.OPENAI_RELAY_STATE_DIR||'/srv/cloud-level-up/relay/state');
 const secret=options.workerSecret||process.env.AI_RELAY_SECRET,workerId=options.workerId||process.env.AI_WORKER_ID||'sg-primary',globalLimit=options.globalDailyLimit??100,timeoutMs=options.timeoutMs??60000;
 if(typeof secret!=='string'||secret.length<32||secret.length>512||!SERVICE.test(workerId)||!Number.isSafeInteger(globalLimit)||globalLimit<1||globalLimit>100||!Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>85000)throw new Error('Relay worker resource configuration is invalid.');
 fs.mkdirSync(stateDir,{recursive:true,mode:0o700});const cacheDir=path.join(stateDir,'results');fs.mkdirSync(cacheDir,{recursive:true,mode:0o700});
 const usageFile=path.join(stateDir,'usage.json'),pending=new Map(),nonces=new Map();let closed=false,readingBodies=0;
 const broker=options.broker||createProviderPullBroker({secret,workerId,clock,pollWaitMs:options.pollWaitMs,onlineMs:options.workerOnlineMs});
 const day=()=>new Date(clock()+8*3600000).toISOString().slice(0,10);
 function usage(){
  let value={day:day(),total:0,services:{},requests:{}};
  if(fs.existsSync(usageFile)){
   try{if(fs.statSync(usageFile).size>128*1024)throw new Error();value=JSON.parse(fs.readFileSync(usageFile,'utf8'));if(typeof value.day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value.day)||!Number.isSafeInteger(value.total)||value.total<0||value.total>100||!value.services||typeof value.services!=='object'||Array.isArray(value.services)||Object.keys(value.services).length>64||!value.requests||typeof value.requests!=='object'||Array.isArray(value.requests)||Object.keys(value.requests).length>200)throw new Error();for(const [id,n]of Object.entries(value.services))if(!SERVICE.test(id)||!Number.isSafeInteger(n)||n<0||n>100)throw new Error();for(const [key,item]of Object.entries(value.requests))if(!/^[a-f0-9]{64}$/.test(key)||!item||!/^[a-f0-9]{64}$/.test(item.digest||'')||!Number.isSafeInteger(item.at))throw new Error();}catch{fail(503,'relay_state','Relay usage state is unavailable.');}
  }
  if(value.day!==day()){value.day=day();value.total=0;value.services={};}
  for(const [key,item]of Object.entries(value.requests))if(clock()-item.at>2*86400000)delete value.requests[key];return value;
 }
 const serviceCount=(value,id)=>Object.hasOwn(value.services,id)?value.services[id]:0;
 function remaining(id){const value=usage();return Object.keys(value.requests).length>=200?0:Math.max(0,Math.min(clients.get(id).dailyLimit-serviceCount(value,id),globalLimit-value.total));}
 function available(){if(closed||!broker.ready())return false;const value=usage();return Object.keys(value.requests).length<200&&value.total<globalLimit&&[...clients].some(([id,client])=>serviceCount(value,id)<client.dailyLimit);}
 function reserve(id,key,digest){const value=usage();if(value.requests[key]){if(value.requests[key].digest!==digest)fail(409,'relay_conflict','Request identifier was reused with different content.');fail(503,'relay_uncertain','This request was already attempted; it will not be repeated automatically.');}if(value.total>=globalLimit||serviceCount(value,id)>=clients.get(id).dailyLimit)fail(429,'relay_daily_limit','The relay daily request limit has been reached.');if(Object.keys(value.requests).length>=200)fail(429,'relay_daily_limit','Relay request history is full.');value.total++;value.services[id]=serviceCount(value,id)+1;value.requests[key]={digest,at:clock()};atomic(usageFile,value);}
 function json(res,status,value){if(res.destroyed||res.writableEnded)return;const body=JSON.stringify(value);res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Content-Length':Buffer.byteLength(body),'Cache-Control':'no-store'});res.end(body);}
 function raw(res,value,cached){if(res.destroyed||res.writableEnded)return;res.writeHead(value.status,{'Content-Type':'application/json','Content-Length':value.body.length,'Cache-Control':'no-store','X-Relay-Cached':cached?'1':'0'});res.end(value.body);}
 function cached(key,digest){
  const file=path.join(cacheDir,key+'.json');if(!fs.existsSync(file))return null;
  let record;try{const stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.size>384*1024)throw new Error();record=JSON.parse(fs.readFileSync(file,'utf8'));if(record.digest!==digest)fail(409,'relay_conflict','Request identifier was reused with different content.');if(!Number.isSafeInteger(record.at)||record.at>clock()+60000)throw new Error();if(clock()-record.at>=CACHE_TTL){fs.unlinkSync(file);return null;}if(record.state==='done'){if(!Number.isSafeInteger(record.status)||record.status!==200&&(record.status<400||record.status>599)||typeof record.body!=='string'||record.body.length>Math.ceil(MAX_RESPONSE/3)*4||record.body.length%4)throw new Error();const body=Buffer.from(record.body,'base64');if(body.length>MAX_RESPONSE||body.toString('base64')!==record.body)throw new Error();return {status:record.status,body};}if(record.state==='running'||record.state==='failed')fail(503,'relay_uncertain','This request was already attempted; it will not be repeated automatically.');throw new Error();}catch(error){if(error instanceof RelayError)throw error;fail(503,'relay_state','Relay result state is unavailable.');}
 }
 function prune(){let total=0;const entries=fs.readdirSync(cacheDir).filter(n=>/^[a-f0-9]{64}\.json$/.test(n)).map(name=>{const file=path.join(cacheDir,name),stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.size>384*1024)fail(503,'relay_state','Relay result state is unavailable.');return {file,size:stat.size,at:stat.mtimeMs};}).sort((a,b)=>b.at-a.at);for(const item of entries){if(clock()-item.at>=CACHE_TTL||total+item.size>4*1024*1024)fs.unlinkSync(item.file);else total+=item.size;}}
 async function authenticate(req,route,limit){
  const id=req.headers['x-relay-service'],timestamp=req.headers['x-relay-timestamp'],nonce=req.headers['x-relay-nonce'],requestId=req.headers['x-relay-request-id'],signature=req.headers['x-relay-signature'],contentType=req.headers['content-type'];
  if(typeof id!=='string'||!clients.has(id)||typeof timestamp!=='string'||!/^\d{13}$/.test(timestamp)||Math.abs(clock()-Number(timestamp))>60000||typeof nonce!=='string'||!/^[a-f0-9]{32}$/.test(nonce)||typeof requestId!=='string'||!REQUEST.test(requestId)||typeof signature!=='string'||!/^[a-f0-9]{64}$/.test(signature)||typeof contentType!=='string'||!validType(contentType)||req.headers.authorization||req.headers['content-encoding'])fail(401,'relay_signature','Relay request authentication failed.');
  const allowed=new Set(['host','connection','accept','accept-language','accept-encoding','user-agent','sec-fetch-mode','content-length','transfer-encoding','content-type','x-relay-service','x-relay-timestamp','x-relay-nonce','x-relay-request-id','x-relay-signature']);if(Object.keys(req.headers).some(k=>!allowed.has(k)))fail(400,'relay_headers','Relay headers are not supported.');
  const body=await readBuffer(req,limit),expected=signClientRequest(clients.get(id).secret,req.method,route,id,contentType,timestamp,nonce,requestId,body);
  if(!crypto.timingSafeEqual(Buffer.from(signature,'hex'),Buffer.from(expected,'hex')))fail(401,'relay_signature','Relay request authentication failed.');
  for(const [key,at]of nonces)if(clock()-at>120000)nonces.delete(key);const nonceKey=id+':'+nonce;if(nonces.has(nonceKey))fail(409,'relay_replay','Relay request nonce was already used.');if(nonces.size>=5000)fail(429,'relay_busy','Relay authentication is busy.');nonces.set(nonceKey,clock());
  return {id,requestId,contentType,body};
 }
 async function handle(req,res){
  let counted=false;
  try{
   if(!['127.0.0.1','::ffff:127.0.0.1','::1'].includes(req.socket.remoteAddress))fail(403,'relay_source','Only local Ali services may call this relay.');
   if(await broker.handle(req,res))return;
   const url=new URL(req.url,'http://localhost'),route=url.pathname;if(url.search||url.hash||req.url!==route)fail(404,'relay_route','Relay route is not available.');
   if(route==='/health'&&req.method==='GET'){json(res,200,{ok:!closed,available:available(),protocol:'provider-pull-v1'});return;}
   if(closed)fail(503,'relay_closing','Relay is closing.');
   if(route==='/v1/status'&&req.method==='GET'){const a=await authenticate(req,route,0);json(res,200,{configured:true,available:broker.ready()&&remaining(a.id)>0,serviceId:a.id,dailyLimit:clients.get(a.id).dailyLimit,remainingToday:remaining(a.id),globalDailyLimit:globalLimit,transport:'provider-pull-v1',...broker.state()});return;}
   if(!PATHS.has(route))fail(404,'relay_route','Relay route is not available.');if(req.method!=='POST')fail(405,'relay_method','Relay only accepts POST for provider requests.');
   if(readingBodies>=2)fail(429,'relay_busy','Relay is processing other requests.');readingBodies++;counted=true;
   const a=await authenticate(req,route,MAX_REQUEST);readingBodies--;counted=false;
   if(!a.body.length)fail(400,'relay_body','Relay request body is empty.');
   if(route==='/v1/responses'){
    if(a.contentType!=='application/json')fail(415,'relay_type','Responses requires application/json.');let value;try{value=JSON.parse(a.body.toString('utf8'));}catch{fail(400,'relay_json','Responses body must be a JSON object.');}
    if(!value||typeof value!=='object'||Array.isArray(value)||typeof value.model!=='string'||!value.model||value.model.length>100||value.stream!==undefined&&value.stream!==false||value.background!==undefined&&value.background!==false)fail(400,'relay_mode','Relay supports synchronous, non-streaming Responses requests.');
   }else if(!a.contentType.startsWith('multipart/form-data; boundary='))fail(415,'relay_type','Transcriptions requires multipart/form-data.');
   const key=hash(a.id+'\n'+a.requestId),digest=hash(route+'\n'+a.contentType+'\n'+hash(a.body));
   const existing=pending.get(key);if(existing){if(existing.digest!==digest)fail(409,'relay_conflict','Request identifier was reused with different content.');raw(res,await existing.work,true);return;}
   const prior=cached(key,digest);if(prior){raw(res,prior,true);return;}
   if(!broker.ready())fail(503,'relay_offline','SG relay is not ready.');if(pending.size>=2)fail(429,'relay_busy','Relay is processing other requests.');
   reserve(a.id,key,digest);atomic(path.join(cacheDir,key+'.json'),{state:'running',at:clock(),digest});
   const controller=new AbortController(),cancel=()=>{if(!res.writableEnded)controller.abort();};res.once('close',cancel);req.once('aborted',cancel);
   const work=(async()=>{
    try{
     const response=await broker.forwardRaw(hash(a.id+'\n'+a.requestId),'https://api.openai.com'+route,a.body,a.contentType,{key,deadlineAt:clock()+timeoutMs,signal:controller.signal});
     const body=Buffer.from(await response.arrayBuffer());if(body.length>MAX_RESPONSE)fail(502,'relay_response_limit','Provider response exceeded the relay limit.');
     const result={status:response.status,body};atomic(path.join(cacheDir,key+'.json'),{state:'done',at:clock(),digest,status:result.status,body:body.toString('base64')});prune();return result;
    }catch(error){atomic(path.join(cacheDir,key+'.json'),{state:'failed',at:clock(),digest});throw error;}
    finally{res.removeListener('close',cancel);req.removeListener('aborted',cancel);pending.delete(key);}
   })();pending.set(key,{digest,work,controller});raw(res,await work,false);
  }catch(error){const safe=error instanceof RelayError?error:new RelayError(503,'relay_unavailable','OpenAI relay is temporarily unavailable.');if(['relay_body_limit','relay_length','relay_aborted'].includes(safe.code)){req.resume();res.setHeader('Connection','close');}json(res,safe.status,{error:{type:'relay_error',code:safe.code,message:safe.message}});}finally{if(counted)readingBodies--;}
 }
 prune();const server=http.createServer((req,res)=>{handle(req,res).catch(()=>json(res,503,{error:{type:'relay_error',code:'relay_unavailable',message:'OpenAI relay is temporarily unavailable.'}}));});server.requestTimeout=95000;server.headersTimeout=10000;server.keepAliveTimeout=5000;server.maxConnections=32;
 const originalClose=server.close.bind(server);server.close=callback=>{closed=true;for(const item of pending.values())item.controller.abort();broker.close();return originalClose(callback);};
 server.relay={status:()=>({available:available(),...broker.state()}),broker};return server;
}
if(require.main===module){const server=createOpenAiRelayServer();server.listen(18769,'127.0.0.1',()=>console.log('OpenAI relay listening on Ali loopback'));for(const signal of ['SIGTERM','SIGINT'])process.once(signal,()=>{server.close(()=>process.exit(0));setTimeout(()=>server.closeAllConnections(),5000).unref();});}
module.exports={createOpenAiRelayServer,clientsFromFile,normalizeClients,readBuffer};
