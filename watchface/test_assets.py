"""Validate the built faces against the actual Lua renderer and the upload containers."""
from pathlib import Path
import json
from datetime import datetime
from PIL import Image
from collections import Counter
from build import load_layout, CLOCK_PALETTES, contrast_on_black
from ui_harness import create_ui
from vendor import facebin

root=Path(__file__).resolve().parent
ids=set()
for variant in ['ultra','signal','meridian']:
    layout=load_layout(variant);ids.add(layout['faceId'])
    dest=root/'build' if variant=='ultra' else root/'build'/variant
    assets=dest/'app/lua'
    packed=next(dest.glob('*.bin')).read_bytes();decoded=facebin.unpack_face(packed)
    assert decoded['face_id']==layout['faceId']
    assert decoded['files'][decoded['sentinel_idx']][0]=='lua/main.lua'
    assert dict(decoded['files'])['lua/frame.lua']==(root/'src/frame.lua').read_bytes()
    assert dict(decoded['files'])['lua/main.lua']==(root/'src/main.lua').read_bytes()
    lua=create_ui(layout)
    # Exercise every clock image reference, including midnight and every analog hand position.
    for minute in range(24*60):
        lua.globals().now=int(datetime(2026,10,29,minute//60,minute%60).timestamp())
        lua.globals().timer['cb']()
        for widget in lua.globals().widgets.values():
            p=widget['props'];src=p['src']
            if p['x'] is not None:
                assert p['x']>=0 and p['y']>=0 and p['x']+p['w']<=432 and p['y']+p['h']<=514,(variant,src,'bounds')
            if src:
                file=assets/Path(src).name
                assert file.is_file(),(variant,src)
                assert p['x']>=0 and p['y']>=0 and p['x']+p['w']<=432 and p['y']+p['h']<=514,(variant,src,'bounds')
    for file in assets.glob('*.png'):
        with Image.open(file) as image:
            assert image.mode=='RGBA' and image.getbbox() is not None,file
    manifest=json.loads((dest/'manifest.json').read_text())
    assert manifest['files']==len(decoded['files']) and manifest['bytes']==len(packed)
    if variant=='ultra':
        for char in '0123456789':
            alpha=Image.open(assets/f'clock-{CLOCK_PALETTES[0]["name"]}-hour-{char}.png').getchannel('A').tobytes()
            for palette in CLOCK_PALETTES:
                for part in ['hour','minute']:
                    with Image.open(assets/f'clock-{palette["name"]}-{part}-{char}.png') as image:
                        assert image.size==(layout['clockW'],layout['clockH']) and image.getchannel('A').tobytes()==alpha
    else:
        for file in list(assets.glob('value-*.png'))+list(assets.glob('clock-*.png')):
            with Image.open(file) as image:
                # Ignore the faint Lanczos halo; the visible strokes must retain padding.
                left,top,right,bottom=image.getchannel('A').point(lambda alpha:255 if alpha>=32 else 0).getbbox()
                assert 0<left<right<image.width and 0<top<bottom<image.height,('clipped glyph',file)
        if variant=='signal':
            assert len(list(assets.glob('clock-*.png')))==32*20
            for palette in CLOCK_PALETTES:
                for part in ['hour','minute']:
                    with Image.open(assets/f'clock-{palette["name"]}-{part}-8.png') as image:
                        pixel=Counter(p for p in zip(*(b.tobytes() for b in image.split())) if p[3]==255).most_common(1)[0][0]
                        assert '#%02X%02X%02X'%pixel[:3]==palette[part]
        if variant=='meridian':
            assert not list(assets.glob('hand-*.png')) and not (assets/'complications.png').exists()
            assert not list(assets.glob('value-*.png')) and not (assets/'heart.png').exists()
            for band in ['normal','high','alert']:
                for state in ['fresh','old']:
                    with Image.open(assets/f'trend-{band}-{state}-flat.png') as image:
                        pixel=Counter(p for p in zip(*(b.tobytes() for b in image.split())) if p[3]==255).most_common(1)[0][0]
                        assert '#%02X%02X%02X'%pixel[:3]==layout['invalidColor' if state=='old' else band+'Color']
    print(variant,manifest['files'],'resources;',manifest['bytes'],'bytes; runtime resources/entry/geometry passed')
assert len(ids)==3
assert len(CLOCK_PALETTES)==32
assert [(p['hour'],p['minute']) for p in CLOCK_PALETTES[:8]]==[('#EEEEEE','#76ABAE'),('#FEFAE0','#CCD5AE'),('#D6E6F2','#769FCD'),('#F4EEFF','#A6B1E1'),('#F5EBEB','#D5B4B4'),('#F9F5F6','#F2BED1'),('#C0DBEA','#BA90C6'),('#F9F3DF','#FFC898')]
with Image.open(root/'build/preview-clock-palettes.png') as image:assert image.size==(432*4,576*8)
assert all(contrast_on_black(p[part])>=4.5 for p in CLOCK_PALETTES for part in ['hour','minute'])
assert all(p['source'].startswith('https://colorhunt.co/') for p in CLOCK_PALETTES)
print('Palette minimum contrast on black:',round(min(contrast_on_black(p[part]) for p in CLOCK_PALETTES for part in ['hour','minute']),3))
