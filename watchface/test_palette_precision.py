"""Run the actual selector in desktop and optional reduced-precision Lua VMs."""
import argparse
import subprocess
from datetime import date, timedelta
from pathlib import Path

from lupa import LuaRuntime
from build import load_palettes, clock_palette_source
from vendor import facebin

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--lua', action='append', default=[], help='Additional Lua CLI to compare with desktop Lua')
args = parser.parse_args()

source = (Path(__file__).parent / 'src/main.lua').read_text()
selector = source[source.index('local function clockPalette(now)'):source.index('\nlocal root=')]
baseline = dict(facebin.unpack_face((Path(__file__).parent.parent / 'releases/0.1.18/ottai-signal-watch6-0.1.18.bin').read_bytes())['files'])['lua/main.lua'].decode()
assert selector==baseline[baseline.index('local function clockPalette(now)'):baseline.index('\nlocal root=')], 'palette selector source must remain unchanged'
cases = []
for start in [date(2026, 10, 26), date(2027, 12, 15), date(2028, 2, 15)]:
    for offset in range(64):
        day = start + timedelta(days=offset)
        previous = day - timedelta(days=1)
        for hour in [0, 3, 4, 11, 15, 19]:
            cases.append((day.year, day.timetuple().tm_yday, previous.year,
                          previous.timetuple().tm_yday, hour))
rows = ',\n'.join('{' + ','.join(map(str, row)) + '}' for row in cases)
# Stub civil-date fields to isolate arithmetic; timestamp/DST behavior is in test_ui.py.
selector_cases = selector + '''
local result={}
for _,row in ipairs({''' + rows + '''}) do
    os.date=function(format, timestamp)
        if format=='%H' then return tostring(row[5]) end
        assert(format=='%Y' or format=='%j', 'unexpected calendar field')
        local year=timestamp==0 and row[3] or row[1]
        local yday=timestamp==0 and row[4] or row[2]
        return tostring(format=='%Y' and year or yday)
    end
    result[#result+1]=clockPalette(43200)
end
return table.concat(result,string.char(10))
'''
selected_indices = None
for variant in ['ultra', 'signal', 'meridian']:
    palettes = load_palettes(variant)
    program = 'local clockPalettes=(function() ' + clock_palette_source(palettes) + ' end)()\n' + selector_cases
    expected = LuaRuntime().execute(program).splitlines()
    assert len(expected) == len(cases)
    index_by_name = {p['name']:i for i,p in enumerate(palettes)}
    indices = [index_by_name[name] for name in expected]
    if selected_indices is None:
        selected_indices = indices
    assert indices == selected_indices, f'{variant}: variants must use the same selector with their own palette names'
    for block in range(3):
        daily = [expected[i:i+6] for i in range(block*384, (block+1)*384, 6)]
        for phase in range(2, 6):
            assert len({row[phase] for row in daily}) >= 12, (variant, 'same local phase must vary across days')
        assert {name for row in daily for name in row[2:]} == {p['name'] for p in palettes}
        assert all(row[0] == row[1] for row in daily), 'overnight slot must remain stable'
        assert all(row[i] != row[i+1] for row in daily for i in (1, 2, 3, 4)), 'adjacent slots must differ'
        assert all(a[-1] == b[0] for a, b in zip(daily, daily[1:])), 'midnight must preserve the prior evening'
        profiles = [tuple(row[2:]) for row in daily]
        assert all(any(a != b for a, b in zip(profiles, profiles[period:])) for period in range(1, 15)), 'short repeating daily schedule'

    for runtime in args.lua:
        run = subprocess.run([runtime, '-'], input='io.write((function()\n' + program + '\nend)())',
                             capture_output=True, text=True, check=True)
        actual = run.stdout.splitlines()
        assert actual == expected, f'{variant}, {runtime}: reduced-precision selector differs from desktop Lua'
    print(f'{variant}: {len(cases)} civil-date cases, per-phase diversity, 32 pairs, no short daily cycle; {len(args.lua)} additional Lua VMs agree')
