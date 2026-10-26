const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const model=require('../src/common/model'),faceExport=require('../src/common/face-export')
const script=fs.readFileSync(path.join(__dirname,'../src/pages/index/index.ux'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'').replace('export default','module.exports =')
function setup() {
  const writes=[],sent=[],timeouts=new Map();let id=0,exits=0
  const connection={send:options=>sent.push(options.data)}
  const sandbox={module:{exports:{}},model,faceExport,interconnect:{instance:()=>connection},file:{writeText:options=>writes.push(options)},
    storage:{get:options=>options.success(''),set:()=>{}},app:{terminate:()=>exits++},Date,
    setTimeout:(fn,ms)=>{timeouts.set(++id,{fn,ms});return id},clearTimeout:id=>timeouts.delete(id),setInterval:()=>++id,clearInterval:()=>{}}
  vm.runInNewContext(script,sandbox)
  const page=sandbox.module.exports;Object.assign(page,page.private);page.onInit();page.onShow()
  return {writes,sent,page,get exits(){return exits},send:frame=>connection.onmessage({data:JSON.stringify(frame)}),
    flush:()=>{while(timeouts.size){const [key,value]=[...timeouts.entries()].sort((a,b)=>a[1].ms-b[1].ms)[0];timeouts.delete(key);value.fn()}}}
}
const at=Date.now()-600000
function frame(time,value,watchfaceSync=false) {return {type:'glucose',version:1,sourceAt:time,value,unit:'mmol/L',trend:'↗',history:[{time,value}],watchfaceSync}}
let run=setup()
run.send(frame(at,6.8,true));run.send(frame(at+300000,6.6))
run.writes[0].success();assert.equal(run.writes.length,2)
run.writes[1].success();run.flush()
assert.equal(run.exits,1,'a newer ordinary frame must retain the automatic session return intent')
assert.deepEqual(run.sent.filter(x=>x.type==='face_export').map(x=>x.frameKey),[faceExport.key(frame(at+300000,6.6))])
run=setup();run.send(frame(at,6.8,true));run.writes[0].success()
run.send(frame(at+300000,6.6));run.writes[1].fail({},300);run.flush()
assert.equal(run.exits,0,'new data must cancel an old queued exit, including when its export fails')
run=setup();run.send(frame(at,6.8));run.writes[0].success();run.flush()
assert.equal(run.exits,0,'manual viewing stays open')
console.log('sync return: pending corrections, delayed exits, write failures and manual viewing passed')
