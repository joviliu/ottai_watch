function finite(value) { return typeof value === 'number' && isFinite(value) }
function validValue(value) { return finite(value) && value > 0 && value <= 60 }
function parseFrame(raw, now) {
  if (typeof raw !== 'string' || raw.length > 16384) throw new Error('Invalid packet')
  var f = JSON.parse(raw)
  if (f.type !== 'glucose' || f.version !== 1 || f.unit !== 'mmol/L' || !validValue(f.value) ||
      !finite(f.sourceAt) || f.sourceAt <= 0 || f.sourceAt > now + 90000 ||
      typeof f.trend !== 'string' || !/^(\?|[↑↗→↘↓⇈⇊↟↡]{1,2})$/.test(f.trend) ||
      !Array.isArray(f.history) || f.history.length < 1 || f.history.length > 24) throw new Error('Invalid frame')
  var previous = 0
  f.history.forEach(function (point) {
    if (!finite(point.time) || point.time <= previous || point.time > f.sourceAt || !validValue(point.value)) throw new Error('Invalid history')
    previous = point.time
  })
  var last = f.history[f.history.length - 1]
  if (last.time !== f.sourceAt || Math.abs(last.value - f.value) > 0.001) throw new Error('History mismatch')
  return f
}
function clock(at) {
  var date = new Date(at)
  return ('0' + date.getHours()).slice(-2) + ':' + ('0' + date.getMinutes()).slice(-2)
}
function chart(frame) {
  var samples = frame.history.slice()
  for (var i = samples.length - 1; i > 0; i--) {
    if (samples[i].time - samples[i - 1].time > 600000) { samples = samples.slice(i); break }
  }
  var values = samples.map(function (s) { return Math.round(s.value * 10) })
  var lo = Math.max(0, Math.min.apply(null, [39].concat(values)) - 5)
  var hi = Math.max.apply(null, [78].concat(values)) + 5
  return {
    options: {xAxis:{min:0,max:Math.max(1,values.length - 1),display:false,axisTick:2},yAxis:{min:lo,max:hi,display:false,axisTick:2},series:{lineStyle:{width:'2px'}}},
    data:[{strokeColor:'#70dfc3',data:values}], count:values.length,
    references:{lowerY:Math.round((hi-39)*53/(hi-lo)),upperY:Math.round((hi-78)*53/(hi-lo))},
    range:(lo / 10).toFixed(1) + ' — ' + (hi / 10).toFixed(1) + ' · 基准 3.9 / 7.8',
    times:clock(samples[0].time) + ' — ' + clock(samples[samples.length - 1].time)
  }
}
module.exports = {parseFrame:parseFrame,clock:clock,chart:chart}
