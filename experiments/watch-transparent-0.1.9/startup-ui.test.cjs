const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const model = require('../src/common/model'), faceExport = require('../src/common/face-export')
const ux = fs.readFileSync(path.join(__dirname,'../src/pages/index/index.ux'),'utf8')
const script = ux.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'').replace('export default','module.exports =')
const at = Date.now() - 300000
function frame(value=6.8, sync=false) {
  return {type:'glucose',version:1,sourceAt:at,value,unit:'mmol/L',trend:'→',history:[{time:at,value}],watchfaceSync:sync}
}
function setup(cached='') {
  const writes=[], sent=[], timeouts=new Map(), intervals=new Map(), logs=[]
  let now=0, id=0, exits=0
  const connection={send:options=>sent.push(options.data)}
  const sandbox={module:{exports:{}},model,faceExport,Date,
    interconnect:{instance:()=>connection},file:{writeText:options=>writes.push(options)},
    storage:{get:options=>options.success(cached),set:()=>{}},
    app:{getInfo:()=>({source:{type:'bluetooth'}}),terminate:()=>exits++},console:{info:message=>logs.push(message)},
    setTimeout:(fn,ms)=>{timeouts.set(++id,{fn,at:now+ms});return id},clearTimeout:id=>timeouts.delete(id),
    setInterval:(fn,ms)=>{intervals.set(++id,{fn,ms});return id},clearInterval:id=>intervals.delete(id)}
  vm.runInNewContext(script,sandbox,{filename:'watch-index.ux'})
  const page=sandbox.module.exports;Object.assign(page,page.private);page.onInit();page.onShow()
  function advance(ms) {
    const until=now+ms
    while (timeouts.size) {
      const [key,value]=[...timeouts.entries()].sort((a,b)=>a[1].at-b[1].at)[0]
      if (value.at>until) break
      now=value.at;timeouts.delete(key);value.fn()
    }
    now=until
  }
  return {page,writes,sent,logs,timeouts,intervals,advance,get exits(){return exits},
    send:value=>connection.onmessage({data:JSON.stringify(value)})}
}

assert.match(ux, /class="page" if="{{uiVisible}}"/, 'the whole main UI must be gated')
assert.match(ux, /\.shell[^}]*background-color:#00000000/, 'the launch shell requests transparency')
const manifest=require('../src/manifest.json')
assert.equal(manifest.display.backgroundColor,'#00000000')

let run=setup()
run.send(frame());run.writes[0].success()
assert.equal(run.page.value,'6.8','data and export must run before UI presentation')
run.advance(1999);assert.equal(run.page.uiVisible,false)
run.advance(1);assert.equal(run.page.uiVisible,true,'ordinary manual viewing appears after the bounded delay')
assert.equal(run.exits,0)
assert.deepEqual(run.logs,['GlucoseWatch6 launch source type: bluetooth'],'launch source is diagnostic only')

run=setup(JSON.stringify(frame(6.7,true)))
run.advance(2000)
assert.equal(run.page.uiVisible,true,'a cached sync flag cannot hide a manual or offline launch')
assert.equal(run.page.value,'6.7')
assert.equal(run.exits,0)
assert.equal(run.writes.length,0,'cached data alone is not a fresh export')

run=setup();run.advance(1000);run.send(frame(6.8,true));run.advance(1000)
assert.equal(run.page.uiVisible,false,'live sync holds the UI beyond the initial delay while writing')
run.writes[0].success();run.advance(399)
assert.equal(run.exits,0)
run.advance(1)
assert.equal(run.exits,1,'successful current export returns before exposing the main UI')
assert.equal(run.page.uiVisible,false)
run.advance(5000)
assert.equal(run.page.uiVisible,false,'no fallback timer can reveal content after successful return')

run=setup();run.send(frame(6.8,true));run.writes[0].fail({},300)
assert.equal(run.page.uiVisible,true,'write failure reveals the diagnostic UI immediately')
assert.match(run.page.status,/文件写入失败 300/)
run.advance(5000);assert.equal(run.exits,0,'failure cannot claim success or exit')

run=setup();run.send(frame(6.8,true));run.advance(2000);run.send(frame(6.9,true));run.advance(999)
assert.equal(run.page.uiVisible,false)
run.advance(1)
assert.equal(run.page.uiVisible,true,'corrections must not extend a stalled hidden session indefinitely')
assert.match(run.page.status,/等待较久/)
assert.equal(run.exits,0)
run.writes[0].success()
assert.equal(run.writes.length,2)
run.advance(500);assert.equal(run.exits,0,'old write completion cannot return ahead of the current correction')
run.writes[1].success();run.advance(400)
assert.equal(run.exits,1,'a late successful retry still finishes the automatic session')

run=setup();run.advance(2000);run.send(frame(6.8,true))
assert.equal(run.page.uiVisible,true,'an already visible manual page must not be hidden by a sync flag')

run=setup();run.send(frame(6.8,true));run.page.onHide()
assert.equal(run.timeouts.size,0,'hide clears UI, export-return, chart and ACK timers')
assert.equal(run.intervals.size,0)
run.writes[0].success();run.advance(5000)
assert.equal(run.exits,0,'a file callback after hiding must not terminate another page')
assert.equal(run.page.uiVisible,false)
run.page.onShow();run.advance(2000)
assert.equal(run.page.uiVisible,true,'returning manually after a hidden attempt remains usable')

run=setup();run.send(frame(6.8,true));run.writes[0].success();run.page.onDestroy()
assert.equal(run.timeouts.size,0,'destroy clears every pending page timer')
assert.equal(run.intervals.size,0)
run.advance(5000);run.send(frame(6.9,true))
assert.equal(run.exits,0)
assert.equal(run.writes.length,1,'destroyed pages ignore subsequent messages')

console.log('startup UI: bounded manual delay, live sync, cache isolation, failures, corrections and lifecycle passed')
