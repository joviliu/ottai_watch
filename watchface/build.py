"""Build an original 432x514 Lua watchface. Requires Pillow; no vendor compiler."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageColor
from vendor import facebin
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
WHITE = '#f5f5f5'
GLUCOSE_COLOR = '#924ff7'
VALUE_COLORS = {
    'normal': {'fresh': GLUCOSE_COLOR, 'old': '#7e6a9c'},
    'high': {'fresh': '#ffd60a', 'old': '#99864b'},
    'alert': {'fresh': '#ff453a', 'old': '#9b625e'},
}
CLOCK_ORANGE = '#ff682b'
CLOCK_PALETTES = [
    {'name': 'classic', 'hour': '#F5F5F5', 'minute': '#FF682B'},
    {'name': 'rose_cream', 'hour': '#FAE8E0', 'minute': '#EF7C8E'},
    {'name': 'pixel_citrus', 'hour': '#41A6F6', 'minute': '#EF7D57'},
    {'name': 'silver_blush', 'hour': '#B9B7BD', 'minute': '#E7D2CC'},
    {'name': 'neon_pop', 'hour': '#2FF3E0', 'minute': '#FA26A0'},
    {'name': 'ivory_sage', 'hour': '#FEFAE0', 'minute': '#CCD5AE'},
    {'name': 'icy_orchid', 'hour': '#C8F4F9', 'minute': '#C26DBC'},
    {'name': 'mint_candy', 'hour': '#B4F8C8', 'minute': '#FFAEBC'},
    {'name': 'twilight_berry', 'hour': '#249FDE', 'minute': '#BC4A9B'},
    {'name': 'teal_mauve', 'hour': '#85D2D0', 'minute': '#887BB0'},
    {'name': 'amber_red', 'hour': '#FDB750', 'minute': '#FC2E20'},
    {'name': 'cotton_rose', 'hour': '#EFEBE0', 'minute': '#FB6B90'},
]


def clock_palette_source():
    return 'return {' + ','.join(
        '{name=' + json.dumps(p['name']) + '}'
        for p in CLOCK_PALETTES) + '}\n'


def contrast_on_black(color):
    rgb=[value/255 for value in ImageColor.getrgb(color)]
    linear=[value/12.92 if value<=0.04045 else ((value+0.055)/1.055)**2.4 for value in rgb]
    return (sum(value*weight for value,weight in zip(linear,[0.2126,0.7152,0.0722]))+0.05)/0.05


def glyph(char, width=96, height=160, color=WHITE, blood=False, clock_rows=10):
    # Original 6x10 patterns match the reference proportions without stretching circles.
    patterns={
        '0':['.####.','######']+['##..##']*6+['######','.####.'],
        '1':['.####.']*2+['...##.']*8,
        '2':['.####.','######','##..##','....##','...##.','..##..','.##...','##....','######','######'],
        '3':['#####.','######']+['....##']*2+['.#####']*2+['....##']*2+['######','#####.'],
        '4':['##..##']*4+['######']*2+['....##']*4,
        '5':['######']*2+['##....']*2+['#####.','.#####']+['....##']*2+['######','#####.'],
        '6':['.####.','######']+['##....']*2+['#####.','######']+['##..##']*2+['######','.####.'],
        '7':['######']*2+['....##','...##.','..##..']+['.##...']*5,
        '8':['.####.','######']+['##..##']*2+['.####.','######']+['##..##']*2+['######','.####.'],
        '9':['.####.','######']+['##..##']*2+['######','.#####']+['....##']*2+['######','.####.'],
        'dash':['......']*4+['######']*2+['......']*4,
    }
    if blood:
        patterns={
            '0':['.###.','#...#','#..##','#.#.#','##..#','#...#','.###.'],
            '1':['..#..','.##..','..#..','..#..','..#..','..#..','.###.'],
            '2':['.###.','#...#','....#','...#.','..#..','.#...','#####'],
            '3':['####.','....#','....#','.###.','....#','....#','####.'],
            '4':['...#.','..##.','.#.#.','#..#.','#####','...#.','...#.'],
            '5':['#####','#....','#....','####.','....#','....#','####.'],
            '6':['.###.','#....','#....','####.','#...#','#...#','.###.'],
            '7':['#####','....#','...#.','..#..','.#...','.#...','.#...'],
            '8':['.###.','#...#','#...#','.###.','#...#','#...#','.###.'],
            '9':['.###.','#...#','#...#','.####','....#','....#','.###.'],
            'dash':['.....']*3+['#####']+['.....']*3,
        }
    rows=patterns.get(char)
    if not blood and clock_rows==14:
        rows=[row for i,row in enumerate(rows) for _ in range(2 if i in (2,3,6,7) else 1)]
    ncols,nrows=(5,7) if blood else (6,clock_rows)
    assert char=='dot' or len(rows)==nrows and all(len(row)==ncols for row in rows)
    scale=4; dots=Image.new('RGBA',(width*scale,height*scale));draw=ImageDraw.Draw(dots)
    pitch_x=width/ncols;pitch_y=height/nrows
    radius=min(width if char=='dot' else pitch_x,pitch_y)*(.375 if blood else .455)
    cells=[(0,nrows-1)] if char=='dot' else [(col,row) for row,pattern in enumerate(rows) for col,cell in enumerate(pattern) if cell=='#']
    for col,row in cells:
        x=width/2 if char=='dot' else pitch_x/2+col*pitch_x
        y=pitch_y/2+row*pitch_y
        assert 0<=x-radius and x+radius<width and 0<=y-radius and y+radius<height
        draw.ellipse(((x-radius)*scale,(y-radius)*scale,(x+radius)*scale,(y+radius)*scale),fill=color)
    return dots.resize((width,height),Image.Resampling.LANCZOS)


def arrow(kind,color=GLUCOSE_COLOR):
    image=Image.new('RGBA',(54,54)); draw=ImageDraw.Draw(image)
    if kind=='unknown':
        draw.text((17,7),'?',font=ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),38),fill=color)
    else:
        base=Image.new('RGBA',(54,54)); d=ImageDraw.Draw(base)
        d.line([(10,27),(44,27)],fill=color,width=5)
        d.line([(32,15),(44,27),(32,39)],fill=color,width=5)
        angles={'flat':0,'up_right':45,'up':90,'up_fast':90,'down_right':-45,'down':-90,'down_fast':-90}
        image=base.rotate(angles[kind],resample=Image.Resampling.BICUBIC)
        if kind.endswith('fast'):
            d=ImageDraw.Draw(image); y=17 if kind=='up_fast' else 37
            d.line([(17,y),(27,y-9 if kind=='up_fast' else y+9),(37,y)],fill=color,width=4)
    return image


def build():
    layout=json.loads((ROOT/'layout.json').read_text())
    face_id=layout['faceId'];title=layout['title']
    dest=ROOT/'build'; assets=dest/'app/lua'
    if dest.exists(): shutil.rmtree(dest)
    assets.mkdir(parents=True)
    assert len(CLOCK_PALETTES) >= 2 and len({p['name'] for p in CLOCK_PALETTES}) == len(CLOCK_PALETTES)
    for palette in CLOCK_PALETTES:
        for part in ['hour', 'minute']:
            assert contrast_on_black(palette[part]) >= 4.5
            for char in '0123456789':
                glyph(char,layout['clockW'],layout['clockH'],palette[part],clock_rows=layout['clockRows']).save(
                    assets/f'clock-{palette["name"]}-{part}-{char}.png')
    (assets/'clock-palettes.lua').write_text(clock_palette_source())
    assert len(list(assets.glob('clock-*.png'))) == 20*len(CLOCK_PALETTES)
    for char in '0123456789':
        baseline=Image.open(assets/f'clock-{CLOCK_PALETTES[0]["name"]}-hour-{char}.png').getchannel('A').tobytes()
        for palette in CLOCK_PALETTES:
            for part in ['hour', 'minute']:
                with Image.open(assets/f'clock-{palette["name"]}-{part}-{char}.png') as image:
                    assert image.size == (layout['clockW'],layout['clockH'])
                    assert image.getchannel('A').tobytes() == baseline
                    expected=ImageColor.getrgb(palette[part])+(255,)
                    assert any(pixel == expected for _,pixel in image.getcolors(image.width*image.height))
    for band,states in VALUE_COLORS.items():
        for state,color in states.items():
            for char in list('0123456789')+['dot','dash']:
                glyph(char,12 if char=='dot' else 40,56,color,blood=True).save(assets/f'value-{band}-{state}-{char}.png')
            for kind in ['unknown','up','up_right','flat','down_right','down','up_fast','down_fast']:
                arrow(kind,color).save(assets/f'trend-{band}-{state}-{kind}.png')
    battery=Image.new('RGBA',(34,24)); d=ImageDraw.Draw(battery)
    d.rounded_rectangle((1,3,28,21),radius=3,outline=WHITE,width=2)
    d.rectangle((29,9,32,15),fill=WHITE);d.rectangle((5,7,21,17),fill=WHITE)
    battery.save(assets/'battery.png')
    heart=Image.new('RGBA',(30,28)); d=ImageDraw.Draw(heart)
    d.ellipse((2,3,15,16),fill='#f07d9a');d.ellipse((14,3,27,16),fill='#f07d9a')
    d.polygon([(2,11),(27,11),(15,26)],fill='#f07d9a');heart.save(assets/'heart.png')
    for file in (ROOT/'src').glob('*.lua'): shutil.copy2(file,assets/file.name)
    fields=[]
    for key in ['clockW','clockH','clockX','clockY','valueY','sourceY','trendY']:
        value=layout[key]
        fields.append(key+'='+('{'+','.join(map(str,value))+'}' if isinstance(value,list) else str(value)))
    (assets/'layout.lua').write_text('return {'+','.join(fields)+'}\n')
    preview=Image.new('RGBA',(432,514),'black');d=ImageDraw.Draw(preview)
    font=lambda size: ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),size)
    def centered(text,y,size,color):
        d.text((216,y),text,anchor='mt',font=font(size),fill=color)
    centered('MON 26 OCT',17,28,WHITE)
    for i,(char,x) in enumerate(zip('1705',layout['clockX'])):
        preview.alpha_composite(glyph(char,layout['clockW'],layout['clockH'],WHITE if i<2 else CLOCK_ORANGE,clock_rows=layout['clockRows']),(x,layout['clockY']))
    def value_preview(image,text,color=GLUCOSE_COLOR):
        chars=['dot' if c=='.' else 'dash' if c=='-' else c for c in text]
        widths=[12 if c=='dot' else 40 for c in chars]
        x=(432-sum(widths)-4*(len(chars)-1))//2
        for char,width in zip(chars,widths):
            image.alpha_composite(glyph(char,width,56,color,blood=True),(x,layout['valueY']));x+=width+4
    value_preview(preview,'6.8')
    preview.alpha_composite(arrow('up_right'),(341,layout['trendY']))
    d.text((64,layout['sourceY']),'17:00',anchor='mt',font=font(34),fill='#e9f2f8')
    preview.alpha_composite(battery,(60,466));d.text((110,456),'82%',font=font(36),fill='#c4d0d8')
    preview.alpha_composite(heart,(230,464));d.text((280,456),'72',font=font(36),fill='#c4d0d8')
    preview.save(dest/'preview-example.png')
    columns=min(4,len(CLOCK_PALETTES));rows=(len(CLOCK_PALETTES)+columns-1)//columns
    palettes_preview=Image.new('RGB',(432*columns,576*rows),'black')
    for i,palette in enumerate(CLOCK_PALETTES):
        sample=preview.copy()
        ImageDraw.Draw(sample).rectangle((0,layout['clockY'],431,layout['clockY']+layout['clockH']-1),fill='black')
        for j,(char,x) in enumerate(zip('1705',layout['clockX'])):
            sample.alpha_composite(glyph(char,layout['clockW'],layout['clockH'],palette['hour' if j<2 else 'minute'],
                                         clock_rows=layout['clockRows']),(x,layout['clockY']))
        x,y=(i%columns)*432,(i//columns)*576
        palettes_preview.paste(sample,(x,y))
        ImageDraw.Draw(palettes_preview).text((x+216,y+518),palette['name'].replace('_',' ').title(),
            anchor='mt',font=font(24),fill=WHITE)
        ImageDraw.Draw(palettes_preview).text((x+216,y+546),palette['hour']+' / '+palette['minute'],
            anchor='mt',font=font(20),fill='#b9c2c8')
    palettes_preview.save(dest/'preview-clock-palettes.png')
    colors_preview=Image.new('RGB',(432*3,514),'black')
    for i,(text,band) in enumerate([('6.8','normal'),('9.0','high'),('13.0','alert')]):
        sample=preview.copy()
        ImageDraw.Draw(sample).rectangle((120,layout['valueY']-2,416,layout['valueY']+58),fill='black')
        color=VALUE_COLORS[band]['fresh']
        value_preview(sample,text,color)
        sample.alpha_composite(arrow('up_right',color),(341,layout['trendY']))
        colors_preview.paste(sample,(i*432,0))
    colors_preview.save(dest/'preview-colors.png')
    # The installed preview uses placeholders so synthetic glucose cannot look live.
    install_preview=preview.copy();ImageDraw.Draw(install_preview).rectangle((12,min(layout['valueY'],layout['sourceY'],layout['trendY'])-8,420,450),fill='black')
    value_preview(install_preview,'--')
    ImageDraw.Draw(install_preview).text((64,layout['sourceY']),'--:--',anchor='mt',font=font(34),fill='#e9f2f8')
    files=[('lua/'+p.name,p.read_bytes()) for p in sorted(assets.iterdir())]
    main_index=next(i for i,(name,_) in enumerate(files) if name=='lua/main.lua')
    packed=facebin.pack_face(files,facebin.rgba_to_bgra(install_preview.tobytes()),title=title,face_id=face_id,sentinel_idx=main_index)
    checked=facebin.unpack_face(packed)
    assert checked['files']==files and checked['preview']==(432,514,432*514*4)
    assert checked['face_id']==face_id
    assert checked['sentinel_idx']==main_index and files[checked['sentinel_idx']][0]=='lua/main.lua'
    output=dest/'ottai-minimal-watch6.bin';output.write_bytes(packed)
    prefix=title.replace(' ','')
    with zipfile.ZipFile(dest/'ottai-minimal-watch6.zip','w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(prefix+'/resource.bin',packed)
        archive.writestr(prefix+'/resources/manifest.xml','<Watchface name="'+title+'" width="432" height="514" id="'+face_id+'"><Resources/></Watchface>')
        archive.writestr(prefix+'/uidmap.map','')
        archive.writestr(prefix+'/preview/preview.png',_png(install_preview))
    (dest/'manifest.json').write_text(json.dumps({'faceId':face_id,'width':432,'height':514,
        'sha256':hashlib.sha256(packed).hexdigest(),'bytes':len(packed),'files':len(files)},indent=2)+'\n')
    print(output)


def _png(image):
    import io
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


if __name__=='__main__': build()
