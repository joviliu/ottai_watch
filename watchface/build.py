"""Build an original 432x514 Lua watchface. Requires Pillow; no vendor compiler."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageFilter
from functools import lru_cache
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
        '{name=' + json.dumps(p['name']) + ',hour=0x' + p['hour'][1:] + ',minute=0x' + p['minute'][1:] + '}'
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


def arrow(kind,color=GLUCOSE_COLOR,filled=False):
    image=Image.new('RGBA',(54,54)); draw=ImageDraw.Draw(image)
    if kind=='unknown':
        draw.text((17,7),'?',font=ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),38),fill=color)
    else:
        base=Image.new('RGBA',(54,54)); d=ImageDraw.Draw(base)
        if filled:
            d.polygon([(11,21),(31,21),(31,12),(46,27),(31,42),(31,33),(11,33)],fill=color)
            d.ellipse((6,21,18,33),fill=color)
        else:
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


def colored_alpha(image,color):
    result=Image.new('RGBA',image.size,color)
    result.putalpha(image.getchannel('A'))
    return result


@lru_cache(maxsize=32)
def jersey_mask(char,width,height,outlined):
    scale=4;pad=7 if outlined else 3
    font=ImageFont.truetype(str(ROOT/'fonts/Graduate-Regular.ttf'),1024)
    top=font.getbbox('0123456789')[1];bottom=font.getbbox('0123456789')[3]
    widest=max(font.getbbox(c)[2]-font.getbbox(c)[0] for c in '0123456789')
    bbox=font.getbbox(char)
    natural=Image.new('L',(widest,bottom-top))
    ImageDraw.Draw(natural).text(((widest-bbox[2]+bbox[0])/2-bbox[0],-top),char,font=font,fill=255)
    result=Image.new('L',(width*scale,height*scale))
    result.paste(natural.resize(((width-pad*2)*scale,(height-pad*2)*scale),Image.Resampling.LANCZOS),(pad*scale,pad*scale))
    return result,result.filter(ImageFilter.MaxFilter(25)) if outlined else None,result.filter(ImageFilter.MaxFilter(13)) if outlined else None


def jersey_glyph(char,width,height,color,outline=None):
    scale=4
    if char in ('dot','dash'):
        image=Image.new('RGBA',(width*scale,height*scale));draw=ImageDraw.Draw(image)
        if char=='dot':
            radius=min(width*.22,height*.05);x=width/2;y=height-3-radius
            draw.ellipse(((x-radius)*scale,(y-radius)*scale,(x+radius)*scale,(y+radius)*scale),fill=color)
        else:draw.rounded_rectangle((3*scale,(height/2-1)*scale,(width-3)*scale,(height/2+1)*scale),radius=scale,fill=color)
        return colored_alpha(image.resize((width,height),Image.Resampling.LANCZOS),color)
    mask,outer,separator=jersey_mask(char,width,height,outline is not None)
    image=Image.new('RGBA',mask.size)
    if outline:
        image.paste(outline,(0,0,*mask.size),outer)
        image.paste('black',(0,0,*mask.size),separator)
    image.paste(color,(0,0,*mask.size),mask)
    image=image.resize((width,height),Image.Resampling.LANCZOS)
    return image if outline else colored_alpha(image,color)


def hand_image(index,count,length,width,color,size):
    import math
    scale=3;center=size/2
    angle=index*2*math.pi/count
    image=Image.new('RGBA',(size*scale,size*scale));d=ImageDraw.Draw(image)
    step=max(1,width//3)
    for i in range(math.ceil((length+12)/step)+1):
        distance=-12+min(i*step,length+12)
        x=round(center+math.sin(angle)*distance-width/2);y=round(center-math.cos(angle)*distance-width/2)
        d.ellipse((x*scale,y*scale,(x+width)*scale,(y+width)*scale),fill=color)
    return image.resize((size,size),Image.Resampling.LANCZOS)


def background(layout):
    import math
    image=Image.new('RGBA',(432,514),'black');d=ImageDraw.Draw(image)
    font=lambda size:ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-SemiBold.ttf'),size)
    if layout['style']=='solid':
        for fraction in (.35,.65):
            y=round(layout['clockY']+layout['clockH']*fraction)
            d.rounded_rectangle((212,y,220,y+9),radius=3,fill=DATE_COLOR)
        d.line((28,381,404,381),fill='#29343C',width=1)
        d.rounded_rectangle((22,392,410,440),radius=14,fill='#101C24',outline='#26363F',width=1)
        d.text((40,404),'GLUCOSE',font=font(18),fill=DATE_COLOR)
        d.text((30,464),'LAST UPDATE',font=font(21),fill=DATE_COLOR)
    elif layout['style']=='analog':
        x,y,size,_=layout['dialBox'];cx,cy=x+size/2,y+size/2
        radius=size/2-3
        d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),outline='#28383C',width=2)
        for i in range(60):
            a=i*math.pi/30;outer=radius-8;inner=outer-(16 if i%5==0 else 6)
            d.line((cx+math.sin(a)*inner,cy-math.cos(a)*inner,cx+math.sin(a)*outer,cy-math.cos(a)*outer),fill='#B3C0C0' if i%5==0 else '#46575B',width=3 if i%5==0 else 1)
        inset=radius-34
        for text,x,y in [('12',cx,cy-inset),('3',cx+inset,cy),('6',cx,cy+inset),('9',cx-inset,cy)]:
            d.text((x,y),text,anchor='mm',font=font(26),fill='#DCD7C9')
    return image


def preview(layout,assets,text='6.8',band='normal',state='fresh',palette=None,placeholders=False):
    if placeholders and layout.get('invalidColor'):state='old'
    image=background(layout);d=ImageDraw.Draw(image)
    font=lambda size:ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),size)
    def label(text,box,color):
        x,y,w,h,size=box
        for offset,line in enumerate(text.split('\n')):d.text((x+w/2,y+offset*size),line,anchor='mt',font=font(size),fill=color)
    label('THU 29 OCT',layout['dateBox'],DATE_COLOR)
    colors=palette or CLOCK_PALETTES[0]
    if layout['style']=='analog':
        x,y,size,_=layout['dialBox']
        image.alpha_composite(hand_image(10*60+9,720,112,10,colors['hour'],size),(x,y))
        image.alpha_composite(hand_image(9,60,174,6,colors['minute'],size),(x,y))
        ImageDraw.Draw(image).ellipse((210,y+size/2-6,222,y+size/2+6),fill=colors['minute'])
    else:
        for i,(char,x) in enumerate(zip('1009',layout['clockX'])):
            part='hour' if i<2 else 'minute';name=colors['name']
            img=Image.open(assets/f'clock-{name}-{part}-{char}.png')
            image.alpha_composite(img,(x,layout['clockY']))
    text='--' if placeholders else text
    if layout.get('valueBox'):
        label(text,layout['valueBox'],'#87939C' if state=='old' else '#C4D0D8')
    else:
        widths=[layout['valueDotW'] if c=='.' else layout['valueW'] for c in text]
        x=int(layout['valueCenter']-(sum(widths)+4*(len(widths)-1))/2)
        for char,width in zip(text,widths):
            name='dot' if char=='.' else 'dash' if char=='-' else char
            image.alpha_composite(Image.open(assets/f'value-{band}-{state}-{name}.png'),(x,layout['valueY']));x+=width+4
    image.alpha_composite(Image.open(assets/f'trend-{band}-{state}-{"unknown" if placeholders else "up_right"}.png'),(layout['trendX'],layout['trendY']))
    if not layout.get('hideSource'):label('--:--' if placeholders else '10:04'+('\nOLD' if state=='old' else ''),layout['sourceBox'],DATE_COLOR)
    for key,name,text in [('battery','battery','--%' if placeholders else '82%'),('heart','heart','--' if placeholders else '72')]:
        if key=='heart' and layout.get('hideHeart'):continue
        x,y,w,h=layout[key+'Icon'];image.alpha_composite(Image.open(assets/f'{name}.png'),(x,y))
        label(text,layout[key+'Box'],'#C4D0D8')
    return image


def build_face(variant='ultra'):
    layout=load_layout(variant);face_id=layout['faceId'];title=layout['title']
    dest=ROOT/'build' if variant=='ultra' else ROOT/'build'/variant
    if dest.exists():shutil.rmtree(dest)
    assets=dest/'app/lua';assets.mkdir(parents=True)
    assert len(CLOCK_PALETTES)>=2 and len({p['name'] for p in CLOCK_PALETTES})==len(CLOCK_PALETTES)
    colors=CLOCK_PALETTES
    if layout['style']!='analog':
        for palette in colors:
            for part in ['hour','minute']:
                assert contrast_on_black(palette[part])>=4.5
                for char in '0123456789':
                    img=glyph(char,layout['clockW'],layout['clockH'],palette[part],clock_rows=layout['clockRows']) if layout['style']=='dots' else jersey_glyph(char,layout['clockW'],layout['clockH'],palette[part],palette['minute' if part=='hour' else 'hour'])
                    img.save(assets/f'clock-{palette["name"]}-{part}-{char}.png')
        assert len(list(assets.glob('clock-*.png')))==20*len(colors)
    (assets/'clock-palettes.lua').write_text(clock_palette_source())
    for band,states in VALUE_COLORS.items():
        for state,color in states.items():
            if state=='fresh':color=layout.get(band+'Color',color)
            if state=='old':color=layout.get('invalidColor',color)
            for char in list('0123456789')+['dot','dash']:
                if layout.get('valueBox'):continue
                w=layout['valueDotW'] if char=='dot' else layout['valueW']
                img=glyph(char,w,layout['valueH'],color,blood=True) if layout['style']=='dots' else jersey_glyph(char,w,layout['valueH'],color)
                img.save(assets/f'value-{band}-{state}-{char}.png')
            size=layout.get('trendSize',54)
            for kind in ['unknown','up','up_right','flat','down_right','down','up_fast','down_fast']:
                img=arrow(kind,color,layout.get('cartoonTrend',False)).resize((size,size),Image.Resampling.LANCZOS)
                if layout['style']!='dots':img=colored_alpha(img,color)
                img.save(assets/f'trend-{band}-{state}-{kind}.png')
    battery=Image.new('RGBA',(34,24));d=ImageDraw.Draw(battery)
    d.rounded_rectangle((1,3,28,21),radius=3,outline=WHITE,width=2);d.rectangle((29,9,32,15),fill=WHITE);d.rectangle((5,7,21,17),fill=WHITE);battery.save(assets/'battery.png')
    heart=Image.new('RGBA',(30,28));d=ImageDraw.Draw(heart)
    d.ellipse((2,3,15,16),fill='#f07d9a');d.ellipse((14,3,27,16),fill='#f07d9a');d.polygon([(2,11),(27,11),(15,26)],fill='#f07d9a')
    if not layout.get('hideHeart'):heart.save(assets/'heart.png')
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
        palettes_preview=Image.new('RGB',(432*4,576*((len(CLOCK_PALETTES)+3)//4)),'black')
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
