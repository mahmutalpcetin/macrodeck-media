import unittest
from resources import cpu_usage, gpu_value

class ResourceTests(unittest.TestCase):
    def test_native_gpu_read_avoids_subprocess_and_falls_back_only_when_unavailable(self):
        from unittest.mock import patch,MagicMock
        from types import SimpleNamespace
        from resources import ResourceMonitor
        native=MagicMock();native.sample.return_value=27
        kernel=SimpleNamespace(GetSystemTimes=lambda *args:False,GlobalMemoryStatusEx=lambda *args:False)
        with patch('resources.NativeGpu',return_value=native),patch('resources.c.WinDLL',return_value=kernel),patch('resources.subprocess.run') as run:
            monitor=ResourceMonitor();monitor.gpu_tool='test-tool'
            self.assertEqual(monitor.sample()['gpu'],27);run.assert_not_called()
            native.sample.return_value=None
            run.return_value=SimpleNamespace(returncode=0,stdout='8\n')
            self.assertEqual(monitor.sample()['gpu'],8)
            monitor.close();native.close.assert_called_once()

    def test_cpu_delta_excludes_idle_from_kernel_time(self):
        self.assertIsNone(cpu_usage(None,(10,20,30)))
        self.assertEqual(cpu_usage((10,20,30),(30,70,80)),80)
        self.assertIsNone(cpu_usage((10,20,30),(10,20,30)))
    def test_gpu_unavailable_is_not_reported_as_zero(self):
        self.assertIsNone(gpu_value('N/A\n[Not Supported]'))
        self.assertEqual(gpu_value('0\n'),0)
        self.assertEqual(gpu_value('23\n70\n'),70)
        self.assertIsNone(gpu_value('101\n-1'))

if __name__=='__main__':unittest.main()
