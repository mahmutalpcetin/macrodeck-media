import bootstrap
import tempfile
from pathlib import Path
import unittest
from brightness import BrightnessSettings,validate_brightness
from protocol import Device
from rendering import render_brightness

class BrightnessTests(unittest.TestCase):
    def test_persistent_and_temporary_commands_are_distinct(self):
        d=object.__new__(Device);d.info={'backlight_pwm':True,'brightness_persist':True}
        headers=[]
        def request(header,kind):
            headers.append(header)
            return {'type':kind,'value':header['value'],'preferred':38,'saved':True}
        d.request=request
        d.brightness(38,persist=True);d.brightness(15)
        self.assertTrue(headers[0]['persist'])
        self.assertNotIn('persist',headers[1])
        self.assertEqual(d.info['preferred_brightness'],38)
        self.assertEqual(d.info['brightness'],15)

    def test_standby_dimming_preserves_preference_and_never_brightens_low_setting(self):
        from brightness import effective_brightness
        with tempfile.TemporaryDirectory() as folder:
            settings=BrightnessSettings(Path(folder)/'brightness.json');settings.save(72)
            self.assertEqual(effective_brightness(settings.load(),True),15)
            self.assertEqual(settings.load(),72)
            self.assertEqual(effective_brightness(settings.load(),False),72)
            self.assertEqual(effective_brightness(5,True),5)

    def test_drag_captures_only_slider_and_clamps_outside_edges(self):
        from brightness import BrightnessDrag
        drag=BrightnessDrag()
        self.assertIsNone(drag.begin(150,60))
        self.assertIsNone(drag.move(150,122,'move'))
        self.assertEqual(drag.begin(20,122),5)
        self.assertEqual(drag.move(400,170,'move'),100)
        self.assertEqual(drag.move(-20,170,'up'),5)
        self.assertIsNone(drag.move(200,122,'move'))

    def test_setting_survives_restart_and_bad_file_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'brightness.json';settings=BrightnessSettings(path)
            self.assertEqual(settings.load(),100)
            settings.save(35)
            self.assertEqual(BrightnessSettings(path).load(),35)
            path.write_text('{bad',encoding='utf-8')
            self.assertEqual(settings.load(),100)
    def test_no_blackout_or_invalid_ui_value(self):
        for value in (0,101,True,12.5,'50'):
            with self.assertRaises(ValueError):validate_brightness(value)
    def test_device_ack_must_match_and_old_firmware_is_not_sent_commands(self):
        d=object.__new__(Device);d.info={'backlight_pwm':True}
        requests=[]
        def request(obj,kind):requests.append(obj);return {'type':kind,'value':25}
        d.request=request
        self.assertEqual(d.brightness(25)['value'],25)
        with self.assertRaises(RuntimeError):d.brightness(30)
        d.info={};requests.clear()
        with self.assertRaises(RuntimeError):d.brightness(25)
        self.assertEqual(requests,[])
    def test_settings_screen_fits_display(self):
        for level in (5,50,100):self.assertEqual(render_brightness(level).size,(320,240))

if __name__=='__main__':unittest.main()
