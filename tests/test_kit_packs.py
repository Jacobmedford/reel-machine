"""the four packs the kit ships (packs/): open fonts with their licence beside them, the kit's neutral creator, every
colour on the palette, and a build that declares each local face by the name the pack's CSS asks for.

Builds run on a temp copy in a temp REEL_MACHINE_HOME; the Google Fonts download is patched (nothing reaches the
network). Run: cd <kit> && PY -m unittest discover -s tests -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(KIT, "pipeline"))
import pack as P  # noqa: E402
import style as ST  # noqa: E402

PACKS = os.path.join(KIT, "packs")
NAMES = ["harbor", "film", "signal", "terminal"]
LOCAL = {"LeagueGothic-Regular.ttf": "League Gothic", "DMSerifDisplay-Regular.ttf": "DM Serif Display"}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def style(name):
    return json.loads(read(os.path.join(PACKS, name, "style.json")))


class Shipped(unittest.TestCase):
    def test_the_kit_ships_four_packs_harbor_first(self):
        with mock.patch.object(P, "KIT_PACKS", PACKS):
            self.assertEqual(P.kit_names(), NAMES)

    def test_each_pack_has_its_sources(self):
        for n in NAMES:
            for f in ("style.json", "STYLE.md", "extra.css"):
                self.assertTrue(os.path.isfile(os.path.join(PACKS, n, f)), f"{n}/{f}")

    def test_open_fonts_ship_with_their_licence_beside_them(self):
        for n in NAMES:
            d = os.path.join(PACKS, n, "local-fonts")
            self.assertEqual(sorted(f for f in os.listdir(d) if f.lower().endswith((".ttf", ".otf"))), sorted(LOCAL), n)
            ofl = read(os.path.join(d, "OFL.txt"))
            self.assertIn("SIL Open Font License, Version 1.1", ofl)
            for f, family in LOCAL.items():
                self.assertIn(f"{f}: {family}", ofl, n)
        for root, _, files in os.walk(PACKS):
            if any(f.lower().endswith((".ttf", ".otf")) for f in files) and os.path.basename(root) == "local-fonts":
                self.assertIn("OFL.txt", files, root)

    def test_the_display_face_and_the_accent_serif(self):
        for n in NAMES:
            S = style(n)
            self.assertEqual(S["fonts"]["display"]["family"], "League Gothic", n)
            self.assertIn("--font-accent: 'DM Serif Display', Georgia, serif;", read(os.path.join(PACKS, n, "extra.css")))

    def test_no_creator_until_they_give_theirs(self):
        for n in NAMES:
            self.assertEqual(style(n)["creator"], {"name": "", "handle": "", "site": ""}, n)

    def test_every_pack_passes_its_contrast_checks(self):
        """a clean pack builds without a WARNING: Signal answers its one deliberate variant in style.json's checks"""
        for n in NAMES:
            self.assertEqual(ST.check(ST.load(os.path.join(PACKS, n, "style.json"))), [], n)

    def test_every_colour_is_on_the_palette(self):
        for n in NAMES:
            self.assertEqual(P.lint_colors(style(n), read(os.path.join(PACKS, n, "extra.css"))), [], n)

    def test_style_md_has_the_mode_sections(self):
        for n in NAMES:
            md = read(os.path.join(PACKS, n, "STYLE.md"))
            for h in ("## Type", "## Colour", "## Captions", "## Hi-fi", "## Lo-fi", "## Showcase", "## Never"):
                self.assertIn(h, md, f"{n}: {h}")


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-kitpacks-")
        self.patches = [mock.patch.dict(os.environ, {"REEL_MACHINE_HOME": os.path.join(self.tmp, "home"),
                                                     "REEL_KIT_HOME": os.path.join(self.tmp, "home")}),
                        mock.patch.object(ST, "font_faces", return_value=[])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_declares_each_local_face_by_its_family_name(self):
        for n in NAMES:
            d = os.path.join(self.tmp, n)
            shutil.copytree(os.path.join(PACKS, n), d, ignore=shutil.ignore_patterns("board", "fonts", "brand.css"))
            with mock.patch("builtins.print"):
                css = read(P.build(d))
            for f, family in LOCAL.items():
                self.assertIn(f"font-family:'{family}'; src:url('fonts/{f}')", css, n)
                self.assertTrue(os.path.exists(os.path.join(d, "fonts", f)), n)
            self.assertIn("--font-display: 'League Gothic'", css, n)
            self.assertLess(css.index("--font-display"), css.index("--font-accent: 'DM Serif Display'"), n)


if __name__ == "__main__":
    unittest.main()
