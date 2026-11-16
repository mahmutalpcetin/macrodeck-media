import bootstrap
import asyncio
from pathlib import Path
import queue
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import json
from unittest.mock import patch
from backend import MediaBackend
from brightness import BrightnessSettings
from interaction import InteractionState
from model import Track,DEFAULT_CONFIG
from source_settings import SourceSettings
from ui_settings import UiSettings

class Reader:
    instances=[]
    def __init__(self):
        self.sources=['Spotify','Chrome'];self.pinned_source=None;self.session=None;self.calls=[]
        self.instances.append(self)
    async def safe_read(self):
        await asyncio.sleep(0)
        source=self.pinned_source or 'Chrome'
        self.session=SimpleNamespace(source_app_user_model_id=source)
        return Track(title='Test track',artist='Test artist',source=source,available=True,supported_actions=('play_pause',))
    async def control(self,action):return await self.control_for(self.session,action)
    async def control_for(self,session,action):
        self.calls.append((session.source_app_user_model_id if session else None,action));return True

class Device:
    instances=[]
    fail_next=False
    def __init__(self,port):
        self.info={'device':'MacroDeck','protocol':3,'version':'test','backlight_pwm':True,'touch_enabled':True}
        self.on_touch=None;self.closed=False;self.levels=[];self.frames=[];self.instances.append(self)
    def request(self,value,kind):return dict(self.info)
    def configure(self,value):return {'type':'configured'}
    def brightness(self,value,persist=False):self.levels.append(value);return {'type':'brightness','value':value}
    def frame(self,image):
        if Device.fail_next:
            Device.fail_next=False;raise OSError('Injected USB error')
        time.sleep(.001);self.frames.append(image.copy())
        return {'bytes_sent':1000,'raw_bytes':153600,'regions':1,'elapsed_ms':1}
    def read_events(self):return []
    def close(self):self.closed=True

class Monitor:
    def sample(self):return {'cpu':12,'gpu':4,'ram':40}
    def close(self):pass

async def until(predicate,timeout=2):
    end=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>end:raise TimeoutError('Backend condition not reached')
        await asyncio.sleep(.01)

class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.commands=queue.Queue();self.messages=queue.Queue();self.stop=threading.Event()
        self.settings=BrightnessSettings(self.root/'brightness.json');self.settings.save(100)
        Reader.instances=[];Device.instances=[];Device.fail_next=False
        self.volume_calls=[]
        def volume(action,step):
            self.volume_calls.append((action,step));return {'level':41,'muted':False}
        self.patches=[patch('encoder.endpoint_volume',volume),patch('backend.output_device',lambda source:{'name':'Test Speaker','kind':'app'}),patch('backend.MediaReader',Reader),patch('backend.Device',Device),patch('backend.ResourceMonitor',Monitor),
                      patch('backend.find_device_port',lambda:'FAKE'),patch('backend.endpoint_volume',lambda:{'level':40,'muted':False})]
        for item in self.patches:item.start()
        self.backend=MediaBackend(SimpleNamespace(port='FAKE',demo=False),dict(DEFAULT_CONFIG),UiSettings(),self.settings,100,
                                  self.messages,self.commands,self.stop,self.root)
        self.commands.put(('connect','FAKE'))
        self.task=None
    async def asyncTearDown(self):
        self.stop.set()
        if self.task is not None:await asyncio.wait_for(self.task,3)
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()
    def start(self):self.task=asyncio.create_task(self.backend.run())
    def pointer(self,x,y,phase='down'):self.commands.put(('pointer',{'x':x,'y':y,'phase':phase}))

    async def test_tap_on_old_lcd_page_does_not_close_menu_still_transferring(self):
        from rendering import render_brightness
        from PIL import ImageChops
        (self.root/'touch-calibration.json').write_text(json.dumps([1,0,0,0,1,0]))
        self.start();await until(lambda:Device.instances and Device.instances[-1].frames)
        device=Device.instances[-1];original=device.frame
        entered=threading.Event();release=threading.Event()
        def delayed(image):
            entered.set();release.wait(2);return original(image)
        device.frame=delayed
        def tap(i,x,y):device.on_touch({'type':'touch','id':i,'raw_x':x,'raw_y':y,'event_ms':i*200,'received_at':time.monotonic()})
        try:
            tap(1,145,10)
            await until(entered.is_set)
            # The old media play area overlaps the new menu's Back button.
            tap(2,160,210)
            await asyncio.sleep(.04)
            release.set()
            await until(lambda:ImageChops.difference(device.frames[-1],render_brightness(100)).getbbox() is None)
            await asyncio.sleep(.15)
            self.assertIsNone(ImageChops.difference(device.frames[-1],render_brightness(100)).getbbox())
            self.assertEqual(Reader.instances[-1].calls,[])
        finally:release.set()

    async def test_card_reset_resets_encoder_ids_and_restores_brightness(self):
        self.start();await until(lambda:Device.instances and Device.instances[-1].frames)
        device=Device.instances[-1]
        device.on_touch({'type':'control','id':9,'action':'volume_up','event_ms':9000,'received_at':time.monotonic()})
        await until(lambda:len(self.volume_calls)==1)
        device.on_touch({'type':'device_reset','info':device.info})
        await asyncio.sleep(.03)
        device.on_touch({'type':'control','id':1,'action':'volume_up','event_ms':100,'received_at':time.monotonic()})
        await until(lambda:len(self.volume_calls)==2)
        self.assertFalse(self.task.done())
        self.assertTrue(device.frames)

    async def test_slow_media_does_not_block_encoder_volume_or_brightness_drag(self):
        started=asyncio.Event();release=asyncio.Event()
        async def slow_control(session,action):
            started.set();await release.wait();return True
        self.start();await until(lambda:Device.instances and Device.instances[-1].frames)
        Reader.instances[-1].control_for=slow_control
        self.commands.put(('media','play_pause'))
        await asyncio.wait_for(started.wait(),1)
        Device.instances[-1].on_touch({'type':'control','id':1,'action':'volume_up','event_ms':1000,'received_at':time.monotonic()})
        self.pointer(145,10);self.pointer(145,10,'up')
        self.pointer(103,120);self.pointer(103,120,'up')
        await until(lambda:self.volume_calls and Device.instances[-1].levels[-1]==33)
        self.assertFalse(release.is_set())
        self.assertEqual(self.settings.load(),33)
        release.set()

    async def test_fast_preview_drag_coalesces_and_saves_without_media_commands(self):
        self.pointer(145,10);self.pointer(145,10,'up')
        self.pointer(20,120)
        for x in range(30,201,10):self.pointer(x,120,'move')
        self.pointer(200,120,'up')
        self.start()
        await until(lambda:Device.instances and Device.instances[-1].frames)
        self.assertEqual(self.settings.load(),66)
        self.assertEqual(Device.instances[-1].levels[-1],66)
        self.assertLessEqual(len(Device.instances[-1].levels),2)
        self.assertEqual(Reader.instances[-1].calls,[])

    async def test_source_menu_selects_source_and_never_plays_it(self):
        self.start();await until(lambda:Device.instances and Device.instances[-1].frames)
        self.pointer(40,10);self.pointer(40,10,'up');self.pointer(100,95);self.pointer(100,95,'up')
        await until(lambda:SourceSettings(self.root/'source.json').load()=='Spotify')
        self.assertEqual(Reader.instances[-1].calls,[])

    async def test_usb_failure_recovers_through_auto_button(self):
        Device.fail_next=True
        self.start();await until(lambda:Device.instances and Device.instances[0].closed)
        self.commands.put(('auto_connect',None))
        await until(lambda:len(Device.instances)>1 and Device.instances[-1].frames)
        self.assertFalse(Device.instances[-1].closed)
        self.assertFalse(self.task.done())

    async def test_idle_dimming_wakes_without_changing_saved_brightness(self):
        class AlreadyIdle(InteractionState):
            def __init__(self,now,idle_seconds):
                super().__init__(now,idle_seconds);self.last_activity=now-100
        with patch('backend.InteractionState',AlreadyIdle):
            self.start()
            await until(lambda:Device.instances and 15 in Device.instances[-1].levels)
            self.pointer(150,200)
            await until(lambda:Device.instances[-1].levels[-1]==100)
            self.assertEqual(Reader.instances[-1].calls,[])
            self.assertEqual(self.settings.load(),100)
