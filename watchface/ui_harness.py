from pathlib import Path
from lupa import LuaRuntime
from build import clock_palette_source

mock_lua='''
widgets={}; subscriptions={}; now=1792972800; payload=nil; SCRIPT_PATH='/lua'
os.time=function()return now end
io.open=function(path,mode)
 if payload and path:match('face%-0.txt$') then return {read=function()return payload end,close=function()end} end
 return nil
end
local function object(props)
 local obj={props=props,events={},flags={},updates=0}
 function obj:set(values)
  if values.img_recolor then error('Watch 6 image recolor is unavailable') end
  self.updates=self.updates+1;for k,v in pairs(values)do self.props[k]=v end
 end
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

def create_ui(layout, timestamp=None):
    root=Path(__file__).resolve().parent
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.globals().LAYOUT=lua.table_from(layout,recursive=True)
    lua.globals().FRAME=lua.execute((root/"src/frame.lua").read_text())
    lua.globals().CLOCK_PALETTES=lua.execute(clock_palette_source())
    lua.execute(mock_lua)
    if timestamp is not None:lua.globals().now=timestamp
    lua.execute((root/"src/main.lua").read_text())
    return lua
