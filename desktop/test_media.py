import bootstrap
import asyncio
from types import SimpleNamespace as NS
import unittest
from media import MediaReader,select_session,source_label

class Session:
    def __init__(self,name,playing=False,enabled=True):
        self.source_app_user_model_id=name;self.playing=playing;self.calls=[];self.enabled=enabled
    def get_playback_info(self):
        return NS(playback_status=4 if self.playing else 5,controls=NS(is_next_enabled=self.enabled))
    async def try_skip_next_async(self):self.calls.append('next');return True

class MediaTests(unittest.TestCase):
    def test_failed_media_read_releases_stale_manager_for_retry(self):
        async def scenario():
            reader=MediaReader();reader.manager=object();reader.session=object();reader.cover=b'old'
            async def failed():raise RuntimeError('Disconnected Windows media service')
            reader.read=failed
            with self.assertRaises(RuntimeError):await reader.safe_read()
            self.assertIsNone(reader.manager);self.assertIsNone(reader.session);self.assertIsNone(reader.cover)
        asyncio.run(scenario())

    def test_source_preference_survives_restart_and_can_return_to_auto(self):
        import tempfile
        from pathlib import Path
        from source_settings import SourceSettings
        with tempfile.TemporaryDirectory() as folder:
            settings=SourceSettings(Path(folder)/'source.json')
            settings.save('Chrome')
            self.assertEqual(SourceSettings(settings.path).load(),'Chrome')
            settings.save(None)
            self.assertIsNone(SourceSettings(settings.path).load())
            settings.path.write_text('{bad',encoding='utf-8')
            self.assertIsNone(settings.load())

    def test_pinned_source_does_not_switch_when_closed(self):
        reader=MediaReader();apple=Session('AppleMusic');spotify=Session('Spotify',True)
        reader.choose_session([apple,spotify],spotify)
        self.assertEqual(reader.cycle_source(),'AppleMusic')
        self.assertIs(reader.choose_session([apple,spotify],spotify),apple)
        self.assertIsNone(reader.choose_session([spotify],spotify))
        self.assertIsNone(reader.session)
        self.assertIsNone(reader.cycle_source())
        self.assertIs(reader.choose_session([spotify],spotify),spotify)

    def test_playing_browser_beats_paused_music(self):
        apple=Session('AppleMusic');chrome=Session('chrome',True)
        self.assertIs(select_session([apple,chrome],apple,apple),chrome)
    def test_current_wins_when_multiple_sources_play(self):
        apple=Session('AppleMusic',True);spotify=Session('Spotify',True)
        self.assertIs(select_session([apple,spotify],spotify,apple),spotify)
    def test_pause_retains_selected_source_and_closed_session_is_removed(self):
        apple=Session('AppleMusic');spotify=Session('Spotify')
        self.assertIs(select_session([apple,spotify],apple,spotify),spotify)
        self.assertIs(select_session([apple],spotify,spotify),apple)
        self.assertIsNone(select_session([],spotify,spotify))
    def test_control_targets_shown_session_without_reselecting(self):
        reader=MediaReader();selected=Session('chrome');reader.session=selected
        asyncio.run(reader.control('next'));self.assertEqual(selected.calls,['next'])
        selected.enabled=False
        with self.assertRaises(RuntimeError):asyncio.run(reader.control('next'))
        self.assertEqual(selected.calls,['next'])
    def test_browser_is_not_falsely_labelled_youtube(self):
        self.assertEqual(source_label('chrome.exe'),'CHROME')
        self.assertEqual(source_label('Spotify.exe'),'SPOTIFY')
        self.assertEqual(source_label('unknown'),'MEDYA')

if __name__=='__main__':unittest.main()
