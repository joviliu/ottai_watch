from pathlib import Path
from lupa import LuaRuntime
import json
import subprocess

root=Path(__file__).resolve().parent
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().FRAME=lua.execute((root/'src/frame.lua').read_text())
lua.execute('''
widgets={}; subscriptions={}; now=1792972800; payload=nil; SCRIPT_PATH='/lua'
os.time=function()return now end
io.open=function(path,mode)
 if payload and path:match('face%-0.txt$') then return {read=function()return payload end,close=function()end} end
 return nil
end
local function object(props)
 local obj={props=props,events={}}
 function obj:set(values)for k,v in pairs(values)do self.props[k]=v end end
 function obj:add_flag(flag)end
 function obj:clear_flag(flag)end
 function obj:onevent(event,fn)self.events[event]=fn end
 function obj:Image(values)return object(values)end
 widgets[#widgets+1]=obj;return obj
end
package.preload['frame']=function()return FRAME end
package.preload['lvgl']=function()return {
 HOR_RES=function()return 432 end,VER_RES=function()return 514 end,OPA=function(v)return v end,
 Font=function(name,size)return name..size end,FLAG={SCROLLABLE=1,EVENT_BUBBLE=2},
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
assert '--' in text_values() and 'WAITING' in text_values()
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
assert '6.8' in text_values()
lua.globals().ScreenStateChangedCB('ON','OFF',0)
assert lua.globals().timer['paused']
lua.globals().now=1792973100
lua.globals().payload=frame(6.6,'↘',1792973100000)
lua.globals().ScreenStateChangedCB('OFF','ON',0)
assert not lua.globals().timer['paused'] and '6.6' in text_values()
lua.globals().payload='partial'
lua.globals().timer['cb']()
assert '6.6' in text_values()
lua.globals().now=1792973800
lua.globals().timer['cb']()
assert any(v and v.endswith('OLD') for v in text_values())
lua.globals().pageOnPause();assert lua.globals().timer['paused']
lua.globals().pageOnResume();assert not lua.globals().timer['paused']
print('Lua UI checks: metrics, new-file updates, cache, stale marker and screen-off timer pause passed')
