import bootstrap
import asyncio
import ctypes
from io import BytesIO
import time
import unittest
from encoder import EncoderRuntime,volume_inputs,INPUT
from protocol import Device


class Reader:
    def __init__(self):self.calls=[]
    async def control(self,action):self.calls.append(action)


class EncoderTests(unittest.TestCase):
    def test_acceleration_preserves_fine_control_and_resets(self):
        from volume import VolumeAcceleration
        a = VolumeAcceleration()
        self.assertEqual([a.step('volume_up',t) for t in [0,.04,.08,.12]], [1,1,7,7])
        self.assertEqual(a.step('volume_down',.15),1)
        self.assertEqual(a.step('volume_down',1),1)
        self.assertEqual(a.step('volume_down',1.3),1)
        a.reset()
        self.assertEqual([a.step('volume_up',t) for t in [0,.02,.04]], [1,1,9])
        a.reset()
        self.assertEqual([a.step('volume_up',t) for t in [0,.1,.2]], [1,1,3])

    def test_acceleration_uses_device_time_when_usb_batches_events(self):
        from unittest.mock import patch
        async def scenario():
            calls=[]
            def volume(action,step):calls.append(step);return {'level':50,'muted':False}
            runtime=EncoderRuntime();reader=Reader();received=time.monotonic()
            with patch('encoder.endpoint_volume',volume):
                for i,stamp in enumerate((1000,1300,1600),1):
                    await runtime.handle({'type':'control','id':i,'action':'volume_up','event_ms':stamp,'received_at':received},reader)
            self.assertEqual(calls,[1,1,1])
        asyncio.run(scenario())

    def test_com_events_route_to_media_and_volume_without_real_input(self):
        async def scenario():
            calls=[]; reader=Reader();runtime=EncoderRuntime(volume=calls.append)
            for i,action in enumerate(["play_pause","next","previous","volume_up","volume_down"],1):
                event={"type":"control","id":i,"action":action,"received_at":time.monotonic()}
                await runtime.handle(event,reader);await runtime.handle(event,reader)
            self.assertEqual(reader.calls,["play_pause","next","previous"])
            self.assertEqual(calls,["volume_up","volume_down"])
        asyncio.run(scenario())

    def test_stale_and_demo_events_do_not_execute(self):
        async def scenario():
            calls=[];reader=Reader();runtime=EncoderRuntime(volume=calls.append)
            await runtime.handle({"type":"control","id":1,"action":"next","received_at":time.monotonic()-5},reader)
            await runtime.handle({"type":"control","id":2,"action":"volume_up","received_at":time.monotonic()},reader,demo=True)
            self.assertEqual(calls,[]);self.assertEqual(reader.calls,[])
        asyncio.run(scenario())

    def test_volume_pair_has_correct_windows_layout_and_key_release(self):
        pair=volume_inputs("volume_up")
        self.assertEqual(ctypes.sizeof(INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)
        self.assertEqual(pair[0].value.keyboard.vk,0xAF)
        self.assertEqual(pair[1].value.keyboard.flags,2)
        with self.assertRaises(ValueError):volume_inputs("anything_else")

    def test_control_event_is_not_lost_during_frame_ack(self):
        class Wire:
            def __init__(self):self.data=BytesIO(b'{"type":"control","id":1,"action":"next"}\n{"type":"ack","seq":1}\n')
            def read(self,n):return self.data.read(n)
            @property
            def in_waiting(self):return len(self.data.getbuffer())-self.data.tell()
        device=object.__new__(Device);device.port=Wire()
        self.assertEqual(device.wait("ack",1)["seq"],1)
        self.assertEqual(device.read_events()[0]["action"],"next")

if __name__=="__main__":unittest.main()
