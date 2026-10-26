local lvgl=require('lvgl')
local dataman=require('dataman')
local frameModel=require('frame')
local layout=require('layout')
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
for i,x in ipairs(layout.clockX) do
    digits[i]=image('clock-'..(i<=2 and 'hour-' or 'minute-')..'0',x,layout.clockY,layout.clockW,layout.clockH)
end
local glucose={}
for i=1,4 do glucose[i]=image('value-normal-fresh-dash',0,layout.valueY,40,56) end
local function showValue(text,stale,band)
    local width=0
    for i=1,#text do width=width+(text:sub(i,i)=='.' and 12 or 40) end
    local x=math.floor((432-width-4*(#text-1))/2)
    for i,obj in ipairs(glucose) do
        if i<=#text then
            local char=text:sub(i,i)
            local name=char=='.' and 'dot' or char=='-' and 'dash' or char
            local w=char=='.' and 12 or 40
            obj:clear_flag(lvgl.FLAG.HIDDEN)
            obj:set{src=SCRIPT_PATH..'/value-'..band..'-'..(stale and 'old-' or 'fresh-')..name..'.png',x=x,w=w}
            x=x+w+4
        else obj:add_flag(lvgl.FLAG.HIDDEN) end
    end
end
showValue('--',false,'normal')
local trend=image('trend-normal-fresh-unknown',341,layout.trendY,54,54)
local source=label('--:--',14,layout.sourceY,100,68,28,0xe9f2f8)
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
        for i=1,4 do digits[i]:set{src=SCRIPT_PATH..'/clock-'..(i<=2 and 'hour-' or 'minute-')..clock:sub(i,i)..'.png'} end
        lastClock=clock
    end
    local day=os.date('%a %d %b',now):upper()
    if day~=lastDate then date:set{text=day};lastDate=day end
    current=frameModel.latest(read,now*1000,current)
    if current then
        local stale=now*1000-current.sourceAt>=600000
        local value=string.format('%.1f',current.value)
        local shown=tonumber(value)
        local band
        if shown>=3.9 and shown<=7.8 then band='normal'
        elseif shown>7.8 and shown<=12.0 then band='high'
        else band='alert' end
        local valueKey=value..tostring(stale)
        if valueKey~=lastValue then showValue(value,stale,band);lastValue=valueKey end
        local trendKey=band..'-'..(stale and 'old-' or 'fresh-')..current.trend
        if trendKey~=lastTrend then trend:set{src=SCRIPT_PATH..'/trend-'..trendKey..'.png'};lastTrend=trendKey end
        local stamp=os.date('%H:%M',math.floor(current.sourceAt/1000))..(stale and '\nOLD' or '')
        if stamp~=lastSource then
            source:set{text=stamp,text_color=stale and 0xffbc73 or 0xe9f2f8}
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
