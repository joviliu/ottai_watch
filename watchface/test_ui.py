from pathlib import Path
import json
import subprocess
from datetime import datetime, timedelta
from build import CLOCK_PALETTES, load_layout
from ui_harness import create_ui

root=Path(__file__).resolve().parent
lua=create_ui(load_layout())
def text_values(): return [w['props']['text'] for w in lua.globals().widgets.values() if w['props']['text'] is not None]
def value_widgets():
    return [w for w in lua.globals().widgets.values() if '/value-' in (w['props']['src'] or '') and not w['flags'][4]]
def native_value():
    box=lua.globals().LAYOUT['valueBox']
    if box:
        return next(w for w in lua.globals().widgets.values() if w['props']['x']==box[1] and w['props']['y']==box[2] and w['props']['text'] is not None)
def value_text():
    native=native_value()
    if native:return native['props']['text']
    chars=[w['props']['src'].split('-')[-1].removesuffix('.png') for w in value_widgets()]
    return ''.join('.' if c=='dot' else '-' if c=='dash' else c for c in chars)
def centered_value():
    native=native_value()
    if native:
        assert native['props']['text_align']==2 and native['props']['text_font']=='MiSans-Regular28'
        return
    parts=value_widgets()
    assert abs(min(w['props']['x'] for w in parts)+max(w['props']['x']+w['props']['w'] for w in parts)-2*lua.globals().LAYOUT['valueCenter'])<=1
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
for hour,minute in [(3,59),(4,0),(10,59),(11,0),(14,59),(15,0),(18,59),(19,0),(23,59),(0,0)]:
    clock_at(hour,minute);palette=palette_name()
    assert palette in {p['name'] for p in CLOCK_PALETTES}
    assert_clock(palette,f'{hour:02d}{minute:02d}')
    updates=[w['updates'] for w in clock_widgets()]
    lua.globals().timer['cb']()
    assert [w['updates'] for w in clock_widgets()]==updates,'unchanged minute must not rewrite clock images'
for before,after in [(3,4),(10,11),(14,15),(18,19)]:
    clock_at(before,59);previous=palette_name()
    clock_at(after,0);assert palette_name()!=previous,'adjacent slots must select from disjoint palette groups'
clock_at(19,0);night=palette_name()
clock_at(0,0,datetime(2026,10,28));assert palette_name()==night,'midnight must not start a new slot'
clock_at(3,59,datetime(2026,10,28));assert palette_name()==night
for evening,morning in [(datetime(2026,12,31),datetime(2027,1,1)),
                         (datetime(2028,2,29),datetime(2028,3,1)),
                         (datetime(2026,10,31),datetime(2026,11,1))]:
    clock_at(19,0,evening);night=palette_name()
    clock_at(1,30,morning.replace(fold=0));assert palette_name()==night
    clock_at(1,30,morning.replace(fold=1));assert palette_name()==night
    clock_at(3,59,morning);assert palette_name()==night
    clock_at(4,0,morning);assert palette_name()!=night
chosen={}
for offset in range(14):
    day=datetime(2026,10,27)+timedelta(days=offset)
    for hour in [4,11,15,19]:
        clock_at(hour,0,day);chosen[(offset,hour)]=palette_name()
for (offset,hour),palette in reversed(list(chosen.items())):
    clock_at(hour,0,datetime(2026,10,27)+timedelta(days=offset));assert palette_name()==palette,'selection must depend on the local slot, not visit order'
assert len(set(chosen.values()))>2,'slot selection must vary beyond a fixed alternating pair'
reload_time=int(datetime(2026,10,29,15,0).timestamp())
lua.globals().now=reload_time;lua.globals().timer['cb']();expected=palette_name()
reloaded=create_ui(load_layout(),reload_time)
new_clocks=[w for w in reloaded.globals().widgets.values() if '/clock-' in (w['props']['src'] or '')]
assert len(new_clocks)==4 and all(f'/clock-{expected}-' in w['props']['src'] for w in new_clocks),'reloading the face in the same slot must preserve its palette'
clock_at(14,59);previous=palette_name()
lua.globals().ScreenStateChangedCB('ON','OFF',0)
assert lua.globals().timer['paused']
lua.globals().now=int(datetime(2026,10,27,15,0).timestamp())
lua.globals().timer['cb']();assert_clock(previous,'1459')
lua.globals().ScreenStateChangedCB('OFF','ON',0)
assert not lua.globals().timer['paused'];assert palette_name()!=previous
assert_clock(palette_name(),'1500')
assert all('/value-normal-old-' in w['props']['src'] for w in value_widgets())
assert any(v and v.endswith('OLD') for v in text_values())
assert lua.globals().timer['period']==15000
print('Lua UI checks: metrics, new-file updates, cache, stale marker and screen-off timer pause passed')
print('Clock palette checks: stable 04/11/15/19 slots, paired selection, no adjacent repeat, midnight, cache and screen-off/resume passed')

# Signal uses baked colors; Meridian uses native colored objects, without image recolor.
for variant in ['signal','meridian']:
    lua=create_ui(load_layout(variant))
    assert value_text()=='--'
    if variant=='meridian':
        assert '--:--' not in text_values() and lua.globals().subscriptions['healthHeartRate'] is None
        assert native_value()['props']['text_color']==0x87939c
    else:assert '--:--' in text_values()
    for value,band in [(3.8,'alert'),(3.9,'normal'),(7.8,'normal'),(7.9,'high'),(12.0,'high'),(12.1,'alert'),(60.0,'alert')]:
        lua.globals().payload=frame(value,'↘',lua.globals().now*1000)
        lua.globals().timer['cb']()
        assert value_text()==f'{value:.1f}'
        centered_value()
        if variant=='meridian':
            assert native_value()['props']['text_color']==0xc4d0d8
            assert any(f'/trend-{band}-fresh-down_right.png' in (w['props']['src'] or '') for w in lua.globals().widgets.values())
        else:assert all(f'/value-{band}-fresh-' in w['props']['src'] for w in value_widgets())
    lua.globals().payload='partial';lua.globals().timer['cb']();assert value_text()=='60.0'
    lua.globals().now+=601;lua.globals().timer['cb']()
    if variant=='meridian':assert native_value()['props']['text_color']==0x87939c
    else:assert all('-old-' in w['props']['src'] for w in value_widgets())
    if variant=='signal':
        assert any(v.endswith('OLD') for v in text_values())
        source=next(w for w in lua.globals().widgets.values() if (w['props']['text'] or '').endswith('OLD'))
        assert source['props']['text_color']==0xb9c2c8
    else:assert not any('OLD' in v or ':' in v for v in text_values())
    def hand_nodes(width):
        return [w for w in lua.globals().widgets.values() if w['props']['w']==width and w['props']['h']==width and w['props']['bg_color'] is not None]
    if variant=='meridian':
        clock_at(23,59)
        assert (hand_nodes(10)[-1]['props']['x'],hand_nodes(10)[-1]['props']['y'])==(210,131)
        assert (hand_nodes(6)[-1]['props']['x'],hand_nodes(6)[-1]['props']['y'])==(195,72)
        lua.globals().now+=60;lua.globals().timer['cb']()
        assert (hand_nodes(10)[-1]['props']['x'],hand_nodes(10)[-1]['props']['y'])==(211,131)
        assert (hand_nodes(6)[-1]['props']['x'],hand_nodes(6)[-1]['props']['y'])==(213,71)
    seen=set()
    for offset in range(32):
        for hour in [4,11,15,19]:
            clock_at(hour,0,datetime(2026,10,29)+timedelta(days=offset))
            reference=create_ui(load_layout(),lua.globals().now)
            clock=next(w for w in reference.globals().widgets.values() if '/clock-' in (w['props']['src'] or ''))
            name=clock['props']['src'].split('/clock-')[1].split('-hour-')[0];seen.add(name)
            chosen=next(p for p in CLOCK_PALETTES if p['name']==name)
            if variant=='signal':
                assert_clock(name,f'{hour:02d}00');colored=clock_widgets()
            else:
                for width,part in [(10,'hour'),(6,'minute')]:
                    assert all(w['props']['bg_color']==int(chosen[part][1:],16) for w in hand_nodes(width))
                colored=hand_nodes(10)+hand_nodes(6)
            before=[w['updates'] for w in colored]
            lua.globals().timer['cb']();assert [w['updates'] for w in colored]==before
    assert seen=={p['name'] for p in CLOCK_PALETTES},'all 32 palette pairs must be reachable'
    lua.globals().ScreenStateChangedCB('ON','OFF',0);assert lua.globals().timer['paused']
    lua.globals().now+=3600;lua.globals().ScreenStateChangedCB('OFF','ON',0);assert not lua.globals().timer['paused']
    lua.globals().pageOnPause();assert lua.globals().timer['paused']
    lua.globals().pageOnResume();assert not lua.globals().timer['paused']
    assert lua.globals().timer['period']==15000
print('Signal/Meridian: all 32 baked/native palette pairs, hand precision, gray invalid data and lifecycle passed')
