"""Read-only Windows resource sampling; NVIDIA GPU utilization when available."""
import ctypes as c
import os
from pathlib import Path
import threading
import shutil
import subprocess

class MemoryStatus(c.Structure):
    _fields_ = [('length',c.c_uint32),('load',c.c_uint32)] + [(name,c.c_uint64) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]


def cpu_usage(previous, current):
    if previous is None:return None
    idle = current[0]-previous[0]
    total = current[1]+current[2]-previous[1]-previous[2]
    if total <= 0 or idle < 0:return None
    return round(max(0,min(100,100*(total-idle)/total)))


def gpu_value(output):
    values=[]
    for line in output.splitlines():
        try:
            value=float(line.strip())
            if 0 <= value <= 100:values.append(value)
        except ValueError:pass
    return round(max(values)) if values else None


class GpuUtilization(c.Structure):
    _fields_=[('gpu',c.c_uint32),('memory',c.c_uint32)]


class NativeGpu:
    """Read-only NVML calls from the already-installed NVIDIA driver."""
    def __init__(self):
        self.library=None;self.handles=[]
        paths=[Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/nvml.dll',
               Path(os.environ.get('ProgramW6432',r'C:\Program Files'))/'NVIDIA Corporation/NVSMI/nvml.dll']
        library_path=next((path for path in paths if path.is_file()),None)
        if library_path is None:return
        library=None;initialized=False
        try:
            library=c.CDLL(str(library_path))
            library.nvmlInit_v2.argtypes=[];library.nvmlInit_v2.restype=c.c_int
            library.nvmlShutdown.argtypes=[];library.nvmlShutdown.restype=c.c_int
            if library.nvmlInit_v2()!=0:return
            initialized=True
            library.nvmlDeviceGetCount_v2.argtypes=[c.POINTER(c.c_uint32)]
            library.nvmlDeviceGetCount_v2.restype=c.c_int
            library.nvmlDeviceGetHandleByIndex_v2.argtypes=[c.c_uint32,c.POINTER(c.c_void_p)]
            library.nvmlDeviceGetHandleByIndex_v2.restype=c.c_int
            library.nvmlDeviceGetUtilizationRates.argtypes=[c.c_void_p,c.POINTER(GpuUtilization)]
            library.nvmlDeviceGetUtilizationRates.restype=c.c_int
            count=c.c_uint32()
            if library.nvmlDeviceGetCount_v2(c.byref(count))!=0:return
            for index in range(min(count.value,64)):
                handle=c.c_void_p()
                if library.nvmlDeviceGetHandleByIndex_v2(index,c.byref(handle))==0:self.handles.append(handle)
            if self.handles:self.library=library
        except (OSError,AttributeError):pass
        finally:
            if initialized and self.library is None:library.nvmlShutdown()

    def sample(self):
        values=[]
        if self.library is not None:
            for handle in self.handles:
                value=GpuUtilization()
                if self.library.nvmlDeviceGetUtilizationRates(handle,c.byref(value))==0 and value.gpu<=100:
                    values.append(value.gpu)
        return max(values) if values else None

    def close(self):
        if self.library is not None:
            self.library.nvmlShutdown();self.library=None
        self.handles=[]


class ResourceMonitor:
    def __init__(self):
        self.previous=None
        self.lock=threading.Lock()
        self.native_gpu=NativeGpu()
        self.gpu_tool=shutil.which('nvidia-smi')

    def sample(self):
        with self.lock:return self._sample()

    def close(self):
        with self.lock:self.native_gpu.close()

    def _sample(self):
        result={'cpu':None,'gpu':None,'ram':None}
        kernel=c.WinDLL('kernel32',use_last_error=True)
        idle=c.c_uint64();system=c.c_uint64();user=c.c_uint64()
        if kernel.GetSystemTimes(c.byref(idle),c.byref(system),c.byref(user)):
            current=(idle.value,system.value,user.value)
            result['cpu']=cpu_usage(self.previous,current);self.previous=current
        memory=MemoryStatus();memory.length=c.sizeof(memory)
        if kernel.GlobalMemoryStatusEx(c.byref(memory)):result['ram']=int(memory.load)
        result['gpu']=self.native_gpu.sample()
        if result['gpu'] is None and self.gpu_tool:
            try:
                run=subprocess.run([self.gpu_tool,'--query-gpu=utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2,creationflags=subprocess.CREATE_NO_WINDOW)
                if run.returncode==0:result['gpu']=gpu_value(run.stdout)
            except (OSError,subprocess.TimeoutExpired):pass
        return result
