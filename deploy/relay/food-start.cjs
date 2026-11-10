'use strict';
// Dedicated food budget, clients, worker and state; analysis retains its own 49 calls.
const {createOpenAiRelayServer}=require('./vendor/openai-relay-server.cjs');
const server=createOpenAiRelayServer({globalDailyLimit:30,timeoutMs:80000});
server.listen(18781,'127.0.0.1');
process.once('SIGTERM',()=>server.close(()=>process.exit(0)));
