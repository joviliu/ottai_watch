const assert = require('node:assert/strict')
const model = require('../src/common/face-export')
const frame = {sourceAt:1792972800000,value:6.8,trend:'↗'}
const text = model.encode(frame)
const fields = text.trim().split('|')
assert.deepEqual(fields.slice(0,4),['OTT1','1792972800000','6.8','up_right'])
assert.equal(Number(fields[4]),model.checksum(fields.slice(0,4).join('|')))
let success = 0, failure = 0
model.publisher({writeText:options => {
  assert.equal(options.uri,'internal://files/ottai-face-0.txt')
  assert.equal(options.text,text); options.success()
}},result => { assert.equal(result.sourceAt,frame.sourceAt); success++ },() => {failure++})(frame)
model.publisher({writeText:options => options.fail({},300)},() => {success++},code => {assert.equal(code,300); failure++})(frame)
assert.equal(success,1); assert.equal(failure,1)
const writes=[], completed=[]
const publish=model.publisher({writeText:options => writes.push(options)},result => completed.push(model.key(result)),() => {})
publish(frame)
const corrected={...frame,value:6.6,trend:'↘'}
publish(corrected)
assert.equal(writes.length,1,'file writes must serialize even for the same measurement time')
writes[0].success()
assert.equal(writes.length,2)
assert.equal(completed.length,0,'superseded write must not confirm or auto-exit before the correction')
writes[1].success()
assert.deepEqual(completed,[model.key(corrected)])
assert.equal(writes[1].text,model.encode(corrected))
console.log('watchface export: checksum, slot and write-result checks passed')
