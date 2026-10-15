"""pipeline/inline_vendor.py: vendor scripts inlined into a composition, so a render worker that loses a fetch cannot
lose its animation. Pure string work plus the CLI's in-place rewrite and its .pre-inline copy."""
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import hook  # noqa: E402
import inline_vendor as IV  # noqa: E402

GSAP = "/*! fake gsap */\n!function(t){t.gsap={timeline:function(){return {}}}}(this);\n"
PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="vendor/look.css"></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="2.0000" data-fps="30">
  <video id="v" src="clean.mp4" data-start="0" data-duration="2.0000" data-track-index="1"></video>
</div>
<script src="vendor/gsap.min.js"></script>
<script src="data.js"></script>
<script>
(function () {
  var FPS = 30, TOTAL = 2.0000;
  var tl = gsap.timeline({ paused: true });
  window.__timelines['main'] = tl;
})();
</script>
</body>
</html>
"""


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Scripts(HTMLParser):
    """every <script> element as the browser's tokenizer splits it: (attrs, text)"""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self._cur = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._cur = [dict(attrs), ""]

    def handle_data(self, data):
        if self._cur is not None:
            self._cur[1] += data

    def handle_endtag(self, tag):
        if tag == "script" and self._cur is not None:
            self.out.append(tuple(self._cur))
            self._cur = None


def scripts(doc):
    p = Scripts()
    p.feed(doc)
    p.close()
    return p.out


def payload(src):
    """the bytes a data: URL carries"""
    m = re.fullmatch(r"data:text/javascript;name=[A-Za-z0-9._-]+;base64,([A-Za-z0-9+/=]*)", src)
    assert m, src[:80]
    return base64.b64decode(m.group(1))


class Inline(unittest.TestCase):
    def setUp(self):
        self.pub = tempfile.mkdtemp()
        put(os.path.join(self.pub, "vendor", "gsap.min.js"), GSAP)

    def tearDown(self):
        shutil.rmtree(self.pub, ignore_errors=True)

    def test_the_vendor_script_carries_its_exact_bytes(self):
        out = IV.inline(PAGE, self.pub)
        self.assertNotIn('src="vendor/gsap.min.js"', out)
        a, text = scripts(out)[0]
        self.assertEqual(payload(a["src"]), GSAP.encode())
        self.assertEqual(text, "")
        self.assertIn("gsap", a["src"].split(";base64,")[0])          # the HyperFrames lint finds GSAP by its src
        self.assertEqual(IV.inlined(out), ["vendor/gsap.min.js"])
        self.assertEqual(IV.fetched(out), [])
        self.assertEqual(IV.fetched(PAGE), ["vendor/gsap.min.js"])

    def test_it_runs_where_the_tag_was_before_the_composition_script(self):
        s = scripts(IV.inline(PAGE, self.pub))
        self.assertEqual(len(s), 3)
        self.assertEqual(payload(s[0][0]["src"]), GSAP.encode())
        self.assertEqual(s[1][0].get("src"), "data.js")
        self.assertIn("gsap.timeline", s[2][1])

    def test_everything_else_is_untouched(self):
        out = IV.inline(PAGE, self.pub)
        start = out.index("<script data-inlined=")
        end = out.index("</script>", start) + len("</script>")
        self.assertEqual(out[:start] + out[end:], PAGE.replace('<script src="vendor/gsap.min.js"></script>', ""))
        self.assertIn('<script src="data.js"></script>', out)                 # not a vendor file: stays a fetch
        self.assertIn('<link rel="stylesheet" href="vendor/look.css">', out)  # not a script

    def test_idempotent(self):
        once = IV.inline(PAGE, self.pub)
        self.assertEqual(IV.inline(once, self.pub), once)
        self.assertEqual(IV.inline("<p>no scripts</p>", self.pub), "<p>no scripts</p>")

    def test_quotes_dot_slash_and_extra_attributes(self):
        for tag in ("<script src='vendor/gsap.min.js'></script>", "<script src=./vendor/gsap.min.js></script>",
                    '<SCRIPT type="text/javascript" SRC="vendor/gsap.min.js" ></SCRIPT>',
                    '<script src="vendor/gsap.min.js">\n</script >'):
            out = IV.inline(f"<body>{tag}</body>", self.pub)
            self.assertEqual(IV.inlined(out), ["vendor/gsap.min.js"], tag)
            self.assertEqual(IV.fetched(out), [], tag)
            self.assertEqual(payload(scripts(out)[0][0]["src"]), GSAP.encode(), tag)
        out = IV.inline('<script id="g" src="vendor/gsap.min.js" data-x="1"></script>', self.pub)
        a = scripts(out)[0][0]
        self.assertEqual({k: v for k, v in a.items() if k != "src"},
                         {"id": "g", "data-x": "1", "data-inlined": "vendor/gsap.min.js"})

    def test_several_vendor_files_keep_their_order(self):
        put(os.path.join(self.pub, "vendor", "plugins", "Flip.min.js"), "window.FLIP = 1;")
        doc = '<script src="vendor/gsap.min.js"></script><script src="vendor/plugins/Flip.min.js"></script>'
        out = IV.inline(doc, self.pub)
        self.assertEqual(IV.inlined(out), ["vendor/gsap.min.js", "vendor/plugins/Flip.min.js"])
        self.assertEqual([payload(a["src"]) for a, _ in scripts(out)], [GSAP.encode(), b"window.FLIP = 1;"])

    def test_async_defer_and_module_tags_are_left_alone_and_reported(self):
        for tag in ('<script src="vendor/gsap.min.js" defer></script>', '<script async src="vendor/gsap.min.js"></script>',
                    '<script type="module" src="vendor/gsap.min.js"></script>'):
            self.assertEqual(IV.inline(tag, self.pub), tag)
            self.assertEqual(IV.fetched(tag), ["vendor/gsap.min.js"])

    def test_other_scripts_are_never_inlined(self):
        for tag in ('<script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"></script>',
                    '<script src="/vendor/gsap.min.js"></script>', '<script src="gsap.min.js"></script>',
                    '<script src="vendor/gsap.min.js?v=2"></script>', '<script src="vendor/notes.txt"></script>'):
            self.assertEqual(IV.inline(tag, self.pub), tag)

    def test_a_tag_written_inside_an_inline_script_or_a_comment_is_not_a_tag(self):
        doc = ('<!-- <script src="vendor/gsap.min.js"></script> -->\n'
               "<script>var s = '<script src=\"vendor/gsap.min.js\"><\\/script>';</script>")
        self.assertEqual(IV.inline(doc, self.pub), doc)

    def test_any_library_text_is_safe_in_the_page(self):
        lib = 'var a = "</script><p>not html</p>", b = "<!--<script>", q = \'"\', m = "\u2212"; window.R = [a, b, q, m];'
        put(os.path.join(self.pub, "vendor", "evil.js"), lib)
        out = IV.inline('<body><script src="vendor/evil.js"></script><p id="after">after</p></body>', self.pub)
        s = scripts(out)
        self.assertEqual(len(s), 1)
        self.assertEqual(payload(s[0][0]["src"]), lib.encode("utf-8"))      # the exact bytes, nothing escaped
        self.assertIn('<p id="after">after</p>', out[out.index("</script>"):])

    def test_a_missing_vendor_file_stops_with_its_path(self):
        os.remove(os.path.join(self.pub, "vendor", "gsap.min.js"))
        with self.assertRaises(FileNotFoundError) as cm:
            IV.inline(PAGE, self.pub)
        self.assertIn("vendor/gsap.min.js", str(cm.exception))

    def test_a_path_out_of_vendor_is_refused(self):
        put(os.path.join(self.pub, "secret.js"), "nope")
        with self.assertRaises(ValueError):
            IV.inline('<script src="vendor/../secret.js"></script>', self.pub)

    def test_the_hook_cut_works_the_same_on_an_inlined_page(self):
        plain = hook.truncate(PAGE, 1.0)
        cut = hook.truncate(IV.inline(PAGE, self.pub), 1.0)
        self.assertEqual(IV.inline(plain, self.pub), cut)
        self.assertRegex(cut, r"TOTAL = 1\.0000")


EDIT = '''TITLE = "Lab Inline"
STYLE = "hifi"
SRC = "{src}"
KEEP = [(1.0, 2.2)]
FRAMES = {{"WIDE": (1080, 1920, 0, 0)}}
SHOTS = [(0.0, "WIDE")]
CAPS = [(0.05, "One line.", "", "end")]
CARDS = []
'''
TIMELINE = '''{"fps": 30, "total_audio": 1.2, "total": 1.5, "keep": [{"src_in": 1.0, "src_out": 2.2, "out": 0.0,
 "picture_out": 0.0}], "picture_cuts": [], "reframes": [], "shots": [{"t": 0.0, "frame": "WIDE"}], "pieces": []}'''


class Build(unittest.TestCase):
    """build.py writes the composition with GSAP already inside it"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = self.p = os.path.join(self.tmp, "proj")
        put(os.path.join(p, "style", "style.json"), "{}")
        put(os.path.join(p, "style", "brand.css"), ":root { --c-light: #eee; }\n")
        os.makedirs(os.path.join(p, "style", "fonts"))
        put(os.path.join(p, "public", "vendor", "gsap.min.js"), GSAP)
        put(os.path.join(p, "edit.py"), EDIT.format(src=os.path.join(p, "public", "clean.mp4")))
        put(os.path.join(p, "timeline.json"), TIMELINE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self):
        return subprocess.run([sys.executable, os.path.join(HERE, "..", "pipeline", "build.py"), self.p],
                              capture_output=True, text=True)

    def test_the_built_page_carries_gsap_inline(self):
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.p, "public", "index.html"), encoding="utf-8") as fh:
            doc = fh.read()
        self.assertEqual(IV.inlined(doc), ["vendor/gsap.min.js"])
        self.assertEqual(IV.fetched(doc), [])
        s = scripts(doc)
        self.assertEqual(payload(s[0][0]["src"]), GSAP.encode())   # GSAP runs first, the timeline script after it
        self.assertIn("window.__timelines['main'] = tl;", s[-1][1])

    def test_no_gsap_file_stops_the_build(self):
        os.remove(os.path.join(self.p, "public", "vendor", "gsap.min.js"))
        r = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("vendor/gsap.min.js", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.p, "public", "index.html")))


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        put(os.path.join(self.d, "vendor", "gsap.min.js"), GSAP)
        self.page = os.path.join(self.d, "index.html")
        put(self.page, PAGE)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(HERE, "..", "pipeline", "inline_vendor.py"), *args],
                              capture_output=True, text=True)

    def read(self, p):
        with open(p, encoding="utf-8") as fh:
            return fh.read()

    def test_rewrites_in_place_and_keeps_the_original(self):
        r = self.cli(self.page)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(self.page), IV.inline(PAGE, self.d))
        self.assertEqual(self.read(self.page + ".pre-inline"), PAGE)
        self.assertIn("vendor/gsap.min.js", r.stdout)

    def test_a_second_run_changes_nothing(self):
        self.cli(self.page)
        once, kept = self.read(self.page), self.read(self.page + ".pre-inline")
        r = self.cli(self.page)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(self.page), once)
        self.assertEqual(self.read(self.page + ".pre-inline"), kept)       # the original, not the inlined page

    def test_nothing_to_inline_writes_nothing(self):
        put(self.page, "<p>plain</p>")
        r = self.cli(self.page)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.page + ".pre-inline"))

    def test_vendor_files_from_another_folder(self):
        other = os.path.join(self.d, "card")
        os.makedirs(other)
        page = os.path.join(other, "index.html")
        put(page, PAGE)
        r = self.cli(page, self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(IV.inlined(self.read(page)), ["vendor/gsap.min.js"])

    def test_a_missing_file_fails_and_leaves_the_page(self):
        os.remove(os.path.join(self.d, "vendor", "gsap.min.js"))
        r = self.cli(self.page)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("vendor/gsap.min.js", r.stderr)
        self.assertEqual(self.read(self.page), PAGE)
        self.assertFalse(os.path.exists(self.page + ".pre-inline"))

    def test_a_fetch_it_cannot_inline_fails(self):
        put(self.page, '<script defer src="vendor/gsap.min.js"></script>')
        r = self.cli(self.page)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("vendor/gsap.min.js", r.stderr)

    def test_the_rewrite_never_writes_through_a_hard_link(self):
        twin = os.path.join(self.d, "twin.html")
        os.link(self.page, twin)
        self.cli(self.page)
        self.assertEqual(self.read(twin), PAGE)


if __name__ == "__main__":
    unittest.main()
