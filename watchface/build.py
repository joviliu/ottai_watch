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
CLOCK_PALETTES = json.loads((ROOT/'palettes.json').read_text())
DATE_COLOR = '#B9C2C8'



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


def load_layout(variant='ultra'):
    layout=json.loads((ROOT/'layout.json').read_text())
    layout.update(json.loads((ROOT/'faces.json').read_text())[variant])
    return layout


def solid_glyph(char,width,height,color):
    text='.' if char=='dot' else '-' if char=='dash' else char
    scale=4
    font=ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-SemiBold.ttf'),height*scale)
    # Use one baseline and scale for the entire alphabet: decimal/dash must not grow to digit size.
    digits=font.getbbox('0123456789')
    bbox=font.getbbox(text)
    ratio=min((height-4)*scale/(digits[3]-digits[1]),(width-4)*scale/max(font.getbbox('0')[2],1))
    if char in ('dot','dash'): ratio=(height-4)*scale/(digits[3]-digits[1])
    font=ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-SemiBold.ttf'),max(1,int(height*scale*ratio)))
    bbox=font.getbbox(text);baseline=font.getbbox('0123456789')
    image=Image.new('RGBA',(width*scale,height*scale))
    ImageDraw.Draw(image).text(((width*scale-(bbox[2]-bbox[0]))/2-bbox[0],(height*scale-(baseline[3]-baseline[1]))/2-baseline[1]),text,font=font,fill=color)
    return image.resize((width,height),Image.Resampling.LANCZOS)


def hand_image(index,count,length,width,color):
    import math
    size=328;scale=3;center=size/2
    angle=index*2*math.pi/count
    forward=(math.sin(angle),-math.cos(angle));side=(math.cos(angle),math.sin(angle))
    points=[]
    for distance,lateral in [(-17,-width/2),(length-10,-width/2),(length,0),(length-10,width/2),(-17,width/2)]:
        points.append(((center+distance*forward[0]+lateral*side[0])*scale,(center+distance*forward[1]+lateral*side[1])*scale))
    image=Image.new('RGBA',(size*scale,size*scale));d=ImageDraw.Draw(image)
    d.polygon(points,fill=color);d.ellipse(((center-6)*scale,(center-6)*scale,(center+6)*scale,(center+6)*scale),fill=color)
    return image.resize((size,size),Image.Resampling.LANCZOS)


def background(layout):
    import math
    image=Image.new('RGBA',(432,514),'black');d=ImageDraw.Draw(image)
    font=lambda size:ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-SemiBold.ttf'),size)
    if layout['style']=='solid':
        d.text((28,16),'OTTAI',font=font(19),fill='#76ABAE')
        d.text((404,16),'SIGNAL',anchor='rt',font=font(19),fill='#718089')
        for y in (128,168):d.rounded_rectangle((212,y,220,y+9),radius=3,fill='#76ABAE')
        d.line((28,282,404,282),fill='#29343C',width=1)
        d.rounded_rectangle((22,292,410,435),radius=24,fill='#101C24',outline='#26363F',width=1)
        d.text((42,302),'GLUCOSE',font=font(18),fill=DATE_COLOR)
        d.text((30,454),'LAST UPDATE',font=font(21),fill=DATE_COLOR)
    elif layout['style']=='analog':
        cx,cy=216,202
        d.ellipse((cx-147,cy-147,cx+147,cy+147),outline='#28383C',width=2)
        for i in range(60):
            a=i*math.pi/30;outer=139;inner=outer-(12 if i%5==0 else 5)
            d.line((cx+math.sin(a)*inner,cy-math.cos(a)*inner,cx+math.sin(a)*outer,cy-math.cos(a)*outer),fill='#B3C0C0' if i%5==0 else '#46575B',width=3 if i%5==0 else 1)
        for text,x,y in [('12',216,84),('3',332,202),('6',216,320),('9',100,202)]:
            d.text((x,y),text,anchor='mm',font=font(26),fill='#DCD7C9')
        d.text((216,250),'MERIDIAN',anchor='mt',font=font(17),fill='#8EAAA6')
        d.text((216,273),'OTTAI',anchor='mt',font=font(13),fill='#657A79')
        d.line((46,355,386,355),fill='#28383C',width=1)
    return image


def preview(layout,assets,text='6.8',band='normal',state='fresh',palette=None,placeholders=False):
    image=background(layout);d=ImageDraw.Draw(image)
    font=lambda size:ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),size)
    def label(text,box,color):
        x,y,w,h,size=box
        for offset,line in enumerate(text.split('\n')):d.text((x+w/2,y+offset*size),line,anchor='mt',font=font(size),fill=color)
    label('THU 29 OCT',layout['dateBox'],DATE_COLOR)
    if layout['style']=='analog':
        image.alpha_composite(hand_image(10*60+9,720,81,11,'#F0D9B4'),(52,38))
        image.alpha_composite(hand_image(9,60,121,6,'#8DBDB3'),(52,38))
    else:
        colors=palette or (CLOCK_PALETTES[0] if layout['style']=='dots' else {'name':'signal','hour':'#EEEEEE','minute':'#76ABAE'})
        for i,(char,x) in enumerate(zip('1009',layout['clockX'])):
            image.alpha_composite(Image.open(assets/f'clock-{colors["name"]}-{"hour" if i<2 else "minute"}-{char}.png'),(x,layout['clockY']))
    text='--' if placeholders else text
    widths=[layout['valueDotW'] if c=='.' else layout['valueW'] for c in text]
    x=int(layout['valueCenter']-(sum(widths)+4*(len(widths)-1))/2)
    for char,width in zip(text,widths):
        name='dot' if char=='.' else 'dash' if char=='-' else char
        image.alpha_composite(Image.open(assets/f'value-{band}-{state}-{name}.png'),(x,layout['valueY']));x+=width+4
    image.alpha_composite(Image.open(assets/f'trend-{band}-{state}-{"unknown" if placeholders else "up_right"}.png'),(layout['trendX'],layout['trendY']))
    label('--:--' if placeholders else '10:04'+('\nOLD' if state=='old' else ''),layout['sourceBox'],DATE_COLOR)
    for key,name,text in [('battery','battery','--%' if placeholders else '82%'),('heart','heart','--' if placeholders else '72')]:
        x,y,w,h=layout[key+'Icon'];image.alpha_composite(Image.open(assets/f'{name}.png'),(x,y))
        label(text,layout[key+'Box'],'#C4D0D8')
    return image


def build_face(variant='ultra'):
    layout=load_layout(variant);face_id=layout['faceId'];title=layout['title']
    dest=ROOT/'build' if variant=='ultra' else ROOT/'build'/variant
    if dest.exists():shutil.rmtree(dest)
    assets=dest/'app/lua';assets.mkdir(parents=True)
    assert len(CLOCK_PALETTES)>=2 and len({p['name'] for p in CLOCK_PALETTES})==len(CLOCK_PALETTES)
    colors=CLOCK_PALETTES if layout['style']=='dots' else [{'name':'signal','hour':'#EEEEEE','minute':'#76ABAE'}]
    if layout['style']=='analog':
        for part,count,length,width,color in [('hour',720,81,11,'#F0D9B4'),('minute',60,121,6,'#8DBDB3')]:
            for index in range(count):hand_image(index,count,length,width,color).save(assets/f'hand-{part}-{index}.png')
    else:
        for palette in colors:
            for part in ['hour','minute']:
                assert contrast_on_black(palette[part])>=4.5
                for char in '0123456789':
                    img=glyph(char,layout['clockW'],layout['clockH'],palette[part],clock_rows=layout['clockRows']) if layout['style']=='dots' else solid_glyph(char,layout['clockW'],layout['clockH'],palette[part])
                    img.save(assets/f'clock-{palette["name"]}-{part}-{char}.png')
        assert len(list(assets.glob('clock-*.png')))==20*len(colors)
    (assets/'clock-palettes.lua').write_text(clock_palette_source())
    for band,states in VALUE_COLORS.items():
        for state,color in states.items():
            for char in list('0123456789')+['dot','dash']:
                w=layout['valueDotW'] if char=='dot' else layout['valueW']
                img=glyph(char,w,layout['valueH'],color,blood=True) if layout['style']=='dots' else solid_glyph(char,w,layout['valueH'],color)
                img.save(assets/f'value-{band}-{state}-{char}.png')
            for kind in ['unknown','up','up_right','flat','down_right','down','up_fast','down_fast']:arrow(kind,color).save(assets/f'trend-{band}-{state}-{kind}.png')
    battery=Image.new('RGBA',(34,24));d=ImageDraw.Draw(battery)
    d.rounded_rectangle((1,3,28,21),radius=3,outline=WHITE,width=2);d.rectangle((29,9,32,15),fill=WHITE);d.rectangle((5,7,21,17),fill=WHITE);battery.save(assets/'battery.png')
    heart=Image.new('RGBA',(30,28));d=ImageDraw.Draw(heart)
    d.ellipse((2,3,15,16),fill='#f07d9a');d.ellipse((14,3,27,16),fill='#f07d9a');d.polygon([(2,11),(27,11),(15,26)],fill='#f07d9a');heart.save(assets/'heart.png')
    if layout['style']!='dots':background(layout).save(assets/'background.png')
    for file in (ROOT/'src').glob('*.lua'):shutil.copy2(file,assets/file.name)
    def lua_value(value):
        if isinstance(value,list):return '{'+','.join(map(str,value))+'}'
        return json.dumps(value)
    (assets/'layout.lua').write_text('return {'+','.join(key+'='+lua_value(value) for key,value in layout.items())+'}\n')
    preview(layout,assets).save(dest/'preview-example.png')
    colors_preview=Image.new('RGB',(432*4,514),'black')
    for i,(text,band,state) in enumerate([('6.8','normal','fresh'),('9.0','high','fresh'),('13.0','alert','fresh'),('6.8','normal','old')]):
        colors_preview.paste(preview(layout,assets,text,band,state),(i*432,0))
    colors_preview.save(dest/'preview-colors.png')
    if layout['style']=='dots':
        palettes_preview=Image.new('RGB',(432*4,576*2),'black')
        for i,palette in enumerate(CLOCK_PALETTES):
            x,y=(i%4)*432,(i//4)*576;palettes_preview.paste(preview(layout,assets,palette=palette),(x,y))
            d=ImageDraw.Draw(palettes_preview);font=ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),22)
            d.text((x+216,y+518),palette['name'].replace('_',' ').title(),anchor='mt',font=font,fill=WHITE)
            d.text((x+216,y+546),palette['hour']+' / '+palette['minute'],anchor='mt',font=font,fill=DATE_COLOR)
        palettes_preview.save(dest/'preview-clock-palettes.png')
    install_preview=preview(layout,assets,placeholders=True)
    files=[('lua/'+p.name,p.read_bytes()) for p in sorted(assets.iterdir())]
    main_index=next(i for i,(name,_) in enumerate(files) if name=='lua/main.lua')
    packed=facebin.pack_face(files,facebin.rgba_to_bgra(install_preview.tobytes()),title=title,face_id=face_id,sentinel_idx=main_index)
    checked=facebin.unpack_face(packed)
    assert checked['files']==files and checked['preview']==(432,514,432*514*4)
    assert checked['face_id']==face_id and checked['sentinel_idx']==main_index and files[main_index][0]=='lua/main.lua'
    slug='ottai-minimal-watch6' if variant=='ultra' else 'ottai-'+variant+'-watch6'
    output=dest/(slug+'.bin');output.write_bytes(packed)
    with zipfile.ZipFile(dest/(slug+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
        prefix=title.replace(' ','')
        archive.writestr(prefix+'/resource.bin',packed)
        archive.writestr(prefix+'/resources/manifest.xml',f'<Watchface name="{title}" width="432" height="514" id="{face_id}"><Resources/></Watchface>')
        archive.writestr(prefix+'/uidmap.map','');archive.writestr(prefix+'/preview/preview.png',_png(install_preview))
    (dest/'manifest.json').write_text(json.dumps({'faceId':face_id,'title':title,'variant':variant,'width':432,'height':514,'sha256':hashlib.sha256(packed).hexdigest(),'bytes':len(packed),'files':len(files)},indent=2)+'\n')
    print(output)
    return dest


def _png(image):
    import io
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=['ultra','signal','meridian','all'],default='ultra')
    args=parser.parse_args()
    for variant in (['ultra','signal','meridian'] if args.variant=='all' else [args.variant]):build_face(variant)
