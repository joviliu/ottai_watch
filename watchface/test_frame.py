"""Cross-check the real JS export with the Lua reader, including partial/stale files."""
import json
import subprocess
from pathlib import Path
from lupa import LuaRuntime

root=Path(__file__).resolve().parent
lua=LuaRuntime(unpack_returned_tuples=True)
model=lua.execute((root/'src/frame.lua').read_text())
at=1792972800000
frame={'sourceAt':at,'value':6.8,'trend':'↗'}
script='process.stdout.write(require("./watch/src/common/face-export").encode('+json.dumps(frame)+'))'
encoded=subprocess.check_output(['node','-e',script],cwd=root.parent,text=True)
parsed=model.parse(encoded,at)
assert parsed['value']==6.8 and parsed['trend']=='up_right' and parsed['sourceAt']==at
for invalid in [encoded[:-2],encoded.replace('6.8','0.0'),encoded.replace('up_right','unknown'),encoded+'junk']:
    assert model.parse(invalid,at) is None
assert model.parse(encoded,at-90001) is None
assert model.parse(encoded,at+86400000)['sourceAt']==at  # stale values retain their real time
lua.globals().payload=encoded
lua.execute('reads=0; function read(path) reads=reads+1; if path:match("face%-1") then return payload else return payload:sub(1,20) end end')
latest=model.latest(lua.globals().read,at,None)
assert latest['sourceAt']==at
assert lua.globals().reads==6
assert model.latest(lambda _:None,at,latest)['sourceAt']==at
lua.execute((root/'src/main.lua').read_text().replace("local lvgl=require('lvgl')", "return function()\nlocal lvgl=require('lvgl')")+'\nend')
print('Lua frame checks: JS compatibility, checksum, partial files, future/stale timestamps and cache passed')
