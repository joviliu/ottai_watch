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
const gap = {...frame,history:[{time:now-900000,value:5.7},{time:now,value:5.6}]}
assert.equal(model.chart(gap).count,1,'do not connect across missing data')
console.log('watch model: validation, history and gap checks passed')
