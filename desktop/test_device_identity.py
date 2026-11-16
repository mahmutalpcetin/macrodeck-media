import bootstrap
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import protocol

class IdentityTests(TestCase):
    def test_first_connection_is_manual_then_tracks_approved_usb_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            port=SimpleNamespace(device='COM8',vid=0x1a86,pid=0x55d3,serial_number='test-only-serial')
            with patch.object(protocol,'DEVICE_PROFILE',Path(temp)/'device.json'),patch.object(protocol.list_ports,'comports',return_value=[port]):
                self.assertIsNone(protocol.find_device_port())
                self.assertFalse(protocol.is_project_uart('COM8'))
                protocol.remember_device('COM8')
                self.assertEqual(protocol.find_device_port(),'COM8')
                self.assertTrue(protocol.is_project_uart('COM8'))
                port.device='COM9'
                self.assertEqual(protocol.find_device_port(),'COM9')
                port.serial_number='another-board'
                self.assertIsNone(protocol.find_device_port())
                self.assertFalse(protocol.is_project_uart('COM9'))
    def test_unknown_or_ambiguous_identity_never_autoconnects(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'device.json'
            one=SimpleNamespace(device='COM1',vid=1,pid=2,serial_number='demo')
            two=SimpleNamespace(device='COM2',vid=1,pid=2,serial_number='demo')
            with patch.object(protocol,'DEVICE_PROFILE',path),patch.object(protocol.list_ports,'comports',return_value=[one,two]):
                protocol.remember_device('COM1')
                self.assertIsNone(protocol.find_device_port())
                path.write_text('[]')
                self.assertIsNone(protocol.find_device_port())
