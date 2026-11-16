"""Reproducible GUI gallery using only invented demo media."""
from pathlib import Path
import sys
from io import BytesIO
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'desktop'))
from PIL import Image,ImageDraw
from model import Track
from rendering import render,render_header_status,render_brightness,render_sources,render_volume,render_idle,font
from theme import BG,SURFACE,FG,MUTED,CORAL,SALMON,PLUM

OUT=ROOT/'docs';OUT.mkdir(exist_ok=True)
cover=Image.new('RGB',(400,400),PLUM);draw=ImageDraw.Draw(cover)
for radius in range(180,20,-12):
    draw.ellipse((200-radius,200-radius,200+radius,200+radius),outline=CORAL if radius%24==12 else SALMON,width=4)
draw.ellipse((172,172,228,228),fill=BG)
buffer=BytesIO();cover.save(buffer,format='PNG')
track=Track(title='Geceye Bir Şarkı',artist='Örnek sanatçı',album='Örnek albüm',source='Spotify',
            position=78,duration=243,playing=True,available=True,cover=buffer.getvalue(),demo=True)
resources={'cpu':24,'gpu':16,'ram':52}
media=render_header_status(render(track),resources=resources,source=track.source,output_name="USB Kulaklık")
screens=[('medya','Medya · uzun başlık ve kapak',media),
         ('kaynaklar','Kaynak seçimi',render_sources(['AppleMusic','Spotify','Chrome'])),
         ('parlaklik','Sürüklenebilir parlaklık',render_brightness(38)),
         ('ses','Ses değişimi',render_volume(media,72)),
         ('bekleme','Saat ve sistem kullanımı',render_idle(resources))]
wide=Image.new('RGB',(480,270),SURFACE);d=ImageDraw.Draw(wide)
d.rectangle((0,0,45,269),fill=CORAL);d.rectangle((434,0,479,269),fill=SALMON)
d.text((90,94),'GENİŞ VİDEO',font=font(30,True),fill=FG)
buf=BytesIO();wide.save(buf,format='PNG')
video=Track(title='Uzun bir video başlığı — kenarlar kesilmeden',artist='Örnek kanal',source='Chrome',
            position=124,duration=780,available=True,cover=buf.getvalue(),demo=True)
screens.append(('video','Video · küçük resim kesilmez',render_header_status(render(video),resources=resources,source='Chrome',output_name='USB Kulaklık')))
gallery=Image.new('RGB',(2040,1220),BG);gd=ImageDraw.Draw(gallery)
gd.text((32,16),'MacroDeck Medya 2.0',font=font(35,True),fill=FG)
gd.text((32,64),'Örnek içeriklerle arayüz görünümü · 320 × 240 cihaz ekranı',font=font(20),fill=MUTED)
for i,(name,title,im) in enumerate(screens):
    x=24+(i%3)*680;y=115+(i//3)*550
    gd.text((x,y),title,font=font(23,True),fill=FG)
    gallery.paste(im.resize((640,480),Image.Resampling.NEAREST),(x,y+40))
    im.save(OUT/f'{name}.png')
gallery.save(OUT/'arayuz-2.0.png')
print(OUT/'arayuz-2.0.png')
