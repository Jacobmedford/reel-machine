"""pipeline/animcheck.py: refuse a render whose graphics did not animate. The pure parts (worker slots, probe moments,
the static page, the per-probe verdict) and the whole check on a tiny project with the snapshot step stubbed: the
stub draws the animated page or the static page, and the render is encoded from those pictures, so the check is
proven to pass a good render and fail one where a worker rendered the static page."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import animcheck as AC  # noqa: E402
import inline_vendor as IV  # noqa: E402

FPS = 30


class Slots(unittest.TestCase):
    def test_the_renderers_split_contiguous_runs_of_equal_length(self):
        self.assertEqual(AC.slots(2133, 6), [(0, 356), (356, 712), (712, 1068), (1068, 1424), (1424, 1780), (1780, 2133)])
        self.assertEqual(AC.slots(10, 3), [(0, 4), (4, 8), (8, 10)])

    def test_never_an_empty_slot(self):
        self.assertEqual(AC.slots(4, 6), [(0, 1), (1, 2), (2, 3), (3, 4)])
        self.assertEqual(AC.slots(5, 1), [(0, 5)])

    def test_default_workers_follows_the_renderer(self):
        self.assertEqual(AC.default_workers(10), 6)        # this Mac
        self.assertEqual(AC.default_workers(64), 8)
        self.assertEqual(AC.default_workers(256), 16)


def edit(**kw):
    E = types.SimpleNamespace(CAPS=[], FX=[], BEHIND=[], BOXES=[], OVERLAYS=[], CARDS=[], BW=[], GRADES=[],
                              CUT_WINDOWS=[], CAMERA={}, HOOK=None, END_CARD=None, STYLE="hifi", TOTAL=10.0, END_IN=10.0)
    E.__dict__.update(kw)
    return E


class Windows(unittest.TestCase):
    def test_captions_effects_behind_and_lofi_layers(self):
        E = edit(CAPS=[(1.0, "One *line*", ""), (2.0, "Two", "big", 3.0), (5.0, "End", "", "end")],
                 FX=[dict(id="intro", layer="top", at=0.5, end=1.5), dict(id="cta", layer="over", at=8.0, end="end")],
                 BEHIND=[dict(kind="titles", items=[(4.0, "BIG"), (4.5, "WORD")], end=5.0),
                         dict(kind="float", end=7.0, items=[dict(src="a.mp4", at=6.0, x=0, y=0, w=100)]),
                         dict(kind="plate", src="p.jpg", at=7.5, end=7.9)],
                 BOXES=[dict(text="Hi", at=0.0, end=0.4)], OVERLAYS=[dict(src="o.png", at=9.0, end=9.5)])
        w = {(round(a, 3), round(b, 3), what) for a, b, _, what in AC.windows(E)}
        self.assertIn((1.0, 2.0, 'caption "One line"'), w)
        self.assertIn((2.0, 3.0, 'caption "Two"'), w)
        self.assertIn((5.0, 10.0, 'caption "End"'), w)
        self.assertIn((0.5, 1.5, "effect intro"), w)
        self.assertIn((8.0, 10.0, "effect cta"), w)
        self.assertIn((4.0, 5.0, "behind the head: titles"), w)
        self.assertIn((6.0, 7.0, "behind the head: float"), w)
        self.assertIn((7.5, 7.9, "behind the head: plate"), w)
        self.assertIn((0.0, 0.4, "text box"), w)
        self.assertIn((9.0, 9.5, "overlay"), w)

    def test_lofi_word_captions_come_from_words(self):
        E = edit(STYLE="lofi")
        words = [{"text": "hi", "start": 1.0, "end": 1.4}, {"text": "there", "start": 1.5, "end": 2.0}]
        w = [(a, b, what) for a, b, _, what in AC.windows(E, words)]
        self.assertIn((1.0, 2.0, "word captions"), w)

    def test_edges_are_every_in_and_out_and_cut(self):
        E = edit(CAPS=[(1.0, "One", "", 2.0)], CARDS=[("c1", "cards/c1.mp4", 3.0, 4.0, "dark")], BW=[(5.0, 5.5)],
                 GRADES=[(6.0, 7.0, "warm")], CUT_WINDOWS=[(8.0, 8.5)], CAMERA=dict(punch=[(9.0, 1.1)]))
        e = AC.edges(E, {"picture_cuts": [2.5]}, AC.windows(E))
        for t in (1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 5.5, 6.0, 7.0, 8.0, 8.5, 9.0):
            self.assertIn(t, e)


class Pick(unittest.TestCase):
    def test_the_busiest_moment_in_the_slot_away_from_edges(self):
        wins = [(0.0, 10.0, 2, "caption"), (4.0, 6.0, 3, "effect a")]
        k = AC.pick((0, 300), wins, [4.0, 6.0])
        self.assertTrue(4.0 + 3.5 / FPS <= k / FPS <= 6.0 - 3.5 / FPS, k)
        self.assertAlmostEqual(k / FPS, 5.0, delta=0.2)          # the middle of the busiest stretch

    def test_never_on_an_edge(self):
        wins = [(1.0, 1.2, 5, "pop")]
        k = AC.pick((0, 60), wins, [1.0, 1.2, 0.5])
        for e in (1.0, 1.2, 0.5):
            self.assertGreaterEqual(abs(k / FPS - e), 3.5 / FPS - 1e-9)

    def test_a_calm_slot_takes_its_middle(self):
        self.assertEqual(AC.pick((300, 600), [], []), 450)

    def test_a_slot_full_of_edges_still_gets_a_probe(self):
        k = AC.pick((0, 6), [], [i / FPS for i in range(6)])
        self.assertTrue(0 <= k < 6)

    def test_probes_one_per_slot(self):
        E = edit(TOTAL=4.0, END_IN=4.0, CAPS=[(0.1, "A", "", 1.9), (2.1, "B", "", 3.9)])
        P = AC.probes(E, {"picture_cuts": [2.0]}, 120, 3)
        self.assertEqual(len(P), 3)
        for (s, e), p in zip(AC.slots(120, 3), P):
            self.assertTrue(s <= p["frame"] < e)
            self.assertAlmostEqual(p["t"], p["frame"] / FPS)

    def assert_every_run_probed(self, frames, n, workers, why=""):
        for w in range(1, workers + 1):                      # the renderer may start fewer workers than its ceiling
            for s, e in AC.slots(n, w):
                self.assertTrue(any(s <= k < e for k in frames), f"{why} {w} workers: run {s}-{e - 1} has no probe {frames}")

    def test_fewer_workers_than_the_ceiling_still_get_a_probe_in_every_run(self):
        # the busy moments sit at the start of slot 2 and the end of slot 3: a 5-worker run (427-853) lies between them
        n = 2133
        E = edit(TOTAL=n / FPS, END_IN=n / FPS,
                 FX=[dict(id="a", layer="top", at=12.0, end=13.6), dict(id="b", layer="top", at=33.0, end=35.5)])
        P = AC.probes(E, {"picture_cuts": []}, n, 6)
        self.assert_every_run_probed([p["frame"] for p in P], n, 6)

    def test_every_split_is_covered_on_random_edits(self):
        import random
        rng = random.Random(7)
        for trial in range(60):
            n = rng.randint(60, 5000)
            T = n / FPS
            starts = sorted(rng.uniform(0, T) for _ in range(rng.randint(0, 14)))
            E = edit(TOTAL=T, END_IN=T, CAPS=[(a, f"c{i}", "", min(T, a + rng.uniform(0.3, 4))) for i, a in enumerate(starts)],
                     FX=[dict(id=f"f{i}", layer="top", at=a, end=min(T, a + rng.uniform(0.5, 6)))
                         for i, a in enumerate(sorted(rng.uniform(0, T) for _ in range(rng.randint(0, 6))))])
            cuts = sorted(rng.uniform(0, T) for _ in range(rng.randint(0, 40)))
            for w in (1, 2, 3, 6, 9):
                P = AC.probes(E, {"picture_cuts": cuts}, n, w)
                self.assert_every_run_probed([p["frame"] for p in P], n, w, f"trial {trial} n {n}")
                self.assertEqual([p["frame"] for p in P], sorted({p["frame"] for p in P}))
        for n in (60, 61, 90, 137, 1000, 2133):
            self.assert_every_run_probed([p["frame"] for p in AC.even_probes(n, 6)], n, 6, f"page n {n}")


def random_edit(rng, n):
    """captions and effects at random over n frames, and random picture cuts"""
    T = n / FPS
    starts = sorted(rng.uniform(0, T) for _ in range(rng.randint(0, 14)))
    E = edit(TOTAL=T, END_IN=T, CAPS=[(a, f"c{i}", "", min(T, a + rng.uniform(0.3, 4))) for i, a in enumerate(starts)],
             FX=[dict(id=f"f{i}", layer="top", at=a, end=min(T, a + rng.uniform(0.5, 6)))
                 for i, a in enumerate(sorted(rng.uniform(0, T) for _ in range(rng.randint(0, 6))))])
    return E, {"picture_cuts": sorted(rng.uniform(0, T) for _ in range(rng.randint(0, 40)))}


class PieceProbes(unittest.TestCase):
    """a render made of pieces (pieces.py): each piece is rendered on its own and the producer splits the piece's
    frames over its own workers, so the probes go inside each piece the way probes() places them in a whole render"""

    def test_one_piece_over_the_whole_render_is_the_whole_render_check(self):
        import random
        rng = random.Random(11)
        for trial in range(40):
            n = rng.randint(60, 3000)
            E, TL = random_edit(rng, n)
            for w in (1, 2, 3, 6):
                whole = AC.probes(E, TL, n, w)
                piece = AC.piece_probes(E, TL, [(0, n, w, "p00")])
                self.assertEqual([p["frame"] for p in piece], [p["frame"] for p in whole], f"trial {trial} w {w}")
                self.assertEqual([p["slot"] for p in piece], [f"p00.{p['slot']}" for p in whole])
                self.assertEqual([p["what"] for p in piece], [p["what"] for p in whole])

    def test_every_run_of_every_split_inside_every_piece_has_a_probe(self):
        import random
        rng = random.Random(5)
        for trial in range(40):
            n = rng.randint(200, 3000)
            E, TL = random_edit(rng, n)
            bounds = [0] + sorted(rng.sample(range(1, n), rng.randint(0, 14))) + [n]
            runs = [(a, b, rng.randint(1, 4), f"p{i:02d}") for i, (a, b) in enumerate(zip(bounds, bounds[1:]))]
            P = AC.piece_probes(E, TL, runs)
            self.assertEqual(sum(len([p for p in P if p["piece"] == r[3]]) for r in runs), len(P))
            for a, b, w, label in runs:
                mine = [p for p in P if p["piece"] == label]
                frames = [p["frame"] for p in mine]
                self.assertEqual(frames, sorted(set(frames)))
                self.assertTrue(all(a <= k < b for k in frames), (trial, label, a, b, frames))
                for w2 in range(1, w + 1):                   # the producer may start fewer workers than it planned
                    for s, e in AC.slots(b - a, w2):
                        self.assertTrue(any(a + s <= k < a + e for k in frames),
                                        f"trial {trial} {label} {w2} workers: run {a + s}-{a + e - 1} has no probe")
                for p in mine:
                    self.assertTrue(p["first"] <= p["frame"] <= p["last"])
                    self.assertTrue(a <= p["first"] and p["last"] < b)
                    self.assertRegex(p["slot"], rf"^{label}\.\d+$")
                    self.assertEqual((p["piece_first"], p["piece_last"]), (a, b - 1))
                    self.assertAlmostEqual(p["t"], p["frame"] / FPS)

    def test_slots_are_labelled_by_piece_in_frames_of_the_whole_render(self):
        E = edit(TOTAL=3.0, END_IN=3.0, CAPS=[(0.1, "A", "", 2.9)])
        P = AC.piece_probes(E, {"picture_cuts": []}, [(0, 45, 2, "p00"), (45, 90, 2, "p01")])
        self.assertEqual([p["slot"] for p in P], ["p00.1", "p00.2", "p01.1", "p01.2"])
        self.assertEqual([(p["first"], p["last"]) for p in P], [(0, 22), (23, 44), (45, 67), (68, 89)])
        self.assertEqual([p["piece"] for p in P], ["p00", "p00", "p01", "p01"])

    def test_runs_from_the_piece_table_and_the_cache_metas(self):
        pieces = [dict(index=0, start=0, end=117, key="a"), dict(index=1, start=117, end=284, key="b"),
                  dict(index=12, start=284, end=300, key="c")]
        metas = {"a": dict(workers=2), "b": dict(frames=167)}            # b's meta has no worker count, c has no meta
        self.assertEqual(AC.piece_runs(pieces, metas), [(0, 117, 2, "p00"), (117, 284, 4, "p01"), (284, 300, 4, "p12")])
        self.assertEqual(AC.piece_label(pieces[2]), "p12")


PAGE ="""<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="3.0000" data-fps="30" data-width="1080" data-height="1920">
  <div class="cap" id="cap0">Hello</div>
</div>
<script src="vendor/gsap.min.js"></script>
<script src="data.js"></script>
<script>
(function () {
  var FPS = 30, TOTAL = 3.0000;
  var tl = gsap.timeline({ paused: true });
  tl.set('#cap0', { opacity: 1 }, 0.5);
  window.__timelines['main'] = tl;
})();
</script>
</body></html>
"""


class StaticPage(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "vendor"))
        with open(os.path.join(self.d, "vendor", "gsap.min.js"), "w") as fh:
            fh.write("/* gsap */ window.gsap = {};")
        self.page = IV.inline(PAGE, self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_the_composition_script_becomes_an_empty_timeline(self):
        out = AC.static_page(self.page)
        self.assertNotIn("tl.set('#cap0'", out)
        self.assertIn("window.__timelines['main'] = gsap.timeline({ paused: true }).to({}, { duration: 3.0000 });", out)
        self.assertEqual(IV.inlined(out), ["vendor/gsap.min.js"])          # GSAP itself stays
        self.assertIn('<script src="data.js"></script>', out)
        self.assertEqual(out.replace(AC.static_stub(3.0), ""), self.page[:self.page.index("<script>\n(function")]
                         + self.page[self.page.index("</script>", self.page.index("(function")) + 9:])

    def test_a_page_without_a_timeline_script_is_refused(self):
        with self.assertRaises(ValueError):
            AC.static_page("<html><body><div data-composition-id=\"main\" data-duration=\"1\"></div></body></html>")


def img(caption=None, base=90, h=1920, w=1080):
    """a test picture: flat grey footage, optionally a white caption box at a height that moves with time"""
    a = np.full((h, w, 3), base, np.uint8)
    a[::7, :, :] = base + 25                                        # some texture, so the encode has work to do
    if caption is not None:
        y = 1200 + int(caption) % 200
        a[y:y + 90, 240:840] = 235
    return a


class Verdict(unittest.TestCase):
    def setUp(self):
        self.S, self.F = img(caption=10), img()
        rng = np.random.default_rng(1)
        self.noise = lambda a: np.clip(a.astype(np.int16) + rng.integers(-4, 5, a.shape), 0, 255).astype(np.uint8)

    def test_a_render_that_matches_the_animated_page(self):
        v = AC.verdict(self.noise(self.S), self.S, self.F)
        self.assertEqual(v["state"], "animated")
        self.assertGreater(v["match"], 0.95)

    def test_a_render_that_shows_the_static_page(self):
        v = AC.verdict(self.noise(self.F), self.S, self.F)
        self.assertEqual(v["state"], "static")
        self.assertLess(v["match"], 0.05)

    def test_a_render_that_matches_neither(self):
        v = AC.verdict(np.zeros_like(self.S), self.S, self.F)
        self.assertEqual(v["state"], "neither")

    def test_nothing_animated_here_proves_nothing(self):
        v = AC.verdict(self.noise(self.F), self.F, self.F)
        self.assertEqual(v["state"], "calm")

    def test_a_little_noise_never_counts_as_animation(self):
        v = AC.verdict(self.F, self.F, self.noise(self.F))
        self.assertEqual(v["state"], "calm")


class Decide(unittest.TestCase):
    def row(self, state, expect=True):
        return dict(t=1.0, frame=30, state=state, expect=expect)

    def test_pass_and_fail(self):
        self.assertTrue(AC.decide([self.row("animated"), self.row("calm")])[0])
        self.assertFalse(AC.decide([self.row("animated"), self.row("static")])[0])
        self.assertFalse(AC.decide([self.row("neither")])[0])

    def test_all_calm_passes_only_when_nothing_was_due_on_screen(self):
        self.assertTrue(AC.decide([self.row("calm", expect=False), self.row("calm", expect=False)])[0])
        ok, why = AC.decide([self.row("calm", expect=True), self.row("calm", expect=False)])
        self.assertFalse(ok)
        self.assertIn("script", why)


EDIT = '''TITLE = "Lab Anim"
STYLE = "hifi"
SRC = "{src}"
KEEP = [(0.0, 3.0)]
FRAMES = {{"WIDE": (1080, 1920, 0, 0)}}
SHOTS = [(0.0, "WIDE")]
CAPS = [(0.2, "One", "", 0.9), (1.1, "Two", "", 1.9), (2.1, "Three", "", 2.9)]
CARDS = []
'''
TIMELINE = {"fps": 30, "total_audio": 3.0, "total": 3.0, "keep": [{"src_in": 0.0, "src_out": 3.0, "out": 0.0,
            "picture_out": 0.0}], "picture_cuts": [], "reframes": [], "shots": [{"t": 0.0, "frame": "WIDE"}], "pieces": []}


def fake_snapshots(dirs, times):
    """stands in for two `hyperframes snapshot` runs: the animated page shows a caption whose height follows the time,
    the static page shows none"""
    for d in dirs:
        with open(os.path.join(d, "index.html"), encoding="utf-8") as fh:
            static = AC.STUB_MARK in fh.read()
        os.makedirs(os.path.join(d, "snapshots"), exist_ok=True)
        for i, t in enumerate(times):
            a = img() if static else img(caption=round(t * FPS))
            Image.fromarray(a).save(os.path.join(d, "snapshots", f"frame-{i:02d}-at-{t:g}s.png"))
    return [(d, 0, "") for d in dirs]


def encode(path, frames):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
                          "-r", "30", "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt",
                          "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", path],
                         stdin=subprocess.PIPE)
    for a in frames:
        p.stdin.write(a.tobytes())
    p.stdin.close()
    assert p.wait() == 0


def anim_project(tmp):
    """a 3 s project (90 frames) with a built page, its edit and its timeline"""
    p = os.path.join(tmp, "proj")
    for d in ("public/vendor", "renders", "work", "style"):
        os.makedirs(os.path.join(p, d))
    with open(os.path.join(p, "style", "style.json"), "w") as fh:
        fh.write("{}")
    with open(os.path.join(p, "public", "index.html"), "w") as fh:
        fh.write(PAGE)
    with open(os.path.join(p, "public", "vendor", "gsap.min.js"), "w") as fh:
        fh.write("/* gsap */")
    with open(os.path.join(p, "edit.py"), "w") as fh:
        fh.write(EDIT.format(src=os.path.join(p, "src.mp4")))
    with open(os.path.join(p, "timeline.json"), "w") as fh:
        json.dump(TIMELINE, fh)
    return p


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class Check(unittest.TestCase):
    """the whole check on a 3 s project (90 frames, 3 workers), the snapshots stubbed, the render encoded for real"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = anim_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, frames):
        out = os.path.join(self.p, "renders", "lab-v1.mp4")
        encode(out, frames)
        with mock.patch.object(AC, "run_snapshots", side_effect=fake_snapshots):
            return AC.check(self.p, out, workers=3)

    def test_a_good_render_passes(self):
        ok, rows = self.run_check([img(caption=k) for k in range(90)])
        self.assertTrue(ok, rows)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["state"] for r in rows], ["animated"] * 3)
        self.assertFalse(os.path.exists(os.path.join(self.p, "work", "animcheck")))   # the link trees are gone

    def test_one_worker_on_the_static_page_fails(self):
        frames = [img() if 30 <= k < 60 else img(caption=k) for k in range(90)]      # worker 2 of 3 lost its script
        ok, rows = self.run_check(frames)
        self.assertFalse(ok)
        self.assertEqual([r["state"] for r in rows], ["animated", "static", "animated"])
        self.assertTrue(os.path.exists(os.path.join(self.p, "work", "animcheck", "sheet.jpg")))

    def test_a_render_one_frame_late_still_passes(self):
        ok, rows = self.run_check([img(caption=max(0, k - 1)) for k in range(90)])
        self.assertTrue(ok, rows)

    def test_the_cli_exit_code(self):
        out = os.path.join(self.p, "renders", "lab-v1.mp4")
        encode(out, [img() for _ in range(90)])                                    # every worker static
        with mock.patch.object(AC, "run_snapshots", side_effect=fake_snapshots), \
                mock.patch.object(sys, "argv", ["animcheck.py", self.p, "renders/lab-v1.mp4", "--workers", "3"]):
            with self.assertRaises(SystemExit) as cm:
                AC.main()
        self.assertNotEqual(cm.exception.code, 0)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class PieceCheck(unittest.TestCase):
    """the check of a render made of two pieces (frames 0-44 and 45-89, two producer workers each), the snapshots
    stubbed, the render encoded for real"""
    RUNS = [(0, 45, 2, "p00"), (45, 90, 2, "p01")]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = anim_project(self.tmp)
        self.out = os.path.join(self.p, "renders", "lab-v1.mp4")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, frames, runs=RUNS):
        encode(self.out, frames)
        with mock.patch.object(AC, "run_snapshots", side_effect=fake_snapshots):
            return AC.check(self.p, self.out, runs=runs)

    def write_pieces(self, metas):
        with open(os.path.join(self.p, "renders", "lab-v1.pieces.json"), "w") as fh:
            json.dump([dict(index=0, start=0, end=45, key="k0"), dict(index=1, start=45, end=90, key="k1")], fh)
        cache = os.path.join(self.p, "work", "render-pieces", "cache")
        os.makedirs(cache, exist_ok=True)
        for k, m in metas.items():
            with open(os.path.join(cache, k + ".json"), "w") as fh:
                json.dump(m, fh)

    def cli(self, frames):
        import contextlib
        import io
        encode(self.out, frames)
        self.printed = io.StringIO()
        with mock.patch.object(AC, "run_snapshots", side_effect=fake_snapshots), \
                mock.patch.object(sys, "argv", ["animcheck.py", self.p, "renders/lab-v1.mp4", "--pieces"]), \
                contextlib.redirect_stdout(self.printed):
            try:
                AC.main()
            except SystemExit as e:
                return e.code
        return 0

    def test_a_good_render_passes_with_probes_in_every_piece(self):
        ok, rows = self.run_check([img(caption=k) for k in range(90)])
        self.assertTrue(ok, rows)
        self.assertEqual([r["slot"] for r in rows], ["p00.1", "p00.2", "p01.1", "p01.2"])
        self.assertEqual([r["state"] for r in rows], ["animated"] * 4)
        self.assertFalse(os.path.exists(os.path.join(self.p, "work", "animcheck")))

    def test_a_frozen_worker_run_inside_a_piece_fails_and_names_the_piece(self):
        ok, rows = self.run_check([img() if 45 <= k < 68 else img(caption=k) for k in range(90)])  # p01, worker 1
        self.assertFalse(ok)
        bad = [r for r in rows if r["state"] in ("static", "neither")]
        self.assertEqual([(r["piece"], r["slot"]) for r in bad], [("p01", "p01.1")])
        self.assertTrue(os.path.exists(os.path.join(self.p, "work", "animcheck", "sheet.jpg")))

    def test_no_pieces_to_check_passes_without_a_snapshot(self):
        with mock.patch.object(AC, "run_snapshots", side_effect=AssertionError("no snapshot without a piece")):
            self.assertEqual(AC.check(self.p, self.out, runs=[]), (True, []))

    def test_pieces_that_run_past_the_render_cannot_be_checked(self):
        with self.assertRaises(ValueError):
            self.run_check([img(caption=k) for k in range(90)], runs=[(0, 45, 2, "p00"), (45, 120, 2, "p01")])

    def test_a_probe_on_a_pieces_first_frame_never_borrows_the_frame_before_it(self):
        # the retry a frame either side (clip rounding) stays inside the piece: frame 44 belongs to the piece before
        encode(self.out, [img(caption=k) if k < 45 else img() for k in range(90)])      # p01 static throughout
        P = [dict(AC._entry(45, [(45, 90)], []), slot="p01.1", piece="p01", piece_first=45, piece_last=89)]
        work = os.path.join(self.p, "work", "animcheck")
        with mock.patch.object(AC, "run_snapshots", side_effect=fake_snapshots):
            ok, rows = AC.run(os.path.join(self.p, "public"), self.out, P, 90, work, os.path.join(work, "sheet.jpg"), "x")
        self.assertFalse(ok)
        self.assertEqual(rows[0]["state"], "static")

    def test_the_runs_come_from_the_pieces_json_and_the_cache_metas(self):
        self.write_pieces({"k0": dict(workers=2)})                     # k1: no meta, the fallback worker count
        self.assertEqual(AC.render_runs(self.p, "renders/lab-v1.mp4"), [(0, 45, 2, "p00"), (45, 90, 4, "p01")])
        self.assertEqual(AC.render_runs(self.p, self.out), [(0, 45, 2, "p00"), (45, 90, 4, "p01")])

    def test_the_cli_checks_every_piece(self):
        self.write_pieces({"k0": dict(workers=2), "k1": dict(workers=2)})
        self.assertEqual(self.cli([img(caption=k) for k in range(90)]), 0)
        table = self.printed.getvalue()
        for slot in ("p00.1", "p00.2", "p01.1", "p01.2"):
            self.assertIn(slot, table)
        self.assertIn("4 probes in 2 pieces", table)
        self.assertEqual(self.cli([img() if 45 <= k < 68 else img(caption=k) for k in range(90)]), 1)

    def test_the_cli_without_a_pieces_json_could_not_check(self):
        self.assertEqual(self.cli([img(caption=k) for k in range(90)]), 2)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class Page(unittest.TestCase):
    """--page: a card's own folder and its mp4, no edit.py, one probe in the middle of every worker's run"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cards = os.path.join(self.tmp, "cards")
        self.card = os.path.join(self.cards, "c1")
        os.makedirs(os.path.join(self.card, "vendor"))
        with open(os.path.join(self.card, "index.html"), "w") as fh:
            fh.write(PAGE)
        with open(os.path.join(self.card, "vendor", "gsap.min.js"), "w") as fh:
            fh.write("/* gsap */")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, frames):
        encode(os.path.join(self.card, "c1.mp4"), frames)
        with mock.patch.object(AC, "run_snapshots", side_effect=fake_snapshots):
            return AC.check_page(self.card, "c1.mp4", workers=3)

    def test_even_probes(self):
        self.assertEqual([p["frame"] for p in AC.even_probes(90, 3)], [15, 45, 75])
        self.assertEqual([p["frame"] for p in AC.even_probes(2, 6)], [0, 1])

    def test_a_good_card_passes_and_leaves_nothing_behind(self):
        ok, rows = self.run_check([img(caption=k) for k in range(90)])
        self.assertTrue(ok, rows)
        self.assertEqual([r["state"] for r in rows], ["animated"] * 3)
        self.assertEqual(os.listdir(self.cards), ["c1"])
        self.assertEqual(sorted(os.listdir(self.card)), ["c1.mp4", "index.html", "vendor"])

    def test_a_frozen_run_fails_with_its_pictures_beside_the_render(self):
        ok, rows = self.run_check([img() if 60 <= k < 90 else img(caption=k) for k in range(90)])
        self.assertFalse(ok)
        self.assertEqual([r["state"] for r in rows], ["animated", "animated", "static"])
        self.assertTrue(os.path.exists(os.path.join(self.card, "c1.animcheck.jpg")))
        self.assertEqual(os.listdir(self.cards), ["c1"])

    def test_the_cli(self):
        encode(os.path.join(self.card, "c1.mp4"), [img() for _ in range(90)])
        with mock.patch.object(AC, "run_snapshots", side_effect=fake_snapshots), \
                mock.patch.object(sys, "argv", ["animcheck.py", "--page", self.card, "c1.mp4", "--workers", "3"]):
            with self.assertRaises(SystemExit) as cm:
                AC.main()
        self.assertEqual(cm.exception.code, 1)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class RenderWiring(unittest.TestCase):
    """render.py runs the check after the render and before QA; a failed check stops it before QA and delivery"""

    def setUp(self):
        import render
        from scipy.io import wavfile
        self.render = render
        self.tmp = tempfile.mkdtemp()
        p = self.p = os.path.join(self.tmp, "proj")
        for d in ("public/vendor", "renders", "work", "style/fonts"):
            os.makedirs(os.path.join(p, d))
        with open(os.path.join(p, "style", "style.json"), "w") as fh:
            fh.write("{}")
        with open(os.path.join(p, "style", "brand.css"), "w") as fh:
            fh.write(":root { --c-light: #eee; }\n")
        with open(os.path.join(p, "public", "vendor", "gsap.min.js"), "w") as fh:
            fh.write("/* gsap */")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=3",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                        os.path.join(p, "public", "clean.mp4")], check=True)
        x = (0.1 * np.sin(np.arange(3 * 48000) / 48000 * 2 * np.pi * 220) * 32767).astype(np.int16)
        wavfile.write(os.path.join(p, "public", "master.wav"), 48000, np.stack([x, x], 1))
        with open(os.path.join(p, "edit.py"), "w") as fh:
            fh.write(EDIT.format(src=os.path.join(p, "public", "clean.mp4")))
        with open(os.path.join(p, "timeline.json"), "w") as fh:
            json.dump(TIMELINE, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def go(self, check_code):
        calls, real = [], subprocess.run

        def fake_hf(args, cwd):
            calls.append(args[0])
            if args[0] == "render":
                out = os.path.normpath(os.path.join(cwd, args[args.index("-o") + 1]))
                real(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-frames:v",
                      "90", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", out], check=True)
            return subprocess.CompletedProcess(args, 0, "check ok", "")

        def fake_run(cmd, *a, **kw):
            script = os.path.basename(cmd[1]) if len(cmd) > 1 else ""
            if script in ("animcheck.py", "qa.py"):
                calls.append(script)
                return subprocess.CompletedProcess(cmd, check_code if script == "animcheck.py" else 0)
            return real(cmd, *a, **kw)

        delivered = []
        with mock.patch.object(self.render, "hf", side_effect=fake_hf), \
                mock.patch.object(self.render.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(self.render, "deliver", side_effect=lambda *a: delivered.append(a)), \
                mock.patch.object(sys, "argv", ["render.py", self.p, "lab-v1"]):
            try:
                self.render.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return calls, delivered, code

    def test_the_check_runs_between_the_render_and_qa(self):
        calls, delivered, code = self.go(0)
        self.assertEqual(calls, ["check", "render", "animcheck.py", "qa.py"])
        self.assertEqual(len(delivered), 1)
        with open(os.path.join(self.p, "public", "index.html"), encoding="utf-8") as fh:
            self.assertEqual(IV.fetched(fh.read()), [])                   # the page it rendered fetched no GSAP

    def test_a_failed_check_stops_before_qa_and_delivery(self):
        calls, delivered, code = self.go(1)
        self.assertEqual(calls, ["check", "render", "animcheck.py"])
        self.assertEqual(delivered, [])
        self.assertIn("did not animate", str(code))
        self.assertIn("Nothing was delivered", str(code))

    def test_a_check_that_could_not_run_stops_too_and_says_so(self):
        calls, delivered, code = self.go(2)
        self.assertEqual(calls, ["check", "render", "animcheck.py"])
        self.assertEqual(delivered, [])
        self.assertIn("could not run", str(code))
        self.assertIn("Nothing was delivered", str(code))


if __name__ == "__main__":
    unittest.main()
