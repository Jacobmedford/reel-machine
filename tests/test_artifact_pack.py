"""storyboard/artifact.py: a review page packed for a Claude artifact. The Artifact tool publishes the HTML file alone,
so fonts and images go inside the page as data: URIs, a video waits for its upload_asset url (--fill writes it in),
and a run that finds anything still relative writes nothing."""
import base64
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "storyboard"))
import artifact as A  # noqa: E402

URL = "/_blob/" + "a" * 32
FONT = b"\x00\x01\x00\x00lab sans"
PAGE = """<meta charset="utf-8" />
<title>Lab Cut First Cut</title>
<style>
/* the theme block below */
@font-face { font-family:'Lab Sans'; src:url('fonts/LabSans.ttf') format('truetype'); }
@font-face { font-family:'Spare Face'; src:url('fonts/Spare.ttf') format('truetype'); }
body { font: 400 16px/1.5 'Lab Sans', system-ui, sans-serif; }
</style>
<video id="v" src="first-cut.mp4" poster="poster.jpg" controls></video>
<script>document.getElementById('v').load();</script>
"""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
        fh.write(data)


def run(*args):
    """main() in this process: (exit code, everything it said)"""
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["artifact.py", *args]), contextlib.redirect_stdout(out):
        try:
            A.main()
        except SystemExit as e:
            if isinstance(e.code, str):
                return 1, out.getvalue() + e.code
            return e.code or 0, out.getvalue()
    return 0, out.getvalue()


def relative_refs(html):
    vals = [m.group(2) for m in re.finditer(r"""\s(?:src|poster|href|srcset)\s*=\s*(["'])(.*?)\1""", html, re.S)]
    vals += [m.group(2) for m in re.finditer(r"""url\(\s*(['"]?)([^'")]*)\1\s*\)""", html)]
    return [v for v in vals if not v.startswith(("data:", "/_blob/", "#", "http"))]


class Pack(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.page = os.path.join(self.d, "approvals", "first-cut")
        self.out = os.path.join(self.d, "scratch", "first-cut")
        write(os.path.join(self.page, "index.html"), PAGE)
        write(os.path.join(self.page, "fonts", "LabSans.ttf"), FONT)
        write(os.path.join(self.page, "fonts", "Spare.ttf"), b"\x00\x01\x00\x00spare")
        write(os.path.join(self.page, "poster.jpg"), b"\xff\xd8\xff\xe0poster")
        write(os.path.join(self.page, "first-cut.mp4"), b"\x00\x00\x00\x18ftypmp42 the cut")
        write(os.path.join(self.page, "files.json"),
              json.dumps(["first-cut.mp4", "poster.jpg", "fonts/LabSans.ttf", "fonts/Spare.ttf"]))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def index(self):
        return read(os.path.join(self.out, "index.html"))

    def test_fonts_and_poster_ride_inside_and_the_video_waits_for_its_upload(self):
        code, said = run(self.page, "--out", self.out)
        self.assertEqual(code, 0, said)
        html = self.index()
        self.assertIn("url('data:font/ttf;base64," + base64.b64encode(FONT).decode() + "')", html)
        self.assertIn('poster="data:image/jpeg;base64,', html)
        self.assertEqual(relative_refs(html), ["first-cut.mp4"])
        self.assertNotIn("Spare Face", html)                 # a family nothing on the page names is not carried
        self.assertNotIn("the theme block below", html)      # CSS comments never render: they go
        self.assertIn("UPLOAD 1 file", said)
        self.assertIn(os.path.join(self.page, "first-cut.mp4"), said)
        readable = read(os.path.join(self.out, "readable.html"))
        self.assertIn("[fonts/LabSans.ttf, 12 bytes, sha256 ", readable)
        self.assertNotIn(base64.b64encode(FONT).decode(), readable)

    def test_fill_writes_the_uploaded_url_and_leaves_nothing_relative(self):
        run(self.page, "--out", self.out)
        code, said = run(self.page, "--out", self.out, "--fill", f"first-cut.mp4={URL}")
        self.assertEqual(code, 0, said)
        self.assertIn(f'src="{URL}"', self.index())
        self.assertEqual(relative_refs(self.index()), [])
        self.assertIn("READY", said)
        record = json.loads(read(os.path.join(self.out, "artifact.json")))
        self.assertEqual(record["uploads"][0]["url"], URL)

    def test_a_lone_url_fills_the_one_file_waiting(self):
        code, said = run(self.page, "--out", self.out, "--fill", URL)
        self.assertEqual(code, 0, said)
        self.assertIn(f'src="{URL}"', self.index())

    def test_a_run_with_an_error_writes_nothing(self):
        run(self.page, "--out", self.out, "--fill", f"first-cut.mp4={URL}")
        before = self.index()
        code, said = run(self.page, "--out", self.out, "--fill", "first-cut.mp4=first-cut.mp4")
        self.assertEqual(code, 1)
        self.assertIn("not an uploaded url", said)
        self.assertEqual(self.index(), before)

    def test_a_url_holding_an_older_cut_is_refused(self):
        run(self.page, "--out", self.out, "--fill", f"first-cut.mp4={URL}")
        write(os.path.join(self.page, "first-cut.mp4"), b"\x00\x00\x00\x18ftypmp42 a new cut")
        code, said = run(self.page, "--out", self.out, "--fill", f"first-cut.mp4={URL}")
        self.assertEqual(code, 1)
        self.assertIn("changed since", said)

    def test_a_listed_file_named_only_in_a_script_fails(self):
        write(os.path.join(self.page, "frames", "f000.jpg"), b"\xff\xd8\xff\xe0frame")
        write(os.path.join(self.page, "index.html"), PAGE + "<script>var f = 'frames/f000.jpg';</script>\n")
        write(os.path.join(self.page, "files.json"), json.dumps(["first-cut.mp4", "frames/f000.jpg"]))
        code, said = run(self.page, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("frames/f000.jpg is still a relative ref", said)
        self.assertFalse(os.path.exists(os.path.join(self.out, "index.html")))

    def test_it_never_writes_over_the_page_or_a_page_it_did_not_make(self):
        code, said = run(self.page, "--out", self.page)
        self.assertEqual(code, 1)
        self.assertIn("own folder", said)
        other = os.path.join(self.d, "hand-made")
        write(os.path.join(other, "index.html"), "a page someone made by hand")
        code, said = run(self.page, "--out", other)
        self.assertEqual(code, 1)
        self.assertEqual(read(os.path.join(other, "index.html")), "a page someone made by hand")

    def test_a_page_over_the_viewer_cap_fails(self):
        with mock.patch.object(A, "PAGE_CAP", 200):
            code, said = run(self.page, "--out", self.out)
        self.assertEqual(code, 1)
        self.assertIn("16 MB cap", said)
        self.assertFalse(os.path.exists(os.path.join(self.out, "index.html")))

    def test_a_project_folder_means_its_storyboard(self):
        project = os.path.join(self.d, "lab")
        write(os.path.join(project, "storyboard", "index.html"), '<title>Lab</title><img src="frames/f000.jpg">')
        write(os.path.join(project, "storyboard", "frames", "f000.jpg"), b"\xff\xd8\xff\xe0frame")
        code, said = run(project, "--out", self.out)
        self.assertEqual(code, 0, said)
        self.assertIn("READY", said)
        self.assertIn('src="data:image/jpeg;base64,', self.index())

    def test_srcset_keeps_a_data_url_whole(self):
        self.assertEqual(A.srcset("a.jpg 1x, data:image/png;base64,AA== 2x"),
                         [("a.jpg", "1x"), ("data:image/png;base64,AA==", "2x")])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_a_mov_goes_up_as_an_mp4_phone_copy(self):
        os.remove(os.path.join(self.page, "first-cut.mp4"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=0.5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.join(self.page, "first-cut.mov")], check=True)
        write(os.path.join(self.page, "index.html"), PAGE.replace("first-cut.mp4", "first-cut.mov"))
        code, said = run(self.page, "--out", self.out)
        self.assertEqual(code, 0, said)
        copy = os.path.join(self.out, "upload", "first-cut.mp4")
        self.assertIn(copy, said)
        codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", copy], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(codec, "h264")


class Template(unittest.TestCase):
    def test_the_storyboard_template_names_its_theme_once(self):
        # storyboard.py replaces every __THEME__: one named in a comment pasted the whole theme (every font) twice
        self.assertEqual(read(os.path.join(HERE, "..", "storyboard", "page.html")).count("__THEME__"), 1)


if __name__ == "__main__":
    unittest.main()
