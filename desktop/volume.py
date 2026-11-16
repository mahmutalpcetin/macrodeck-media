"""Windows default output endpoint volume, in exact percentage steps."""
import ctypes as c
from uuid import UUID

class GUID(c.Structure):
    _fields_=[('data',c.c_ubyte*16)]
    def __init__(self,value):
        super().__init__();self.data[:]=UUID(value).bytes_le

def endpoint_volume(action='read', step=1):
    if action not in ('volume_up','volume_down','mute','read'):raise ValueError(action)
    if type(step) is not int or not 1 <= step <= 9:raise ValueError('Invalid volume step')
    ole=c.WinDLL('ole32')
    ole.CoInitializeEx.argtypes=[c.c_void_p,c.c_uint32];ole.CoInitializeEx.restype=c.c_long
    ole.CoUninitialize.argtypes=[];ole.CoUninitialize.restype=None
    initialized=ole.CoInitializeEx(None,0)
    if initialized<0 and (initialized & 0xffffffff)!=0x80010106:
        raise OSError('Windows ses arabirimi başlatılamadı')
    owns_apartment=initialized in (0,1)
    objects=[]
    def call(obj,index,types,*args):
        table=c.cast(obj,c.POINTER(c.POINTER(c.c_void_p))).contents
        fn=c.WINFUNCTYPE(c.c_long,c.c_void_p,*types)(table[index])
        result=fn(obj,*args)
        if result<0:raise OSError(f'Audio HRESULT {result & 0xffffffff:08x}')
    try:
        enum=c.c_void_p();device=c.c_void_p();volume=c.c_void_p()
        cls=GUID('bcde0395-e52f-467c-8e3d-c4579291692e');iid=GUID('a95664d2-9614-4f35-a746-de8db63617e6')
        ole.CoCreateInstance.argtypes=[c.POINTER(GUID),c.c_void_p,c.c_uint32,c.POINTER(GUID),c.POINTER(c.c_void_p)]
        ole.CoCreateInstance.restype=c.c_long
        result=ole.CoCreateInstance(c.byref(cls),None,23,c.byref(iid),c.byref(enum))
        if result<0:raise OSError('Ses aygıtı açılamadı')
        objects.append(enum)
        call(enum,4,[c.c_int,c.c_int,c.POINTER(c.c_void_p)],0,1,c.byref(device));objects.append(device)
        endpoint=GUID('5cdf2c82-841e-4546-9722-0cf74078229a')
        call(device,3,[c.POINTER(GUID),c.c_uint32,c.c_void_p,c.POINTER(c.c_void_p)],c.byref(endpoint),23,None,c.byref(volume));objects.append(volume)
        level=c.c_float();call(volume,9,[c.POINTER(c.c_float)],c.byref(level))
        muted=c.c_int();call(volume,15,[c.POINTER(c.c_int)],c.byref(muted))
        if action == 'mute':
            call(volume,14,[c.c_int,c.c_void_p],not muted.value,None)
        elif action != 'read':
            percent=max(0,min(100,round(level.value*100)+(step if action=='volume_up' else -step)))
            call(volume,7,[c.c_float,c.c_void_p],percent/100,None)
        call(volume,9,[c.POINTER(c.c_float)],c.byref(level))
        call(volume,15,[c.POINTER(c.c_int)],c.byref(muted))
        return {'level':round(level.value*100),'muted':bool(muted.value)}
    finally:
        for obj in reversed(objects):
            table=c.cast(obj,c.POINTER(c.POINTER(c.c_void_p))).contents
            c.WINFUNCTYPE(c.c_ulong,c.c_void_p)(table[2])(obj)
        if owns_apartment:ole.CoUninitialize()


def change_volume_percent(action,step=1):
    return endpoint_volume(action,step)['level']


class VolumeAcceleration:
    """Require consecutive fast ticks; reset immediately on direction changes."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.last_time = None
        self.direction = None
        self.fast_ticks = 0

    def step(self, action, now):
        elapsed = now-self.last_time if self.last_time is not None else None
        if action != self.direction or elapsed is None or elapsed <= 0 or elapsed > 0.18:
            self.fast_ticks = 0
            result = 1
        else:
            self.fast_ticks += 1
            result = 1 if self.fast_ticks < 2 else (9 if elapsed < 0.030 else 7 if elapsed < 0.045 else 5 if elapsed < 0.065 else 3 if elapsed < 0.12 else 2)
        self.last_time = now
        self.direction = action
        return result
