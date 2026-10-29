const assert = require('node:assert/strict')
const model = require('../src/common/model')
const now = 1792980000000
const frame = {type:'glucose',version:1,value:5.6,unit:'mmol/L',trend:'→',sourceAt:now,history:[{time:now-300000,value:5.7},{time:now,value:5.6}]}
assert.equal(model.parseFrame(JSON.stringify(frame),now).value,5.6)
for (const patch of [{value:0},{value:null},{unit:'mg/dL'},{sourceAt:now+120000},{trend:'garbled'},{version:2},{history:[{time:now,value:9}]}]) {
  assert.throws(() => model.parseFrame(JSON.stringify({...frame,...patch}),now))
}
assert.throws(() => model.parseFrame(JSON.stringify({...frame,history:[frame.history[1],frame.history[0]]}),now))
assert.equal(model.parseFrame(JSON.stringify(frame),now+3600000).sourceAt,now,'old source time stays old')
assert.deepEqual(model.chart(frame).data[0].data,[57,56])
const chart = model.chart(frame)
assert.equal(chart.data.length,1,'reference rules are overlays, not chart series with point markers')
assert.deepEqual(chart.references,{lowerY:48,upperY:5})
assert.equal(chart.options.yAxis.min,34)
assert.equal(chart.options.yAxis.max,83)
for (const value of [2.1,15.0,60.0]) {
  const extreme = model.chart({...frame,history:[{time:now-300000,value},{time:now,value}]})
  assert.ok(extreme.options.yAxis.min < Math.min(39,value*10))
  assert.ok(extreme.options.yAxis.max > Math.max(78,value*10))
  assert.equal(extreme.data.length,1)
  assert.ok(0<=extreme.references.upperY && extreme.references.upperY<extreme.references.lowerY && extreme.references.lowerY<=53)
}
const gap = {...frame,history:[{time:now-900000,value:5.7},{time:now,value:5.6}]}
assert.equal(model.chart(gap).count,1,'do not connect across missing data')
console.log('watch model: validation, history and gap checks passed')
