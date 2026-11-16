import bootstrap
import asyncio
import json
import unittest
from io import BytesIO
from types import SimpleNamespace
from media import AppleMusicReader
from protocol import Device
from rendering import render_calibration
from touch import fit_calibration, position, hit_test, verify_corner, validate_calibration


class Wire:
    def __init__(self, data): self.data = BytesIO(data)
    @property
    def in_waiting(self): return len(self.data.getbuffer()) - self.data.tell()
    def read(self, count): return self.data.read(count)


class TouchTests(unittest.TestCase):
    def test_rotated_and_inverted_coordinates(self):
        raw = [(3800,300), (3800,3700), (300,300)]
        cal = fit_calibration(raw)
        x,y = position(cal, 2050,2000)
        self.assertAlmostEqual(x,160); self.assertAlmostEqual(y,120)
        self.assertTrue(verify_corner(cal, (300,3700)))
        self.assertFalse(verify_corner(cal, raw[0]))

    def test_degenerate_and_nonfinite_calibrations_rejected(self):
        with self.assertRaises(ValueError): fit_calibration([(100,100)]*3)
        for values in ([0]*6, [float("nan")]*6, [True]*6):
            with self.assertRaises(ValueError): validate_calibration(values)

    def test_only_media_buttons_respond(self):
        self.assertEqual(hit_test(98,197), "previous")
        self.assertEqual(hit_test(160,197), "play_pause")
        self.assertEqual(hit_test(222,197), "next")
        for x,y in [(160,150),(-1,197),(320,197),(160,239),(12,44)]:
            self.assertIsNone(hit_test(x,y))

    def test_touch_event_is_preserved_between_acknowledgements(self):
        device = object.__new__(Device)
        device.port = Wire(b'{"type":"touch","id":1,"raw_x":400,"raw_y":1200}\n{"type":"ack","seq":5}\n')
        self.assertEqual(device.wait("ack", 5)["seq"], 5)
        events = device.read_events()
        self.assertEqual(len(events),1); self.assertEqual(events[0]["raw_x"],400)
        self.assertEqual(device.read_events(), [])

    def test_partial_event_survives_poll_boundary(self):
        device = object.__new__(Device)
        device.port = Wire(b'{"type":"touch","id":2,')
        self.assertEqual(device.read_events(), [])
        device.port = Wire(b'"raw_x":120,"raw_y":300}\n')
        self.assertEqual(device.read_events()[0]["id"],2)

    def test_calibration_screens(self):
        for index in range(4): self.assertEqual(render_calibration(index).size,(320,240))

    def test_media_routing_targets_displayed_player(self):
        calls = []
        class Session:
            def __init__(self, source): self.source_app_user_model_id = source
            def get_playback_info(self): return SimpleNamespace(playback_status=4, controls=SimpleNamespace())
            async def try_toggle_play_pause_async(self):
                calls.append(self.source_app_user_model_id); return True
        other = Session("Spotify")
        apple = Session("AppleInc.AppleMusicWin!App")
        reader = AppleMusicReader()
        reader.manager = SimpleNamespace(get_sessions=lambda: [other, apple])
        reader.session = apple
        self.assertTrue(asyncio.run(reader.control("play_pause")))
        self.assertEqual(calls,[apple.source_app_user_model_id])
        reader.manager = SimpleNamespace(get_sessions=lambda: [other])
        reader.session = None
        with self.assertRaises(RuntimeError): asyncio.run(reader.control("next"))
        self.assertEqual(calls,[apple.source_app_user_model_id])


if __name__ == "__main__": unittest.main()
