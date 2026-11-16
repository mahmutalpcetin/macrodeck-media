import bootstrap
import json
import time
import zlib
from pathlib import Path
from collections import deque
import serial
from PIL import ImageChops
from serial.tools import list_ports
from model import validate_config
from rendering import rgb565
from frame_codec import encode_frame
from storage import atomic_json

DEVICE_PROFILE=Path(__file__).with_name('device.json')

def _approved_ports():
    try:
        profile=json.loads(DEVICE_PROFILE.read_text(encoding='utf-8'))
        if not isinstance(profile,dict) or not isinstance(profile.get('serial'),str) or not profile['serial']:return []
        if any(type(profile.get(key)) is not int for key in ('vid','pid')):return []
    except (OSError,ValueError,TypeError):return []
    return [p for p in list_ports.comports() if p.vid==profile['vid'] and p.pid==profile['pid'] and p.serial_number==profile['serial']]

def remember_device(port):
    # Called only after a user-selected port has returned a valid MacroDeck hello.
    match=next((p for p in list_ports.comports() if p.device==port),None)
    if match and match.vid is not None and match.pid is not None and match.serial_number:
        atomic_json(DEVICE_PROFILE,{'vid':match.vid,'pid':match.pid,'serial':match.serial_number})


def ports():
    return [(p.device, p.description) for p in list_ports.comports()]


def find_device_port():
    # First connection is manual; subsequent launches reconnect only the approved identity.
    matches=[p.device for p in _approved_ports()]
    return matches[0] if len(matches)==1 else None


def is_project_uart(port):
    return any(p.device==port and p.vid==0x1A86 and p.pid==0x55D3 for p in _approved_ports())


def dirty_regions(image, previous):
    """Keep independent header/art/progress/buttons updates off unchanged rows."""
    if previous is None:return [(0,0,320,240)]
    diff = ImageChops.difference(image,previous)
    whole = diff.getbbox()
    if whole is None:return [(0,0,1,1)]
    regions=[]
    for y in range(whole[1],whole[3]):
        row=diff.crop((0,y,320,y+1)).getbbox()
        if row:
            box=(row[0],y,row[2],y+1)
            if regions and regions[-1][3]==y:
                old=regions[-1];regions[-1]=(min(old[0],box[0]),old[1],max(old[2],box[2]),y+1)
            else:regions.append(box)
    area=lambda b:(b[2]-b[0])*(b[3]-b[1])
    def union(a,b):return (min(a[0],b[0]),a[1],max(a[2],b[2]),b[3])
    # Merge adjacent row groups only when saved command overhead outweighs pixels.
    while len(regions)>1:
        costs=[area(union(a,b))-area(a)-area(b) for a,b in zip(regions,regions[1:])]
        index=min(range(len(costs)),key=costs.__getitem__)
        if costs[index]>512:break
        regions[index:index+2]=[union(regions[index],regions[index+1])]
    if sum(area(b) for b in regions)+512*(len(regions)-1)>=area(whole):return [whole]
    return regions


class Device:
    def __init__(self, port):
        self.port = serial.Serial()
        self.port.port = port; self.port.baudrate = 921600
        self.port.timeout = 0.1; self.port.write_timeout = 8
        self.port.dtr = True; self.port.rts = False
        self.port.open()
        # USB-UART open can reset ESP32; native CDC does not use this reset circuit.
        time.sleep(1.5)
        # Clear any incomplete text header left by a reset during binary transfer.
        self.port.write(b'\n');time.sleep(0.03)
        self.port.reset_input_buffer()
        self.sequence = 0
        self.last_image = None
        self.on_touch = None
        try:
            self.send({'type':'hello'})
            try:self.info=self.wait('hello',timeout=2.5)
            except (TimeoutError,RuntimeError):
                # A previous process can have exited halfway through a binary
                # frame. Only the identified project UART may be reset here.
                if not is_project_uart(port):raise
                self.port.dtr=False;self.port.rts=True;time.sleep(.1)
                self.port.rts=False;time.sleep(1.5);self.port.dtr=True
                self.port.reset_input_buffer();self._rx_line=bytearray()
                self.info=self.request({'type':'hello'},'hello')
            if self.info.get("device") != "MacroDeck" or self.info.get("protocol") != 3:
                raise ValueError("Bu portta uyumlu MacroDeck yazılımı yok.")
            try:remember_device(port)
            except OSError:pass # Manual connection remains usable if preferences are read-only.
        except Exception:
            self.close()
            raise

    def close(self):
        self.port.close()

    def send(self, obj):
        self.port.write(json.dumps(obj, separators=(",", ":")).encode("ascii") + b"\n")

    def _read_message(self):
        if not hasattr(self, "_rx_line"):
            self._rx_line = bytearray()
        if b"\n" not in self._rx_line:
            available=getattr(self.port,'in_waiting',0)
            chunk=self.port.read(min(4096,available) if available else 1)
            if not chunk:return None
            self._rx_line.extend(chunk)
        if b"\n" in self._rx_line:
            line,_,rest=self._rx_line.partition(b"\n")
            self._rx_line=bytearray(rest)
            if len(line)>4096:raise RuntimeError("Geçersiz seri yanıt.")
            try:item=json.loads(line)
            except (ValueError,UnicodeDecodeError):
                # ROM boot text can arrive at a different baud before the app starts.
                marker=line.rfind(b'{"type":"hello"')
                if marker<0:return None
                try:item=json.loads(line[marker:])
                except (ValueError,UnicodeDecodeError):return None
                if item.get('device')!='MacroDeck' or item.get('protocol')!=3:return None
            return item if isinstance(item,dict) else None
        if len(self._rx_line)>4096:
            self._rx_line.clear()
            raise RuntimeError("Geçersiz seri yanıt.")
        return None

    def _boot_notice(self,message):
        if message.get('device')!='MacroDeck' or message.get('protocol')!=3:
            raise RuntimeError('Geçersiz kart başlangıç yanıtı.')
        self.info=message
        self.last_image=None;self.last_ack_at=0
        self._queue_touch({'type':'device_reset','info':message})

    def _queue_touch(self, item):
        event = {**item, "received_at": time.monotonic()}
        callback = getattr(self, "on_touch", None)
        if callback is not None:
            callback(event)
            return
        if not hasattr(self, "_touch_events"):
            self._touch_events = deque(maxlen=16)
        self._touch_events.append(event)

    def read_events(self):
        while self.port.in_waiting or b"\n" in getattr(self,"_rx_line",b""):
            item = self._read_message()
            if item and item.get('type')=='hello':self._boot_notice(item)
            elif item and item.get("type") in ("touch", "control"):
                self._queue_touch(item)
        events = list(getattr(self, "_touch_events", []))
        if hasattr(self, "_touch_events"):
            self._touch_events.clear()
        return events

    def wait(self, kind, seq=None, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self._read_message()
            if not message:
                continue
            if message.get('type')=='hello' and kind!='hello':
                self._boot_notice(message)
                raise RuntimeError('Kart yeniden başladı; aktarım yenilenecek.')
            if message.get("type") in ("touch", "control"):
                self._queue_touch(message)
            elif message.get("type") == "error":
                raise RuntimeError("Kart: " + str(message.get("message")))
            elif message.get("type") == kind and (seq is None or message.get("seq") == seq):
                return message
        raise TimeoutError(f"Kart yanıt vermedi ({kind}).")

    def request(self, obj, kind):
        self.send(obj)
        return self.wait(kind)

    def configure(self, value):
        return self.request({"type": "config", **validate_config(value)}, "configured")

    def brightness(self, value, persist=False):
        from brightness import validate_brightness
        value=validate_brightness(value)
        if not self.info.get('backlight_pwm'):
            raise RuntimeError('Kart yazılımı parlaklık kontrolünü desteklemiyor.')
        header={'type':'brightness','value':value}
        if persist and self.info.get('brightness_persist'):header['persist']=True
        reply=self.request(header,'brightness')
        if reply.get('value') != value:raise RuntimeError('Parlaklık değeri doğrulanamadı.')
        self.info['brightness']=value
        if 'preferred' in reply:self.info['preferred_brightness']=reply['preferred']
        return reply

    def frame(self, image, force_full=False):
        if not self.info.get("frame_buffer"):
            raise RuntimeError("Kartın PSRAM görüntü tamponu açılamadı.")
        if image.size != (320, 240):
            raise ValueError("Tam ekran görüntüsü 320×240 olmalı.")
        started = time.monotonic()
        was_idle = started - getattr(self, "last_ack_at", started) >= 10
        regions = dirty_regions(image, None if force_full or was_idle else self.last_image)
        total = 0; raw_total = 0; compressed_regions = 0
        try:
            for x,y,right,bottom in regions:
                raw = rgb565(image.crop((x,y,right,bottom)))
                payload, encoding = encode_frame(raw, self.info.get('rle565') and self.info.get('codec_self_test'))
                pixel_crc = zlib.crc32(raw)
                self.sequence += 1
                header={"type":"frame","x":x,"y":y,"w":right-x,"h":bottom-y,
                        "length":len(payload),"crc":zlib.crc32(payload),"seq":self.sequence}
                if encoding != 'raw':
                    header.update(encoding=encoding,decoded_length=len(raw),pixel_crc=pixel_crc)
                    compressed_regions += 1
                self.send(header)
                self.wait("ready",self.sequence)
                self.write_payload(payload,self.sequence)
                result = self.wait("ack",self.sequence)
                if result.get('pixel_crc',pixel_crc) != pixel_crc:
                    raise RuntimeError('Kartın görüntü doğrulaması eşleşmedi.')
                total += len(payload); raw_total += len(raw)
        except Exception:
            # A partially acknowledged image must never become the diff baseline.
            self.last_image = None
            raise
        self.last_image = image.copy()
        self.last_ack_at = time.monotonic()
        result.update(bytes_sent=total, raw_bytes=raw_total, compressed_regions=compressed_regions, regions=len(regions), elapsed_ms=round((self.last_ack_at-started)*1000))
        return result

    def write_payload(self, payload, sequence):
        # Stop-and-wait prevents UART/CDC buffers overflowing during HID activity.
        chunk_size=getattr(self,'info',{}).get('chunk_size',1024)
        if type(chunk_size) is not int or not 1 <= chunk_size <= 4096:
            raise RuntimeError('Geçersiz USB paket boyutu.')
        for offset in range(0, len(payload), chunk_size):
            block = payload[offset:offset + chunk_size]
            written = self.port.write(block)
            if written != len(block):
                raise RuntimeError("USB aktarımı yarıda kesildi.")
            reply = self.wait("chunk", sequence)
            if reply.get("offset") != offset + len(block):
                raise RuntimeError("USB paket sırası bozuldu.")
