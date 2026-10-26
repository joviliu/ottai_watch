local lvgl=require('lvgl')
local dataman=require('dataman')
local frameModel=require('frame')
local root=lvgl.Object(nil,{w=lvgl.HOR_RES(),h=lvgl.VER_RES(),bg_color=0,bg_opa=lvgl.OPA(100),border_width=0,pad_all=0})
root:clear_flag(lvgl.FLAG.SCROLLABLE)
root:add_flag(lvgl.FLAG.EVENT_BUBBLE)
local function image(name,x,y,w,h)
    local obj=root:Image{src=SCRIPT_PATH..'/'..name..'.png'}
    obj:set{x=x,y=y,w=w,h=h}
    obj:add_flag(lvgl.FLAG.EVENT_BUBBLE)
    return obj
end
local function label(text,x,y,w,h,size,color)
    local obj=lvgl.Label(root,{text=text,x=x,y=y,w=w,h=h,text_font=lvgl.Font('MiSans-Regular',size),text_color=color,text_align=2})
    obj:add_flag(lvgl.FLAG.EVENT_BUBBLE)
    return obj
end
local date=label('',30,16,372,36,24,0xb9c2c8)
local digits={}
for i,x in ipairs({14,110,234,330}) do digits[i]=image('clock-0',x,65,88,234) end
image('colon',204,65,24,234)
local glucose=label('--',50,330,238,88,76,0xff9e32)
local trend=image('trend-unknown',268,346,54,54)
local source=label('WAITING',48,418,336,30,20,0x8b9ba4)
image('battery',60,466,34,24)
local battery=label('--%',100,459,96,40,28,0xc4d0d8)
local heartIcon=image('heart',230,464,30,28)
local heart=label('--',265,459,106,40,28,0xc4d0d8)
local current,visible,screenOn=nil,true,true
local lastClock,lastSource,lastValue,lastTrend,lastDate
local function read(path)
    local f=io.open(path,'rb')
    if not f then return nil end
    local text=f:read(129);f:close();return text
end
local function render()
    if not visible or not screenOn then return end
    local now=os.time()
    local clock=os.date('%H%M',now)
    if clock~=lastClock then
        for i=1,4 do digits[i]:set{src=SCRIPT_PATH..'/clock-'..clock:sub(i,i)..'.png'} end
        lastClock=clock
    end
    local day=os.date('%a %d %b',now):upper()
    if day~=lastDate then date:set{text=day};lastDate=day end
    current=frameModel.latest(read,now*1000,current)
    if current then
        local value=string.format('%.1f',current.value)
        if value~=lastValue then glucose:set{text=value};lastValue=value end
        if current.trend~=lastTrend then trend:set{src=SCRIPT_PATH..'/trend-'..current.trend..'.png'};lastTrend=current.trend end
        local stale=now*1000-current.sourceAt>=600000
        local stamp=os.date('%H:%M',math.floor(current.sourceAt/1000))..(stale and '  OLD' or '')
        if stamp~=lastSource then
            source:set{text=stamp,text_color=stale and 0xffbc73 or 0x8b9ba4}
            glucose:set{text_color=stale and 0xb99d7e or 0xff9e32}
            lastSource=stamp
        end
    end
end
local function subscribe(name,obj,callback)
    pcall(function() dataman.subscribe(name,obj,function(o,value) callback(math.floor(value/256)) end) end)
end
subscribe('systemStatusBattery',battery,function(value) if value>=0 and value<=100 then battery:set{text=value..'%'} end end)
subscribe('healthHeartRate',heart,function(value) if value>0 and value<260 then heart:set{text=tostring(value)} end end)
-- A small file check while the face is visible; no radio/sensor polling and no screen-off timer.
local timer=lvgl.Timer{period=15000,repeat_count=-1,cb=render}
local function visibility()
    if visible and screenOn then timer:resume();render() else timer:pause() end
end
function ScreenStateChangedCB(pre,now,reason) screenOn=now=='ON';visibility() end
function pageOnPause() visible=false;visibility() end
function pageOnResume() visible=true;visibility() end
if lvgl.EVENT.SCREEN_LOADED then root:onevent(lvgl.EVENT.SCREEN_LOADED,function()visible=true;visibility()end) end
if lvgl.EVENT.SCREEN_UNLOADED then root:onevent(lvgl.EVENT.SCREEN_UNLOADED,function()visible=false;visibility()end) end
if lvgl.EVENT.DELETE then root:onevent(lvgl.EVENT.DELETE,function()timer:delete()end) end
render()
