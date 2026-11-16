import bootstrap
import unittest
from io import BytesIO
import json
from PIL import Image
from model import Track, validate_config, DEFAULT_CONFIG
from rendering import render, rgb565
from protocol import Device, dirty_regions


class FakePort:
    def __init__(self, incoming):
        self.incoming = BytesIO(incoming)
        self.written = bytearray()
    def read(self, count): return self.incoming.read(count)
    def write(self, data): self.written.extend(data); return len(data)


class Tests(unittest.TestCase):
    def test_unsolicited_boot_clears_cached_image_and_reports_reset(self):
        class Wire:
            def __init__(self):self.data=BytesIO(b'{"type":"hello","device":"MacroDeck","protocol":3,"version":"2.0.0"}\n')
            @property
            def in_waiting(self):return len(self.data.getbuffer())-self.data.tell()
            def read(self,n):return self.data.read(n)
        d=object.__new__(Device);d.port=Wire();d.last_image=Image.new('RGB',(320,240));d.info={}
        self.assertEqual(d.read_events()[0]['type'],'device_reset')
        self.assertIsNone(d.last_image)
        self.assertEqual(d.info['version'],'2.0.0')

    def test_invalid_timeline_and_extreme_metadata_do_not_break_display(self):
        from rendering import timestamp
        for value in (float('nan'),float('inf'),None,-5):
            self.assertEqual(timestamp(value),'0:00')
            self.assertEqual(render(Track(title='Başlık '*10000,artist='Sanatçı',position=value,duration=value)).size,(320,240))

    def test_wide_thumbnail_keeps_both_edges(self):
        from PIL import ImageDraw
        from rendering import artwork
        image=Image.new('RGB',(200,100),'white');d=ImageDraw.Draw(image)
        d.rectangle((0,0,20,99),fill='red');d.rectangle((180,0,199,99),fill='blue')
        stream=BytesIO();image.save(stream,format='PNG')
        art=artwork(stream.getvalue())
        self.assertEqual(art.getpixel((0,48)),(255,0,0))
        self.assertEqual(art.getpixel((95,48)),(0,0,255))

    def test_sparse_header_and_progress_updates_skip_unchanged_artwork(self):
        before = Image.new('RGB',(320,240))
        after = before.copy()
        from PIL import ImageDraw,ImageChops
        d=ImageDraw.Draw(after)
        d.rectangle((12,23,60,32),fill='red')
        d.rectangle((180,148,185,153),fill='white')
        regions=dirty_regions(after,before)
        old=ImageChops.difference(after,before).getbbox()
        area=lambda b:(b[2]-b[0])*(b[3]-b[1])
        self.assertEqual(len(regions),2)
        self.assertLess(sum(map(area,regions)),area(old)/10)
        reconstructed=before.copy()
        for b in regions:reconstructed.paste(after.crop(b),b)
        self.assertIsNone(ImageChops.difference(after,reconstructed).getbbox())

    def test_larger_packets_obey_device_advertised_size_and_final_offset(self):
        d=object.__new__(Device);d.info={'chunk_size':4096}
        d.port=FakePort(b''.join(json.dumps({'type':'chunk','seq':3,'offset':offset}).encode()+b'\n' for offset in (4096,8192,9000)))
        payload=b'x'*9000
        d.write_payload(payload,3)
        self.assertEqual(bytes(d.port.written),payload)
        d.info={'chunk_size':8192}
        with self.assertRaises(RuntimeError):d.write_payload(payload,3)

    def test_brightness_number_and_slider_are_independent_updates(self):
        from rendering import render_brightness
        from PIL import ImageChops
        before=render_brightness(40);after=render_brightness(80)
        regions=dirty_regions(after,before)
        old=ImageChops.difference(after,before).getbbox()
        area=lambda b:(b[2]-b[0])*(b[3]-b[1])
        self.assertLess(sum(map(area,regions)),area(old)*0.6)
        rebuilt=before.copy()
        for b in regions:rebuilt.paste(after.crop(b),b)
        self.assertIsNone(ImageChops.difference(after,rebuilt).getbbox())

    def test_buffered_messages_do_not_wait_for_more_serial_bytes(self):
        class Wire:
            def __init__(self):self.data=BytesIO(b'{"type":"touch","id":1}\n{"type":"ack","seq":1}\n')
            @property
            def in_waiting(self):return len(self.data.getbuffer())-self.data.tell()
            def read(self,n):return self.data.read(n)
        d=object.__new__(Device);d.port=Wire()
        self.assertEqual(d.wait('ack',1)['seq'],1)
        self.assertEqual(d.read_events()[0]['id'],1)

    def test_dense_update_and_no_change_do_not_multiply_handshakes(self):
        before=Image.new('RGB',(320,240))
        self.assertEqual(dirty_regions(Image.new('RGB',(320,240),'red'),before),[(0,0,320,240)])
        self.assertEqual(dirty_regions(before,before),[(0,0,1,1)])

    def test_rgb565_uses_little_endian(self):
        image = Image.new("RGB", (320, 240), (255, 0, 0))
        payload = rgb565(image)
        self.assertEqual(len(payload), 153600)
        self.assertEqual(payload[:4], b"\x00\xf8\x00\xf8")
        image.putpixel((0, 0), (0, 255, 0))
        self.assertEqual(rgb565(image)[:2], b"\xe0\x07")

    def test_config_rejects_partial_or_invalid_values(self):
        self.assertEqual(validate_config(DEFAULT_CONFIG), DEFAULT_CONFIG)
        for value in ({"keys": [1]}, {**DEFAULT_CONFIG, "keys": [True] * 6},
                      {**DEFAULT_CONFIG, "keys": [99] * 6}, {**DEFAULT_CONFIG, "steps": 3}):
            with self.assertRaises(ValueError): validate_config(value)

    def test_frame_handshake_and_ack_sequence(self):
        device = object.__new__(Device)
        device.info = {"frame_buffer": True}; device.sequence = 0; device.last_image = None
        chunks = b"".join(json.dumps({"type":"chunk", "seq":1, "offset":i}).encode() + b"\n" for i in range(1024, 153601, 1024))
        device.port = FakePort(b'{"type":"ready","seq":1}\n' + chunks + b'{"type":"ack","seq":0}\n{"type":"ack","seq":1}\n')
        reply = device.frame(Image.new("RGB", (320, 240)))
        self.assertEqual(reply["seq"], 1)
        header, payload = bytes(device.port.written).split(b"\n", 1)
        self.assertEqual(len(payload), 153600)
        self.assertIn(b'"length":153600', header)

    def test_dirty_region_and_unchanged_frame_keepalive(self):
        device = object.__new__(Device)
        device.info = {"frame_buffer": True}; device.sequence = 0
        image = Image.new("RGB", (320, 240))
        device.last_image = image.copy()
        image.putpixel((20, 30), (255, 255, 255))
        device.port = FakePort(b'{"type":"ready","seq":1}\n{"type":"chunk","seq":1,"offset":2}\n{"type":"ack","seq":1}\n')
        reply = device.frame(image)
        header, payload = bytes(device.port.written).split(b"\n", 1)
        self.assertEqual(json.loads(header)["x"], 20)
        self.assertEqual(json.loads(header)["y"], 30)
        self.assertEqual(reply["bytes_sent"], 2)
        self.assertEqual(payload, b"\xff\xff")

    def test_device_error_is_not_treated_as_success(self):
        device = object.__new__(Device)
        device.port = FakePort(b'{"type":"error","message":"crc_mismatch"}\n')
        with self.assertRaisesRegex(RuntimeError, "crc_mismatch"):
            device.wait("ack")

    def test_long_unicode_and_broken_art_are_renderable(self):
        track = Track(title="İstanbul — Çağrı şarkısı " * 30, artist="Öğüşçİı", cover=b"broken",
                      available=True, position=-3, duration=0)
        self.assertEqual(render(track).size, (320, 240))


if __name__ == "__main__":
    unittest.main()
