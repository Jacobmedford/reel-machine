"""pieces.py pure parts: piece planning on beat boundaries, window inputs, cache keys, dirty detection, media
window digests, seam verdicts, where the renderer keeps its work. No rendering here."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import pieces as PC  # noqa: E402

F = PC.FPS

TINY_EDIT = '''TITLE = "Lab Pieces"
STYLE = "hifi"
SRC = "{src}"
KEEP = [(0.0, 3.0)]
FRAMES = {{"WIDE": (1080, 1920, 0, 0)}}
SHOTS = [(0.0, "WIDE")]
CAPS = [(0.2, "One", "", 0.9)]
CARDS = []
'''
TINY_TIMELINE = {"fps": 30, "total_audio": 3.0, "total": 3.0, "keep": [{"src_in": 0.0, "src_out": 3.0, "out": 0.0,
                 "picture_out": 0.0}], "picture_cuts": [], "reframes": [], "shots": [{"t": 0.0, "frame": "WIDE"}],
                 "pieces": []}


def tiny_project(root):
    """the least a Project reads: edit.py, timeline.json and the project's own style pack"""
    p = os.path.join(root, "proj")
    os.makedirs(os.path.join(p, "style"))
    with open(os.path.join(p, "style", "style.json"), "w") as fh:
        fh.write("{}")
    with open(os.path.join(p, "edit.py"), "w") as fh:
        fh.write(TINY_EDIT.format(src=os.path.join(p, "src.mp4")))
    with open(os.path.join(p, "timeline.json"), "w") as fh:
        json.dump(TINY_TIMELINE, fh)
    return p


class WorkDir(unittest.TestCase):
    """the piece renderer and cut.py are two different caches: the renderer keeps its own in work/render-pieces/"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = tiny_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_renderer_works_in_work_render_pieces(self):
        P = PC.Project(self.p)
        self.assertEqual(P.work, os.path.join(self.p, "work", "render-pieces"))
        self.assertEqual(P.cache, os.path.join(self.p, "work", "render-pieces", "cache"))
        self.assertEqual(P.frames, 90)

    def test_never_in_the_folder_cut_py_keeps_its_pieces_in(self):
        P = PC.Project(self.p)
        cut_store = os.path.join(self.p, "work", "pieces")
        self.assertFalse(P.work.startswith(cut_store + os.sep) or P.work == cut_store)
        self.assertFalse(P.cache.startswith(cut_store + os.sep))


class Marks(unittest.TestCase):
    """the animation check's pass in a cached piece's meta, and a piece that failed it set aside, never reused"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        work = os.path.join(self.tmp, "proj", PC.WORK)
        self.P = types.SimpleNamespace(work=work, cache=os.path.join(work, "cache"))
        os.makedirs(self.P.cache)
        for i, k in enumerate(("a", "b")):
            self.piece(k, i)

    def piece(self, k, i=0):
        with open(os.path.join(self.P.cache, k + ".mp4"), "wb") as fh:
            fh.write(b"\0" * 10)
        with open(os.path.join(self.P.cache, k + ".json"), "w") as fh:
            json.dump(dict(index=i, key=k, workers=2), fh)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_pass_mark_keeps_the_meta_and_takes_the_piece_off_the_list(self):
        table = [dict(index=0, key="a"), dict(index=1, key="b"), dict(index=2, key="c")]
        self.assertEqual([p["key"] for p in PC.unchecked(self.P, table)], ["a", "b", "c"])
        PC.mark_checked(self.P, ["a", "c"])                   # c has no meta: nothing to mark, nothing written
        self.assertEqual([p["key"] for p in PC.unchecked(self.P, table)], ["b", "c"])
        self.assertEqual(PC.meta_of(self.P, "a"), dict(index=0, key="a", workers=2, animcheck="pass"))
        self.assertEqual(PC.meta_of(self.P, "c"), {})
        self.assertFalse(os.path.exists(os.path.join(self.P.cache, "c.json")))

    def test_a_set_aside_piece_leaves_the_cache_under_its_key_and_the_time(self):
        when = time.mktime((2026, 10, 14, 9, 5, 7, 0, 0, -1))
        got = PC.set_aside(self.P, "a", when)
        self.assertEqual(sorted(os.path.basename(p) for p in got), ["a-20261014-090507.json", "a-20261014-090507.mp4"])
        self.assertFalse(os.path.exists(os.path.join(self.P.cache, "a.mp4")))
        self.assertFalse(os.path.exists(os.path.join(self.P.cache, "a.json")))
        self.piece("a")                                       # rendered again, failed again in the same second
        again = PC.set_aside(self.P, "a", when)
        self.assertEqual(sorted(os.path.basename(p) for p in again), ["a-20261014-090507-2.json", "a-20261014-090507-2.mp4"])
        self.assertEqual(len(os.listdir(os.path.join(self.P.work, "rejected"))), 4)
        self.assertTrue(os.path.exists(os.path.join(self.P.cache, "b.mp4")))


class PatchPlan(unittest.TestCase):
    """a note that only changes index.html text moves the previous plan to the new composition's name: the compiled
    page gets the edit, and the plan's own records (meta/videos.json) follow the folder to its new name, intact"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        w = self.work = os.path.join(self.tmp, "proj", PC.WORK)
        self.old, self.new, self.st = os.path.join(w, "plan-old"), os.path.join(w, "plan-new"), os.path.join(w, "stage")
        page = "".join(f"line {i}\n" for i in range(30)).replace("line 10\n", "var T = { open: 0.266 };\n")
        self.write(os.path.join(self.st, "index.html"), page)
        self.write(os.path.join(self.st, "brand.css"), ":root {}\n")
        self.write(os.path.join(self.old, "compiled", "index.html"), "<head>@font-face{src:url(data:...)}</head>\n" + page)
        self.videos = {"videos": [{"id": "v", "src": "clean.mp4", "frames": os.path.join(self.old, "videos", "v")}]}
        self.write(os.path.join(self.old, "meta", "videos.json"), json.dumps(self.videos, indent=2))
        PC.save_source(self.old, self.st)
        self.write(os.path.join(self.st, "index.html"), page.replace("open: 0.266", "open: 0.4"))   # the note

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_the_plan_moves_with_its_records_intact(self):
        self.assertTrue(PC.patch_plan(self.old, self.new, self.st))
        self.assertFalse(os.path.exists(self.old) or os.path.exists(self.old + ".source"))
        with open(os.path.join(self.new, "compiled", "index.html"), encoding="utf-8") as fh:
            self.assertIn("var T = { open: 0.4 };", fh.read())
        with open(os.path.join(self.new, "meta", "videos.json"), encoding="utf-8") as fh:
            got = json.load(fh)
        self.assertEqual(got["videos"][0]["frames"], os.path.join(self.new, "videos", "v"))
        with open(os.path.join(self.new + ".source", "index.html"), encoding="utf-8") as fh:
            self.assertIn("open: 0.4", fh.read())

    def test_any_other_staged_change_needs_a_new_plan(self):
        self.write(os.path.join(self.st, "brand.css"), ":root { --c: red; }\n")
        self.assertFalse(PC.patch_plan(self.old, self.new, self.st))
        self.assertTrue(os.path.exists(self.old))


DAY = 86400.0


class Prune(unittest.TestCase):
    """prune: the piece renderer's regenerable leftovers go, only ever inside work/render-pieces/; cut.py's pieces in
    work/pieces/, the project's own folders and anything a link points at stay"""
    NOW = time.mktime((2026, 10, 14, 12, 0, 0, 0, 0, -1))

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = self.p = os.path.join(self.tmp, "proj")
        self.outside = os.path.join(self.tmp, "elsewhere")
        work = os.path.join(p, PC.WORK)
        self.P = types.SimpleNamespace(project=p, work=work, cache=os.path.join(work, "cache"), plan_dir=None)
        self.keepers = []                                    # every file prune must leave alone
        for rel in ("public/clean.mp4", "public/index.html", "renders/v1.mp4", "raw/take.mp4", "assets/aroll.mp4",
                    "cards/c1/c1.mp4", "fx/hook/fx.js", "work/pieces/" + "ab" * 20 + ".mp4", "work/pieces/voice-1.wav",
                    "work/pieces/join.txt", "work/notes.log", "elsewhere/plan-x/frames/f.png"):
            self.keepers.append(self.file(os.path.join(self.tmp, rel) if rel.startswith("elsewhere") else
                                          os.path.join(p, rel), 10))
        for d, age in (("plan-aaa", 3 * DAY), ("plan-bbb", 1 * DAY)):
            self.file(os.path.join(work, d, "plan.json"), 10, age)
            self.file(os.path.join(work, d, "frames", "000001.png"), 1000, age)
            self.file(os.path.join(work, d + ".source", "index.html"), 10, age)
        self.file(os.path.join(work, "plan-ccc.source", "index.html"), 10, 5 * DAY)      # a source without its plan
        os.symlink(os.path.join(self.outside, "plan-x"), os.path.join(work, "plan-zzz"))  # a link out of the work dir
        for rel in ("plan-a.json", "packets/t.json", "driver.log", "concat.txt", "slices.json"):
            self.keepers.append(self.file(os.path.join(work, rel), 10))
        os.makedirs(os.path.join(work, "stage"))
        os.symlink(os.path.join(p, "public", "clean.mp4"), os.path.join(work, "stage", "clean.mp4"))
        self.file(os.path.join(work, "png", "p03", "frame-0001.png"), 500)
        self.file(os.path.join(work, "png", "p02.perf.json"), 50)          # the producer's note beside each piece
        rej = os.path.join(work, "rejected")
        for name, age in (("old-20261001-120000", None), ("new-20261013-120000", None), ("odd", 9 * DAY)):
            for ext in (".mp4", ".json"):
                self.file(os.path.join(rej, name + ext), 100, age)
        for key, age in (("cur0", 30 * DAY), ("cur1", 30 * DAY), ("old1", 9 * DAY), ("old2", 5 * DAY), ("old3", 2 * DAY)):
            self.file(os.path.join(self.P.cache, key + ".mp4"), 1000, age)
            self.file(os.path.join(self.P.cache, key + ".json"), 24, age)
        self.table = [dict(index=0, key="cur0"), dict(index=1, key="cur1")]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def file(self, path, size, age=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(b"\0" * size)
        if age is not None:
            os.utime(path, (self.NOW - age, self.NOW - age))
        return path

    def left(self, *rel):
        return os.path.lexists(os.path.join(self.P.work, *rel))

    def assert_keepers(self):
        for f in self.keepers:
            self.assertTrue(os.path.exists(f), f)
        self.assertTrue(os.path.islink(os.path.join(self.P.work, "stage", "clean.mp4")))

    def test_everything_regenerable_goes_but_the_current_plan_and_table(self):
        self.P.plan_dir = os.path.join(self.P.work, "plan-aaa")         # the plan this run rendered from
        out = PC.prune(self.P, self.table, budget=1024, now=self.NOW)       # room for one unused entry
        self.assertTrue(self.left("plan-aaa", "frames", "000001.png") and self.left("plan-aaa.source"))
        for gone in ("plan-bbb", "plan-bbb.source", "plan-ccc.source", "plan-zzz", "png"):
            self.assertFalse(self.left(gone), gone)
        self.assertTrue(os.path.exists(os.path.join(self.outside, "plan-x", "frames", "f.png")))   # only the link went
        self.assertEqual(sorted(os.listdir(os.path.join(self.P.work, "rejected"))),
                         ["new-20261013-120000.json", "new-20261013-120000.mp4"])
        self.assertEqual(sorted(os.listdir(self.P.cache)),
                         ["cur0.json", "cur0.mp4", "cur1.json", "cur1.mp4", "old3.json", "old3.mp4"])
        self.assert_keepers()
        self.assertEqual((out["plans"], out["rejected"], out["png"], out["evicted"]), (2, 2, 1, 2))
        self.assertGreater(out["freed"], 2000)
        self.assertEqual(os.path.getmtime(os.path.join(self.P.cache, "cur0.mp4")), self.NOW)    # last used: now
        self.assertIn("2 old plans", PC.prune_line(out))

    def test_when_nothing_rendered_the_newest_plan_stays(self):
        out = PC.prune(self.P, self.table, budget=1 << 30, now=self.NOW)
        self.assertTrue(self.left("plan-bbb", "plan.json") and self.left("plan-bbb.source"))
        self.assertFalse(self.left("plan-aaa"))
        self.assertEqual(out["evicted"], 0)                               # the unused entries fit the budget
        self.assertEqual(len(os.listdir(self.P.cache)), 10)
        self.assert_keepers()

    def test_no_budget_keeps_only_the_current_table(self):
        PC.prune(self.P, self.table, budget=0, now=self.NOW)
        self.assertEqual(sorted(os.listdir(self.P.cache)), ["cur0.json", "cur0.mp4", "cur1.json", "cur1.mp4"])
        self.assert_keepers()

    def test_a_project_without_a_piece_render_is_left_as_it_is(self):
        P = types.SimpleNamespace(work=os.path.join(self.tmp, "none", PC.WORK),
                                  cache=os.path.join(self.tmp, "none", PC.WORK, "cache"), plan_dir=None)
        self.assertEqual(PC.prune(P, [], budget=0)["freed"], 0)
        self.assertFalse(os.path.exists(P.work))

    def test_the_budget_comes_from_the_environment_in_mib(self):
        with unittest.mock.patch.dict(os.environ, {"REEL_MACHINE_PIECES_BUDGET": "512"}):
            self.assertEqual(PC.budget(), 512 << 20)
        with unittest.mock.patch.dict(os.environ, {"REEL_MACHINE_PIECES_BUDGET": "lots"}):
            self.assertEqual(PC.budget(), 1 << 30)
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REEL_MACHINE_PIECES_BUDGET", None)
            os.environ.pop("REEL_KIT_PIECES_BUDGET", None)
            self.assertEqual(PC.budget(), 1 << 30)
            os.environ["REEL_KIT_PIECES_BUDGET"] = "256"                # the old name still works
            self.assertEqual(PC.budget(), 256 << 20)

    def test_the_cli(self):
        P = self.P

        class FakeProject:
            def __init__(self, project, strict=False):
                self.__dict__.update(vars(P))

            def pieces(self):
                return [dict(index=0, key="cur0"), dict(index=1, key="cur1")]

        printed = io.StringIO()
        with unittest.mock.patch.object(PC, "Project", FakeProject), \
                unittest.mock.patch.object(sys, "argv", ["pieces.py", self.p, "prune"]), \
                unittest.mock.patch.dict(os.environ, {"REEL_MACHINE_PIECES_BUDGET": "0"}), \
                contextlib.redirect_stdout(printed):
            PC.main()
        self.assertIn("prune:", printed.getvalue())
        self.assertFalse(self.left("plan-aaa"))
        self.assertTrue(self.left("plan-bbb"))
        self.assertEqual(sorted(os.listdir(P.cache)), ["cur0.json", "cur0.mp4", "cur1.json", "cur1.mp4"])
        self.assert_keepers()


def edit(**kw):
    E = types.SimpleNamespace(CAPS=[], BOXES=[], OVERLAYS=[], BEHIND=[], CUT_WINDOWS=[], BW=[], GRADES=[], CAMERA={},
                              FX=[], CARDS=[], SOUND={}, HOLD=0.4, CANVAS=(1080, 1920), STYLE="hifi")
    for k, v in kw.items():
        setattr(E, k, v)
    return E


class Planner(unittest.TestCase):
    def check_cover(self, wins, n):
        self.assertEqual(wins[0][0], 0)
        self.assertEqual(wins[-1][1], n)
        for (a, b), (c, d) in zip(wins, wins[1:]):
            self.assertEqual(b, c)
        for a, b in wins:
            self.assertLess(a, b)

    def test_hook_first_ends_on_first_cut_after_hook(self):
        cuts = [2.8667, 3.9, 5.7, 9.4667, 15.7667]
        wins = PC.plan_pieces(20.0, PC.candidates(cuts, [], 20.0), [], hook=3.626)
        self.assertEqual(wins[0], (0, PC.fr(3.9)))
        self.check_cover(wins, PC.fr(20.0))

    def test_pieces_within_bounds(self):
        cuts = [x * 0.9 for x in range(1, 80)]          # a cut every 0.9 s: plenty of choice
        total = 72.0
        wins = PC.plan_pieces(total, PC.candidates(cuts, [], total), [], hook=2.0)
        self.check_cover(wins, PC.fr(total))
        for a, b in wins[1:-1]:
            self.assertGreaterEqual((b - a) / F, PC.LO - 1e-9)
            self.assertLessEqual((b - a) / F, PC.HI + 1e-9)
        self.assertLessEqual((wins[-1][1] - wins[-1][0]) / F, PC.HI + 1e-9)

    def test_long_take_without_cuts_is_split_evenly(self):
        total = 30.0
        wins = PC.plan_pieces(total, PC.candidates([3.0], [], total), [], hook=2.5)
        self.check_cover(wins, PC.fr(total))
        self.assertEqual(wins[0], (0, PC.fr(3.0)))
        for a, b in wins:
            self.assertLessEqual((b - a) / F, PC.HI + 1e-9)

    def test_avoids_cutting_through_an_effect(self):
        # cuts at 4, 9.5, 10, 15; an effect spans 8.0-11.0: an edge at 9.5 or 10 cuts it, so the planner pays
        # length cost instead and ends a piece at 15 (from 4: 11 s is too long) -> it must still cover; check that
        # with an alternative cut outside the effect available, the effect is not cut
        cuts = [4.0, 7.9, 9.5, 11.1, 15.0, 20.0]
        spans = [(8.0, 11.0, "fx")]
        wins = PC.plan_pieces(20.0, PC.candidates(cuts, [], 20.0), spans, hook=3.5)
        edges = {b for _, b in wins}
        self.assertNotIn(PC.fr(9.5), edges)
        self.check_cover(wins, PC.fr(20.0))

    def test_short_reel_is_one_piece(self):
        self.assertEqual(PC.plan_pieces(3.0, [], [], hook=3.0), [(0, 90)])

    def test_card_edges_are_candidates_and_snapped(self):
        c = PC.candidates([2.86666], [("c1", "cards/c1.mp4", 6.6, 9.4667, "dark", "")], 20.0)
        self.assertEqual(c, [86, 198, 284])

    def test_candidates_skip_zero_and_total(self):
        self.assertEqual(PC.candidates([0.0, 10.0, 12.0], [], 12.0), [300])


class Hook(unittest.TestCase):
    def test_first_sentence(self):
        w = [dict(start=0.1, end=0.4, text="I"), dict(start=0.5, end=1.2, text="edited."), dict(start=1.3, end=1.9, text="Then")]
        self.assertAlmostEqual(PC.hook_end(w, 10.0), 1.2)

    def test_no_sentence_end(self):
        self.assertEqual(PC.hook_end([dict(start=0, end=1, text="hi")], 10.0), 3.0)

    def test_hold_is_added_and_clamped(self):
        w = [dict(start=0.5, end=2.8, text="video.")]
        self.assertAlmostEqual(PC.hook_end(w, 10.0, hold=0.4), 3.2)
        self.assertEqual(PC.hook_end(w, 3.0, hold=0.4), 3.0)


class Inputs(unittest.TestCase):
    def setUp(self):
        self.E = edit(
            CAPS=[(1.0, "one", ""), (2.0, "two", "", 2.5), (6.0, "six", "", "end")],
            FX=[dict(id="a", layer="top", at=0.0, end=2.0), dict(id="b", layer="cam", at=5.0, end="end")],
            CARDS=[("c1", "cards/c1.mp4", 3.0, 4.0, "dark", "x")],
            GRADES=[(4.5, 5.5, "warm")], BW=[(1.5, 1.8)], CUT_WINDOWS=[(0.1, 1.9)],
            CAMERA=dict(settles=[3.0, 7.0], punch=[(1.5, 1.1)], pushes=[(6.5, "end", 1.05)], open=(1.04, 0.45)),
            BEHIND=[dict(kind="float", end=2.5, items=[dict(src="media/x.mp4", at=1.2)])])
        self.TL = dict(picture_cuts=[1.5, 3.0, 4.0, 7.0], reframes=[])
        self.words = [dict(start=0.2, end=0.5, text="one"), dict(start=5.1, end=5.4, text="six")]

    def test_window_sees_only_overlapping_inputs(self):
        inp = PC.window_inputs(self.E, self.TL, self.words, 8.0, 3.0, 4.0)
        self.assertEqual([c[0] for c in inp["cards"]], ["c1"])
        self.assertEqual(inp["fx"], [])
        self.assertEqual([c[1] for c in inp["caps"]], [])
        self.assertEqual(inp["grades"], [])
        self.assertEqual([k for k, _ in inp["camera"]], ["settle"])

    def test_caption_without_end_runs_to_next(self):
        inp = PC.window_inputs(self.E, self.TL, self.words, 8.0, 1.5, 1.9)
        self.assertEqual([c[1] for c in inp["caps"]], ["one"])

    def test_end_means_total(self):
        inp = PC.window_inputs(self.E, self.TL, self.words, 8.0, 7.5, 8.0)
        self.assertEqual([F["id"] for F in inp["fx"]], ["b"])
        self.assertEqual([c[1] for c in inp["caps"]], ["six"])
        self.assertIn("push", [k for k, _ in inp["camera"]])

    def test_edge_touching_input_is_not_in_the_window(self):
        # the kit shows a thing on frames fr(at) .. fr(end) - 1: an effect ending on the window's first frame is gone
        E = edit(FX=[dict(id="a", at=0.0, end=2.8667), dict(id="b", at=0.0, end=2.9)])
        inp = PC.window_inputs(E, dict(picture_cuts=[], reframes=[]), [], 8.0, 2.8667, 4.0)
        self.assertEqual([F["id"] for F in inp["fx"]], ["b"])

    def test_behind_float_span_starts_at_first_item(self):
        self.assertEqual(PC.behind_span(self.E.BEHIND[0], 8.0), (1.2, 2.5))

    def test_globals_skip_time_lists_and_audio(self):
        g = PC.edit_globals(edit(SOUND=dict(sfx=[(1, "pop", -3)]), NEW_SETTING=7))
        self.assertIn("HOLD", g)
        self.assertIn("NEW_SETTING", g)            # unknown settings count as global (the safe side)
        for k in ("SOUND", "CAPS", "FX", "CARDS"):
            self.assertNotIn(k, g)


class Keys(unittest.TestCase):
    def test_key_is_stable_and_sensitive(self):
        a = dict(common="x", window=[0, 117], inputs={"fx": [dict(id="hook", at=0.0)]}, files={}, media={})
        b = dict(a, inputs={"fx": [dict(id="hook", at=0.0)]})
        self.assertEqual(PC.piece_key(a), PC.piece_key(b))
        for change in (dict(window=[0, 118]), dict(common="y"), dict(files={"fx/hook": "1"}), dict(media={"clean.mp4": "2"})):
            self.assertNotEqual(PC.piece_key(a), PC.piece_key(dict(a, **change)))

    def test_dirty_is_what_the_cache_lacks(self):
        pieces = [dict(key="k0"), dict(key="k1"), dict(key="k2")]
        self.assertEqual(PC.dirty(pieces, {"k0", "k2"}), [1])
        self.assertEqual(PC.dirty(pieces, set()), [0, 1, 2])

    def test_one_fx_change_dirties_only_its_window(self):
        E1 = edit(FX=[dict(id="a", at=1.0, end=2.0, note="v1")])
        E2 = edit(FX=[dict(id="a", at=1.0, end=2.0, note="v2")])
        TL = dict(picture_cuts=[], reframes=[])
        for t0, t1, same in ((0.0, 0.9, True), (0.9, 2.1, False), (2.2, 4.0, True)):
            k1 = PC.piece_key(PC.window_inputs(E1, TL, [], 4.0, t0, t1))
            k2 = PC.piece_key(PC.window_inputs(E2, TL, [], 4.0, t0, t1))
            self.assertEqual(k1 == k2, same, (t0, t1))


class Media(unittest.TestCase):
    def test_picture_in_picture_maps_to_media_time(self):
        html = ('<video id="v" class="full g" src="clean.mp4" data-start="0" data-media-start="0" data-duration="71.1">'
                '<video id="walk-v" src="clean.mp4" data-start="59.2647" data-media-start="0" data-duration="2.7667">')
        w = PC.media_windows(html, 58.5333, 62.0333)
        self.assertIn(("clean.mp4", 58.5333, 62.0333), w)
        self.assertIn(("clean.mp4", 0.0, 2.7667), w)

    def test_clip_outside_window_is_ignored(self):
        html = '<video id="s0" src="subject.webm" data-start="0.0313" data-media-start="0.0343" data-duration="2.8333">'
        self.assertEqual(PC.media_windows(html, 10.0, 12.0), [])

    def test_window_digest_looks_back_to_the_keyframe(self):
        pk = [(i / F, i % 10 == 0, f"h{i}") for i in range(40)]
        d = PC.window_digest(pk, 15 / F, 20 / F)
        before_gop = [(t, k, "X" if i == 5 else h) for i, (t, k, h) in enumerate(pk)]
        same_gop = [(t, k, "X" if i == 12 else h) for i, (t, k, h) in enumerate(pk)]
        after = [(t, k, "X" if i == 30 else h) for i, (t, k, h) in enumerate(pk)]
        self.assertEqual(d, PC.window_digest(before_gop, 15 / F, 20 / F))
        self.assertNotEqual(d, PC.window_digest(same_gop, 15 / F, 20 / F))   # frame 12 is a reference for 15-19
        self.assertEqual(d, PC.window_digest(after, 15 / F, 20 / F))


class Coupling(unittest.TestCase):
    def test_shared_layers_are_found(self):
        js = "tl.to('#caps', {opacity: 0}, A); tl.set(\".g\", {filter: f}, B); root.querySelector('#'+ID);"
        self.assertEqual(PC.coupled_selectors(js), ["#caps", ".g"])

    def test_own_selectors_are_not_coupled(self):
        js = "tl.to('.pb-card', {y: 0}); tl.to('#cover-mast', {}); tl.to('.gx', {}); tl.to('.capsule', {})"
        self.assertEqual(PC.coupled_selectors(js), [])


class Transplant(unittest.TestCase):
    PUB = "".join(f"line {i}\n" for i in range(30)).replace("line 10\n", "var BASE = 548;\n")
    # the compiler embeds fonts and rewrites media tags around otherwise verbatim lines
    COMP = "<head>@font-face{src:url(data:...)}</head>\n" + PUB.replace("line 20\n", "<video src=a data-end=1>\n")

    def test_constant_change_moves_into_the_compiled_html(self):
        new = self.PUB.replace("var BASE = 548;", "var BASE = 572;")
        out = PC.transplant(self.PUB, new, self.COMP)
        self.assertEqual(out, self.COMP.replace("var BASE = 548;", "var BASE = 572;"))

    def test_insertion_and_two_hunks(self):
        new = self.PUB.replace("line 3\n", "line 3\nadded\n").replace("line 25\n", "line 25 changed\n")
        out = PC.transplant(self.PUB, new, self.COMP)
        self.assertIn("line 3\nadded\nline 4", out)
        self.assertIn("line 25 changed\n", out)
        self.assertIn("<video src=a data-end=1>", out)

    def test_media_or_font_change_needs_a_new_plan(self):
        self.assertIsNone(PC.transplant(self.PUB, self.PUB.replace("line 5\n", '<img src="x.png">\n'), self.COMP))

    def test_line_the_compiler_rewrote_needs_a_new_plan(self):
        pub = self.PUB.replace("line 20\n", "<div id=v>\n")
        comp = self.COMP.replace("<video src=a data-end=1>\n", "<div id=v data-x=1>\n")
        self.assertIsNone(PC.transplant(pub, pub.replace("<div id=v>", "<div id=w>"), comp))


class Seams(unittest.TestCase):
    def test_clean(self):
        ok, rows = PC.seam_report([117, 284], 300, 300, [512], [], [50.0] * 300)
        self.assertTrue(ok)
        self.assertEqual(len(rows), 2)

    def test_frame_count_or_pts_fail(self):
        self.assertFalse(PC.seam_report([117], 299, 300, [512], [], [])[0])
        self.assertFalse(PC.seam_report([117], 300, 300, [512, 1024], [], [])[0])

    def test_black_near_seam_fails(self):
        ok, rows = PC.seam_report([117], 300, 300, [512], [(3.85, 3.95)], [])
        self.assertFalse(ok)
        self.assertTrue(rows[0]["black"])

    def test_low_psnr_at_seam_fails(self):
        p = [50.0] * 300
        p[118] = 31.0
        ok, rows = PC.seam_report([117], 300, 300, [512], [], p)
        self.assertFalse(ok)
        self.assertEqual(rows[0]["psnr_min"], 31.0)


if __name__ == "__main__":
    unittest.main()
