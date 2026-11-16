import bootstrap
import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from io import BytesIO
from protocol import Device
from touch_runtime import TouchRuntime


class Reader:
    def __init__(self): self.calls=[]
    async def control(self,action): self.calls.append(action); return True


class RuntimeTests(unittest.TestCase):
    def test_valid_fast_taps_use_device_clock_even_when_usb_batches_them(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                runtime=TouchRuntime(Path(tmp)/'cal.json');runtime.coefficients=[1,0,0,0,1,0];reader=Reader()
                received=time.monotonic()
                for index,stamp in enumerate((1000,1040,1180),1):
                    await runtime.handle({'id':index,'phase':'down','raw_x':160,'raw_y':200,'event_ms':stamp,'received_at':received},reader)
                self.assertEqual(reader.calls,['play_pause','play_pause'])
                runtime.reset_connection()
                await runtime.handle({'id':1,'phase':'down','raw_x':160,'raw_y':200,'event_ms':10,'received_at':time.monotonic()},reader)
                self.assertEqual(len(reader.calls),3)
        asyncio.run(scenario())

    def test_drag_events_bypass_tap_debounce_without_media_commands(self):
        async def scenario():
            seen=[]
            async def motion(x,y,phase):seen.append(phase)
            async def navigate(x,y):return True
            with tempfile.TemporaryDirectory() as tmp:
                runtime=TouchRuntime(Path(tmp)/'cal.json',navigate=navigate,motion=motion)
                runtime.coefficients=[1,0,0,0,1,0];reader=Reader()
                for i,phase in enumerate(('down','move','move','up'),1):
                    await runtime.handle({'id':i,'phase':phase,'raw_x':160,'raw_y':200,'received_at':time.monotonic()},reader)
                self.assertEqual(seen,['move','move','up'])
                self.assertEqual(reader.calls,[])
        asyncio.run(scenario())

    def test_move_events_never_count_as_calibration_points(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                runtime=TouchRuntime(Path(tmp)/'cal.json');runtime.start();runtime.frame_sent(0)
                await runtime.handle({'id':1,'phase':'move','raw_x':100,'raw_y':100,'received_at':time.monotonic()},Reader())
                self.assertEqual(runtime.calibration,[])
        asyncio.run(scenario())

    def test_wake_touch_is_consumed_without_playing_media(self):
        async def scenario():
            from interaction import InteractionState
            state=InteractionState(0);state.update(False,61)
            async def navigate(x,y):return state.touch(61)
            with tempfile.TemporaryDirectory() as tmp:
                reader=Reader();runtime=TouchRuntime(Path(tmp)/'cal.json',navigate=navigate)
                runtime.coefficients=[1,0,0,0,1,0]
                await runtime.handle({'id':1,'raw_x':160,'raw_y':200,'received_at':time.monotonic()},reader)
                self.assertEqual(reader.calls,[])
                self.assertFalse(state.idle)
        asyncio.run(scenario())

    def test_duplicate_and_outside_touches_do_not_send_commands(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                reader=Reader(); runtime=TouchRuntime(Path(tmp)/"cal.json")
                runtime.coefficients=[1,0,0,0,1,0]
                event={"id":1,"raw_x":160,"raw_y":200,"received_at":time.monotonic()}
                await runtime.handle(event,reader)
                await runtime.handle(event,reader)
                await runtime.handle({**event,"id":2,"raw_x":20,"raw_y":40},reader)
                self.assertEqual(reader.calls,["play_pause"])
        asyncio.run(scenario())

    def test_calibration_saves_without_sending_media_commands(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/"cal.json"; reader=Reader(); runtime=TouchRuntime(path)
                runtime.start()
                for index,(x,y) in enumerate([(3800,300),(3800,3700),(300,300),(300,3700)]):
                    runtime.frame_sent(index)
                    await runtime.handle({"id":index+1,"raw_x":x,"raw_y":y,"received_at":time.monotonic()},reader)
                self.assertTrue(path.exists()); self.assertIsNone(runtime.calibration)
                self.assertEqual(reader.calls,[])
                self.assertIsNotNone(TouchRuntime(path).coefficients)
        asyncio.run(scenario())

    def test_preview_feedback_does_not_wait_for_windows_response(self):
        async def scenario():
            gate=asyncio.Event(); feedback=[]
            class SlowReader:
                async def control(self,action): await gate.wait()
            with tempfile.TemporaryDirectory() as tmp:
                runtime=TouchRuntime(Path(tmp)/"cal.json",feedback=feedback.append)
                runtime.coefficients=[1,0,0,0,1,0]
                task=asyncio.create_task(runtime.handle({"id":1,"raw_x":160,"raw_y":200,
                                                       "received_at":time.monotonic()},SlowReader()))
                await asyncio.sleep(0)
                self.assertEqual(feedback,["play_pause"]); self.assertFalse(task.done())
                gate.set(); await task
        asyncio.run(scenario())

    def test_touch_is_delivered_while_serial_ack_is_still_pending(self):
        async def scenario():
            touch=b'{"type":"touch","id":1,"raw_x":160,"raw_y":200}\n'
            class SlowWire:
                def __init__(self): self.buffer=BytesIO(touch+b'{"type":"ack","seq":1}\n')
                def read(self,n):
                    if self.buffer.tell()==len(touch): time.sleep(0.15)
                    return self.buffer.read(n)
            device=object.__new__(Device); device.port=SlowWire()
            queue=asyncio.Queue(); loop=asyncio.get_running_loop()
            device.on_touch=lambda item:loop.call_soon_threadsafe(queue.put_nowait,item)
            task=asyncio.create_task(asyncio.to_thread(device.wait,"ack",1))
            item=await asyncio.wait_for(queue.get(),1)
            self.assertEqual(item["id"],1); self.assertFalse(task.done())
            await task
        asyncio.run(scenario())


if __name__=="__main__": unittest.main()
