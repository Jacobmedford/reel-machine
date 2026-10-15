"""preview.py first-cut: a 3 s testsrc2 + tone cut becomes a 720x1280 phone file and an approval page."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import preview  # noqa: E402

FPS = 30
EDIT = '''TITLE = "Lab Cut"
STYLE = "hifi"
SRC = "{src}"
KEEP = [(1.0, 2.2), (3.0, 4.4)]
FRAMES = {{"WIDE": (1080, 1920, 0, 0)}}
SHOTS = [(0.0, "WIDE")]
HOLD = 0.4
'''
WORDS = [{"text": "One", "start": 0.05, "end": 0.40, "src": 1.05}, {"text": "line.", "start": 0.45, "end": 1.10, "src": 1.45},
         {"text": "And", "start": 1.25, "end": 1.50, "src": 3.05}, {"text": "another", "start": 1.55, "end": 2.10, "src": 3.35},
         {"text": "one.", "start": 2.15, "end": 2.55, "src": 3.95}]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"]


def voice(path, gaps=()):
    """2.6 s of tone at -16 dB (the cut's audio, HOLD short of the picture), silent in each gap"""
    t = np.arange(int(2.6 * 48000)) / 48000
    x = 0.16 * np.sin(2 * np.pi * 220 * t)
    for a, b in gaps:
        x[int(a * 48000):int(b * 48000)] = 0.0
    wavfile.write(path, 48000, (np.stack([x, x], 1) * 32767).astype(np.int16))


class Lines(unittest.TestCase):
    def test_sentences_with_times(self):
        self.assertEqual(preview.sentences(WORDS), [(0.05, "One line."), (1.25, "And another one.")])

    def test_a_line_cut_off_by_the_end_says_so(self):
        self.assertEqual(preview.sentences(WORDS, 0.0, 2.0), [(0.05, "One line."), (1.25, "And another ...")])
        self.assertEqual(preview.sentences(WORDS, 0.0, 1.2), [(0.05, "One line.")])     # ends between lines: whole

    def test_a_tap_lands_a_little_before_the_line(self):
        html = preview.lines_html([(1.25, "And another one.")])
        self.assertIn('data-t="1.050"', html)             # whisper's starts run late: hear the first syllable
        self.assertIn(">0:01.2<", html)                    # the label is the line's own time


class FirstCut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.aroll = os.path.join(cls.tmp, "aroll.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=1080x1920:rate={FPS}:duration=3",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-g", "10", "-an", cls.aroll], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def project(self, gaps=(), words=True):
        p = tempfile.mkdtemp(dir=self.tmp)
        os.makedirs(os.path.join(p, "assets"))
        os.makedirs(os.path.join(p, "style"))                 # its own (default) pack: the test never reads HOME's
        with open(os.path.join(p, "style", "style.json"), "w") as fh:
            fh.write("{}")
        shutil.copy(self.aroll, os.path.join(p, "assets", "aroll.mp4"))
        voice(os.path.join(p, "assets", "voice.wav"), gaps)
        with open(os.path.join(p, "edit.py"), "w") as fh:
            fh.write(EDIT.format(src=self.aroll))
        if words:
            with open(os.path.join(p, "words.json"), "w") as fh:
                json.dump(WORDS, fh)
        return p

    def test_phone_file_matches_the_cut(self):
        p = self.project()
        out = preview.first_cut(p)
        self.assertEqual(out, os.path.join(p, "approvals", "first-cut", "first-cut.mp4"))
        streams = probe(out)
        v = [s for s in streams if s["codec_type"] == "video"][0]
        self.assertEqual((v["width"], v["height"]), (720, 1280))
        self.assertLessEqual(abs(float(v["duration"]) - 3.0), 1 / FPS + 1e-6)
        self.assertTrue(any(s["codec_type"] == "audio" for s in streams))

    def test_page_lists_the_video_and_the_lines(self):
        p = self.project()
        preview.first_cut(p)
        d = os.path.join(p, "approvals", "first-cut")
        files = json.loads(read(os.path.join(d, "files.json")))
        self.assertIn("first-cut.mp4", files)
        for f in files:
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)
        page = read(os.path.join(d, "index.html"))
        self.assertIn('src="first-cut.mp4"', page)
        self.assertIn("One line.", page)
        self.assertIn("And another one.", page)
        self.assertIn("say go", page)
        self.assertNotIn("\u2014", page)                 # no em dashes anywhere on the page

    def test_dead_air_shows_on_the_page(self):
        p = self.project(gaps=[(1.4, 1.8)])               # 0.4 s of silence inside the video
        preview.first_cut(p)
        page = read(os.path.join(p, "approvals", "first-cut", "index.html"))
        self.assertIn("0.40 s", page)
        clean = self.project()
        preview.first_cut(clean)
        page = read(os.path.join(clean, "approvals", "first-cut", "index.html"))
        self.assertIn("No pause of 0.25 s or more", page)

    def test_dead_air_finds_inner_gaps_only(self):
        p = self.project(gaps=[(0.0, 0.3), (1.4, 1.8)])   # a quiet head is not dead air inside the video
        gaps = preview.dead_air(os.path.join(p, "assets", "voice.wav"))
        self.assertEqual(len(gaps), 1)
        self.assertAlmostEqual(gaps[0][0], 1.4, delta=0.02)
        self.assertAlmostEqual(gaps[0][1] - gaps[0][0], 0.4, delta=0.02)

    def test_stale_words_are_not_listed(self):
        p = self.project()
        with open(os.path.join(p, "words.json"), "w") as fh:     # times from the whole take, before the cut
            json.dump([dict(w, start=w["src"], end=w["src"] + 0.3) for w in WORDS], fh)
        preview.first_cut(p)
        page = read(os.path.join(p, "approvals", "first-cut", "index.html"))
        self.assertNotIn("And another one.", page)
        self.assertIn("words.py", page)


if __name__ == "__main__":
    unittest.main()
