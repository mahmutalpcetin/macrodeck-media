import bootstrap
import argparse
import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import ImageTk, Image
from media import MediaReader,source_label
from model import Track, ACTION_NAMES, DEFAULT_CONFIG, validate_config
from protocol import Device,ports
from rendering import render
from brightness import BrightnessSettings
from desktop_ui import build_ui, IDLE_CHOICES
from ui_settings import UiSettings,load_ui_settings,save_ui_settings
from backend import MediaBackend
from storage import atomic_json
from ui_mailbox import UiMailbox
import startup
import theme

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "settings.json"
TOUCH_SETTINGS = ROOT / "touch-calibration.json"
LOG = logging.getLogger("macrodeck")
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    handler = RotatingFileHandler(ROOT / "macrodeck.log", maxBytes=200000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)


def read_config():
    try:
        return validate_config(json.loads(SETTINGS.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError):
        return validate_config(DEFAULT_CONFIG)


def demo_track():
    return Track("Geceye Bir Şarkı", "Örnek sanatçı · Türkçe karakter testi", "Önizleme — gerçek parça değil",
                 playing=True, available=True, position=78, duration=243, demo=True)


class App:
    def __init__(self,args):
        self.args=args
        self.root=tk.Tk()
        self.root.report_callback_exception=self.callback_error
        self.messages=UiMailbox();self.commands=queue.Queue();self.stop=threading.Event()
        self.config=read_config()
        self.ui_settings=load_ui_settings(ROOT/'ui-settings.json')
        self.brightness_settings=BrightnessSettings(ROOT/'brightness.json')
        self.brightness_initial=self.brightness_settings.load()
        self.brightness_timer=None;self._resize_timer=None
        self._last_image=None;self._preview_size=(640,480);self._pointer_down=False
        self._source_state=None
        self.status=tk.StringVar(value='Kart otomatik aranıyor · Önizleme hazır')
        build_ui(self)
        icon=ROOT/'assets/macrodeck.ico'
        if icon.exists():self.root.iconbitmap(str(icon))
        self.refresh_ports();self.show_image(render(Track()))
        self.tray_events=queue.SimpleQueue();self.tray=None
        if getattr(args,'tray',True):
            try:
                from tray import TrayIcon
                self.tray=TrayIcon(icon,self.tray_events)
                if not self.tray.start():
                    LOG.warning('Bildirim alanı kullanılamıyor: %s',self.tray.error)
                    self.tray=None
            except Exception:
                LOG.exception('Bildirim alanı kullanılamıyor');self.tray=None
        self.hide_button.configure(state='normal' if self.tray else 'disabled')
        self.root.protocol('WM_DELETE_WINDOW',self.window_close)
        self.root.bind('<Unmap>',self.window_unmapped,add='+')
        self.backend=MediaBackend(args,self.config,self.ui_settings,self.brightness_settings,self.brightness_initial,
                                  self.messages,self.commands,self.stop)
        self.thread=threading.Thread(target=self.run_worker,daemon=True)
        self.thread.start();self.root.after(50,self.poll)
        if args.port:self.commands.put(('connect',args.port))
        if args.minimized:
            if self.tray:self.root.after_idle(self.hide_window)
            else:self.root.iconify()

    def hide_window(self):
        if getattr(self,'_closing',False):return
        if self.tray and self.tray.available:self.root.withdraw()

    def show_window(self):
        if getattr(self,'_closing',False):return
        self.root.deiconify();self.root.lift()
        self.root.focus_force()
        self.redraw_preview()

    def window_close(self):
        if self.tray and self.tray.available:self.hide_window()
        else:self.close()

    def window_unmapped(self,event):
        if event.widget is self.root and self.root.state()=='iconic' and self.tray and self.tray.available:
            self.root.after_idle(self.hide_window)

    def run_worker(self):
        try:asyncio.run(self.backend.run())
        except Exception:
            LOG.exception('Arka plan işlemi beklenmedik biçimde durdu')
            self.messages.put(('device',None))
            self.messages.put(('status','Arka plan işlemi durdu. Bağlantı sekmesindeki Otomatik düğmesiyle yeniden başlatabilirsin.'))

    def ensure_backend(self):
        if self.thread.is_alive():return
        self.backend=MediaBackend(self.args,read_config(),self.ui_settings,self.brightness_settings,self.brightness_settings.load(),
                                  self.messages,self.commands,self.stop)
        self.thread=threading.Thread(target=self.run_worker,daemon=True);self.thread.start()

    def auto_connect(self):
        self.ensure_backend();self.commands.put(('auto_connect',None))

    def save_report(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='Tanılama raporunu kaydet',
                 defaultextension='.json',initialfile='macrodeck-tanilama.json',filetypes=[('JSON raporu','*.json')])
        if not path:return
        try:
            from dataclasses import asdict
            state=self.backend.snapshot();state.pop('last_notice',None)
            report={'application':'MacroDeck','version':'2.0.0','device':state,'screen':asdict(self.ui_settings)}
            atomic_json(path,report);self.status.set('Tanılama raporu kaydedildi.')
        except (OSError,ValueError) as exc:messagebox.showerror('Rapor kaydedilemedi',str(exc))

    def resize_preview(self,event=None):
        if getattr(self,'_closing',False):return
        if self._resize_timer is not None:self.root.after_cancel(self._resize_timer)
        self._resize_timer=self.root.after(80,self.redraw_preview)

    def redraw_preview(self):
        if getattr(self,'_closing',False):return
        self._resize_timer=None
        if self._last_image is not None:self.show_image(self._last_image)

    def preview_pointer(self,event,phase):
        if phase=='down':self._pointer_down=True
        elif not self._pointer_down:return
        width,height=self._preview_size
        x=max(0,min(319,event.x*320/max(1,width)))
        y=max(0,min(239,event.y*240/max(1,height)))
        self.commands.put(('pointer',{'x':x,'y':y,'phase':phase}))
        if phase=='up':self._pointer_down=False

    def choose_source(self,event=None):
        index=self.source_combo.current()
        if 0 <= index < len(self.source_ids):self.commands.put(('select_source',self.source_ids[index]))

    def save_display_preferences(self):
        try:
            settings=UiSettings.validate({'idle_seconds':IDLE_CHOICES[self.idle_var.get()],
                'dim_enabled':self.dim_enabled_var.get(),'dim_percent':self.dim_percent_var.get()})
            save_ui_settings(ROOT/'ui-settings.json',settings)
            self.ui_settings=settings;self.commands.put(('ui_settings',settings))
        except (ValueError,KeyError,OSError,tk.TclError) as exc:
            messagebox.showerror('Ekran ayarı',str(exc))

    def update_sources(self,sources,pinned):
        state=(tuple(sources),pinned)
        if state==self._source_state:return
        self._source_state=state
        self.source_ids=[None]+list(dict.fromkeys(sources))
        if pinned is not None and pinned not in self.source_ids:self.source_ids.append(pinned)
        labels=['Otomatik']+[source_label(source)+(' · kapalı' if source not in sources else '') for source in self.source_ids[1:]]
        self.source_combo.configure(values=labels)
        self.source_combo.current(self.source_ids.index(pinned))

    def update_track(self,track):
        self.track_title.set(track.title[:512]);self.track_artist.set(track.artist[:512])
        for action,button in self.media_buttons.items():
            button.configure(state='normal' if track.available and action in track.supported_actions else 'disabled')
        self.media_buttons['play_pause'].configure(text='Duraklat' if track.playing else 'Oynat')

    def brightness_changed(self,value):
        level=max(5,min(100,round(float(value))))
        self.brightness_label.set(f"%{level}")
        if self.brightness_timer is not None:self.root.after_cancel(self.brightness_timer)
        self.brightness_timer=self.root.after(150,lambda:self.queue_brightness(level))

    def queue_brightness(self,level):
        if self.brightness_timer is not None:self.root.after_cancel(self.brightness_timer)
        self.brightness_timer=None
        self.brightness_var.set(level);self.brightness_label.set(f'%{level}')
        self.commands.put(('brightness',level))

    def toggle_startup(self):
        try:
            startup.set_enabled(self.autostart.get())
        except OSError as exc:
            self.autostart.set(startup.enabled())
            messagebox.showerror("MacroDeck",str(exc))

    def refresh_ports(self):
        choices = [p for p, _ in ports()]
        self.port_box["values"] = choices
        if self.port.get() not in choices:
            self.port.set(choices[0] if choices else "")

    def callback_error(self, kind, value, trace):
        LOG.error("Arayüz hatası", exc_info=(kind, value, trace))
        messagebox.showerror("MacroDeck", f"İşlem tamamlanamadı: {value}")

    def connect(self):
        self.ensure_backend()
        if self.port.get():
            self.commands.put(("connect", self.port.get()))
        else:
            self.status.set("Kart bulunamadı. USB kablosunu ve soketi kontrol et.")

    def save(self):
        config = validate_config({"keys": [ACTION_NAMES.index(v.get()) for v in self.key_vars],
                                  "invert": self.invert.get(), "steps": int(self.steps.get())})
        atomic_json(SETTINGS,config)
        self.commands.put(("config", config))

    def show_image(self,image):
        self._last_image=image
        if self.root.state()=='withdrawn':return
        width=self.preview_host.winfo_width()-24;height=self.preview_host.winfo_height()-24
        if width<32 or height<24:width,height=640,480
        scale=min(width/320,height/240,3)
        width=max(32,round(320*scale));height=max(24,round(240*scale))
        self._preview_size=(width,height)
        self.photo=ImageTk.PhotoImage(image.resize((width,height),Image.Resampling.NEAREST))
        self.preview.configure(image=self.photo)


    def poll(self):
        if self.stop.is_set():
            return
        while not self.tray_events.empty():
            action=self.tray_events.get_nowait()
            if action=='exit':self.close();return
            if action in ('show','unavailable'):
                self.show_window()
                if action=='unavailable':
                    self.hide_button.configure(state='disabled')
                    self.status.set('Bildirim simgesi kullanılamıyor; pencere açık tutuldu.')
        latest_image = None
        for _ in range(30):
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "image": latest_image = value
            elif kind == "status": self.status.set(value)
            elif kind == "brightness":
                self.brightness_var.set(value);self.brightness_label.set(f"%{value}")
            elif kind == 'sources':self.update_sources(*value)
            elif kind == 'track':self.update_track(value)
            elif kind == 'volume':
                self.volume_label.set('Sistem sesi: sessiz' if value['muted'] else f"Sistem sesi: %{value['level']}")
            elif kind == 'audio_output':
                prefix='Varsayılan çıkış: ' if value['kind']=='default' else 'Ses çıkışı: '
                name=' / '.join(value.get('devices',[])) if value['kind']=='multiple' else value.get('name')
                self.output_label.set(prefix+(name or 'Okunamadı'))
            elif kind == 'device':
                self.connection_label.set('●  Bağlı · '+value['port'] if value else '○  Cihaz bağlı değil')
                self.device_label.set('Kart yazılımı '+value.get('version','—') if value else 'Kart bekleniyor')
                if value:self.port.set(value['port'])
            elif kind == 'transfer':
                if value['raw_bytes']<=2:continue
                saved=round(100*(1-value['bytes_sent']/max(1,value['raw_bytes'])))
                self.transfer_label.set(f"Son güncelleme: {value['elapsed_ms']} ms · %{max(0,saved)} daha az veri")
        if latest_image is not None: self.show_image(latest_image)
        self.root.after(50, self.poll)


    def close(self):
        if getattr(self,'_closing',False):return
        self._closing=True
        if self.tray:self.tray.stop()
        if self.brightness_timer is not None:
            self.root.after_cancel(self.brightness_timer)
            self.brightness_timer=None
            try:self.brightness_settings.save(max(5,min(100,round(self.brightness_var.get()))))
            except (OSError,ValueError,tk.TclError):pass
        self.stop.set();self.root.withdraw()
        self._close_deadline=time.monotonic()+3
        self.finish_close()

    def finish_close(self):
        if not self.thread.is_alive() or time.monotonic() >= self._close_deadline:
            self.root.destroy()
        else:self.root.after(50,self.finish_close)

    def run(self):
        self.root.mainloop()


async def once(args):
    track = demo_track() if args.demo else await MediaReader().safe_read()
    print(json.dumps(track.summary(), ensure_ascii=True, indent=2))
    image = render(track)
    if args.snapshot:
        path = Path(args.snapshot); path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    if args.port:
        device = Device(args.port)
        try:
            print(json.dumps(device.info, indent=2))
            print(device.frame(image))
        finally:
            device.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MacroDeck medya ekranı")
    parser.add_argument("--port", help="Kullanıcı tarafından seçilen seri port")
    parser.add_argument("--minimized", action="store_true", help="Bildirim alanında gizli aç")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--once", action="store_true", help="Bir kez oku / gönder ve çık")
    parser.add_argument("--snapshot", help="PNG önizleme dosyası (--once ile)")
    args = parser.parse_args()
    if args.once:
        asyncio.run(once(args))
    else:
        from single_instance import acquire
        if acquire():App(args).run()
