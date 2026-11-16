"""Read-only Windows output-device names and per-application audio sessions."""
import ctypes as c
from pathlib import PureWindowsPath
from volume import GUID

class PROPERTYKEY(c.Structure):
    _fields_=[('fmtid',GUID),('pid',c.c_uint32)]
class BLOB(c.Structure):
    _fields_=[('size',c.c_uint32),('data',c.c_void_p)]
class VALUE(c.Union):
    _fields_=[('text',c.c_wchar_p),('blob',BLOB),('number',c.c_uint64)]
class PROPVARIANT(c.Structure):
    _fields_=[('vt',c.c_uint16),('reserved',c.c_uint16*3),('value',VALUE)]


def choose_output(source,endpoints,default_name):
    source=(source or '').lower()
    tokens=('applemusic','spotify','chrome','msedge','firefox','brave','vlc')
    token=next((token for token in tokens if token in source),None)
    if token:
        for field in ('active','sessions'):
            matches=list(dict.fromkeys(item['name'] for item in endpoints
                         if any(token in process.lower() for process in item[field])))
            if len(matches)==1:return {'name':matches[0],'kind':'app'}
            if len(matches)>1:return {'name':'Birden çok çıkış','kind':'multiple','devices':matches}
    return {'name':default_name,'kind':'default' if default_name else 'unavailable'}


def output_device(source=''):
    ole=c.WinDLL('ole32');kernel=c.WinDLL('kernel32',use_last_error=True)
    ole.CoInitializeEx.argtypes=[c.c_void_p,c.c_uint32];ole.CoInitializeEx.restype=c.c_long
    ole.CoUninitialize.argtypes=[];ole.CoUninitialize.restype=None
    ole.PropVariantClear.argtypes=[c.POINTER(PROPVARIANT)];ole.PropVariantClear.restype=c.c_long
    ole.CoCreateInstance.argtypes=[c.POINTER(GUID),c.c_void_p,c.c_uint32,c.POINTER(GUID),c.POINTER(c.c_void_p)]
    ole.CoCreateInstance.restype=c.c_long
    kernel.OpenProcess.argtypes=[c.c_uint32,c.c_int,c.c_uint32];kernel.OpenProcess.restype=c.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes=[c.c_void_p,c.c_uint32,c.c_wchar_p,c.POINTER(c.c_uint32)]
    kernel.QueryFullProcessImageNameW.restype=c.c_int
    kernel.CloseHandle.argtypes=[c.c_void_p];kernel.CloseHandle.restype=c.c_int
    hr=ole.CoInitializeEx(None,0)
    if hr<0 and (hr&0xffffffff)!=0x80010106:raise OSError('Ses cihazları okunamadı')
    owned=hr in (0,1);objects=[];processes={}
    def call(obj,index,types,*args):
        table=c.cast(obj,c.POINTER(c.POINTER(c.c_void_p))).contents
        result=c.WINFUNCTYPE(c.c_long,c.c_void_p,*types)(table[index])(obj,*args)
        if result<0:raise OSError(f'Audio output HRESULT {result&0xffffffff:08x}')
    def pointer(obj,index,types=(),args=()):
        result=c.c_void_p();call(obj,index,[*types,c.POINTER(c.c_void_p)],*args,c.byref(result))
        objects.append(result);return result
    def name(device):
        store=pointer(device,4,[c.c_uint32],[0])
        key=PROPERTYKEY(GUID('a45c254e-df1c-4efd-8020-67d146a850e0'),14);value=PROPVARIANT()
        try:
            call(store,5,[c.POINTER(PROPERTYKEY),c.POINTER(PROPVARIANT)],c.byref(key),c.byref(value))
            return str(value.value.text or '') if value.vt==31 else ''
        finally:ole.PropVariantClear(c.byref(value))
    def process_name(pid):
        if pid not in processes:
            text='';handle=kernel.OpenProcess(0x1000,False,pid)
            if handle:
                try:
                    buf=c.create_unicode_buffer(32768);size=c.c_uint32(len(buf))
                    if kernel.QueryFullProcessImageNameW(handle,0,buf,c.byref(size)):text=PureWindowsPath(buf.value).name
                finally:kernel.CloseHandle(handle)
            processes[pid]=text
        return processes[pid]
    try:
        enum=c.c_void_p()
        cls=GUID('bcde0395-e52f-467c-8e3d-c4579291692e');iid=GUID('a95664d2-9614-4f35-a746-de8db63617e6')
        if ole.CoCreateInstance(c.byref(cls),None,23,c.byref(iid),c.byref(enum))<0:raise OSError('Ses cihazları açılamadı')
        objects.append(enum);default=None
        try:default=name(pointer(enum,4,[c.c_int,c.c_int],[0,1]))
        except OSError:pass
        devices=pointer(enum,3,[c.c_int,c.c_uint32],[0,1])
        count=c.c_uint32();call(devices,3,[c.POINTER(c.c_uint32)],c.byref(count))
        endpoints=[]
        for index in range(min(count.value,128)):
            try:
                device=pointer(devices,4,[c.c_uint32],[index]);label=name(device)
                if not label:continue
                manager_id=GUID('77aa99a0-1bd6-484f-8bc7-2c654c9a9b6f')
                manager=pointer(device,3,[c.POINTER(GUID),c.c_uint32,c.c_void_p],[c.byref(manager_id),23,None])
                sessions=pointer(manager,5);size=c.c_int();call(sessions,3,[c.POINTER(c.c_int)],c.byref(size))
                item={'name':label,'active':set(),'sessions':set()}
                for index in range(min(size.value,256)):
                    try:
                        control=pointer(sessions,4,[c.c_int],[index]);state=c.c_int()
                        call(control,3,[c.POINTER(c.c_int)],c.byref(state))
                        if state.value not in (0,1):continue
                        control_id=GUID('bfb7ff88-7239-4fc9-8fa2-07c950be9c6d')
                        extended=pointer(control,0,[c.POINTER(GUID)],[c.byref(control_id)])
                        pid=c.c_uint32();call(extended,14,[c.POINTER(c.c_uint32)],c.byref(pid))
                        process=process_name(pid.value)
                        if process:
                            item['sessions'].add(process)
                            if state.value==1:item['active'].add(process)
                    except OSError:continue
                endpoints.append(item)
            except OSError:continue
        return choose_output(source,endpoints,default)
    finally:
        for obj in reversed(objects):
            table=c.cast(obj,c.POINTER(c.POINTER(c.c_void_p))).contents
            c.WINFUNCTYPE(c.c_ulong,c.c_void_p)(table[2])(obj)
        if owned:ole.CoUninitialize()
