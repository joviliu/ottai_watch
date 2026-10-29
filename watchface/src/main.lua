local lvgl=require('lvgl')
local dataman=require('dataman')
local frameModel=require('frame')
local layout=require('layout')
local clockPalettes=require('clock-palettes')
local function clockPalette(now)
    local hour=tonumber(os.date('%H',now))
    -- Civil-date anchor keeps the overnight slot stable across midnight and DST.
    local dayTime=hour<4 and now-43200 or now
    local year=tonumber(os.date('%Y',dayTime))-1
    local day=365*year+math.floor(year/4)-math.floor(year/100)+math.floor(year/400)+tonumber(os.date('%j',dayTime))-1
    local phase=hour<4 and 3 or hour<11 and 0 or hour<15 and 1 or hour<19 and 2 or 3
    local slot=day*4+phase
    -- Alternating disjoint groups avoid adjacent repeats without storing prior choices.
    local parity=slot%2
    local count=math.floor((#clockPalettes+1-parity)/2)
    local state=slot%2147483646+1
    for _=1,3 do state=(state*48271)%2147483647 end
    return clockPalettes[(state%count)*2+parity+1].name
end
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
local muted=0xb9c2c8
local function at(text,box,color) return label(text,box[1],box[2],box[3],box[4],box[5],color) end
local function icon(name,box) return image(name,box[1],box[2],box[3],box[4]) end
if layout.style~='dots' then image('background',0,0,432,514) end
local date=at('',layout.dateBox,muted)
local digits={}
local hourHand,minuteHand,hub
local function disc(size)
    local obj=lvgl.Object(root,{x=0,y=0,w=size,h=size,radius=size/2,bg_color=0,bg_opa=lvgl.OPA(100),border_width=0,pad_all=0})
    obj:clear_flag(lvgl.FLAG.SCROLLABLE);obj:add_flag(lvgl.FLAG.EVENT_BUBBLE)
    return obj
end
local function hand(length,width)
    local result={}
    local step=math.max(1,math.floor(width/3))
    for i=0,math.ceil((length+12)/step) do
        result[#result+1]={obj=disc(width),distance=-12+math.min(i*step,length+12),width=width}
    end
    return result
end
local function paintHand(nodes,index,count,color)
    local angle=index*2*math.pi/count
    local cx,cy=layout.dialBox[1]+layout.dialBox[3]/2,layout.dialBox[2]+layout.dialBox[4]/2
    for _,node in ipairs(nodes) do
        node.obj:set{x=math.floor(cx+math.sin(angle)*node.distance-node.width/2+.5),
                     y=math.floor(cy-math.cos(angle)*node.distance-node.width/2+.5),bg_color=color}
    end
end
if layout.style=='analog' then
    hourHand=hand(112,10);minuteHand=hand(174,6);hub=disc(12)
    hub:set{x=layout.dialBox[1]+layout.dialBox[3]/2-6,y=layout.dialBox[2]+layout.dialBox[4]/2-6}
else
    local initialPalette=clockPalette(os.time())
    for i,x in ipairs(layout.clockX) do
        digits[i]=image('clock-'..initialPalette..'-'..(i<=2 and 'hour-' or 'minute-')..'0',x,layout.clockY,layout.clockW,layout.clockH)
    end
end
local glucose={}
local glucoseLabel=layout.valueBox and at('--',layout.valueBox,0x87939c) or nil
if not glucoseLabel then
    for i=1,4 do glucose[i]=image('value-normal-fresh-dash',0,layout.valueY,layout.valueW,layout.valueH) end
end
local function showValue(text,stale,band)
    if glucoseLabel then
        glucoseLabel:set{text=text,text_color=stale and 0x87939c or 0xc4d0d8}
        return
    end
    local width=0
    for i=1,#text do width=width+(text:sub(i,i)=='.' and layout.valueDotW or layout.valueW) end
    local x=math.floor(layout.valueCenter-(width+4*(#text-1))/2)
    for i,obj in ipairs(glucose) do
        if i<=#text then
            local char=text:sub(i,i)
            local name=char=='.' and 'dot' or char=='-' and 'dash' or char
            local w=char=='.' and layout.valueDotW or layout.valueW
            obj:clear_flag(lvgl.FLAG.HIDDEN)
            obj:set{src=SCRIPT_PATH..'/value-'..band..'-'..(stale and 'old-' or 'fresh-')..name..'.png',x=x,w=w}
            x=x+w+4
        else obj:add_flag(lvgl.FLAG.HIDDEN) end
    end
end
showValue('--',layout.invalidColor~=nil,'normal')
local trendSize=layout.trendSize or 54
local trend=image('trend-normal-'..(layout.invalidColor and 'old-' or 'fresh-')..'unknown',layout.trendX,layout.trendY,trendSize,trendSize)
local source=not layout.hideSource and at('--:--',layout.sourceBox,muted) or nil
icon('battery',layout.batteryIcon)
local battery=at('--%',layout.batteryBox,0xc4d0d8)
local heart
if not layout.hideHeart then
    icon('heart',layout.heartIcon);heart=at('--',layout.heartBox,0xc4d0d8)
end
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
    local palette=clockPalette(now)
    local clockKey=palette..clock
    if clockKey~=lastClock then
        if layout.style=='analog' then
            local colors
            for _,pair in ipairs(clockPalettes) do if pair.name==palette then colors=pair;break end end
            local hour,minute=tonumber(clock:sub(1,2)),tonumber(clock:sub(3,4))
            paintHand(hourHand,(hour%12)*60+minute,720,colors.hour)
            paintHand(minuteHand,minute,60,colors.minute)
            hub:set{bg_color=colors.minute}
        else
            for i=1,4 do digits[i]:set{src=SCRIPT_PATH..'/clock-'..palette..'-'..(i<=2 and 'hour-' or 'minute-')..clock:sub(i,i)..'.png'} end
        end
        lastClock=clockKey
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
        if source and stamp~=lastSource then
            source:set{text=stamp,text_color=muted}
            lastSource=stamp
        end
    end
end
local function subscribe(name,obj,callback)
    pcall(function() dataman.subscribe(name,obj,function(o,value) callback(math.floor(value/256)) end) end)
end
subscribe('systemStatusBattery',battery,function(value) if value>=0 and value<=100 then battery:set{text=value..'%'} end end)
if heart then subscribe('healthHeartRate',heart,function(value) if value>0 and value<260 then heart:set{text=tostring(value)} end end) end
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
