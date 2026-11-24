import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

import frames


class FrameEncoderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'engine.session').write_text('fixture-stream')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, **changes):
        meta={'width':2,'height':2,'stride':8,'format':'RGBA','frame':1,'stream':'fixture-stream',
              'renderer':'opengl','capturedAtMs':1,'readbackMs':2}
        meta.update(changes)
        # OpenGL order: blue/white bottom row, then red/green top row.
        pixels=bytes([0,0,255,255,255,255,255,255,255,0,0,255,0,255,0,255])
        (self.root/'frame.raw').write_bytes(json.dumps(meta).encode()+b'\n'+pixels)

    def test_original_pixels_are_upright_and_encoding_runs_once(self):
        self.write()
        stamp=frames.encode_frame(self.root)
        with Image.open(self.root/'frame.png') as image:
            self.assertEqual(list(image.getdata()),[(255,0,0),(0,255,0),(0,0,255),(255,255,255)])
        self.assertEqual(frames.encode_frame(self.root,stamp),stamp)
        meta=json.loads((self.root/'frame.json').read_text())
        self.assertEqual(meta['stream'],'fixture-stream')
        self.assertGreaterEqual(meta['encodeMs'],0)

    def test_previous_engine_frames_are_not_published_after_restart(self):
        self.write(stream='previous-process')
        frames.encode_frame(self.root)
        self.assertFalse((self.root/'frame.json').exists())

    def test_invalid_dimensions_stride_and_incomplete_data_are_rejected(self):
        for changed in ({'width':1281},{'height':801},{'width':True},{'stride':7},{'readbackMs':float('nan')}):
            self.write(**changed)
            with self.assertRaises(ValueError): frames.read_frame(self.root/'frame.raw')
        self.write()
        with (self.root/'frame.raw').open('ab') as stream: stream.write(b'extra')
        with self.assertRaises(ValueError): frames.read_frame(self.root/'frame.raw')


if __name__=='__main__': unittest.main()
