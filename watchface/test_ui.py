from pathlib import Path
from lupa import LuaRuntime
import json
import subprocess

root=Path(__file__).resolve().parent
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().LAYOUT=lua.table_from(json.loads((root/'layout.json').read_text()),recursive=True)
lua.globals().FRAME=lua.execute((root/'src/frame.lua').read_text())
lua.execute('''
widgets={}; subscriptions={}; now=1792972800; payload=nil; SCRIPT_PATH='/lua'
os.time=function()return now end
io.open=function(path,mode)
 if payload and path:match('face%-0.txt$') then return {read=function()return payload end,close=function()end} end
 return nil
end
local function object(props)
 local obj={props=props,events={},flags={}}
 function obj:set(values)for k,v in pairs(values)do self.props[k]=v end end
 function obj:add_flag(flag)self.flags[flag]=true end
 function obj:clear_flag(flag)self.flags[flag]=nil end
 function obj:onevent(event,fn)self.events[event]=fn end
 function obj:Image(values)return object(values)end
 widgets[#widgets+1]=obj;return obj
end
package.preload['frame']=function()return FRAME end
package.preload['layout']=function()return LAYOUT end
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
''')
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
print('Lua UI checks: metrics, new-file updates, cache, stale marker and screen-off timer pause passed')
