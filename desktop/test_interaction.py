import bootstrap
import unittest
from interaction import InteractionState
from rendering import render,render_idle,render_volume
from model import Track
from PIL import ImageChops

class InteractionTests(unittest.TestCase):
    def test_idle_requires_pause_and_inactivity(self):
        state=InteractionState(0)
        self.assertFalse(state.update(False,59))
        self.assertTrue(state.update(False,60))
        self.assertTrue(state.touch(61))
        self.assertFalse(state.update(False,62))
        self.assertFalse(state.update(True,200))
        self.assertFalse(state.update(False,250))
        self.assertTrue(state.update(False,260))
        self.assertFalse(state.update(False,261,True))
    def test_volume_overlay_never_changes_art_or_header(self):
        image=render(Track(title='Test',playing=True))
        changed=render_volume(image,50)
        box=ImageChops.difference(image,changed).getbbox()
        self.assertGreaterEqual(box[1],140)
        self.assertLessEqual(box[3],176)
        self.assertEqual(render_idle({'cpu':100,'gpu':None,'ram':42}).size,(320,240))

if __name__=='__main__':unittest.main()
