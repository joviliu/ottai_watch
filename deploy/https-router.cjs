'use strict';
const https=require('node:https'),http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const tlsDir=process.env.TLS_DIR||'/srv/cloud-level-up/tls';
const context=()=>({key:fs.readFileSync(path.join(tlsDir,'server.key')),cert:fs.readFileSync(path.join(tlsDir,'server.crt')),minVersion:'TLSv1.2'});
const hopHeaders=new Set(['connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade']);
const server=https.createServer(context(),(req,res)=>{
  const headers={};for(const [name,value] of Object.entries(req.headers))if(!hopHeaders.has(name))headers[name]=value;
  headers['x-forwarded-for']=req.socket.remoteAddress;headers['x-forwarded-proto']='https';
  const ottai=req.url.startsWith('/ottai/');
  const upstream=http.request({host:'127.0.0.1',port:ottai?18776:Number(process.env.UPSTREAM_PORT||18766),method:req.method,path:ottai?req.url.slice(6):req.url,headers},incoming=>{
    res.statusCode=incoming.statusCode;for(const [name,value] of Object.entries(incoming.headers))if(!hopHeaders.has(name))res.setHeader(name,value);
    res.setHeader('Strict-Transport-Security','max-age=31536000');incoming.on('error',()=>res.destroy());incoming.pipe(res);
  });
  upstream.setTimeout(180000,()=>upstream.destroy());
  upstream.on('error',()=>{if(res.headersSent){res.destroy();return;}res.writeHead(502,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify({error:'后台正在启动，请稍后重试'}));});
  req.on('aborted',()=>upstream.destroy());res.on('close',()=>{if(!res.writableEnded)upstream.destroy();});req.pipe(upstream);
});
server.headersTimeout=10000;server.requestTimeout=180000;server.keepAliveTimeout=5000;
process.on('SIGHUP',()=>{try{server.setSecureContext(context());console.log('TLS certificate reloaded');}catch(error){console.error('TLS reload failed:',error.code||error.name);}});
process.on('SIGTERM',()=>{server.close(()=>process.exit(0));setTimeout(()=>process.exit(1),10000).unref();});
server.listen(Number(process.env.HTTPS_PORT||8443),process.env.HTTPS_HOST||'0.0.0.0',()=>console.log('Cloud Level Up HTTPS listening'));
