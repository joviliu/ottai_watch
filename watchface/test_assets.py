"""Validate the built faces against the actual Lua renderer and the upload containers."""
from pathlib import Path
import json
import hashlib
import re
import io
from datetime import datetime
from urllib.parse import urlparse
from PIL import Image
from collections import Counter
from colorsys import rgb_to_hsv
from build import load_layout, load_palettes, CLOCK_PALETTES, VALUE_COLORS, clock_palette_source, contrast_on_black
from ui_harness import create_ui
from vendor import facebin

root=Path(__file__).resolve().parent
def assert_led_mask(image,file,color):
    assert image.width%8==0 and image.height%8==0,file
    alpha=image.getchannel('A');cells=set()
    for y in range(image.height):
        for x in range(image.width):
            if alpha.getpixel((x,y))<128:continue
            cx,cy=x//8*8+4,y//8*8+4;cells.add((cx,cy))
            assert (x+.5-cx)**2+(y+.5-cy)**2<=3.5**2,(file,'continuous stroke or off-grid dot',x,y)
    assert cells,file
    expected=tuple(int(color.lstrip('#')[i:i+2],16) for i in (0,2,4))
    for cx,cy in cells:
        assert alpha.getpixel((cx,cy))==255 and alpha.getpixel((cx-4,cy-4))<128,(file,'dot must be circular and filled')
        assert image.getpixel((cx,cy))[:3]==expected,(file,'LED center color')
assert hashlib.sha256((root/'palettes.json').read_bytes()).hexdigest()=='1b31ec7073a0f4b724e6ddb38fdbd7354bbf43233b3d2e9112313a2db94077ea','Signal palette JSON must remain byte-identical'
assert load_palettes()==CLOCK_PALETTES==load_palettes('signal'),'legacy palette API must continue to mean Signal'
palette_sets={variant:load_palettes(variant) for variant in ['ultra','signal','meridian']}
assert len({json.dumps(palettes,sort_keys=True) for palettes in palette_sets.values()})==3,'each face must have its own palette list'
for variant,palettes in palette_sets.items():
    assert len(palettes)==32,(variant,'palette count')
    assert len({p['name'] for p in palettes})==32,(variant,'duplicate palette names')
    assert len({(p['hour'],p['minute']) for p in palettes})==32,(variant,'duplicate color pairs')
    for palette in palettes:
        assert re.fullmatch(r'[a-z][a-z0-9_]*',palette['name']) and palette['label'].strip(),(variant,palette)
        source=urlparse(palette['source'])
        assert source.scheme=='https' and source.hostname and '.' in source.hostname and source.path not in ('','/'),(variant,palette['source'])
        assert not source.username and not source.password and source.hostname not in ('example.com','example.org','example.net'),(variant,palette['source'])
        for part in ['hour','minute']:
            assert re.fullmatch(r'#[0-9A-F]{6}',palette[part]),(variant,palette)
            assert contrast_on_black(palette[part])>=4.5,(variant,palette,part)
    print(variant,'palette minimum contrast on black:',round(min(contrast_on_black(p[part]) for p in palettes for part in ['hour','minute']),3))
assert Counter(p['style'] for p in palette_sets['meridian'])=={'metallic':16,'plastic':16}
assert Counter(p['style'] for p in palette_sets['ultra'])=={'sport':24,'business':8}
for palette in palette_sets['ultra']:
    assert sum(rgb_to_hsv(*(int(palette[part][i:i+2],16)/255 for i in (1,3,5)))[1]>=.65 for part in ['hour','minute'])<=1,(palette['name'],'Ultra pairs need a quieter companion color')
for parity in [0,1]:
    assert Counter(p['style'] for p in palette_sets['meridian'][parity::2])=={'metallic':8,'plastic':8},'each selector group must include both Meridian materials'
    assert Counter(p['style'] for p in palette_sets['ultra'][parity::2])=={'sport':12,'business':4},'each selector group must preserve Ultra sport/business balance'
ids=set()
for variant in ['ultra','signal','meridian']:
    palettes=palette_sets[variant]
    layout=load_layout(variant);ids.add(layout['faceId'])
    dest=root/'build' if variant=='ultra' else root/'build'/variant
    assets=dest/'app/lua'
    packed=next(dest.glob('*.bin')).read_bytes();decoded=facebin.unpack_face(packed)
    assert decoded['face_id']==layout['faceId']
    assert decoded['files'][decoded['sentinel_idx']][0]=='lua/main.lua'
    assert dict(decoded['files'])['lua/frame.lua']==(root/'src/frame.lua').read_bytes()
    assert dict(decoded['files'])['lua/main.lua']==(root/'src/main.lua').read_bytes()
    assert dict(decoded['files'])['lua/clock-palettes.lua']==clock_palette_source(palettes).encode(),(variant,'packed palette list')
    assert (assets/'clock-palettes.lua').read_text()==clock_palette_source(palettes),(variant,'built palette list')
    assert not list(assets.glob('source-*.png')) and not any(name.startswith('lua/source-') for name,data in decoded['files']),(variant,'timestamp must use native text')
    if variant!='ultra':
        baseline=(root.parent/f'releases/0.1.18/ottai-{variant}-watch6-0.1.18.bin').read_bytes()
        if variant=='signal':
            assert hashlib.sha256(baseline).hexdigest()=='beb199a2ffffb2707ffaa23c84a32547d866a1122c9b66f943768bd990ee5bac','Signal reference BIN must remain byte-identical'
        baseline_files=dict(facebin.unpack_face(baseline)['files']);current_files=dict(decoded['files'])
        assert current_files.keys()==baseline_files.keys(),(variant,'LED changes must not add/remove resources')
        allowed={'lua/main.lua','lua/background.png'} if variant=='signal' else {'lua/main.lua','lua/clock-palettes.lua'}
        changed=[name for name,data in current_files.items() if name not in allowed and data!=baseline_files[name]]
        assert not changed,(variant,'unrelated resources changed',changed)
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
    if variant!='meridian':
        assert len(list(assets.glob('clock-*.png')))==32*20
        for palette in palettes:
            for part in ['hour','minute']:
                with Image.open(assets/f'clock-{palette["name"]}-{part}-8.png') as image:
                    pixel=Counter(p for p in zip(*(b.tobytes() for b in image.split())) if p[3]==255).most_common(1)[0][0]
                    assert '#%02X%02X%02X'%pixel[:3]==palette[part],(variant,palette['name'],part)
    if variant=='ultra':
        assert contrast_on_black(layout['normalColor'])>contrast_on_black('#924FF7'),'Ultra normal glucose purple must be brighter'
        with Image.open(assets/'background.png') as image:
            assert image.size==(432,514)
            for y in range(332,437,8):
                for x in range(8,425,8):
                    assert image.getpixel((x,y))==(27,30,36,255),'inactive LED centers must stay dim near-black gray'
                    if x<424:assert image.getpixel((x+4,y))==(0,0,0,255),'LED board must retain black gaps, without a filled panel'
                    if y<436:assert image.getpixel((x,y+4))==(0,0,0,255)
        for band,states in VALUE_COLORS.items():
            for state,color in states.items():
                if state=='fresh':color=layout.get(band+'Color',color)
                assert len(list(assets.glob(f'value-{band}-{state}-*.png')))==12
                assert len(list(assets.glob(f'trend-{band}-{state}-*.png')))==8
                files=[assets/f'value-{band}-{state}-{char}.png' for char in list('0123456789')+['dot','dash']]
                files+=[assets/f'trend-{band}-{state}-{kind}.png' for kind in ['flat','up','down','up_fast','down_fast','up_right','down_right','unknown']]
                for file in files:
                    with Image.open(file) as image:
                        if file.name.startswith('trend-'):assert image.size==(56,56),'Ultra arrow must be a 7x7 LED glyph'
                        else:assert image.size==(8 if file.stem.endswith('-dot') else 40,56)
                        assert_led_mask(image,file,color)
        frozen_clocks=dict(facebin.unpack_face((root.parent/'releases/0.1.18/ottai-minimal-watch6-0.1.18.bin').read_bytes())['files'])
        for char in '0123456789':
            alpha=Image.open(assets/f'clock-{palettes[0]["name"]}-hour-{char}.png').getchannel('A').tobytes()
            reference=next(data for name,data in frozen_clocks.items() if name.startswith('lua/clock-') and name.endswith(f'-hour-{char}.png'))
            with Image.open(io.BytesIO(reference)) as image:assert image.getchannel('A').tobytes()==alpha,'Ultra main clock glyphs must retain their original dot geometry'
            for palette in palettes:
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
            with Image.open(io.BytesIO(baseline_files['lua/background.png'])) as original,Image.open(assets/'background.png') as current:
                expected=original.copy();region=(0,450,250,514)
                expected.paste((0,0,0,255),region)
                expected.alpha_composite(original.crop(region),(8,450))
                assert current.tobytes()==expected.tobytes(),'Signal LAST UPDATE must move right8px with all other background pixels unchanged'
            with Image.open(assets/f'clock-{palettes[0]["name"]}-hour-0.png') as image:
                left,top,right,bottom=image.getchannel('A').point(lambda a:255 if a>=32 else 0).getbbox()
                assert .95<(right-left)/(bottom-top)<1.25,'Poiret One zero must retain its rounded proportions'
        if variant=='meridian':
            assert not list(assets.glob('hand-*.png')) and not (assets/'complications.png').exists()
            assert not list(assets.glob('value-*.png')) and not (assets/'heart.png').exists()
            for band in ['normal','high','alert']:
                for state in ['fresh','old']:
                    with Image.open(assets/f'trend-{band}-{state}-flat.png') as image:
                        pixel=Counter(p for p in zip(*(b.tobytes() for b in image.split())) if p[3]==255).most_common(1)[0][0]
                        assert '#%02X%02X%02X'%pixel[:3]==layout['invalidColor' if state=='old' else band+'Color']
    with Image.open(dest/'preview-clock-palettes.png') as image:assert image.size==(432*4,576*8)
    print(variant,manifest['files'],'resources;',manifest['bytes'],'bytes; runtime resources/entry/geometry passed')
assert len(ids)==3
assert len(CLOCK_PALETTES)==32
assert [(p['hour'],p['minute']) for p in CLOCK_PALETTES[:8]]==[('#EEEEEE','#76ABAE'),('#FEFAE0','#CCD5AE'),('#D6E6F2','#769FCD'),('#F4EEFF','#A6B1E1'),('#F5EBEB','#D5B4B4'),('#F9F5F6','#F2BED1'),('#C0DBEA','#BA90C6'),('#F9F3DF','#FFC898')]
assert all(p['source'].startswith('https://colorhunt.co/') for p in CLOCK_PALETTES)
