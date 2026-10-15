"""render.py --hook end to end on a tiny project, with only the renderer swapped for an ffmpeg stub: the build, the
cut copy in work/hook (hard links into public/), the audio slice, the frame count and the approval stop."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import render  # noqa: E402

EDIT = '''TITLE = "Lab Hook"
STYLE = "hifi"
SRC = "{src}"
KEEP = [(1.0, 2.2), (3.0, 4.4)]
FRAMES = {{"WIDE": (1080, 1920, 0, 0)}}
SHOTS = [(0.0, "WIDE")]
HOLD = 0.4
CAPS = [(0.05, "One line.", "", 1.2), (1.25, "And another one.", "", "end")]
CARDS = []
FX = [dict(id="intro", layer="top", at=0.0, end=1.0, note="A title over the first line")]
'''
WORDS = [{"text": "One", "start": 0.05, "end": 0.40, "src": 1.05}, {"text": "line.", "start": 0.45, "end": 1.10, "src": 1.45},
         {"text": "And", "start": 1.25, "end": 1.50, "src": 3.05}, {"text": "another", "start": 1.55, "end": 2.10, "src": 3.35},
         {"text": "one.", "start": 2.15, "end": 2.55, "src": 3.95}]
TIMELINE = {"fps": 30, "total_audio": 2.6, "total": 3.0,
            "keep": [{"src_in": 1.0, "src_out": 2.2, "out": 0.0, "picture_out": 0.0},
                     {"src_in": 3.0, "src_out": 4.4, "out": 1.2, "picture_out": 1.5}],
            "picture_cuts": [1.5], "reframes": [], "shots": [{"t": 0.0, "frame": "WIDE"}], "pieces": []}


def fake_hf(args, cwd):
    """stands in for `hyperframes render`: a testsrc video exactly as long as the composition's root says"""
    with open(os.path.join(cwd, "index.html"), encoding="utf-8") as fh:
        doc = fh.read()
    dur = float(re.search(r'data-composition-id="main"[^>]*data-duration="([0-9.]+)"', doc).group(1))
    out = args[args.index("-o") + 1]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30",
                    "-frames:v", str(round(dur * 30)), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    out], check=True)
    return subprocess.CompletedProcess(args, 0, "", "")


class RenderHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = self.project = os.path.join(self.tmp, "proj")
        for d in ("assets", "public/vendor", "style/fonts", "renders", "work"):
            os.makedirs(os.path.join(p, d))
        with open(os.path.join(p, "style", "style.json"), "w") as fh:
            fh.write("{}")                                   # the default pack, nothing downloaded
        with open(os.path.join(p, "style", "brand.css"), "w") as fh:
            fh.write(":root { --c-light: #eee; }\n")
        with open(os.path.join(p, "public", "vendor", "gsap.min.js"), "w") as fh:
            fh.write("/* stub */")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=3",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", "10",
                        os.path.join(p, "public", "clean.mp4")], check=True)
        t = np.arange(int(3.0 * 48000)) / 48000
        x = (0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
        wavfile.write(os.path.join(p, "public", "master.wav"), 48000, np.stack([x, x], 1))
        with open(os.path.join(p, "edit.py"), "w") as fh:
            fh.write(EDIT.format(src=os.path.join(p, "public", "clean.mp4")))
        with open(os.path.join(p, "words.json"), "w") as fh:
            json.dump(WORDS, fh)
        with open(os.path.join(p, "timeline.json"), "w") as fh:
            json.dump(TIMELINE, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hook_render_plumbing(self):
        E = render.load_edit(self.project)
        with mock.patch.object(render, "hf", side_effect=fake_hf):
            final = render.render_hook(self.project, E, "lab-v1")
        p = self.project
        self.assertEqual(final, os.path.join(p, "renders", "lab-v1-hook.mp4"))
        # the hook ends on the join after "One line." (1.2 s: "And" starts inside the hold): 36 frames
        n = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", final], capture_output=True, text=True).stdout
        self.assertEqual(n.strip(), "36")
        streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json",
                                  final], capture_output=True, text=True).stdout
        audio = [s for s in json.loads(streams)["streams"] if s["codec_type"] == "audio"]
        self.assertTrue(audio and abs(float(audio[0]["duration"]) - 1.2) < 0.03, streams)
        # the cut copy ends at the hook; the composition in public/ keeps its full length
        with open(os.path.join(p, "work", "hook", "index.html"), encoding="utf-8") as fh:
            self.assertIn('data-duration="1.2000"', fh.read())
        with open(os.path.join(p, "public", "index.html"), encoding="utf-8") as fh:
            self.assertIn('data-duration="3.0000"', fh.read())
        # assets are hard links into public/, not copies
        self.assertEqual(os.stat(os.path.join(p, "work", "hook", "clean.mp4")).st_ino,
                         os.stat(os.path.join(p, "public", "clean.mp4")).st_ino)
        # the approval stop
        d = os.path.join(p, "approvals", "hook")
        with open(os.path.join(d, "files.json")) as fh:
            files = json.load(fh)
        self.assertEqual(files[:2], ["hook.mp4", "poster.jpg"])
        for f in files:
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)
        with open(os.path.join(d, "index.html"), encoding="utf-8") as fh:
            page = fh.read()
        self.assertIn("One line.", page)
        self.assertNotIn("And another", page)
        self.assertIn("A title over the first line", page)
        self.assertNotIn("\u2014", page)


if __name__ == "__main__":
    unittest.main()
