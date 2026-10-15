"""pack.py and new.py --pack: named style packs, built offline, swapped into projects without losing the old one.

Every test runs in a temp REEL_MACHINE_HOME (the new name wins over the old one, so a shell that sets either never
points a test at a real home). Font files are dummies with the names style.py gives Google fonts, so a
build never touches the network (style.font_faces, the download, is patched to fail if anything calls it).
Run: cd <kit> && PY -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(os.path.dirname(HERE), "pipeline")
sys.path.insert(0, PIPE)

import pack as PK  # noqa: E402
import style as ST  # noqa: E402

STYLE = {
    "fonts": {"display": {"family": "League Gothic", "italic": False, "weight": 400},
              "text": {"family": "Barlow Condensed", "italic": False, "weight": 700},
              "mono": {"family": "IBM Plex Mono", "italic": False, "weight": 500},
              "caption": {"family": "Barlow Condensed", "italic": False, "weight": 700}},
    "colors": {"accent": "#E2744D"},
    "modes": {"hifi": {"j_lead": 0.3}, "lofi": {"j_lead": 0.2}},
}
EXTRA = "/* film: test treatment */\nhtml body .cap.onfoot { background:none; }\n"


def put(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
        fh.write(data)


def get(path, mode="r"):
    with open(path, mode) as fh:
        return fh.read()


def write_pack(d, colors=None, extra=None, local=("LeagueGothic-Regular.ttf", "AccentSerif-Regular.ttf"), j_lead=None):
    os.makedirs(d, exist_ok=True)
    S = json.loads(json.dumps(STYLE))
    S["colors"].update(colors or {})
    if j_lead is not None:
        S["modes"]["hifi"]["j_lead"] = j_lead
    put(os.path.join(d, "style.json"), json.dumps(S, indent=1))
    put(os.path.join(d, "STYLE.md"), f"# {os.path.basename(d)}\n")
    if extra is not None:
        put(os.path.join(d, "extra.css"), extra)
    if local:
        os.makedirs(os.path.join(d, "local-fonts"), exist_ok=True)
        for f in local:
            put(os.path.join(d, "local-fonts", f), b"not a real font: " + f.encode())


def google_files(d, names=("BarlowCondensed-normal-400.ttf", "BarlowCondensed-normal-700.ttf",
                           "IBMPlexMono-normal-500.ttf")):
    os.makedirs(d, exist_ok=True)
    for n in names:
        put(os.path.join(d, n), b"dummy " + n.encode())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-pack-")
        self.home = os.path.join(self.tmp, "home")
        self.default = os.path.join(self.home, "style")
        write_pack(self.default)
        google_files(os.path.join(self.default, "fonts"))          # the default pack's downloaded Google fonts
        put(os.path.join(self.default, "brand.css"), "/* the default pack, built by its own wrapper */\n")
        write_pack(os.path.join(self.home, "packs", "film"), colors={"accent": "#F0B49A"}, extra=EXTRA)
        write_pack(os.path.join(self.home, "packs", "signal"), extra="html body .cap { color:var(--c-ink); }\n",
                   j_lead=0.15)
        os.makedirs(os.path.join(self.home, "packs", "broken"))     # a folder without style.json is not a pack
        self.env = mock.patch.dict(os.environ, {"REEL_MACHINE_HOME": self.home})
        self.env.start()
        self.net = mock.patch.object(ST, "font_faces", side_effect=AssertionError("a pack build went to the network"))
        self.net.start()

    def tearDown(self):
        self.net.stop()
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class PackDir(Base):
    def test_default_names_map_to_style(self):
        self.assertEqual(PK.pack_dir(None), self.default)
        self.assertEqual(PK.pack_dir("harbor"), self.default)

    def test_named_pack_maps_to_packs(self):
        self.assertEqual(PK.pack_dir("film"), os.path.join(self.home, "packs", "film"))

    def test_unknown_pack_stops_with_the_list(self):
        with self.assertRaises(SystemExit) as e:
            PK.pack_dir("nope")
        msg = str(e.exception)
        for name in ("harbor", "film", "signal"):
            self.assertIn(name, msg)
        self.assertNotIn("broken", msg)

    def test_pack_without_style_json_stops_with_the_list(self):
        with self.assertRaises(SystemExit) as e:
            PK.pack_dir("broken")
        self.assertIn("film", str(e.exception))

    def test_names_never_leave_packs(self):
        for bad in ("../style", "film/..", "", "."):
            with self.assertRaises(SystemExit):
                PK.pack_dir(bad)

    def test_list(self):
        self.assertEqual(PK.names(), ["harbor", "film", "signal"])


class Cli(Base):
    def run_cli(self, *args):
        env = dict(os.environ, REEL_MACHINE_HOME=self.home)
        return subprocess.run([sys.executable, os.path.join(PIPE, "pack.py"), *args], capture_output=True, text=True,
                              env=env)

    def test_list_names_every_pack(self):
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("harbor", "film", "signal"):
            self.assertIn(name, r.stdout)

    def test_build_refuses_a_default_pack_with_its_own_wrapper(self):
        put(os.path.join(self.default, "apply-style.sh"), "#!/bin/sh\n")
        for name in ("harbor", "default"):
            r = self.run_cli("build", name)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("apply-style.sh", r.stderr)
            self.assertEqual(get(os.path.join(self.default, "brand.css")),
                             "/* the default pack, built by its own wrapper */\n")

    def test_build_rebuilds_a_default_pack_without_a_wrapper(self):
        """a pack.py install home: hand edits to style/, then `pack.py build harbor` (or default) brings brand.css up
        to date with its local fonts and extra.css, offline (the Google faces come from style/fonts)"""
        for name, accent in (("harbor", "#3366FF"), ("default", "#AA2200")):
            sj = os.path.join(self.default, "style.json")
            S = json.loads(get(sj))
            S["colors"]["accent"] = accent
            put(sj, json.dumps(S, indent=1))
            put(os.path.join(self.default, "extra.css"), f"/* edited by hand: {name} */\n")
            r = self.run_cli("build", name)
            self.assertEqual(r.returncode, 0, r.stderr)
            css = get(os.path.join(self.default, "brand.css"))
            self.assertIn(f"--c-accent: {accent}", css)
            self.assertIn(f"edited by hand: {name}", css)
            self.assertIn("font-family:'League Gothic'; src:url('fonts/LeagueGothic-Regular.ttf')", css)
            self.assertIn("src:url('fonts/BarlowCondensed-normal-700.ttf')", css)
            self.assertTrue(os.path.exists(os.path.join(self.default, "fonts", "LeagueGothic-Regular.ttf")))

    def test_build_of_the_default_pack_needs_one(self):
        shutil.rmtree(self.default)
        r = self.run_cli("build", "harbor")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("onboarding", r.stderr)


class Build(Base):
    def setUp(self):
        super().setUp()
        self.film = PK.pack_dir("film")

    def brand(self):
        return get(os.path.join(self.film, "brand.css"), "rb")

    def test_build_twice_is_byte_identical(self):
        PK.build(self.film)
        first = self.brand()
        PK.build(self.film)
        self.assertEqual(first, self.brand())

    def test_extra_css_appended_once_after_the_tokens(self):
        PK.build(self.film)
        PK.build(self.film)
        css = self.brand().decode()
        self.assertEqual(css.count("film: test treatment"), 1)
        self.assertLess(css.index("--c-accent: #F0B49A"), css.index("film: test treatment"))

    def test_local_fonts_copied_with_their_faces(self):
        PK.build(self.film)
        css = self.brand().decode()
        self.assertTrue(os.path.exists(os.path.join(self.film, "fonts", "LeagueGothic-Regular.ttf")))
        self.assertIn("font-family:'League Gothic'; src:url('fonts/LeagueGothic-Regular.ttf')", css)
        self.assertIn("font-family:'AccentSerif'; src:url('fonts/AccentSerif-Regular.ttf')", css)
        self.assertNotIn("font-family:'League Gothic'; src:url('fonts/LeagueGothic-normal", css)

    def test_google_fonts_reused_offline_from_the_default_pack(self):
        PK.build(self.film)
        css = self.brand().decode()
        self.assertTrue(os.path.exists(os.path.join(self.film, "fonts", "BarlowCondensed-normal-700.ttf")))
        self.assertIn("src:url('fonts/IBMPlexMono-normal-500.ttf')", css)

    def test_missing_family_goes_to_the_kit_download(self):
        os.remove(os.path.join(self.default, "fonts", "IBMPlexMono-normal-500.ttf"))
        self.net.stop()
        rule = "@font-face { font-family:'IBM Plex Mono'; src:url('fonts/IBMPlexMono-normal-500.ttf') format('truetype'); font-style:normal; font-weight:500; font-display:block; }"
        with mock.patch.object(ST, "font_faces", return_value=[rule]) as dl:
            PK.build(self.film)
        self.net.start()
        asked = {f["family"] for f in dl.call_args[0][0]["fonts"].values()}
        self.assertEqual(asked, {"IBM Plex Mono"})
        self.assertIn(rule, self.brand().decode())

    def test_build_without_extra_css(self):
        os.remove(os.path.join(self.film, "extra.css"))
        PK.build(self.film)
        self.assertIn(b"--c-accent", self.brand())

    def test_build_needs_style_json(self):
        with self.assertRaises(SystemExit):
            PK.build(os.path.join(self.home, "packs", "broken"))


class Use(Base):
    def setUp(self):
        super().setUp()
        self.project = os.path.join(self.home, "projects", "lab")
        os.makedirs(os.path.join(self.project, "style"))
        put(os.path.join(self.project, "style", "style.json"), '{"marker": "old"}')

    def test_use_keeps_the_old_style_under_a_new_name(self):
        PK.use(self.project, "film")
        old = os.path.join(self.project, f"style-before-film-{time.strftime('%m-%d-%y')}")
        self.assertEqual(json.loads(get(os.path.join(old, "style.json"))), {"marker": "old"})
        new = json.loads(get(os.path.join(self.project, "style", "style.json")))
        self.assertEqual(new["colors"]["accent"], "#F0B49A")
        self.assertIn(b"film: test treatment", get(os.path.join(self.project, "style", "brand.css"), "rb"))

    def test_use_twice_numbers_the_old_copies(self):
        PK.use(self.project, "film")
        PK.use(self.project, "film")
        stamp = time.strftime('%m-%d-%y')
        self.assertTrue(os.path.isdir(os.path.join(self.project, f"style-before-film-{stamp}")))
        self.assertTrue(os.path.isdir(os.path.join(self.project, f"style-before-film-{stamp}-2")))

    def test_use_unknown_pack_changes_nothing(self):
        before = sorted(os.listdir(self.project))
        with self.assertRaises(SystemExit):
            PK.use(self.project, "nope")
        self.assertEqual(sorted(os.listdir(self.project)), before)
        self.assertEqual(json.loads(get(os.path.join(self.project, "style", "style.json"))), {"marker": "old"})

    def test_use_pack_without_style_json_changes_nothing(self):
        with self.assertRaises(SystemExit) as e:
            PK.use(self.project, "broken")
        self.assertIn("film", str(e.exception))
        self.assertEqual(json.loads(get(os.path.join(self.project, "style", "style.json"))), {"marker": "old"})
        self.assertFalse([d for d in os.listdir(self.project) if d.startswith("style-before")])

    def test_use_rebuilds_a_stale_pack(self):
        PK.build(PK.pack_dir("film"))
        css = os.path.join(PK.pack_dir("film"), "brand.css")
        os.utime(css, (time.time() - 60, time.time() - 60))
        put(os.path.join(PK.pack_dir("film"), "extra.css"), EXTRA + "/* added later */\n")
        PK.use(self.project, "film")
        self.assertIn(b"added later", get(os.path.join(self.project, "style", "brand.css"), "rb"))

    def test_use_harbor_copies_the_default_pack_as_is(self):
        PK.use(self.project, "harbor")
        self.assertEqual(get(os.path.join(self.project, "style", "brand.css")),
                         "/* the default pack, built by its own wrapper */\n")


class NewPack(Base):
    """new.py end to end in a subprocess (it reads REEL_MACHINE_HOME at import)"""

    @classmethod
    def setUpClass(cls):
        cls.clipdir = tempfile.mkdtemp(prefix="reel-machine-clip-")
        cls.clip = os.path.join(cls.clipdir, "take.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x568:d=0.2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.clip], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.clipdir, ignore_errors=True)

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.home, "vendor"))
        put(os.path.join(self.home, "vendor", "gsap.min.js"), "// gsap")

    def new(self, *args):
        env = dict(os.environ, REEL_MACHINE_HOME=self.home)
        return subprocess.run([sys.executable, os.path.join(PIPE, "new.py"), *args], capture_output=True, text=True,
                              env=env)

    def test_without_pack_copies_the_default_pack(self):
        r = self.new("vid", self.clip, "--mode", "hifi")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = os.path.join(self.home, "projects", "vid", "style")
        self.assertEqual(get(os.path.join(got, "style.json")), get(os.path.join(self.default, "style.json")))
        self.assertEqual(get(os.path.join(got, "brand.css")), "/* the default pack, built by its own wrapper */\n")

    def test_with_pack_copies_the_named_pack_built(self):
        r = self.new("vid", self.clip, "--mode", "lofi", "--pack", "film")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = os.path.join(self.home, "projects", "vid", "style")
        self.assertEqual(json.loads(get(os.path.join(got, "style.json")))["colors"]["accent"], "#F0B49A")
        self.assertIn("film: test treatment", get(os.path.join(got, "brand.css")))
        self.assertTrue(os.path.exists(os.path.join(got, "fonts", "AccentSerif-Regular.ttf")))

    def test_unknown_pack_stops_before_making_the_project(self):
        r = self.new("vid", self.clip, "--mode", "hifi", "--pack", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("film", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, "projects", "vid")))

    def test_pack_without_style_json_stops_before_making_the_project(self):
        r = self.new("vid", self.clip, "--mode", "hifi", "--pack", "broken")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("signal", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, "projects", "vid")))

    def test_style_is_still_an_alias_of_mode(self):
        r = self.new("vid", self.clip, "--style", "lofi", "--pack", "signal")
        self.assertEqual(r.returncode, 0, r.stderr)
        edit = get(os.path.join(self.home, "projects", "vid", "edit.py"))
        self.assertIn('STYLE = "lofi"', edit)


if __name__ == "__main__":
    unittest.main()
