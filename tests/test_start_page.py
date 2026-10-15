"""preview.py start: the first page after the takes are in, built from intake.json for a fixture project with two takes.

The page lists every take in order with its poster and length, the three modes with their example clips, the styles in
the creator's home (the default pack plus packs/) and what to send; every file it references is in files.json; it
holds no home folder path and no em dash; with words.json present it shows each take's first line."""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import preview  # noqa: E402

KIT = os.path.dirname(HERE)
HOMES = os.sep + "Users" + os.sep          # the folder macOS keeps home folders in
HDR_WHY = "shot with HDR on: converted to standard range (the shoot guide says HDR off)"
LOFI_WHY = "1080p or a phone shape: usually a selfie in hand (lo-fi); say hi-fi if it sat on a tripod"
INTAKE = {
    "version": 1, "slug": "lab-start", "title": "Lab Start", "source": "raw/joined.mov",
    "plan": {"mode": "encode", "size": [1080, 1920], "fps": "30/1", "hdr": True,
             "why": [HDR_WHY, "the takes differ in pix_fmt"]},
    "recommended": {"mode": "lofi", "why": LOFI_WHY},
    "takes": [
        {"name": "IMG_2843.mov", "file": "raw/IMG_2843.mov", "start": 0.0, "duration": 61.233,
         "recorded": "2026-10-13T19:02:11Z", "size": [1080, 1920], "hdr": True,
         "poster": "approvals/start/posters/01.jpg"},
        {"name": "IMG_2851.mov", "file": "raw/IMG_2851.mov", "start": 61.233, "duration": 42.4,
         "recorded": "2026-10-13T19:05:40Z", "size": [1080, 1920], "hdr": False,
         "poster": "approvals/start/posters/02.jpg"},
    ],
    "ignored": ["notes.txt"],
}


def spread(text, a, b, src0):
    """words of text spread evenly over output a..b, with src = src0 + (start - a)"""
    ws = text.split()
    step = (b - a) / len(ws)
    return [{"text": w, "start": round(a + i * step, 3), "end": round(a + (i + 0.8) * step, 3),
             "src": round(src0 + i * step, 3)} for i, w in enumerate(ws)]


LONG = "so this one runs on and on without a single stop because I kept talking right through it"
WORDS = (spread("Here is the first thing. And then a second line.", 0.5, 4.0, 0.5)
         + spread(LONG, 61.233, 66.0, 61.233))          # starts exactly on take 2's first frame: it belongs to take 2


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def jpg(path, color=(90, 110, 130), size=(54, 96)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, color).save(path, quality=80)


def mp4(path, seconds=1, size="54x96"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", path], check=True)


def block(page, elem_id):
    """the HTML of the element with this id, up to the close of its tag (article, li or section)"""
    m = re.search(rf'<(article|li|section)\b[^>]*\bid="{re.escape(elem_id)}"[^>]*>(.*?)</\1>', page, re.S)
    return m.group(0) if m else ""


def references(page):
    """every local file the page points at: src, poster and href attributes and url() in its CSS"""
    refs = re.findall(r'\b(?:src|poster|href)="([^"]+)"', page) + re.findall(r"url\(['\"]?([^'\")]+)['\"]?\)", page)
    return sorted({r for r in refs if not r.startswith(("http:", "https:", "data:", "#", "mailto:", "api/"))})


class StartPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.examples = os.path.join(cls.tmp, "examples")             # stands in for KIT/storyboard/examples
        for m in ("hifi", "lofi", "showcase"):
            mp4(os.path.join(cls.examples, f"{m}.mp4"))
        jpg(os.path.join(cls.examples, "style-film.jpg"), (160, 120, 80))
        jpg(os.path.join(cls.examples, "style-harbor.jpg"), (10, 10, 10))   # loses to the pack's own board frame

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.home = tempfile.mkdtemp(dir=self.tmp)
        write_json(os.path.join(self.home, "style", "style.json"), {})          # the default pack (harbor)
        jpg(os.path.join(self.home, "style", "board", "frame.jpg"), (40, 60, 50))
        for name in ("film", "signal"):
            write_json(os.path.join(self.home, "packs", name, "style.json"), {})
        os.makedirs(os.path.join(self.home, "packs", "half-made"))            # no style.json: not a pack
        env = {"REEL_KIT_HOME": self.home, "REEL_MACHINE_HOME": self.home}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.addCleanup(self.env.stop)

    def project(self, words=True, intake=None):
        p = tempfile.mkdtemp(dir=self.tmp)
        write_json(os.path.join(p, "style", "style.json"), {})                 # its own pack: no fonts to fetch
        write_json(os.path.join(p, "intake.json"), intake or INTAKE)
        for k in (1, 2):
            jpg(os.path.join(p, "approvals", "start", "posters", f"{k:02d}.jpg"))
        if words:
            write_json(os.path.join(p, "words.json"), WORDS)
        return p

    def build(self, p):
        out = preview.start(p, examples=self.examples)
        folder = os.path.join(p, "approvals", "start")
        self.assertEqual(out, os.path.join(folder, "index.html"))
        return folder, read(out)

    def test_every_take_in_order_with_its_poster_and_length(self):
        _, page = self.build(self.project())
        one, two = block(page, "take-01"), block(page, "take-02")
        self.assertIn("IMG_2843.mov", one)
        self.assertIn("IMG_2851.mov", two)
        self.assertLess(page.index('id="take-01"'), page.index('id="take-02"'))
        self.assertIn('src="posters/01.jpg"', one)
        self.assertIn('src="posters/02.jpg"', two)
        self.assertIn(">1:01<", one)
        self.assertIn(">0:42<", two)
        self.assertIn(preview.recorded_label(INTAKE["takes"][0]["recorded"]), one)

    def test_a_re_encoded_take_says_why(self):
        _, page = self.build(self.project())
        one, two = block(page, "take-01"), block(page, "take-02")
        self.assertIn("re-encoded: ", one)
        self.assertIn("HDR", one)                                    # shot in HDR: converted
        self.assertIn("re-encoded: ", two)
        self.assertNotIn("HDR", two)                                 # not this take's reason
        self.assertIn("pix_fmt", two)
        copied = dict(INTAKE, plan=dict(INTAKE["plan"], mode="copy", why=[], hdr=False))
        _, page = self.build(self.project(intake=copied))
        self.assertNotIn("re-encoded", page)

    def test_three_modes_with_their_clips_and_the_recommended_one(self):
        folder, page = self.build(self.project())
        for m in ("hifi", "lofi", "showcase"):
            card = block(page, f"mode-{m}")
            self.assertTrue(card, m)
            video = re.search(r"<video\b[^>]*>", card).group(0)
            self.assertIn(f'src="examples/{m}.mp4"', video)
            for attr in ("muted", "loop", "playsinline"):
                self.assertRegex(video, rf"\b{attr}\b", (m, attr))
            self.assertTrue(os.path.exists(os.path.join(folder, "examples", f"{m}.mp4")), m)
        self.assertIn("full-screen data cards and type behind you", block(page, "mode-hifi"))
        self.assertIn("real screenshots over you and word-by-word captions", block(page, "mode-lofi"))
        self.assertIn("a different hand-built motion graphic on every line", block(page, "mode-showcase"))
        self.assertIn("Recommended", block(page, "mode-lofi"))
        self.assertIn(LOFI_WHY, block(page, "mode-lofi"))
        self.assertNotIn("Recommended", block(page, "mode-hifi") + block(page, "mode-showcase"))

    def test_the_styles_in_the_creators_home(self):
        _, page = self.build(self.project())
        harbor, film, signal = block(page, "style-harbor"), block(page, "style-film"), block(page, "style-signal")
        self.assertLess(page.index('id="style-harbor"'), page.index('id="style-film"'))
        self.assertLess(page.index('id="style-film"'), page.index('id="style-signal"'))
        self.assertNotIn("half-made", page)
        self.assertIn("The default, tutorials and builds.", harbor)
        self.assertIn("Stories, slower, a film grade.", film)
        self.assertIn("Proof, results and news, fastest.", signal)
        self.assertIn('src="styles/harbor.jpg"', harbor)            # the pack's own board/frame.jpg
        self.assertIn('src="styles/film.jpg"', film)                # the kit's storyboard/examples/style-film.jpg
        self.assertNotIn("<img", signal)                            # neither: a plain card with its name
        self.assertIn("Signal", signal)

    def test_a_packs_own_frame_wins_over_the_kits(self):
        folder, _ = self.build(self.project())
        with Image.open(os.path.join(folder, "styles", "harbor.jpg")) as im:
            r, g, b = im.convert("RGB").getpixel((5, 5))
        self.assertGreater(g, 40)                                    # (40, 60, 50), not the kit's black frame

    def test_a_recolored_packs_board_wins_over_the_kits_example(self):
        jpg(os.path.join(self.home, "packs", "film", "board", "img", "hifi.jpg"), (200, 30, 30))
        folder, _ = self.build(self.project())
        with Image.open(os.path.join(folder, "styles", "film.jpg")) as im:
            r, g, b = im.convert("RGB").getpixel((5, 5))
        self.assertGreater(r, 150)                                   # the pack's own board (200, 30, 30) ...
        self.assertLess(g, 80)                                       # ... not the kit's example (160, 120, 80)

    def test_what_to_send(self):
        _, page = self.build(self.project())
        send = block(page, "send")
        for words in ("a repo, an article, a post, a docs page", "dashboards, anything behind a login", "B-roll",
                      "Paste links and drop files in the chat."):
            self.assertIn(words, send)

    def test_the_head(self):
        _, page = self.build(self.project())
        self.assertIn(">New video<", page)
        self.assertIn(">Lab Start<", page)
        self.assertIn("Here is what you dropped in. Pick a mode and a style in the chat, and send any links, "
                      "screenshots or videos this one needs.", page)
        self.assertIn("notes.txt", page)                             # a file the intake left out is named

    def test_every_card_takes_a_note(self):
        _, page = self.build(self.project())
        ids = ["take-01", "take-02", "mode-hifi", "mode-lofi", "mode-showcase", "style-harbor", "style-film",
               "style-signal", "send"]
        for i in ids:
            b = block(page, i)
            self.assertRegex(re.match(r"<[^>]*>", b).group(0), r"\bdata-comment-target\b", i)
            self.assertIn("data-note", b, i)
        self.assertIn("window.claude.use('comments')", page)
        self.assertIn("openComposer({ element:", page)
        self.assertIn("fetch('api/notes'", page)                     # storyboard/serve.py, where there are no artifacts
        self.assertEqual(len(re.findall(r'\bid="([^"]+)"', page)), len(set(re.findall(r'\bid="([^"]+)"', page))))

    def test_every_file_it_references_is_in_files_json(self):
        folder, page = self.build(self.project())
        files = json.loads(read(os.path.join(folder, "files.json")))
        for f in files:
            self.assertTrue(os.path.isfile(os.path.join(folder, f)), f)
        refs = references(page)
        self.assertTrue(refs)
        for r in refs:
            self.assertIn(r, files)
        for want in ("posters/01.jpg", "posters/02.jpg", "examples/hifi.mp4", "examples/lofi.mp4",
                     "examples/showcase.mp4", "styles/harbor.jpg", "styles/film.jpg"):
            self.assertIn(want, files)

    def test_no_home_path_and_no_em_dash(self):
        folder, page = self.build(self.project())
        files = read(os.path.join(folder, "files.json"))
        for text in (page, files):
            self.assertNotIn(HOMES, text)
            self.assertNotIn(os.path.expanduser("~"), text)
            self.assertNotIn(self.tmp, text)
            self.assertNotIn("\u2014", text)

    def test_first_lines_from_words_json(self):
        _, page = self.build(self.project())
        self.assertIn("Here is the first thing.", block(page, "take-01"))
        self.assertNotIn("second line", block(page, "take-01"))        # the first sentence only
        first14 = " ".join(LONG.split()[:14])
        self.assertIn(first14 + " ...", block(page, "take-02"))        # no sentence end: 14 words
        self.assertNotIn(" ".join(LONG.split()[:15]), page)

    def test_no_words_yet(self):
        _, page = self.build(self.project(words=False))
        self.assertNotIn("Here is the first thing.", page)
        self.assertIn("transcript", page)                           # says the first lines come later

    def test_a_missing_poster_is_made_from_the_take(self):
        p = self.project()
        os.remove(os.path.join(p, "approvals", "start", "posters", "02.jpg"))
        mp4(os.path.join(p, "raw", "IMG_2851.mov"), seconds=2, size="108x192")
        folder, page = self.build(p)
        self.assertIn('src="posters/02.jpg"', block(page, "take-02"))
        self.assertTrue(os.path.isfile(os.path.join(folder, "posters", "02.jpg")))

    def test_the_command_line(self):
        p = self.project()
        env = dict(os.environ, REEL_KIT_HOME=self.home, REEL_MACHINE_HOME=self.home)
        r = subprocess.run([sys.executable, os.path.join(KIT, "pipeline", "preview.py"), p, "start"], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(p, "approvals", "start", "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(p, "approvals", "start", "files.json")))

    def test_no_intake_stops_with_the_command_to_run(self):
        p = self.project()
        os.remove(os.path.join(p, "intake.json"))
        with self.assertRaises(SystemExit) as e:
            preview.start(p, examples=self.examples)
        self.assertIn("intake.py", str(e.exception))


class Parts(unittest.TestCase):
    def test_length_label(self):
        self.assertEqual(preview.length_label(61.233), "1:01")
        self.assertEqual(preview.length_label(42.4), "0:42")
        self.assertEqual(preview.length_label(59.6), "1:00")
        self.assertEqual(preview.length_label(1805.0), "30:05")

    def test_recorded_label(self):
        utc = datetime.timezone.utc
        self.assertEqual(preview.recorded_label("2026-10-13T19:02:11Z", tz=utc, now=datetime.datetime(2026, 10, 14, tzinfo=utc)),
                         "Oct 13, 7:02 pm")
        self.assertEqual(preview.recorded_label("2025-01-02T09:05:00Z", tz=utc, now=datetime.datetime(2026, 10, 14, tzinfo=utc)),
                         "Jan 2, 2025, 9:05 am")
        self.assertEqual(preview.recorded_label(None), "")
        self.assertEqual(preview.recorded_label("not a time"), "")

    def test_first_line(self):
        self.assertEqual(preview.first_line(WORDS, 0.0, 61.233), "Here is the first thing.")
        self.assertEqual(preview.first_line(WORDS, 61.233, 42.4), " ".join(LONG.split()[:14]) + " ...")
        self.assertEqual(preview.first_line(WORDS, 200.0, 10.0), "")
        short = spread("Ends without a stop", 0.0, 1.0, 0.0)
        self.assertEqual(preview.first_line(short, 0.0, 5.0), "Ends without a stop")        # all it said, no "..."
        punct = [{"text": "Wait", "start": 0, "end": 0.2, "src": 0}, {"text": ",", "start": 0.2, "end": 0.3, "src": 0.2},
                 {"text": "what?", "start": 0.3, "end": 0.6, "src": 0.3}]
        self.assertEqual(preview.first_line(punct, 0.0, 1.0), "Wait, what?")

    def test_encode_note(self):
        plan = INTAKE["plan"]
        self.assertIn("HDR", preview.encode_note(INTAKE["takes"][0], plan))
        self.assertEqual(preview.encode_note(INTAKE["takes"][1], plan), "the takes differ in pix_fmt")
        self.assertEqual(preview.encode_note(INTAKE["takes"][0], dict(plan, mode="copy")), "")
        wide = dict(INTAKE["takes"][1], size=[1920, 1080])
        self.assertIn("1920x1080, fit to 1080x1920", preview.encode_note(wide, dict(plan, why=[])))


if __name__ == "__main__":
    unittest.main()
