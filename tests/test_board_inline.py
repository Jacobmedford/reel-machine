"""onboarding/board.py: every board frame (the look, the library cards in the creator's style) is snapshotted with
GSAP already inside the page, so a dropped fetch cannot show a card standing still on the style board."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "onboarding"))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import board  # noqa: E402
import inline_vendor as IV  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class Snap(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "vendor"))
        with open(os.path.join(self.d, "vendor", "gsap.min.js"), "w") as fh:
            fh.write("/* gsap */")
        with open(os.path.join(self.d, "index.html"), "w") as fh:
            fh.write('<div data-composition-id="main" data-duration="2"></div><script src="vendor/gsap.min.js"></script>'
                     "<script>window.__timelines['main'] = gsap.timeline({ paused: true });</script>")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_gsap_is_inside_the_page_when_the_snapshot_runs(self):
        seen = []

        def fake_hf(args, cwd):
            with open(os.path.join(cwd, "index.html"), encoding="utf-8") as fh:
                doc = fh.read()
            seen.append((IV.fetched(doc), IV.inlined(doc)))
            os.makedirs(os.path.join(cwd, "snapshots"), exist_ok=True)
            Image.fromarray(np.zeros((1920, 1080, 3), np.uint8)).save(os.path.join(cwd, "snapshots", "frame-00.png"))

        out = os.path.join(self.d, "frame.jpg")
        with mock.patch.object(board, "hf", side_effect=fake_hf):
            board.snap(self.d, 1.0, out)
        self.assertEqual(seen, [([], ["vendor/gsap.min.js"])])
        self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
