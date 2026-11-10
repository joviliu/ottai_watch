'use strict';
const {createOpenAiRelayServer}=require('./vendor/openai-relay-server.cjs');
const server=createOpenAiRelayServer({globalDailyLimit:49,timeoutMs:80000});
server.listen(18779,'127.0.0.1');
process.once('SIGTERM',()=>server.close(()=>process.exit(0)));
