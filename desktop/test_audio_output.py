import bootstrap
import unittest
from PIL import ImageChops
from audio_output import choose_output
from rendering import render,render_header_status
from model import Track

def endpoint(name,active=(),sessions=()):
    return {'name':name,'active':active,'sessions':sessions}

class AudioOutputTests(unittest.TestCase):
    def test_app_routed_headphones_beat_default_speakers(self):
        state=choose_output('Spotify.exe',[endpoint('Hoparlör',('chrome.exe',)),endpoint('Kulaklık',('Spotify.exe',))],'Hoparlör')
        self.assertEqual(state,{'name':'Kulaklık','kind':'app'})
    def test_paused_session_keeps_known_route_and_active_route_wins(self):
        endpoints=[endpoint('USB kulaklık',sessions=('AppleMusic.exe',))]
        self.assertEqual(choose_output('AppleMusic',endpoints,'Hoparlör')['name'],'USB kulaklık')
        endpoints.append(endpoint('Bluetooth',active=('AppleMusic.exe',)))
        self.assertEqual(choose_output('AppleMusic',endpoints,'Hoparlör')['name'],'Bluetooth')
    def test_ambiguous_routes_do_not_guess_a_device(self):
        state=choose_output('Chrome',[endpoint('A',('chrome.exe',)),endpoint('B',('chrome.exe',))],'A')
        self.assertEqual(state['kind'],'multiple')
        self.assertEqual(state['devices'],['A','B'])
    def test_no_match_is_explicit_default_and_missing_endpoint_is_unknown(self):
        self.assertEqual(choose_output('Firefox',[],'Realtek'),{'name':'Realtek','kind':'default'})
        self.assertEqual(choose_output('',[],None),{'name':None,'kind':'unavailable'})
    def test_device_name_changes_only_reserved_header_area(self):
        image=render(Track())
        before=render_header_status(image,output_name='Realtek')
        after=render_header_status(image,output_name='Çok uzun bir Bluetooth kulaklık adı '*20)
        box=ImageChops.difference(before,after).getbbox()
        self.assertGreaterEqual(box[0],212)
        self.assertLessEqual(box[2],311)
        self.assertGreaterEqual(box[1],5)
        self.assertLessEqual(box[3],20)
