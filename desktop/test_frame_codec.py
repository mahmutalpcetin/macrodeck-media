import bootstrap
from array import array
import random
import unittest
from frame_codec import encode_rle565,decode_rle565,encode_frame

class CodecTests(unittest.TestCase):
    def test_lossless_for_solid_literal_mixed_and_maximum_run(self):
        rng=random.Random(24)
        cases=[b'\x34\x12',b'\x00\xf8'*76800,bytes(rng.randrange(256) for _ in range(8192)),b'\x00\x00'*100+b'\xff\xff'+b'\xe0\x07'*32769]
        for raw in cases:
            packed=encode_rle565(raw)
            self.assertEqual(decode_rle565(packed,len(raw)),raw)
        self.assertLess(len(encode_rle565(cases[1])),32)
    def test_varied_image_patterns_roundtrip(self):
        rng=random.Random(27)
        for size in (1,2,3,4,31,256,1024,32768,32769):
            values=[]
            while len(values)<size:
                values.extend([rng.randrange(65536)]*rng.randrange(1,29))
            raw=array('H',values[:size]).tobytes()
            self.assertEqual(decode_rle565(encode_rle565(raw),len(raw)),raw)
    def test_decoder_rejects_overflow_truncation_and_incomplete_images(self):
        for packed,size in [(b'\x03\x80\x34\x12',2),(b'\x03\x80\x34',8),(b'\x00',2),(b'\x00\x00\x34',2),(b'\x00\x00\x34\x12',4),(b'',2)]:
            with self.assertRaises(ValueError):decode_rle565(packed,size)
        for size in (0,1,153602):
            with self.assertRaises(ValueError):decode_rle565(b'',size)
    def test_raw_fallback_when_disabled_small_or_incompressible(self):
        rng=random.Random(4);raw=bytes(rng.randrange(256) for _ in range(4096))
        self.assertEqual(encode_frame(raw,True),(raw,'raw'))
        self.assertEqual(encode_frame(b'\x00\x00'*100,True)[1],'raw')
        self.assertEqual(encode_frame(b'\x00\x00'*1000,False)[1],'raw')
        self.assertEqual(encode_frame(b'\x00\x00'*1000,True)[1],'rle565')

if __name__=='__main__':unittest.main()
