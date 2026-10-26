const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const model = require('../src/common/model')
const faceExport = require('../src/common/face-export')
const ux = fs.readFileSync(require('node:path').join(__dirname,'../src/pages/index/index.ux'),'utf8')
const script = ux.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/^import .*$/gm,'').replace('export default','module.exports =')
const sent = [], timers = [], cache = [], intervals = []
let terminated = 0
const connection = {send(options) {
  assert.equal(typeof options.data,'object','Vela interconnect.send requires an object')
  sent.push(JSON.parse(JSON.stringify(options.data)))
}}
const sandbox = {
  module:{exports:{}}, model, faceExport, app:{terminate:() => terminated++}, file:{writeText:options => options.success()}, interconnect:{instance:() => connection},
  storage:{get:options => options.success(''),set:options => cache.push(options)},
  setTimeout:fn => timers.push(fn),clearTimeout:() => {},setInterval:(fn,ms) => { intervals.push({fn,ms}); return intervals.length },clearInterval:() => {},
  console,Date
}
vm.runInNewContext(script,sandbox,{filename:'watch-index.ux'})
const page = sandbox.module.exports
Object.assign(page,page.private)
page.onInit(); page.onShow()
assert.deepEqual(sent[0],{type:'request_latest'})
const at = Date.now() - 300000
const frame = {type:'glucose',version:1,value:7.5,unit:'mmol/L',trend:'↑',sourceAt:at,history:[{time:at,value:7.5}]}
connection.onmessage({data:JSON.stringify(frame)})
assert.equal(page.value,'7.5')
assert.equal(page.trend,'↑')
assert.equal(page.frame.sourceAt,at)
while(timers.length) timers.shift()()
assert.deepEqual(sent.at(-1),{type:'ack',sourceAt:at})
assert.ok(sent.some(message => message.type === 'face_export' && message.sourceAt === at))
assert.equal(JSON.parse(cache[0].value).sourceAt,at)
const count = sent.length
connection.onmessage({data:JSON.stringify({...frame,sourceAt:at-300000,history:[{time:at-300000,value:7.5}]})})
connection.onmessage({data:JSON.stringify({...frame,value:0})})
assert.equal(sent.length,count,'old or invalid data must not be acknowledged as a new display')
assert.equal(page.value,'7.5','invalid data must preserve last real value')
page.onHide(); page.onShow()
assert.equal(page.value,'7.5','opening must preserve the cached value requested by the user')
assert.equal(page.source,'欧态更新 ' + model.clock(at))
assert.ok(page.status.includes('上次读数'))
assert.equal(intervals.at(-1).ms,60000)
const requests = sent.length
for (let i=0;i<3;i++) intervals.at(-1).fn()
assert.equal(sent.length,requests,'age updates must not poll the phone for glucose')
page.onHide(); page.onDestroy()
assert.equal(terminated,0,'manual viewing must never auto-exit')
connection.onmessage({data:JSON.stringify({...frame,watchfaceSync:true})})
while(timers.length) timers.shift()()
assert.equal(terminated,1,'explicit watchface sync returns only after successful file export')
sandbox.file.writeText=options => options.fail({},300)
connection.onmessage({data:JSON.stringify({...frame,value:7.6,history:[{time:at,value:7.6}],watchfaceSync:true})})
while(timers.length) timers.shift()()
assert.equal(terminated,1,'failed export must not claim success and exit')
console.log('watch interconnect: object payload, timestamps, ACK, cache retention and no glucose polling passed')
