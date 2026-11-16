import bootstrap
from array import array
from io import BytesIO
from pathlib import Path
import sys
import os
import math
from datetime import datetime
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageOps
from model import Track
from media import source_label
from touch import TARGETS, HIT_RECTS
from theme import BG, FG, MUTED, CORAL, SALMON, ROSE, BERRY, PLUM, SURFACE, INK, PALETTE

SIZE = (320, 240)
ACCENT = SALMON


@lru_cache(maxsize=32)
def font(size, bold=False):
    path = Path(os.environ.get('SystemRoot',r'C:\Windows'))/'Fonts'/('segoeuib.ttf' if bold else 'segoeui.ttf')
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default(size=size)


def normalize_text(text):
    return ' '.join(str(text or '')[:4096].split())


def safe_seconds(value):
    try:value=float(value)
    except (TypeError,ValueError,OverflowError):return 0.0
    return max(0.0,value) if math.isfinite(value) else 0.0


def clip(draw,text,face,width):
    text=normalize_text(text)
    if draw.textlength(text,font=face)<=width:return text
    low,high=0,len(text)
    while low<high:
        middle=(low+high+1)//2
        if draw.textlength(text[:middle]+'…',font=face)<=width:low=middle
        else:high=middle-1
    return text[:low]+'…'


def wrap(draw, text, face, width, lines=2):
    text = normalize_text(text)
    result = []
    while text and len(result) < lines:
        if len(result) == lines - 1:
            result.append(clip(draw, text, face, width))
            break
        count = 0
        for i in range(1, len(text) + 1):
            if draw.textlength(text[:i], font=face) > width:
                break
            count = i
        if not count:
            break
        if count < len(text) and " " in text[:count]:
            count = text.rfind(" ", 0, count) or count
        result.append(text[:count].strip())
        text = text[count:].strip()
    return result


def timestamp(seconds):
    seconds = int(safe_seconds(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


@lru_cache(maxsize=4)
def artwork(data):
    if data:
        try:
            with Image.open(BytesIO(data)) as src:
                if src.width * src.height <= 16_000_000:
                    # Preserve wide video thumbnails rather than cropping their sides.
                    fitted=ImageOps.contain(src.convert("RGB"),(96,96),method=Image.Resampling.LANCZOS)
                    canvas=Image.new('RGB',(96,96),SURFACE)
                    canvas.paste(fitted,((96-fitted.width)//2,(96-fitted.height)//2))
                    return canvas
        except (OSError,ValueError,Image.DecompressionBombError):pass
    return None


def render(track: Track):
    image=Image.new('RGB',SIZE,BG)
    d=ImageDraw.Draw(image)
    d.rectangle((0,0,319,2),fill=SALMON)
    # Header helpers preserve this track-specific status area.
    image=render_header_status(image,source=track.source,output_name='DEMO' if track.demo else None)
    d=ImageDraw.Draw(image)
    cover=artwork(track.cover)
    mask=Image.new('L',(96,96));ImageDraw.Draw(mask).rounded_rectangle((0,0,95,95),radius=10,fill=255)
    if cover is not None:image.paste(cover,(10,44),mask)
    else:
        d.rounded_rectangle((10,44,105,139),radius=10,fill=SURFACE)
        d.ellipse((30,64,84,118),outline=PLUM,width=3)
        d.ellipse((50,84,64,98),fill=CORAL)
    if not track.available:
        title=track.title
        detail=track.artist
    else:title=track.title;detail=track.artist
    face=font(16,True)
    title_lines=wrap(d,title,face,192,3)
    for index,line in enumerate(title_lines):d.text((116,43+index*20),line,font=face,fill=FG)
    artist_y=max(91,46+len(title_lines)*20)
    for index,line in enumerate(wrap(d,detail,font(11),192,2 if artist_y<=91 else 1)):
        d.text((116,artist_y+index*15),line,font=font(11),fill=MUTED)
    if track.album and artist_y<=91:
        d.text((116,126),clip(d,track.album,font(9),192),font=font(9),fill=MUTED)
    d.rounded_rectangle((12,148,307,153),radius=2,fill=SURFACE)
    duration=safe_seconds(track.duration);position=safe_seconds(track.position)
    ratio=max(0,min(1,position/duration)) if duration else 0
    if ratio:d.rounded_rectangle((12,148,12+max(4,int(295*ratio)),153),radius=2,fill=CORAL)
    d.text((12,157),timestamp(track.position) if track.available else '--:--',font=font(10),fill=MUTED)
    end=timestamp(track.duration) if track.duration else '--:--'
    d.text((307-d.textlength(end,font=font(10)),157),end,font=font(10),fill=MUTED)
    for action,(left,top,right,bottom) in HIT_RECTS.items():
        fill=SALMON if action=='play_pause' else SURFACE
        d.rounded_rectangle((left,top,right-1,bottom-1),radius=12,fill=fill)
    d.polygon([(64,189),(49,198),(64,207)],fill=FG);d.rectangle((44,189,47,207),fill=FG)
    if track.playing:
        d.rounded_rectangle((151,188,156,207),radius=1,fill=INK)
        d.rounded_rectangle((164,188,169,207),radius=1,fill=INK)
    else:d.polygon([(154,187),(154,208),(171,198)],fill=INK)
    d.polygon([(256,189),(271,198),(256,207)],fill=FG);d.rectangle((273,189,276,207),fill=FG)
    for cx,label,color in [(56,'ÖNCEKİ',FG),(160,'DURAKLAT' if track.playing else 'OYNAT',INK),(264,'SONRAKİ',FG)]:
        face=font(9,True);d.text((cx-d.textlength(label,font=face)/2,216),label,font=face,fill=color)
    for action,box in HIT_RECTS.items():
        if action not in track.supported_actions:
            patch=image.crop(box);image.paste(Image.blend(patch,Image.new('RGB',patch.size,BG),0.65),box)
    return image



def render_calibration(index):
    image = Image.new("RGB", SIZE, BG)
    d = ImageDraw.Draw(image)
    d.text((65, 88), "DOKUNMATİK AYARI", font=font(17, True), fill=FG)
    d.text((60, 116), f"{index+1}/4 · Hedefin ortasına bas", font=font(13), fill=FG)
    d.text((51, 139), "Sonra parmağını tamamen kaldır", font=font(12), fill=MUTED)
    x,y = TARGETS[index]
    d.ellipse((x-13,y-13,x+13,y+13), outline=ACCENT, width=2)
    d.line((x-19,y,x+19,y), fill=FG, width=1)
    d.line((x,y-19,x,y+19), fill=FG, width=1)
    d.ellipse((x-2,y-2,x+2,y+2), fill=ACCENT)
    return image


def rgb565(image):
    if not (1 <= image.width <= 320 and 1 <= image.height <= 240):
        raise ValueError("Görüntü ekran sınırları içinde olmalı.")
    words = array("H", (((r & 248) << 8) | ((g & 252) << 3) | (b >> 3) for r, g, b in image.convert("RGB").getdata()))
    if sys.byteorder != "little":
        words.byteswap()
    return words.tobytes()


def render_volume(image, level, muted=False):
    image = image.copy()
    d = ImageDraw.Draw(image)
    level = max(0, min(100, int(level)))
    d.rectangle((0, 140, 319, 175), fill=BG)
    d.text((12, 145), "SESSİZ" if muted else f"SES  %{round(level)}", font=font(12, True), fill=FG)
    d.rounded_rectangle((90, 151, 307, 159), radius=4, fill=SURFACE)
    if level:
        d.rounded_rectangle((90, 151, 90+max(8,round(217*level/100)),159),radius=4,fill=CORAL)
    return image


def render_header_status(image, muted=False, resources=None, source="", pinned=False, connected=True,output_name=None):
    image=image.copy();d=ImageDraw.Draw(image)
    d.rectangle((0,3,319,39),fill=BG)
    d.rounded_rectangle((8,5,110,21),radius=5,fill=SURFACE)
    label=source_label(source)
    d.text((13,5),clip(d,label,font(10,True),82),font=font(10,True),fill=FG)
    if pinned:
        d.ellipse((101,10,105,14),fill=CORAL)
    else:d.polygon([(100,11),(106,11),(103,14)],fill=MUTED)
    d.text((121,5),datetime.now().strftime('%H:%M'),font=font(11,True),fill=FG)
    # Small gear is the brightness/settings affordance; clock is also tappable.
    d.ellipse((171,8,181,18),outline=MUTED,width=1)
    d.ellipse((175,12,177,14),fill=MUTED)
    for a,b,c,e in ((175,5,177,8),(175,18,177,21),(168,12,171,14),(181,12,184,14)):
        d.rectangle((a,b,c,e),fill=MUTED)
    output=clip(d,output_name or 'Çıkış —',font(9,True),98)
    d.text((310-d.textlength(output,font=font(9,True)),6),output,font=font(9,True),fill=MUTED)
    if muted:
        d.polygon([(190,11),(193,11),(197,7),(197,19),(193,15),(190,15)],fill=CORAL)
        d.line((201,10,206,16),fill=CORAL,width=1);d.line((206,10,201,16),fill=CORAL,width=1)
    resources=resources or {}
    for x,key,label,color in [(12,'cpu','CPU',CORAL),(112,'gpu','GPU',SALMON),(216,'ram','RAM',ROSE)]:
        value=resources.get(key)
        text=f'{label} {value}%' if value is not None else f'{label} —'
        d.text((x,25),text,font=font(9,True),fill=color)
    if not connected:
        d.rectangle((212,5,310,20),fill=BG)
        d.text((251,6),'USB YOK',font=font(9,True),fill=CORAL)
    d.line((12,39,308,39),fill=SURFACE)
    return image



def render_idle(resources=None, muted=False, connected=True):
    image=Image.new('RGB',SIZE,BG);d=ImageDraw.Draw(image)
    clock=datetime.now().strftime('%H:%M');face=font(56,True)
    d.text(((320-d.textlength(clock,font=face))/2,42),clock,font=face,fill=FG)
    day=('Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar')[datetime.now().weekday()]
    date=datetime.now().strftime('%d.%m.%Y')+' · '+day
    face=font(11)
    d.text(((320-d.textlength(date,font=face))/2,116),date,font=face,fill=MUTED)
    resources=resources or {}
    for x,key,color in [(12,'cpu',CORAL),(112,'gpu',SALMON),(212,'ram',ROSE)]:
        value=resources.get(key)
        d.rounded_rectangle((x,146,x+95,207),radius=9,fill=SURFACE)
        d.text((x+10,151),key.upper(),font=font(9,True),fill=MUTED)
        d.text((x+10,164),f'{value}%' if value is not None else '—',font=font(18,True),fill=color)
        d.rounded_rectangle((x+10,195,x+85,198),radius=1,fill=BG)
        if value is not None and value>0:d.rectangle((x+10,195,x+10+round(min(100,max(0,value))*.75),198),fill=color)
    text='USB BAĞLANTISI YOK' if not connected else 'SESSİZ · DOKUNARAK UYANDIR' if muted else 'DOKUNARAK UYANDIR'
    face=font(9,True)
    d.text(((320-d.textlength(text,font=face))/2,222),text,font=face,fill=MUTED)
    return image



def render_brightness(level):
    image=Image.new('RGB',SIZE,BG);d=ImageDraw.Draw(image)
    d.text((20,14),'PARLAKLIK',font=font(19,True),fill=FG)
    d.text((20,40),'Ekran ışığı',font=font(11),fill=MUTED)
    label=f'%{level}';face=font(32,True)
    d.text(((320-d.textlength(label,font=face))/2,62),label,font=face,fill=CORAL)
    d.rounded_rectangle((14,65,52,99),radius=8,fill=SURFACE)
    d.rounded_rectangle((268,65,306,99),radius=8,fill=SURFACE)
    d.text((25,65),'−',font=font(24),fill=FG);d.text((278,65),'+',font=font(24),fill=FG)
    d.rounded_rectangle((20,114,300,130),radius=8,fill=SURFACE)
    end=20+round((level-5)/95*280)
    d.rounded_rectangle((20,114,max(36,end),130),radius=8,fill=CORAL)
    d.ellipse((end-8,114,end+8,130),fill=FG)
    for left,value in ((16,25),(116,50),(216,100)):
        active=level==value
        d.rounded_rectangle((left,153,left+88,184),radius=8,fill=PLUM if active else SURFACE)
        label=f'%{value}';face=font(12,True)
        d.text((left+44-d.textlength(label,font=face)/2,160),label,font=face,fill=FG)
    d.rounded_rectangle((90,198,230,234),radius=10,fill=SALMON)
    d.text((139,204),'GERİ',font=font(16,True),fill=INK)
    return image


def render_sources(sources, pinned=None, page=0):
    choices=[None]+list(dict.fromkeys(sources))
    if pinned is not None and pinned not in choices:choices.append(pinned)
    pages=max(1,(len(choices)+3)//4);page=max(0,min(page,pages-1))
    image=Image.new('RGB',SIZE,BG);d=ImageDraw.Draw(image)
    d.text((16,12),'MEDYA KAYNAĞI',font=font(18,True),fill=FG)
    d.text((277,18),f'{page+1}/{pages}',font=font(10),fill=MUTED)
    for i,source in enumerate(choices[page*4:page*4+4]):
        top=43+i*38;selected=source==pinned
        d.rounded_rectangle((12,top,308,top+33),radius=8,fill=SURFACE,outline=CORAL if selected else SURFACE,width=1)
        label='Otomatik' if source is None else source_label(source)+(' · kapalı' if source not in sources else '')
        d.text((24,top+6),label,font=font(13,True),fill=FG)
        if selected:d.ellipse((285,top+13,292,top+20),fill=CORAL)
    for left,label in ((12,'ÖNCE'),(116,'GERİ'),(220,'SONRA')):
        enabled=label=='GERİ' or label=='ÖNCE' and page>0 or label=='SONRA' and page<pages-1
        d.rounded_rectangle((left,202,left+88,236),radius=8,fill=SALMON if label=='GERİ' else SURFACE)
        face=font(11,True)
        d.text((left+44-d.textlength(label,font=face)/2,211),label,font=face,fill=INK if label=='GERİ' else FG if enabled else MUTED)
    return image
