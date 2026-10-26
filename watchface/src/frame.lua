local M = {}
local trends = {unknown=true,up=true,up_right=true,flat=true,down_right=true,down=true,up_fast=true,down_fast=true}
local function checksum(text)
    local a, b = 1, 0
    for i=1,#text do a=(a+text:byte(i))%65521; b=(b+a)%65521 end
    return b*65536+a
end
function M.parse(text, now)
    if type(text)~='string' or #text>128 then return nil end
    local at,value,trend,sum=text:match('^OTT1|(%d+)|(%d+%.%d)|([a-z_]+)|(%d+)\n$')
    if not at or not trends[trend] then return nil end
    local body='OTT1|'..at..'|'..value..'|'..trend
    at,value,sum=tonumber(at),tonumber(value),tonumber(sum)
    if sum~=checksum(body) or value<=0 or value>60 or at<=0 or at>now+90000 then return nil end
    return {sourceAt=at,value=value,trend=trend}
end
function M.latest(reader, now, previous)
    local best=previous
    for _,dir in ipairs({'/data/quickapp/files/com.example.glucosewatch6/', '/data/quickapp/file/com.example.glucosewatch6/', '/data/files/com.example.glucosewatch6/'}) do
        for slot=0,1 do
            local text=reader(dir..'ottai-face-'..slot..'.txt')
            local frame=M.parse(text,now)
            if frame and (not best or frame.sourceAt>=best.sourceAt) then best=frame end
        end
    end
    return best
end
return M
