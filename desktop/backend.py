"""Media/device event loop, independent of Tk and the desktop window."""
import asyncio
import logging
import math
from pathlib import Path
import time
from model import Track
from media import MediaReader,DisplayedControls,source_label
from protocol import Device,find_device_port
from rendering import render_volume,render_header_status,render_idle,render_brightness,render_sources
from touch_runtime import TouchRuntime
from encoder import EncoderRuntime
from volume import endpoint_volume
from audio_output import output_device
from resources import ResourceMonitor
from interaction import InteractionState
from brightness import BrightnessDrag,effective_brightness
from source_settings import SourceSettings
from touch import hit_test
from input_inbox import InputInbox

LOG=logging.getLogger('macrodeck')


def demo_track():
    return Track('Geceye Bir Şarkı','Örnek sanatçı · Türkçe karakter testi','Önizleme',
                 playing=True,available=True,position=78,duration=243,demo=True)


class MediaBackend:
    def __init__(self,args,config,ui_settings,brightness_settings,brightness_initial,messages,commands,stop,root=None):
        self.args=args;self.config=config;self.ui_settings=ui_settings
        self.brightness_settings=brightness_settings;self.brightness_initial=brightness_initial
        self.messages=messages;self.commands=commands;self.stop=stop
        self.root=Path(root) if root is not None else Path(__file__).resolve().parent
        self.diagnostics={'connected':False,'firmware':None,'last_frame':None,'last_notice':None,'gpu_reader':None}

    def snapshot(self):
        return dict(self.diagnostics)

    async def run(self):
        reader = MediaReader(); displayed_controls=DisplayedControls(reader); device = None; wanted_port = None
        source_settings=SourceSettings(self.root/'source.json')
        reader.pinned_source=source_settings.load()
        applied_brightness=None;brightness_preference_dirty=False
        auto_connect = not bool(self.args.port)
        retry_at = 0; demo = self.args.demo; config = self.config
        last_status = None; notice_until = 0
        track = Track(); last_image_bytes = None; last_sent_at = 0
        last_preview_bytes = None
        loop = asyncio.get_running_loop()
        touch_queue = InputInbox()

        def status(text, hold=0):
            nonlocal last_status, notice_until
            if hold: notice_until = time.monotonic() + hold
            if device is None:
                self.diagnostics['connected']=False
                self.messages.put(('device',None))
            if hold:self.diagnostics['last_notice']=text
            if text != last_status:
                LOG.info(text); self.messages.put(("status", text)); last_status = text

        screen_settings=self.ui_settings
        interaction = InteractionState(time.monotonic(),screen_settings.idle_seconds)
        last_composed = None; priority_image = None
        brightness_level=self.brightness_initial; brightness_panel=False
        source_panel=False;source_page=0;displayed_view=None
        control_tasks=set();media_lock=asyncio.Lock()
        brightness_drag=BrightnessDrag()
        pending_brightness=None; persist_brightness=False
        def drag_value(value,save=False):
            nonlocal brightness_level,pending_brightness,persist_brightness
            brightness_level=value;pending_brightness=value
            persist_brightness=persist_brightness or save
            self.messages.put(('brightness',value))
        async def motion(x,y,phase):
            interaction.touch(time.monotonic())
            if not brightness_panel:return
            value=brightness_drag.move(x,y,phase)
            if value is not None:drag_value(value,phase=='up')
        def select_source(selected):
            nonlocal track,priority_image
            interaction.touch(time.monotonic())
            track=Track(title='Kaynak açılıyor',artist=source_label(selected) if selected else 'Otomatik seçim',source=selected or '',supported_actions=())
            priority_image=None;displayed_controls.transitioning=True
            self.messages.put(('track',track))
            reader.pinned_source=selected;reader.session=None
            try:source_settings.save(selected)
            except OSError as exc:status(str(exc),4)
            status('Kaynak: '+(source_label(selected) if selected else 'Otomatik'),3)
            self.messages.put(('sources',(reader.sources,selected)))

        async def media_action(action,session,requested_at):
            if demo:return
            async with media_lock:
                if time.monotonic()-requested_at>2.5:return
                try:await reader.control_for(session,action)
                except Exception as exc:status(str(exc),4)

        def schedule_media(action,owner=None):
            if demo:return
            owner=owner or reader
            if getattr(owner,'transitioning',False):
                status('Kaynak değişiyor, kısa bir an bekle.',2);return
            if len(control_tasks)>=16:
                status('Medya kaynağı yanıt vermiyor.',3);return
            session=owner.session
            task=asyncio.create_task(media_action(action,session,time.monotonic()));control_tasks.add(task)
            task.add_done_callback(control_tasks.discard)

        async def navigate(x,y):
            nonlocal brightness_panel,source_panel,source_page
            if not (0<=x<320 and 0<=y<240):return True
            if interaction.touch(time.monotonic()):return True
            if brightness_panel:
                level=brightness_drag.begin(x,y)
                if level is not None:drag_value(level)
                elif 14<=x<=52 and 65<=y<=99:drag_value(max(5,brightness_level-5),True)
                elif 268<=x<=306 and 65<=y<=99:drag_value(min(100,brightness_level+5),True)
                elif 153<=y<=184:
                    for left,level in ((16,25),(116,50),(216,100)):
                        if left<=x<=left+88:drag_value(level,True);break
                elif 90<=x<=230 and 198<=y<=234:brightness_panel=False
                return True
            if source_panel:
                choices=[None]+list(dict.fromkeys(reader.sources))
                if reader.pinned_source is not None and reader.pinned_source not in choices:choices.append(reader.pinned_source)
                pages=max(1,(len(choices)+3)//4);source_page=min(source_page,pages-1)
                if 12<=x<=308 and 43<=y<195 and (y-43)%38<=33:
                    index=int((y-43)//38)+source_page*4
                    if 0<=index<len(choices):select_source(choices[index]);source_panel=False
                elif 202<=y<=236:
                    if 116<=x<=204:source_panel=False
                    elif 12<=x<=100:source_page=max(0,source_page-1)
                    elif 220<=x<=308:source_page=min(pages-1,source_page+1)
                return True
            if 112<=x<=187 and y<23:
                brightness_panel=True;return True
            if y<23 and x<112:
                source_panel=True;source_page=0;return True
            return False
        def current_view():
            if brightness_panel:return ('brightness',)
            if source_panel:return ('sources',source_page,tuple(reader.sources),reader.pinned_source)
            if interaction.idle:return ('idle',)
            return ('media',)

        async def hardware_navigate(x,y):
            # A tap belongs to the page the LCD has acknowledged, even if a new
            # menu is already visible in the faster desktop preview.
            if displayed_view != current_view():return True
            return await navigate(x,y)

        async def hardware_motion(x,y,phase):
            if displayed_view == current_view():await motion(x,y,phase)

        touch = TouchRuntime(self.root/'touch-calibration.json', lambda text: status(text, 4), navigate=hardware_navigate,motion=hardware_motion,dispatch=lambda owner,action:schedule_media(action,owner))
        volume_level = None; volume_until = 0
        audio_output_state=(None,{'name':None,'kind':'unavailable'})
        volume_shown = None; volume_muted = False; volume_anim_at = time.monotonic()
        def volume_feedback(state):
            nonlocal volume_level, volume_until, volume_muted, priority_image
            if time.monotonic() >= volume_until and last_composed is not None:
                priority_image = last_composed.copy()
            interaction.touch(time.monotonic())
            self.messages.put(('volume',state))
            volume_level = state['level']; volume_muted = state['muted']
            volume_until = time.monotonic() + 1.4
        encoder = EncoderRuntime(lambda text: status(text,4), feedback=volume_feedback,dispatch=lambda owner,action:schedule_media(action,owner))

        def enqueue_touch(source, event):
            touch_queue.push(source,event)

        async def touch_pump():
            nonlocal applied_brightness,last_image_bytes,priority_image,volume_until,displayed_view
            while True:
                source, event = await touch_queue.get()
                if device is source:
                    if event.get('type')=='device_reset':
                        applied_brightness=None;last_image_bytes=None;priority_image=None;volume_until=0
                        touch.reset_connection();encoder.reset_connection();brightness_drag.active=False
                        displayed_controls.commit(None)
                        displayed_view=None
                        self.diagnostics['firmware']=event.get('info',{}).get('version')
                        self.commands.put(('resync_device',source))
                        status('Kart yeniden başladı · Ekran yenileniyor',3)
                    elif event.get("type") == "control":
                        interaction.touch(time.monotonic())
                        if touch.calibration is None:
                            await encoder.handle(event,displayed_controls,demo)
                    else:
                        await touch.handle(event, displayed_controls, demo)

        resource_values = {}
        async def resource_pump():
            nonlocal resource_values
            monitor=await asyncio.to_thread(ResourceMonitor)
            self.diagnostics['gpu_reader']='driver' if getattr(getattr(monitor,'native_gpu',None),'library',None) is not None else 'fallback'
            try:
                while True:
                    try:resource_values=await asyncio.to_thread(monitor.sample)
                    except Exception:
                        resource_values={};LOG.debug('Resource read failed',exc_info=True)
                    await asyncio.sleep(3 if interaction.idle else 1)
            finally:await asyncio.to_thread(monitor.close)
        async def media_pump():
            nonlocal track
            while True:
                if touch.calibration is None:
                    try:
                        track = demo_track() if demo else await reader.safe_read()
                        self.messages.put(('track',track))
                        self.messages.put(('sources',(reader.sources,reader.pinned_source)))
                    except Exception:
                        LOG.debug("Media read failed",exc_info=True)
                        track = Track(title="Medya bilgisi alınamadı",artist="Müzik veya video aç")
                await asyncio.sleep(0.35)

        async def volume_pump():
            nonlocal volume_muted, volume_level, volume_shown
            while True:
                try:
                    state = await asyncio.to_thread(endpoint_volume)
                    self.messages.put(('volume',state))
                    volume_muted = state['muted']
                    if volume_level is None:
                        volume_level = state['level']; volume_shown = volume_level
                    elif volume_level != state['level']:
                        volume_feedback(state)
                except Exception:
                    LOG.debug("Volume read failed",exc_info=True)
                await asyncio.sleep(0.7)

        async def output_pump():
            nonlocal audio_output_state
            while True:
                source=track.source
                try:state=await asyncio.to_thread(output_device,source)
                except Exception:
                    state={'name':None,'kind':'unavailable'}
                    LOG.debug('Ses çıkışı okunamadı',exc_info=True)
                if source==track.source:
                    audio_output_state=(source,state)
                    self.messages.put(('audio_output',state))
                await asyncio.sleep(2)

        media_task = asyncio.create_task(media_pump())
        volume_task = asyncio.create_task(volume_pump())
        resource_task = asyncio.create_task(resource_pump())
        output_task = asyncio.create_task(output_pump())
        pump = asyncio.create_task(touch_pump())
        try:
            while not self.stop.is_set():
                while not self.commands.empty():
                    kind, value = self.commands.get_nowait()
                    if kind in ("connect", "disconnect"):
                        auto_connect = False
                        if device: await asyncio.to_thread(device.close)
                        device = None; wanted_port = value if kind == "connect" else None
                        self.diagnostics['connected']=False
                        self.messages.put(('device',None))
                        retry_at = 0; touch.reset_connection(); encoder.reset_connection(); last_image_bytes = None;displayed_view=None
                        if not wanted_port: status("Bağlantı kesildi · Önizleme açık")
                    elif kind == 'resync_device':
                        if device is value:
                            try:
                                info=await asyncio.to_thread(device.request,{'type':'hello'},'hello')
                                if info.get('device')!='MacroDeck' or info.get('protocol')!=3:raise RuntimeError('Kart yanıtı eşleşmedi.')
                                device.info=info;device.last_image=None
                                applied_brightness=None;last_image_bytes=None
                            except Exception as exc:
                                await asyncio.to_thread(device.close);device=None
                                retry_at=time.monotonic()+1;status(str(exc),3)
                    elif kind == 'auto_connect':
                        auto_connect=True;retry_at=0
                        status('Otomatik bağlantı açık',2)
                    elif kind == 'select_source':select_source(value)
                    elif kind == 'media':
                        interaction.touch(time.monotonic());schedule_media(value)
                    elif kind == 'pointer':
                        if touch.calibration is None:
                            if value['phase']=='down':
                                consumed=await navigate(value['x'],value['y'])
                                if not consumed:
                                    action=hit_test(value['x'],value['y'])
                                    if action:schedule_media(action)
                            else:await motion(value['x'],value['y'],value['phase'])
                    elif kind == 'ui_settings':
                        screen_settings=value;interaction.idle_seconds=value.idle_seconds
                        interaction.touch(time.monotonic());status('Ekran ayarları kaydedildi.',3)
                    elif kind == "demo":
                        demo = value
                    elif kind == "calibrate":
                        if not device or not device.info.get("touch_enabled"):
                            status("Önce dokunmatik destekli karta bağlan.", 4)
                        else:
                            brightness_panel=False;source_panel=False;brightness_drag.active=False
                            touch.start(); last_image_bytes = None
                    elif kind == "cancel_calibration":
                        touch.cancel(); last_image_bytes = None
                        status("Dokunmatik ayarı iptal edildi.", 3)
                    elif kind == "brightness":
                        interaction.touch(time.monotonic())
                        brightness_level=value
                        try:
                            self.brightness_settings.save(value)
                            brightness_preference_dirty=True
                            self.messages.put(('brightness',value))
                            status(f"Parlaklık %{value}" + ("" if device else " · Bağlanınca uygulanacak"),2)
                        except Exception as exc:
                            status(str(exc),4)
                    elif kind == "config":
                        config = value
                        if device:
                            try:
                                await asyncio.to_thread(device.configure, config)
                                status("Tuş ayarları kaydedildi.", 3)
                            except Exception as exc:
                                await asyncio.to_thread(device.close); device = None
                                status(str(exc), 4); retry_at = time.monotonic() + 3
                        else: status("Ayarlar kaydedildi; kart bağlanınca uygulanacak.", 3)

                if pending_brightness is not None:
                    value=pending_brightness;save_value=persist_brightness
                    pending_brightness=None;persist_brightness=False
                    try:
                        if save_value:
                            self.brightness_settings.save(value);brightness_preference_dirty=True
                    except Exception as exc:status(str(exc),4)

                if auto_connect and device is None and time.monotonic() >= retry_at:
                    wanted_port = await asyncio.to_thread(find_device_port)
                    if not wanted_port:retry_at=time.monotonic()+2
                if wanted_port and device is None and time.monotonic() >= retry_at:
                    try:
                        device = await asyncio.to_thread(Device, wanted_port)
                        source = device
                        device.on_touch = lambda event, source=source: loop.call_soon_threadsafe(enqueue_touch, source, event)
                        await asyncio.to_thread(device.configure, config)
                        if device.info.get('backlight_pwm'):
                            answer=await asyncio.to_thread(device.brightness,brightness_level,persist=True)
                            applied_brightness=brightness_level;brightness_preference_dirty=False
                            if answer.get('saved') is False:status('Parlaklık bilgisayarda kayıtlı; kart kaydı yapılamadı.',4)
                        touch.reset_connection(); encoder.reset_connection(); last_image_bytes = None
                        displayed_controls.commit(None)
                        displayed_view=None
                        self.diagnostics.update(connected=True,firmware=device.info.get('version'),port=wanted_port)
                        self.messages.put(('device',{'port':wanted_port,**device.info}))
                    except Exception as exc:
                        if device: await asyncio.to_thread(device.close)
                        device = None; retry_at = time.monotonic() + 4
                        status(f"USB bağlantısı bekleniyor: {exc}", 3)

                if device:
                    try:
                        await asyncio.to_thread(device.read_events)
                    except Exception as exc:
                        await asyncio.to_thread(device.close); device = None
                        touch.cancel(); retry_at = time.monotonic() + 4
                        status(f"USB: {exc}", 4)

                frame_session=reader.session
                image, target = touch.image(track)
                now = time.monotonic()
                if volume_level is not None:
                    if volume_shown is None: volume_shown = volume_level
                    blend = 1 - math.exp(-max(0,now-volume_anim_at)/0.12)
                    volume_shown += (volume_level-volume_shown)*blend
                    if abs(volume_level-volume_shown) < 0.2: volume_shown = volume_level
                volume_anim_at = now
                if touch.calibration is None:
                    volume_active = volume_level is not None and now < volume_until
                    idle = interaction.update(track.playing,now,volume_active)
                    if brightness_panel:
                        interaction.touch(now)
                        image=render_brightness(brightness_level)
                    elif source_panel:
                        interaction.touch(now)
                        image=render_sources(reader.sources,reader.pinned_source,source_page)
                    elif volume_active:
                        # Freeze art/header while turning: only the small volume strip changes.
                        image = render_volume(priority_image if priority_image is not None else image, volume_shown, volume_muted)
                    elif idle:
                        image = render_idle(resource_values,volume_muted,device is not None)
                    else:
                        output_name=audio_output_state[1].get('name') if audio_output_state[0]==track.source else None
                        image = render_header_status(image,volume_muted,resource_values,track.source,reader.pinned_source is not None,device is not None,output_name)
                is_idle=interaction.idle and not brightness_panel and not source_panel and touch.calibration is None
                frame_view=current_view()
                media_frame=touch.calibration is None and not brightness_panel and not source_panel and not is_idle and not volume_active
                target_brightness=effective_brightness(brightness_level,is_idle and screen_settings.dim_enabled,screen_settings.dim_percent)
                if device and device.info.get('backlight_pwm') and (target_brightness != applied_brightness or brightness_preference_dirty):
                    try:
                        answer=await asyncio.to_thread(device.brightness,target_brightness,persist=brightness_preference_dirty and not is_idle)
                        applied_brightness=target_brightness;brightness_preference_dirty=False
                        if answer.get('saved') is False:status('Parlaklık bilgisayarda kayıtlı; kart kaydı yapılamadı.',4)
                        LOG.info("Backlight: %s%% (%s)",target_brightness,"standby" if is_idle else "active")
                    except Exception as exc:
                        brightness_preference_dirty=False
                        status(str(exc),4)
                last_composed = image
                image_bytes = image.tobytes()
                if image_bytes != last_preview_bytes:
                    self.messages.put(("image",image)); last_preview_bytes = image_bytes
                if device and (image_bytes != last_image_bytes or time.monotonic() - last_sent_at >= 3):
                    try:
                        # Serial I/O stays on one worker; the event loop can handle
                        # media controls even while a cover image is transferring.
                        if media_frame and getattr(displayed_controls.session,'source_app_user_model_id',None)!=getattr(frame_session,'source_app_user_model_id',None):
                            displayed_controls.transitioning=True
                        frame_result = await asyncio.to_thread(device.frame, image)
                        displayed_view=frame_view
                        if media_frame:displayed_controls.commit(frame_session)
                        self.diagnostics['last_frame']=dict(frame_result)
                        self.messages.put(('transfer',frame_result))
                        if frame_result['elapsed_ms'] >= 500:
                            LOG.info("Display transfer: %s bytes / %s regions / %s ms",frame_result['bytes_sent'],frame_result['regions'],frame_result['elapsed_ms'])
                        touch.frame_sent(target)
                        last_image_bytes = image_bytes; last_sent_at = time.monotonic()
                        if time.monotonic() >= notice_until:
                            if touch.calibration is not None:
                                status(f"Dokunmatik ayarı · {len(touch.calibration)+1}/4 hedefe dokun")
                            elif touch.coefficients is None:
                                status("Bağlı · İlk kullanım için ‘Dokunmatik ayarla’")
                            else:
                                status("Bağlı · Dokunmatik hazır")
                    except Exception as exc:
                        await asyncio.to_thread(device.close); device = None
                        touch.cancel(); retry_at = time.monotonic() + 4
                        status(f"USB: {exc} · Yeniden bağlanılacak", 4)
                await asyncio.sleep(0.02 if brightness_panel or source_panel or time.monotonic() < volume_until else 0.12 if interaction.idle else 0.06)
        finally:
            tasks = (media_task,volume_task,resource_task,output_task,pump,*control_tasks)
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            self.diagnostics['connected']=False
            if device: await asyncio.to_thread(device.close)
