"""COM transport for encoder media events and Windows volume keys."""
import asyncio
import ctypes
import logging
import sys
import time
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("vk",ctypes.c_uint16),("scan",ctypes.c_uint16),("flags",ctypes.c_uint32),
                ("time",ctypes.c_uint32),("extra",ctypes.c_size_t)]
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("x",ctypes.c_int32),("y",ctypes.c_int32),("data",ctypes.c_uint32),
                ("flags",ctypes.c_uint32),("time",ctypes.c_uint32),("extra",ctypes.c_size_t)]
class INPUT_UNION(ctypes.Union):
    _fields_ = [("keyboard",KEYBDINPUT),("mouse",MOUSEINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type",ctypes.c_uint32),("value",INPUT_UNION)]
def volume_inputs(action):
    keys={"volume_up":0xAF,"volume_down":0xAE}
    if action not in keys: raise ValueError("Geçersiz ses komutu")
    pair=(INPUT*2)()
    for index in range(2):
        pair[index].type=1
        pair[index].value.keyboard.vk=keys[action]
        pair[index].value.keyboard.flags=2 if index else 0
    return pair
def change_volume(action):
    pair=volume_inputs(action)
    if sys.platform != "win32": raise RuntimeError("Ses kontrolü Windows gerektirir.")
    user32=ctypes.WinDLL("user32",use_last_error=True)
    send=user32.SendInput
    send.argtypes=[ctypes.c_uint32,ctypes.POINTER(INPUT),ctypes.c_int]
    send.restype=ctypes.c_uint32
    if send(2,pair,ctypes.sizeof(INPUT)) != 2:
        raise ctypes.WinError(ctypes.get_last_error())
from volume import endpoint_volume, VolumeAcceleration
class EncoderRuntime:
    def __init__(self,notice=lambda message:None,volume=None,feedback=lambda level:None,dispatch=None):
        self.notice=notice;self.volume=volume;self.feedback=feedback;self.last_id=0
        self.dispatch=dispatch
        self.acceleration=VolumeAcceleration()
    def reset_connection(self):
        self.last_id=0
        self.acceleration.reset()
    async def handle(self,event,reader,demo=False):
        if event.get("type")!="control":return
        event_id=event.get("id")
        if type(event_id) is not int or event_id<=self.last_id:return
        self.last_id=event_id
        if demo or time.monotonic()-event.get("received_at",0)>2.5:return
        action=event.get("action")
        if action not in ("previous","next","play_pause","volume_up","volume_down","mute"):return
        try:
            if action.startswith("volume_") or action == "mute":
                stamp=event.get('event_ms')
                tick_time=stamp/1000 if type(stamp) is int and 0 <= stamp <= 0xffffffff else event['received_at']
                step = self.acceleration.step(action,tick_time) if action != "mute" else 1
                if self.volume is None:
                    level = await asyncio.to_thread(endpoint_volume,action,step)
                else:
                    level = await asyncio.to_thread(self.volume,action)
                if level is not None:self.feedback(level)
            else:
                if self.dispatch is not None:self.dispatch(reader,action)
                else:await reader.control(action)
            logging.getLogger("macrodeck").info("Encoder komutu: %s",action)
        except Exception as exc:
            self.notice(str(exc))
            logging.getLogger("macrodeck").warning("Encoder komutu uygulanamadı: %s",exc)
