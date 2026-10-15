"""render.py --pieces: the plain render's gates around a picture joined from cached pieces, with the heavy parts
stubbed (the preflight, pieces.render / assemble / check / verify, the animation check, QA, delivery) and the cache
real: which pieces get the animation check, the pass mark in each piece's meta, the set-aside and the one retry, and
what is delivered."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import animcheck as AC  # noqa: E402
import pieces as PC  # noqa: E402
import render  # noqa: E402

EDIT = '''TITLE = "Lab Pieces"
STYLE = "hifi"
SRC = "{src}"
KEEP = [(0.0, 4.0)]
FRAMES = {{"WIDE": (1080, 1920, 0, 0)}}
SHOTS = [(0.0, "WIDE")]
CAPS = [(0.2, "One", "", 3.9)]
CARDS = []
'''
TABLE = [dict(index=0, start=0, end=45, key="k0"), dict(index=1, start=45, end=90, key="k1"),
         dict(index=2, start=90, end=120, key="k2")]


class Lab:
    """a stand-in piece renderer over a real temp cache: renders the pieces the cache lacks, records every call.
    verdicts: one entry per animation check, the labels that come out static (or an exception to raise, or "calm")"""

    def __init__(self, root):
        self.project = p = os.path.join(root, "proj")
        os.makedirs(os.path.join(p, "renders"))
        os.makedirs(os.path.join(p, "style"))
        with open(os.path.join(p, "style", "style.json"), "w") as fh:
            fh.write("{}")
        with open(os.path.join(p, "edit.py"), "w") as fh:
            fh.write(EDIT.format(src=os.path.join(root, "src", "take.mp4")))
        self.P = types.SimpleNamespace(project=p, work=os.path.join(p, PC.WORK), cache=os.path.join(p, PC.WORK, "cache"),
                                       plan_dir=None, frames=120, strict=None)
        self.calls, self.verdicts, self.seams_ok, self.verify_ok, self.qa_code = [], [], True, True, 0
        self.delivered, self.jobs = [], []

    def project_of(self, project, strict=False):
        self.P.strict = strict
        return self.P

    def plant_plans(self):
        """two frozen plans, an old and the newest (this stand-in renders without one: prune keeps the newest)"""
        for name, age in (("plan-old", 3 * 86400), ("plan-new", 0)):
            d = os.path.join(self.P.work, name)
            os.makedirs(os.path.join(d, "frames"))
            with open(os.path.join(d, "plan.json"), "w") as fh:
                fh.write("{}")
            t = os.path.getmtime(os.path.join(d, "plan.json")) - age
            os.utime(os.path.join(d, "plan.json"), (t, t))

    def plans(self):
        return sorted(f for f in os.listdir(self.P.work) if f.startswith("plan-")) if os.path.isdir(self.P.work) else []

    def render(self, P, jobs=3, **kw):
        self.jobs.append(jobs)
        if getattr(self, "render_fails", False):
            raise RuntimeError("piece 1 failed after 2 attempts: driver chunk failed")
        os.makedirs(P.cache, exist_ok=True)
        done = []
        for p in TABLE:
            mp4 = os.path.join(P.cache, p["key"] + ".mp4")
            if not (os.path.exists(mp4) and os.path.exists(mp4[:-4] + ".json")):
                with open(mp4, "wb") as fh:
                    fh.write(b"\0" * 1000)
                with open(mp4[:-4] + ".json", "w") as fh:
                    json.dump(dict(p, frames=p["end"] - p["start"], workers=2), fh)
                done.append(dict(index=p["index"], frames=p["end"] - p["start"], capture_s=1.0, encode_s=0.5, attempts=1))
        self.calls.append(("render", [d["index"] for d in done]))
        return [dict(p) for p in TABLE], {"plan_s": 0.0, "plan": None, "pieces": done, "render_s": 0.1}

    def assemble(self, P, pieces, name):
        final = os.path.join(self.project, "renders", f"{name}.mp4")
        with open(final, "wb") as fh:
            fh.write(b"picture")
        with open(final[:-4] + ".pieces.json", "w") as fh:
            json.dump(pieces, fh)
        self.calls.append(("assemble", name))
        return final, 0.1

    def seams(self, P, final, **kw):
        self.calls.append(("seams",))
        return self.seams_ok, {}

    def verify(self, P, jobs=3):
        self.calls.append(("verify",))
        return self.verify_ok, []

    def animcheck(self, project, final, runs=None, **kw):
        self.calls.append(("animcheck", [r[3] for r in runs]))
        v = self.verdicts.pop(0)
        if isinstance(v, Exception):
            raise v
        state = lambda label: "calm" if v == "calm" else "static" if label in v else "animated"  # noqa: E731
        rows = [dict(piece=r[3], slot=f"{r[3]}.1", frame=r[0] + 5, t=(r[0] + 5) / 30, state=state(r[3]), expect=True)
                for r in runs]
        return AC.decide(rows)[0], rows

    def go(self, *opts, name="lab-v1"):
        real = subprocess.run

        def fake_run(cmd, *a, **kw):
            if len(cmd) > 1 and os.path.basename(cmd[1]) == "qa.py":
                self.calls.append(("qa",))
                return subprocess.CompletedProcess(cmd, self.qa_code)
            return real(cmd, *a, **kw)

        out = io.StringIO()
        with mock.patch.object(render, "preflight") as pre, \
                mock.patch.object(PC, "Project", side_effect=self.project_of), \
                mock.patch.object(PC, "render", side_effect=self.render), \
                mock.patch.object(PC, "assemble", side_effect=self.assemble), \
                mock.patch.object(PC, "check", side_effect=self.seams), \
                mock.patch.object(PC, "verify", side_effect=self.verify), \
                mock.patch.object(AC, "check", side_effect=self.animcheck), \
                mock.patch.object(render.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(render, "deliver", side_effect=lambda *a: self.delivered.append(a)), \
                mock.patch.object(sys, "argv", ["render.py", self.project, name, "--pieces", *opts]), \
                contextlib.redirect_stdout(out):
            self.calls = []
            try:
                render.main()
                code = 0
            except SystemExit as e:
                code = e.code
            self.preflight_calls = pre.call_count
        self.out = out.getvalue()
        return code

    def marked(self):
        return {p["key"] for p in TABLE if PC.meta_of(self.P, p["key"]).get("animcheck") == "pass"}

    def rejected(self):
        d = os.path.join(self.P.work, "rejected")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []


class RenderPieces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lab = Lab(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_first_render_checks_every_piece_then_qa_and_delivery(self):
        lab = self.lab
        lab.verdicts = [set()]
        self.assertEqual(lab.go(), 0)
        self.assertEqual(lab.preflight_calls, 1)
        self.assertEqual(lab.calls, [("render", [0, 1, 2]), ("assemble", "lab-v1"), ("seams",),
                                     ("animcheck", ["p00", "p01", "p02"]), ("qa",)])
        self.assertEqual(len(lab.delivered), 1)
        self.assertEqual(lab.marked(), {"k0", "k1", "k2"})
        self.assertEqual(PC.meta_of(lab.P, "k1")["workers"], 2)            # the mark keeps the rest of the meta
        self.assertEqual(lab.jobs, [3])
        self.assertIn("rendered 3, reused 0", lab.out)
        self.assertIn("checked 3", lab.out)
        self.assertIn("times:", lab.out)

    def test_a_note_checks_only_the_pieces_it_rendered_and_a_no_op_checks_none(self):
        lab = self.lab
        lab.verdicts = [set()]
        self.assertEqual(lab.go(), 0)
        for ext in (".mp4", ".json"):                    # a note dirties piece 1: its key leaves the cache
            os.remove(os.path.join(lab.P.cache, "k1" + ext))
        lab.verdicts = [set()]
        self.assertEqual(lab.go(name="lab-v2"), 0)
        self.assertEqual(lab.calls, [("render", [1]), ("assemble", "lab-v2"), ("seams",), ("animcheck", ["p01"]), ("qa",)])
        self.assertIn("rendered 1, reused 2", lab.out)
        self.assertEqual(lab.go(name="lab-v3"), 0)
        self.assertEqual(lab.calls, [("render", []), ("assemble", "lab-v3"), ("seams",), ("qa",)])
        self.assertIn("rendered 0, reused 3", lab.out)
        self.assertIn("checked 0", lab.out)
        self.assertEqual(len(lab.delivered), 3)

    def test_a_piece_that_fails_once_is_set_aside_and_rendered_again(self):
        lab = self.lab
        lab.verdicts = [{"p01"}, set()]
        self.assertEqual(lab.go(), 0)
        self.assertEqual(lab.calls, [("render", [0, 1, 2]), ("assemble", "lab-v1"), ("seams",),
                                     ("animcheck", ["p00", "p01", "p02"]),
                                     ("render", [1]), ("assemble", "lab-v1"), ("seams",), ("animcheck", ["p01"]),
                                     ("qa",)])
        self.assertEqual(len(lab.delivered), 1)
        self.assertEqual(lab.marked(), {"k0", "k1", "k2"})
        rej = lab.rejected()
        self.assertEqual(len(rej), 2)
        self.assertRegex(rej[0], r"^k1-\d{8}-\d{6}\.json$")
        self.assertRegex(rej[1], r"^k1-\d{8}-\d{6}\.mp4$")
        self.assertIn("p01 did not animate: set aside", lab.out)
        self.assertIn("rendered 3, reused 0, checked 3 (4 probes), set aside and rendered again: p01", lab.out)

    def test_a_piece_that_fails_twice_delivers_nothing(self):
        lab = self.lab
        lab.verdicts = [{"p01"}, {"p01"}]
        code = lab.go()
        self.assertIn("Render again. Nothing was delivered.", str(code))
        self.assertIn(os.path.join("work", "animcheck", "sheet.jpg"), str(code))
        self.assertIn("p01", str(code))
        self.assertEqual(lab.calls[-1], ("animcheck", ["p01"]))
        self.assertNotIn(("qa",), lab.calls)
        self.assertEqual(lab.delivered, [])
        self.assertEqual(lab.marked(), {"k0", "k2"})                  # the pieces that passed keep their pass
        self.assertEqual(len([f for f in lab.rejected() if f.endswith(".mp4")]), 2)   # never reused: both set aside
        self.assertFalse(os.path.exists(os.path.join(lab.P.cache, "k1.mp4")))
        self.assertIn("set aside and rendered again: p01, set aside after failing twice: p01", lab.out)

    def test_a_check_that_could_not_run_delivers_nothing(self):
        lab = self.lab
        lab.verdicts = [RuntimeError("hyperframes snapshot failed")]
        code = lab.go()
        self.assertIn("could not run", str(code))
        self.assertIn("--pieces", str(code))
        self.assertIn("Nothing was delivered", str(code))
        self.assertNotIn(("qa",), lab.calls)
        self.assertEqual(lab.delivered, [])
        self.assertEqual(lab.marked(), set())
        self.assertEqual(lab.rejected(), [])

    def test_a_render_that_animates_nowhere_is_not_rendered_again(self):
        lab = self.lab
        lab.verdicts = ["calm"]                           # the composition's own script stops early: no piece to blame
        code = lab.go()
        self.assertIn("Render again. Nothing was delivered.", str(code))
        self.assertEqual([c[0] for c in lab.calls], ["render", "assemble", "seams", "animcheck"])
        self.assertEqual(lab.marked(), set())
        self.assertEqual(lab.rejected(), [])

    def test_a_seam_failure_delivers_nothing(self):
        lab = self.lab
        lab.seams_ok = False
        code = lab.go()
        self.assertIn("seam", str(code))
        self.assertIn("Nothing was delivered", str(code))
        self.assertEqual([c[0] for c in lab.calls], ["render", "assemble", "seams"])
        self.assertEqual(lab.delivered, [])

    def test_qa_failure_delivers_nothing(self):
        lab = self.lab
        lab.verdicts, lab.qa_code = [set()], 1
        code = lab.go()
        self.assertIn("QA failed", str(code))
        self.assertIn("Nothing was delivered", str(code))
        self.assertEqual(lab.delivered, [])
        self.assertEqual(lab.marked(), {"k0", "k1", "k2"})            # the check itself passed

    def test_verify_runs_only_when_asked_between_the_seams_and_the_check(self):
        lab = self.lab
        lab.verdicts = [set()]
        self.assertEqual(lab.go("--verify"), 0)
        self.assertEqual([c[0] for c in lab.calls], ["render", "assemble", "seams", "verify", "animcheck", "qa"])
        lab.verify_ok = False
        code = lab.go("--verify", name="lab-v2")
        self.assertIn("Nothing was delivered", str(code))
        self.assertEqual([c[0] for c in lab.calls], ["render", "assemble", "seams", "verify"])

    def test_options(self):
        lab = self.lab
        lab.verdicts = [set()]
        self.assertEqual(lab.go("--jobs", "2", "--strict", "--no-deliver", name="lab-v4"), 0)
        self.assertEqual(lab.jobs, [2])
        self.assertTrue(lab.P.strict)
        self.assertEqual(lab.delivered, [])
        self.assertEqual(lab.calls[1], ("assemble", "lab-v4"))

    def test_the_piece_cache_is_pruned_after_the_render(self):
        lab = self.lab
        lab.plant_plans()
        lab.verdicts = [set()]
        self.assertEqual(lab.go(), 0)
        self.assertEqual(lab.plans(), ["plan-new"])
        self.assertIn("prune: 1 old plan", lab.out)
        self.assertRegex(lab.out, r"times: .*qa [\d.]+ s, prune [\d.]+ s, total")

    def test_the_cache_is_pruned_even_when_a_later_gate_fails(self):
        lab = self.lab
        lab.plant_plans()
        lab.seams_ok = False
        self.assertIn("Nothing was delivered", str(lab.go()))
        self.assertEqual(lab.plans(), ["plan-new"])

    def test_a_render_that_never_assembled_prunes_nothing(self):
        lab = self.lab
        lab.plant_plans()
        lab.render_fails = True
        code = lab.go()
        self.assertIn("A piece failed to render", str(code))
        self.assertIn("Nothing was delivered", str(code))
        self.assertEqual(lab.plans(), ["plan-new", "plan-old"])
        self.assertEqual(lab.calls, [])

    def test_the_name_is_never_an_options_value(self):
        self.assertEqual(render.positional(["--pieces", "--jobs", "2", "lab-v9", "--strict"]), ["lab-v9"])
        self.assertEqual(render.positional(["lab-v9", "--no-deliver"]), ["lab-v9"])
        self.assertEqual(render.positional(["--hook"]), [])


if __name__ == "__main__":
    unittest.main()
