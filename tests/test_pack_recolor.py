"""pack.py lint, recolor and install: a pack's colours stay on its palette, a creator's palette moves every pack by
role, and install never touches a pack that is already in the home folder.

Every install and recolor test runs in a temp REEL_KIT_HOME with a temp kit packs folder. Nothing reaches the network
(style.font_faces, the Google Fonts download, is patched) or the render browser (draw_board is patched).
Run: cd <kit> && PY -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import pack as P  # noqa: E402
import style as ST  # noqa: E402

S = {"colors": {"light": "#EBDFBF", "dark": "#232A22", "accent": "#E2744D", "caption_box": "rgba(47,67,58,.94)"}}


class Lint(unittest.TestCase):
    def test_palette_values_pass(self):
        self.assertEqual(P.lint_colors(S, ".a{color:#ebdfbf;background:rgba(226,116,77,.5)}"), [])

    def test_a_stray_color_is_named(self):
        self.assertEqual(P.lint_colors(S, ".a{color:#123456}"), ["#123456"])

    def test_short_hex_and_rgb_read_as_their_colour(self):
        self.assertEqual(P.lint_colors(S, ".a{color:#abc;border-color:rgb(1,2,3)}"), ["#AABBCC", "#010203"])

    def test_selectors_and_comments_are_not_colours(self):
        css = ("/* faded coral #123456 */\n#add .x { color:#ebdfbf; }\n"
               "@media (min-width: 1px) { .a:hover #bad { border:1px solid #abc; } }\n"
               "@keyframes k { 0% { background:#E2744D; } }")
        self.assertEqual(P.lint_colors(S, css), ["#AABBCC"])

    def test_a_colour_inside_a_data_url_is_read(self):
        css = ":root { --grain: url(\"data:image/svg+xml;utf8,<svg><rect fill='#654321'/></svg>\"); }"
        self.assertEqual(P.lint_colors(S, css), ["#654321"])

    def test_style_json_values_are_linted_too(self):
        self.assertEqual(P.lint_colors(dict(S, modes={"showcase": {"motif": "a ribbon in #0000FF"}}), ""), ["#0000FF"])

    def test_each_stray_colour_is_named_once(self):
        self.assertEqual(P.lint_colors(S, ".a{color:#123456} .b{color:#123456}"), ["#123456"])


class Recolor(unittest.TestCase):
    def test_hex_and_rgba_forms_move_and_alpha_stays(self):
        m = {"#E2744D": "#3366FF"}
        self.assertEqual(P.recolor_text("#e2744d rgba(226,116,77,.5)", m), "#3366FF rgba(51,102,255,.5)")

    def test_unmapped_text_is_untouched(self):
        self.assertEqual(P.recolor_text("#000000 url(a.png)", {"#E2744D": "#3366FF"}), "#000000 url(a.png)")

    def test_short_hex_rgb_and_percent_alpha(self):
        self.assertEqual(P.recolor_text("#fff rgb(255,255,255) rgba(255, 255, 255, 40%)", {"#FFFFFF": "#102030"}),
                         "#102030 rgb(16,32,48) rgba(16,32,48,40%)")

    def test_an_rgba_target_keeps_each_occurrence_alpha(self):
        self.assertEqual(P.recolor_text("rgba(47,67,58,.5) #2F433A", {"rgba(47,67,58,.94)": "rgba(16,22,47,.9)"}),
                         "rgba(16,22,47,.5) #10162F")

    def test_a_selector_is_never_rewritten(self):
        self.assertEqual(P.recolor_text("#add .x { color:#E2744D; }", {"#E2744D": "#3366FF"}),
                         "#add .x { color:#3366FF; }")


class PaletteOf(unittest.TestCase):
    def test_roles_and_the_series_as_s1_s2_s3(self):
        s = {"colors": {"accent": "#E2744D", "series": ["#E2744D", "#8F9A79"], "grid": True}}
        self.assertEqual(P.palette_of(s), {"accent": "#E2744D", "s1": "#E2744D", "s2": "#8F9A79"})


# ---------------------------------------------------------------- the four looks, as the kit draws them in Harbor
HARBOR = {"light": "#EBDFBF", "dark": "#232A22", "ink": "#232A22", "muted_light": "#5B6350",
          "muted_dark": "rgba(235,223,191,.6)", "hair_light": "#C6BB8E", "hair_dark": "rgba(235,223,191,.22)",
          "accent": "#E2744D", "accent_on_light": "#A3471F", "negative": "#B5739D", "negative_on_light": "#7E3F6A",
          "positive": "#8F9A79", "positive_on_light": "#3B5549", "series": ["#E2744D", "#8F9A79", "#C6BB8E"],
          "caption_box": "rgba(47,67,58,.94)", "caption_ink": "#EBDFBF", "caption_dim": "rgba(235,223,191,.45)",
          "textbox_bg": "#EBDFBF", "textbox_ink": "#232A22"}
FILM = dict(HARBOR, accent="#F0B49A")                       # its own faded accent: a colour Harbor does not have
SIGNAL = dict(HARBOR, caption_box="#E2744D", caption_ink="#232A22", caption_dim="rgba(35,42,34,.7)",
              textbox_bg="#E2744D", textbox_ink="#232A22")  # the slab is the accent, ink on it
TERMINAL = dict(HARBOR, caption_box="rgba(35,42,34,.92)", caption_ink="#EBDFBF", caption_dim="rgba(235,223,191,.42)",
                textbox_bg="rgba(35,42,34,.94)", textbox_ink="#EBDFBF")   # the box is the dark ground, a touch clear
PALETTE = {"light": "#F4F1EA", "dark": "#10162F", "ink": "#10162F", "accent": "#3366FF",
           "caption_box": "rgba(16,22,47,.9)"}


class ByRole(unittest.TestCase):
    def new(self, pack, palette=None):
        return P.recolor_colors(P.palette_of({"colors": HARBOR}), P.palette_of({"colors": pack}), palette or PALETTE)

    def test_harbor_roles_take_the_creators_colours(self):
        c = self.new(HARBOR)
        self.assertEqual((c["light"], c["dark"], c["accent"], c["caption_box"]),
                         ("#F4F1EA", "#10162F", "#3366FF", "rgba(16,22,47,.9)"))

    def test_a_role_the_palette_leaves_out_keeps_harbors_colour(self):
        c = self.new(HARBOR)
        self.assertEqual((c["negative"], c["muted_light"], c["accent_on_light"]), ("#B5739D", "#5B6350", "#A3471F"))

    def test_a_shade_of_a_harbor_colour_follows_it(self):
        c = self.new(HARBOR)
        self.assertEqual((c["muted_dark"], c["caption_ink"], c["s1"]), ("rgba(244,241,234,.6)", "#F4F1EA", "#3366FF"))

    def test_signal_slab_follows_the_accent_not_the_caption_box(self):
        c = self.new(SIGNAL)
        self.assertEqual((c["caption_box"], c["caption_ink"], c["caption_dim"], c["textbox_bg"]),
                         ("#3366FF", "#10162F", "rgba(16,22,47,.7)", "#3366FF"))

    def test_terminal_box_follows_the_dark_ground_at_its_own_alpha(self):
        c = self.new(TERMINAL)
        self.assertEqual((c["caption_box"], c["textbox_bg"], c["caption_ink"]),
                         ("rgba(16,22,47,.92)", "rgba(16,22,47,.94)", "#F4F1EA"))

    def test_a_colour_harbor_does_not_have_takes_the_creators_colour_for_its_role(self):
        self.assertEqual(self.new(FILM)["accent"], "#3366FF")

    def test_one_role_given_moves_that_role_only(self):
        c = self.new(HARBOR, {"caption_ink": "#FFFFFF"})
        self.assertEqual((c["caption_ink"], c["light"], c["textbox_bg"]), ("#FFFFFF", "#EBDFBF", "#EBDFBF"))


# ---------------------------------------------------------------- install and recolor in a temp home
FONTS = {"display": {"family": "Anton", "italic": False, "weight": 400},
         "text": {"family": "Barlow Condensed", "italic": False, "weight": 700},
         "mono": {"family": "IBM Plex Mono", "italic": False, "weight": 500},
         "caption": {"family": "Barlow Condensed", "italic": False, "weight": 700}}
EXTRA = {"harbor": ":root { --font-accent: 'Young Serif', Georgia, serif; }\n",
         "film": "html body .cap .em { color:#E2744D; background:rgba(35,42,34,.5); }\n",
         "signal": "html body .cap { font-family:'Barlow Condensed'; background:#E2744D; }\n",
         "terminal": "html body .cap { color:var(--c-box-ink); }\n"}


def put(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
        fh.write(data)


def get(path):
    with open(path) as fh:
        return fh.read()


def write_kit_pack(root, name, colors):
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "local-fonts"))
    fonts = json.loads(json.dumps(FONTS))
    if name == "terminal":
        fonts["caption"] = {"family": "IBM Plex Mono", "italic": False, "weight": 500}
    put(os.path.join(d, "style.json"), json.dumps({"version": 1, "creator": {"name": "", "handle": "", "site": ""},
                                                  "fonts": fonts, "colors": colors,
                                                  "modes": {"hifi": {"j_lead": 0.3}}}, indent=2))
    put(os.path.join(d, "STYLE.md"), f"# {name}\n")
    put(os.path.join(d, "extra.css"), EXTRA[name])
    put(os.path.join(d, "local-fonts", "Anton-Regular.ttf"), b"not a real font")
    put(os.path.join(d, "local-fonts", "OFL.txt"), "SIL Open Font License, Version 1.1\n")


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reelkit-recolor-")
        self.home = os.path.join(self.tmp, "home")
        self.kit = os.path.join(self.tmp, "kit", "packs")
        for name, colors in (("harbor", HARBOR), ("film", FILM), ("signal", SIGNAL), ("terminal", TERMINAL)):
            write_kit_pack(self.kit, name, colors)
        self.palette = os.path.join(self.tmp, "palette.json")
        put(self.palette, json.dumps(PALETTE))
        self.drawn = []
        self.patches = [mock.patch.dict(os.environ, {"REEL_MACHINE_HOME": self.home, "REEL_KIT_HOME": self.home}),
                        mock.patch.object(P, "KIT_PACKS", self.kit),
                        mock.patch.object(ST, "font_faces", return_value=[]),
                        mock.patch.object(P, "draw_board", side_effect=lambda d: self.drawn.append(d) or True)]
        for p in self.patches:
            p.start()
        self.assertTrue(os.path.abspath(P.home()).startswith(os.path.abspath(self.tmp)))   # never a real home

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def quiet(self, fn, *a, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = fn(*a, **kw)
        return got, out.getvalue()

    def pack(self, name):
        return os.path.join(self.home, "style") if name == "harbor" else os.path.join(self.home, "packs", name)

    def style(self, name):
        return json.loads(get(os.path.join(self.pack(name), "style.json")))

    def cli(self, *args):
        with mock.patch.object(sys, "argv", ["pack.py", *args]):
            return self.quiet(P.main)


class Install(Home):
    def test_harbor_goes_to_style_and_the_others_to_packs(self):
        made, _ = self.quiet(P.install)
        self.assertEqual(made, [self.pack(n) for n in ("harbor", "film", "signal", "terminal")])
        for d in made:
            self.assertTrue(os.path.exists(os.path.join(d, "local-fonts", "OFL.txt")))
            self.assertTrue(os.path.exists(os.path.join(d, "fonts", "Anton-Regular.ttf")))
            self.assertIn("font-family:'Anton'; src:url('fonts/Anton-Regular.ttf')", get(os.path.join(d, "brand.css")))
        self.assertEqual(self.drawn, made)
        self.assertEqual(P.names(), ["harbor", "film", "signal", "terminal"])

    def test_without_a_palette_the_harbor_colours_stay(self):
        self.quiet(P.install)
        self.assertEqual(self.style("harbor")["colors"], HARBOR)
        self.assertEqual(self.style("signal")["colors"], SIGNAL)

    def test_a_palette_recolors_every_pack_by_role(self):
        self.quiet(P.install, palette=P.load_palette(self.palette))
        self.assertEqual(self.style("harbor")["colors"]["series"], ["#3366FF", "#8F9A79", "#C6BB8E"])
        self.assertEqual(self.style("harbor")["colors"]["negative"], "#B5739D")
        self.assertEqual(self.style("film")["colors"]["accent"], "#3366FF")
        self.assertEqual(self.style("signal")["colors"]["caption_box"], "#3366FF")
        self.assertEqual(self.style("terminal")["colors"]["caption_box"], "rgba(16,22,47,.92)")
        self.assertIn("--c-accent: #3366FF", get(os.path.join(self.pack("film"), "brand.css")))

    def test_the_raw_colours_in_extra_css_move_and_lint_stays_clean(self):
        self.quiet(P.install, palette=P.load_palette(self.palette))
        self.assertEqual(get(os.path.join(self.pack("film"), "extra.css")),
                         "html body .cap .em { color:#3366FF; background:rgba(16,22,47,.5); }\n")
        for n in ("harbor", "film", "signal", "terminal"):
            self.assertEqual(P.lint_colors(self.style(n), get(os.path.join(self.pack(n), "extra.css"))), [], n)

    def test_a_pack_already_in_the_home_is_kept_as_it_is(self):
        os.makedirs(self.pack("harbor"))
        put(os.path.join(self.pack("harbor"), "style.json"), '{"marker": "mine"}')
        put(os.path.join(self.pack("harbor"), "brand.css"), "/* mine */\n")
        os.makedirs(self.pack("film"))
        put(os.path.join(self.pack("film"), "style.json"), '{"marker": "my film"}')
        made, out = self.quiet(P.install, palette=P.load_palette(self.palette))
        self.assertEqual(get(os.path.join(self.pack("harbor"), "style.json")), '{"marker": "mine"}')
        self.assertEqual(get(os.path.join(self.pack("harbor"), "brand.css")), "/* mine */\n")
        self.assertEqual(get(os.path.join(self.pack("film"), "style.json")), '{"marker": "my film"}')
        self.assertEqual(made, [self.pack("signal"), self.pack("terminal")])
        self.assertIn("kept as it is", out)

    def test_a_text_face_replaces_the_text_and_matching_caption_face(self):
        self.quiet(P.install, text_font="Inter")
        h, t = self.style("harbor")["fonts"], self.style("terminal")["fonts"]
        self.assertEqual((h["text"]["family"], h["caption"]["family"]), ("Inter", "Inter"))
        self.assertEqual((t["text"]["family"], t["caption"]["family"]), ("Inter", "IBM Plex Mono"))
        self.assertIn("font-family:'Inter';", get(os.path.join(self.pack("signal"), "extra.css")))

    def test_cli_install_with_a_palette_and_no_boards(self):
        self.cli("install", "--palette", self.palette, "--no-boards")
        self.assertEqual(self.style("signal")["colors"]["textbox_bg"], "#3366FF")
        self.assertEqual(self.drawn, [])

    def test_a_bad_palette_stops_before_anything_changes(self):
        for bad in ({"accnet": "#3366FF"}, {"accent": "blue"}, {"series": "#3366FF"}, ["#3366FF"]):
            put(self.palette, json.dumps(bad))
            with self.assertRaises(SystemExit):
                self.cli("install", "--palette", self.palette)
        self.assertFalse(os.path.exists(self.home))

    def test_no_packs_in_the_kit_stops(self):
        shutil.rmtree(self.kit)
        with self.assertRaises(SystemExit):
            self.quiet(P.install)


class RecolorPack(Home):
    def setUp(self):
        super().setUp()
        self.quiet(P.install)
        self.drawn.clear()

    def test_recolor_starts_from_the_kit_pack_every_time(self):
        p2 = os.path.join(self.tmp, "p2.json")
        put(p2, json.dumps({"accent": "#AA2200"}))
        self.cli("recolor", "signal", "--palette", self.palette)
        self.cli("recolor", "signal", "--palette", p2)
        c, d = self.style("signal")["colors"], self.pack("signal")
        self.assertEqual((c["caption_box"], c["light"]), ("#AA2200", "#EBDFBF"))   # light: Harbor's, not the last palette's
        self.assertEqual(get(os.path.join(d, "extra.css")),
                         "html body .cap { font-family:'Barlow Condensed'; background:#AA2200; }\n")
        self.assertIn("--c-box: #AA2200", get(os.path.join(d, "brand.css")))
        stamp = time.strftime("%m-%d-%y")
        self.assertEqual(json.loads(get(os.path.join(d, f"before-recolor-{stamp}", "style.json")))["colors"], SIGNAL)
        self.assertEqual(json.loads(get(os.path.join(d, f"before-recolor-{stamp}-2", "style.json")))["colors"]["caption_box"],
                         "#3366FF")
        self.assertEqual(self.drawn, [d, d])
        self.assertEqual(P.names(), ["harbor", "film", "signal", "terminal"])

    def test_recolor_keeps_the_packs_other_settings(self):
        sj = os.path.join(self.pack("film"), "style.json")
        s = json.loads(get(sj))
        s["modes"]["hifi"]["j_lead"] = 0.12
        put(sj, json.dumps(s))
        self.cli("recolor", "film", "--palette", self.palette)
        self.assertEqual(self.style("film")["modes"]["hifi"]["j_lead"], 0.12)
        self.assertEqual(self.style("film")["colors"]["accent"], "#3366FF")

    def test_recolor_an_unknown_pack_stops_with_the_list(self):
        with self.assertRaises(SystemExit) as e:
            self.cli("recolor", "nope", "--palette", self.palette)
        self.assertIn("signal", str(e.exception))

    def test_recolor_needs_a_palette_or_a_text_face(self):
        with self.assertRaises(SystemExit):
            self.cli("recolor", "film")

    def test_a_default_pack_with_its_own_build_is_left_to_its_wrapper(self):
        put(os.path.join(self.pack("harbor"), "apply-style.sh"), "#!/bin/sh\n")
        put(os.path.join(self.pack("harbor"), "brand.css"), "/* built by its wrapper */\n")
        _, out = self.cli("recolor", "harbor", "--palette", self.palette, "--no-boards")
        self.assertEqual(self.style("harbor")["colors"]["accent"], "#3366FF")
        self.assertEqual(get(os.path.join(self.pack("harbor"), "brand.css")), "/* built by its wrapper */\n")
        self.assertIn("apply-style.sh", out)


class LintCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reelkit-lint-")
        self.pack = os.path.join(self.tmp, "mine")
        os.makedirs(self.pack)
        put(os.path.join(self.pack, "style.json"), json.dumps({"colors": HARBOR}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lint(self):
        home = os.path.join(self.tmp, "home")
        env = dict(os.environ, REEL_MACHINE_HOME=home, REEL_KIT_HOME=home)
        return subprocess.run([sys.executable, os.path.join(os.path.dirname(P.__file__), "pack.py"), "lint", self.pack],
                              capture_output=True, text=True, env=env)

    def test_a_stray_colour_fails_and_is_named(self):
        put(os.path.join(self.pack, "extra.css"), ".a { color:#123456; }\n")
        r = self.lint()
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("#123456", r.stdout)

    def test_a_clean_pack_passes(self):
        put(os.path.join(self.pack, "extra.css"), ".a { color:#E2744D; background:rgba(35,42,34,.5); }\n")
        r = self.lint()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Board(unittest.TestCase):
    def test_draw_board_runs_the_onboarding_board_on_the_pack(self):
        with mock.patch.object(P.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertTrue(P.draw_board("/somewhere/packs/film"))
        self.assertEqual(run.call_args[0][0][1:],
                         [os.path.join(P.KIT, "onboarding", "board.py"), "--pack", "/somewhere/packs/film"])


if __name__ == "__main__":
    unittest.main()
