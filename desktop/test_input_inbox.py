import bootstrap
import unittest
from input_inbox import InputInbox

class InboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_move_coalescing_retains_down_latest_position_and_release(self):
        source=object();box=InputInbox()
        box.push(source,{'type':'touch','phase':'down','id':1})
        for index in range(2,100):box.push(source,{'type':'touch','phase':'move','id':index})
        box.push(source,{'type':'touch','phase':'up','id':100})
        self.assertEqual([(await box.get())[1]['id'] for _ in range(3)],[1,99,100])
    async def test_overload_removes_move_before_release_or_control(self):
        source=object();box=InputInbox(3)
        box.push(source,{'type':'touch','phase':'down','id':1})
        box.push(source,{'type':'touch','phase':'move','id':2})
        box.push(source,{'type':'control','action':'volume_up','id':3})
        box.push(source,{'type':'touch','phase':'up','id':4})
        self.assertEqual([(await box.get())[1]['id'] for _ in range(3)],[1,3,4])
        self.assertEqual(box.dropped,1)
