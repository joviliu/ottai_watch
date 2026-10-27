from pathlib import Path
from lupa import LuaRuntime
import json
import subprocess
from datetime import datetime, timedelta
from build import clock_palette_source, CLOCK_PALETTES

root=Path(__file__).resolve().parent
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().LAYOUT=lua.table_from(json.loads((root/'layout.json').read_text()),recursive=True)
lua.globals().FRAME=lua.execute((root/'src/frame.lua').read_text())
lua.globals().CLOCK_PALETTES=lua.execute(clock_palette_source())
mock_lua='''
widgets={}; subscriptions={}; now=1792972800; payload=nil; SCRIPT_PATH='/lua'
os.time=function()return now end
io.open=function(path,mode)
 if payload and path:match('face%-0.txt$') then return {read=function()return payload end,close=function()end} end
 return nil
end
local function object(props)
 local obj={props=props,events={},flags={},updates=0}
 function obj:set(values)self.updates=self.updates+1;for k,v in pairs(values)do self.props[k]=v end end
 function obj:add_flag(flag)self.flags[flag]=true end
 function obj:clear_flag(flag)self.flags[flag]=nil end
 function obj:onevent(event,fn)self.events[event]=fn end
 function obj:Image(values)return object(values)end
 widgets[#widgets+1]=obj;return obj
end
package.preload['frame']=function()return FRAME end
package.preload['layout']=function()return LAYOUT end
package.preload['clock-palettes']=function()return CLOCK_PALETTES end
package.preload['lvgl']=function()return {
 HOR_RES=function()return 432 end,VER_RES=function()return 514 end,OPA=function(v)return v end,
 Font=function(name,size)return name..size end,FLAG={SCROLLABLE=1,EVENT_BUBBLE=2,HIDDEN=4},
 EVENT={SCREEN_LOADED='load',SCREEN_UNLOADED='unload',DELETE='delete'},
 Object=function(parent,values)return object(values)end,Label=function(parent,values)return object(values)end,
 Timer=function(values)
  timer=values;timer.paused=false;timer.deleted=false
  function timer:pause()self.paused=true end
  function timer:resume()self.paused=false end
  function timer:delete()self.deleted=true end
  return timer
 end}end
package.preload['dataman']=function()return {subscribe=function(name,obj,fn)
 subscriptions[name]=function(value)fn(obj,value)end
end}end
'''
lua.execute(mock_lua)
lua.execute((root/'src/main.lua').read_text())
def text_values(): return [w['props']['text'] for w in lua.globals().widgets.values() if w['props']['text'] is not None]
def value_widgets():
    return [w for w in lua.globals().widgets.values() if '/value-' in (w['props']['src'] or '') and not w['flags'][4]]
def value_text():
    chars=[w['props']['src'].split('-')[-1].removesuffix('.png') for w in value_widgets()]
    return ''.join('.' if c=='dot' else '-' if c=='dash' else c for c in chars)
def centered_value():
    parts=value_widgets()
    assert abs(min(w['props']['x'] for w in parts)+max(w['props']['x']+w['props']['w'] for w in parts)-432)<=1
assert value_text()=='--' and '--:--' in text_values()
centered_value()
assert lua.globals().timer['period']==15000
lua.globals().subscriptions['systemStatusBattery'](82*256)
lua.globals().subscriptions['healthHeartRate'](72*256)
assert '82%' in text_values() and '72' in text_values()
def frame(value,trend,at):
    data={'value':value,'trend':trend,'sourceAt':at}
    script='process.stdout.write(require("./watch/src/common/face-export").encode('+json.dumps(data)+'))'
    return subprocess.check_output(['node','-e',script],cwd=root.parent,text=True)
lua.globals().payload=frame(6.8,'↗',1792972800000)
lua.globals().timer['cb']()
assert value_text()=='6.8'
centered_value()
lua.globals().payload=frame(12.5,'↗',1792972800000)
lua.globals().timer['cb']()
assert value_text()=='12.5'
centered_value()
lua.globals().ScreenStateChangedCB('ON','OFF',0)
assert lua.globals().timer['paused']
lua.globals().now=1792973100
lua.globals().payload=frame(6.6,'↘',1792973100000)
lua.globals().ScreenStateChangedCB('OFF','ON',0)
assert not lua.globals().timer['paused'] and value_text()=='6.6'
centered_value()
lua.globals().payload='partial'
lua.globals().timer['cb']()
assert value_text()=='6.6'
lua.globals().now=1792973800
lua.globals().timer['cb']()
assert any(v and v.endswith('OLD') for v in text_values())
assert all('-old-' in w['props']['src'] for w in value_widgets())
for value,band in [(3.8,'alert'),(3.9,'normal'),(7.8,'normal'),(7.9,'high'),(12.0,'high'),(12.1,'alert'),(6.8,'normal')]:
    lua.globals().payload=frame(value,'→',lua.globals().now*1000)
    lua.globals().timer['cb']()
    assert value_text()==f'{value:.1f}'
    assert all(f'/value-{band}-fresh-' in w['props']['src'] for w in value_widgets())
    assert any(f'/trend-{band}-fresh-flat.png' in (w['props']['src'] or '') for w in lua.globals().widgets.values())
    centered_value()
lua.globals().now+=601
lua.globals().timer['cb']()
assert all('/value-normal-old-' in w['props']['src'] for w in value_widgets())
lua.globals().pageOnPause();assert lua.globals().timer['paused']
lua.globals().pageOnResume();assert not lua.globals().timer['paused']
def clock_widgets():
    return [w for w in lua.globals().widgets.values() if '/clock-' in (w['props']['src'] or '')]
def clock_at(hour,minute,day=datetime(2026,10,27)):
    lua.globals().now=int(day.replace(hour=hour,minute=minute).timestamp())
    lua.globals().timer['cb']()
def assert_clock(palette,text):
    parts=clock_widgets()
    assert len(parts)==4
    for i,w in enumerate(parts):
        assert w['props']['src']==f'/lua/clock-{palette}-{"hour" if i<2 else "minute"}-{text[i]}.png'
def palette_name():
    return clock_widgets()[0]['props']['src'].split('/clock-')[1].split('-hour-')[0]
for hour,minute in [(5,59),(6,0),(13,59),(14,0),(21,59),(22,0),(23,59),(0,0)]:
    clock_at(hour,minute);palette=palette_name()
    assert palette in {p['name'] for p in CLOCK_PALETTES}
    assert_clock(palette,f'{hour:02d}{minute:02d}')
    updates=[w['updates'] for w in clock_widgets()]
    lua.globals().timer['cb']()
    assert [w['updates'] for w in clock_widgets()]==updates,'unchanged minute must not rewrite clock images'
for before,after in [(5,6),(13,14),(21,22)]:
    clock_at(before,59);previous=palette_name()
    clock_at(after,0);assert palette_name()!=previous,'adjacent slots must select from disjoint palette groups'
clock_at(22,0);night=palette_name()
clock_at(0,0,datetime(2026,10,28));assert palette_name()==night,'midnight must not start a new slot'
clock_at(5,59,datetime(2026,10,28));assert palette_name()==night
for evening,morning in [(datetime(2026,12,31),datetime(2027,1,1)),
                         (datetime(2028,2,29),datetime(2028,3,1)),
                         (datetime(2026,10,31),datetime(2026,11,1))]:
    clock_at(22,0,evening);night=palette_name()
    clock_at(1,30,morning.replace(fold=0));assert palette_name()==night
    clock_at(1,30,morning.replace(fold=1));assert palette_name()==night
    clock_at(5,59,morning);assert palette_name()==night
    clock_at(6,0,morning);assert palette_name()!=night
chosen={}
for offset in range(14):
    day=datetime(2026,10,27)+timedelta(days=offset)
    for hour in [6,14,22]:
        clock_at(hour,0,day);chosen[(offset,hour)]=palette_name()
for (offset,hour),palette in reversed(list(chosen.items())):
    clock_at(hour,0,datetime(2026,10,27)+timedelta(days=offset));assert palette_name()==palette,'selection must depend on the local slot, not visit order'
assert len(set(chosen.values()))>2,'slot selection must vary beyond a fixed alternating pair'
reload_time=int(datetime(2026,10,29,15,0).timestamp())
lua.globals().now=reload_time;lua.globals().timer['cb']();expected=palette_name()
reloaded=LuaRuntime(unpack_returned_tuples=True)
reloaded.globals().LAYOUT=reloaded.table_from(json.loads((root/'layout.json').read_text()),recursive=True)
reloaded.globals().FRAME=reloaded.execute((root/'src/frame.lua').read_text())
reloaded.globals().CLOCK_PALETTES=reloaded.execute(clock_palette_source())
reloaded.execute(mock_lua);reloaded.globals().now=reload_time
reloaded.execute((root/'src/main.lua').read_text())
new_clocks=[w for w in reloaded.globals().widgets.values() if '/clock-' in (w['props']['src'] or '')]
assert len(new_clocks)==4 and all(f'/clock-{expected}-' in w['props']['src'] for w in new_clocks),'reloading the face in the same slot must preserve its palette'
clock_at(13,59);previous=palette_name()
lua.globals().ScreenStateChangedCB('ON','OFF',0)
assert lua.globals().timer['paused']
lua.globals().now=int(datetime(2026,10,27,14,0).timestamp())
lua.globals().timer['cb']();assert_clock(previous,'1359')
lua.globals().ScreenStateChangedCB('OFF','ON',0)
assert not lua.globals().timer['paused'];assert palette_name()!=previous
assert_clock(palette_name(),'1400')
assert all('/value-normal-old-' in w['props']['src'] for w in value_widgets())
assert any(v and v.endswith('OLD') for v in text_values())
assert lua.globals().timer['period']==15000
print('Lua UI checks: metrics, new-file updates, cache, stale marker and screen-off timer pause passed')
print('Clock palette checks: stable 06/14/22 slots, paired selection, no adjacent repeat, midnight, cache and screen-off/resume passed')
