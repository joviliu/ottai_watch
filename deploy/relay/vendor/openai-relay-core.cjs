'use strict';
const crypto=require('node:crypto');
class RelayError extends Error{constructor(status,code,message='OpenAI relay is temporarily unavailable.'){super(message);this.status=status;this.code=code;}}
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const signRequest=(secret,timestamp,nonce,body)=>crypto.createHmac('sha256',secret).update(timestamp+'\n'+nonce+'\n'+hash(body)).digest('hex');
const signClientRequest=(secret,method,route,serviceId,contentType,timestamp,nonce,requestId,body)=>crypto.createHmac('sha256',secret).update([method,route,serviceId,contentType,timestamp,nonce,requestId,hash(body)].join('\n')).digest('hex');
module.exports={RelayError,hash,signRequest,signClientRequest};
