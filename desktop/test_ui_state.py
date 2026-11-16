import bootstrap
from dataclasses import asdict
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch
from ui_mailbox import UiMailbox
from ui_settings import UiSettings,load_ui_settings,save_ui_settings
from storage import atomic_json
from media import MediaReader,DisplayedControls
from types import SimpleNamespace
import asyncio

class UiStateTests(unittest.TestCase):
    def test_slow_window_keeps_latest_image_without_retaining_old_frames(self):
        box=UiMailbox()
        for index in range(10000):
            box.put(('image',index));box.put(('status',str(index)))
        self.assertEqual(box.qsize(),2)
        self.assertEqual(box.get_nowait(),('image',9999))
        self.assertEqual(box.get_nowait(),('status','9999'))
        with self.assertRaises(queue.Empty):box.get_nowait()
    def test_invalid_or_corrupt_preferences_do_not_produce_blackout(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ui.json'
            save_ui_settings(path,UiSettings(120,True,10))
            self.assertEqual(load_ui_settings(path),UiSettings(120,True,10))
            path.write_text('{bad',encoding='utf-8')
            self.assertEqual(load_ui_settings(path),UiSettings())
        for value in ({'idle_seconds':1},{'dim_percent':0},{'dim_percent':101},{'dim_enabled':1},{'idle_seconds':True}):
            with self.assertRaises(ValueError):UiSettings.validate(value)
    def test_failed_preference_serialization_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ayar.json';atomic_json(path,{'source':'Türkçe'})
            with self.assertRaises(TypeError):atomic_json(path,{'source':object()})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),{'source':'Türkçe'})
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])
    def test_physical_controls_follow_acknowledged_session_not_new_selection(self):
        class Reader:
            def __init__(self):self.calls=[]
            async def control_for(self,session,action):self.calls.append((session,action))
        async def scenario():
            reader=Reader();shown=object();next_session=object();controls=DisplayedControls(reader)
            controls.commit(shown)
            await controls.control('play_pause')
            controls.transitioning=True
            with self.assertRaises(RuntimeError):await controls.control('next')
            controls.commit(next_session);await controls.control('play_pause')
            self.assertEqual(reader.calls,[(shown,'play_pause'),(next_session,'play_pause')])
        asyncio.run(scenario())
