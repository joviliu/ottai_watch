// Two checked slots keep the previous reading readable while a file is being written.
const TRENDS = {'?':'unknown','↑':'up','↗':'up_right','→':'flat','↘':'down_right','↓':'down','⇈':'up_fast','⇊':'down_fast','↟':'up_fast','↡':'down_fast'}
function checksum(text) {
  let a = 1, b = 0
  for (let i = 0; i < text.length; i++) { a = (a + text.charCodeAt(i)) % 65521; b = (b + a) % 65521 }
  return b * 65536 + a
}
function encode(frame) {
  const trend = TRENDS[frame.trend] || (frame.trend === '↑↑' ? 'up_fast' : frame.trend === '↓↓' ? 'down_fast' : 'unknown')
  const body = 'OTT1|' + frame.sourceAt + '|' + frame.value.toFixed(1) + '|' + trend
  return body + '|' + checksum(body) + '\n'
}
function key(frame) { return frame.sourceAt + '|' + frame.value + '|' + frame.trend }
function publisher(file, done, fail) {
  let active = null, pending = null, exported = null
  function pump() {
    if (active || !pending) return
    const entry = {frame:pending}; active = entry; pending = null
    const slot = Math.floor(entry.frame.sourceAt / 300000) % 2
    file.writeText({uri:'internal://files/ottai-face-' + slot + '.txt',text:encode(entry.frame),
      success:() => {
        exported = key(entry.frame); active = null
        if (pending && key(pending) !== exported) { pump(); return }
        const latest = pending || entry.frame; pending = null; done(latest)
      },fail:(data,code) => { active = null; fail(code); pump() }})
  }
  return (frame) => {
    if (active && key(active.frame) === key(frame) && !pending) {
      if (frame.watchfaceSync) active.frame = frame
      return
    }
    if (!active && key(frame) === exported) { done(frame); return }
    pending = frame; pump()
  }
}
module.exports = {encode,checksum,key,publisher}
