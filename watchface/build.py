"""Build an original 432x514 Lua watchface. Requires Pillow; no vendor compiler."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from vendor import facebin
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
CYAN = '#f5f5f5'
MINT = '#ff9e32'
FACE_ID = '8670260101'


def glyph(char, width, height):
    font = ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'), 340)
    box = font.getbbox(char)
    image = Image.new('RGBA', (box[2]-box[0]+8, box[3]-box[1]+8))
    ImageDraw.Draw(image).text((4-box[0],4-box[1]),char,font=font,fill=CYAN)
    mask=image.getchannel('A').resize((width-8,height-8),Image.Resampling.LANCZOS)
    padded=Image.new('L',(width,height));padded.paste(mask,(4,4))
    padded=padded.filter(ImageFilter.MaxFilter(7))
    scale=4; dots=Image.new('RGBA',(width*scale,height*scale));draw=ImageDraw.Draw(dots)
    radius=2.6
    for y in range(5,height-3,8):
        for x in range(5,width-3,8):
            if padded.getpixel((x,y))>=70:
                assert 0<=x-radius and x+radius<width and 0<=y-radius and y+radius<height
                draw.ellipse(((x-radius)*scale,(y-radius)*scale,(x+radius)*scale,(y+radius)*scale),fill=CYAN)
    return dots.resize((width,height),Image.Resampling.LANCZOS)


def arrow(kind):
    image=Image.new('RGBA',(54,54)); draw=ImageDraw.Draw(image)
    if kind=='unknown':
        draw.text((17,7),'?',font=ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),38),fill=MINT)
    else:
        base=Image.new('RGBA',(54,54)); d=ImageDraw.Draw(base)
        d.line([(10,27),(44,27)],fill=MINT,width=5)
        d.line([(32,15),(44,27),(32,39)],fill=MINT,width=5)
        angles={'flat':0,'up_right':45,'up':90,'up_fast':90,'down_right':-45,'down':-90,'down_fast':-90}
        image=base.rotate(angles[kind],resample=Image.Resampling.BICUBIC)
        if kind.endswith('fast'):
            d=ImageDraw.Draw(image); y=17 if kind=='up_fast' else 37
            d.line([(17,y),(27,y-9 if kind=='up_fast' else y+9),(37,y)],fill=MINT,width=4)
    return image


def build():
    dest=ROOT/'build'; assets=dest/'app/lua'
    if dest.exists(): shutil.rmtree(dest)
    assets.mkdir(parents=True)
    for char in '0123456789': glyph(char,88,234).save(assets/f'clock-{char}.png')
    colon=Image.new('RGBA',(24,234)); d=ImageDraw.Draw(colon)
    for y in (82,90,146,154):
        for x in (7,17): d.ellipse((x-2.6,y-2.6,x+2.6,y+2.6),fill=MINT)
    colon.save(assets/'colon.png')
    for kind in ['unknown','up','up_right','flat','down_right','down','up_fast','down_fast']:
        arrow(kind).save(assets/f'trend-{kind}.png')
    battery=Image.new('RGBA',(34,24)); d=ImageDraw.Draw(battery)
    d.rounded_rectangle((1,3,28,21),radius=3,outline=CYAN,width=2)
    d.rectangle((29,9,32,15),fill=CYAN);d.rectangle((5,7,21,17),fill=CYAN)
    battery.save(assets/'battery.png')
    heart=Image.new('RGBA',(30,28)); d=ImageDraw.Draw(heart)
    d.ellipse((2,3,15,16),fill='#f07d9a');d.ellipse((14,3,27,16),fill='#f07d9a')
    d.polygon([(2,11),(27,11),(15,26)],fill='#f07d9a');heart.save(assets/'heart.png')
    for file in (ROOT/'src').glob('*.lua'): shutil.copy2(file,assets/file.name)
    preview=Image.new('RGBA',(432,514),'black');d=ImageDraw.Draw(preview)
    font=lambda size: ImageFont.truetype(str(ROOT/'fonts/BarlowCondensed-Light.ttf'),size)
    def centered(text,y,size,color):
        d.text((216,y),text,anchor='mt',font=font(size),fill=color)
    centered('MON 26 OCT',17,28,CYAN)
    for char,x in zip('1428',(14,110,234,330)): preview.alpha_composite(glyph(char,88,234),(x,65))
    preview.alpha_composite(colon,(204,65))
    d.text((168,330),'6.8',anchor='mt',font=font(92),fill=MINT,stroke_width=1)
    preview.alpha_composite(arrow('up_right'),(268,346))
    centered('14:25',418,26,'#8b9ba4')
    preview.alpha_composite(battery,(60,466));d.text((110,456),'82%',font=font(36),fill='#c4d0d8')
    preview.alpha_composite(heart,(230,464));d.text((280,456),'72',font=font(36),fill='#c4d0d8')
    preview.save(dest/'preview-example.png')
    # The installed preview uses placeholders so synthetic glucose cannot look live.
    install_preview=preview.copy();ImageDraw.Draw(install_preview).rectangle((48,340,380,451),fill='black')
    pdraw=ImageDraw.Draw(install_preview);pdraw.text((216,354),'--',anchor='mt',font=font(84),fill=MINT)
    pdraw.text((216,423),'WAITING',anchor='mt',font=font(26),fill='#8b9ba4')
    files=[('lua/'+p.name,p.read_bytes()) for p in sorted(assets.iterdir())]
    main_index=next(i for i,(name,_) in enumerate(files) if name=='lua/main.lua')
    packed=facebin.pack_face(files,facebin.rgba_to_bgra(install_preview.tobytes()),title='Ottai Minimal',face_id=FACE_ID,sentinel_idx=main_index)
    checked=facebin.unpack_face(packed)
    assert checked['files']==files and checked['preview']==(432,514,432*514*4)
    assert checked['face_id']==FACE_ID
    assert checked['sentinel_idx']==main_index and files[checked['sentinel_idx']][0]=='lua/main.lua'
    output=dest/'ottai-minimal-watch6.bin';output.write_bytes(packed)
    with zipfile.ZipFile(dest/'ottai-minimal-watch6.zip','w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('OttaiMinimal/resource.bin',packed)
        archive.writestr('OttaiMinimal/resources/manifest.xml','<Watchface name="Ottai Minimal" width="432" height="514" id="'+FACE_ID+'"><Resources/></Watchface>')
        archive.writestr('OttaiMinimal/uidmap.map','')
        archive.writestr('OttaiMinimal/preview/preview.png',_png(install_preview))
    (dest/'manifest.json').write_text(json.dumps({'faceId':FACE_ID,'width':432,'height':514,
        'sha256':hashlib.sha256(packed).hexdigest(),'bytes':len(packed),'files':len(files)},indent=2)+'\n')
    print(output)


def _png(image):
    import io
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


if __name__=='__main__': build()
