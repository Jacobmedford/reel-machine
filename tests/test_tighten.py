"""tighten.py: the no-dead-air rule on synthetic takes (harmonic bursts over a room-tone floor)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import tighten  # noqa: E402

SR = 48000
PY = sys.executable
TIGHTEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "tighten.py")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def take(path, bursts, length):
    """a mono 48 kHz WAV: room tone at about -70 dBFS everywhere, a voiced burst (220 Hz and harmonics, plus a
    little 4-8 kHz hiss) in each (on, off) window. Returns the bursts."""
    rng = np.random.default_rng(7)
    x = rng.normal(0, 10 ** (-70 / 20), int(length * SR))
    for on, off in bursts:
        a, b = int(round(on * SR)), int(round(off * SR))
        t = np.arange(b - a) / SR
        voice = sum(0.12 / k * np.sin(2 * np.pi * 220 * k * t) for k in range(1, 6))
        voice += rng.normal(0, 0.01, b - a)
        x[a:b] += voice
    wavfile.write(path, SR, (np.clip(x, -1, 1) * 32767).astype(np.int16))
    return bursts


class Tighten(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wav = os.path.join(self.tmp, "take.wav")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def edges(self, bursts):
        return [t for b in bursts for t in b]

    def test_speech_islands_follow_the_bursts(self):
        bursts = take(self.wav, [(0.50, 1.20), (1.60, 2.40), (2.52, 3.00)], 3.6)
        isl = tighten.speech_islands(self.wav, 0.45, 3.05)
        self.assertEqual(len(isl), 3, isl)
        for (on, off), (a, b) in zip(isl, bursts):
            # the map may run a little wide (filter ring after an abrupt end), never narrow: a cut placed from it
            # can't clip a word
            self.assertTrue(a - 0.02 <= on <= a + 0.002, (on, a))
            self.assertTrue(b - 0.002 <= off <= b + 0.025, (off, b))

    def test_one_second_silence_splits_leaving_a_tenth(self):
        take(self.wav, [(0.50, 1.50), (2.50, 3.50)], 4.0)
        keep, cuts = tighten.tighten_keep([(0.45, 3.55)], self.wav)
        self.assertEqual(len(keep), 2, keep)
        self.assertEqual(cuts, [keep[0][1]])
        (s, b), (a, e) = keep
        self.assertEqual((s, e), (0.45, 3.55))
        left = (b - 1.50) + (2.50 - a)                 # air left around the cut, burst edge to burst edge
        self.assertAlmostEqual(left, 0.10, delta=0.02)

    def test_short_silence_does_not_split(self):
        take(self.wav, [(0.50, 1.50), (1.62, 2.60)], 3.0)
        keep, cuts = tighten.tighten_keep([(0.45, 2.65)], self.wav)
        self.assertEqual(keep, [(0.45, 2.65)])
        self.assertEqual(cuts, [])

    def test_no_silence_leaves_keep_unchanged(self):
        take(self.wav, [(0.30, 2.70)], 3.0)
        keep, cuts = tighten.tighten_keep([(0.25, 2.75)], self.wav)
        self.assertEqual(keep, [(0.25, 2.75)])
        self.assertEqual(cuts, [])

    def test_cuts_never_land_within_40ms_of_an_onset_or_offset(self):
        bursts = take(self.wav, [(0.40, 0.90), (1.15, 1.60), (1.95, 2.30), (2.90, 3.20), (4.40, 5.00)], 5.4)
        keep, cuts = tighten.tighten_keep([(0.35, 5.05)], self.wav)
        self.assertEqual(len(cuts), 4)                 # 0.25, 0.35, 0.60 and 1.20 s pauses: all over 0.18
        boundaries = [t for r in keep for t in r]
        for t in boundaries:
            for x in self.edges(bursts):
                self.assertGreaterEqual(abs(t - x), 0.04, f"boundary {t} is {abs(t - x):.3f}s from a burst edge {x}")

    def test_ranges_strictly_increasing_and_inside_the_input(self):
        take(self.wav, [(0.40, 0.90), (1.30, 1.80), (2.40, 2.90), (3.50, 4.10), (4.60, 5.10)], 5.6)
        old = [(0.35, 1.85), (2.35, 4.15), (4.55, 5.15)]
        keep, cuts = tighten.tighten_keep(old, self.wav)
        flat = [t for r in keep for t in r]
        self.assertEqual(flat, sorted(flat))
        self.assertEqual(len(set(flat)), len(flat), "a range touches the next one")
        for a, b in keep:
            self.assertLess(a, b)
            self.assertTrue(any(s - 1e-9 <= a and b <= e + 1e-9 for s, e in old), (a, b))
        self.assertEqual(len(keep), 5)                 # one pause inside the first and second ranges, none in the third
        self.assertNotIn(1.85, cuts)                   # the join between two KEEP ranges is not a new cut

    def test_a_piece_under_two_frames_is_never_made(self):
        # the range starts on the last 10 ms of a word, then a long pause: the usual 0.05 s of air after it would
        # leave a 0.065 s scrap (under two frames), so the cut moves later and the pause still goes
        take(self.wav, [(0.20, 0.53), (1.00, 1.80)], 2.2)
        keep, cuts = tighten.tighten_keep([(0.52, 1.85)], self.wav)
        self.assertEqual(len(keep), 2, keep)
        for a, b in keep:
            self.assertGreaterEqual(b - a, 2 / 30 - 1e-9, keep)
        self.assertLess(keep[1][0] - keep[0][1], 0.40)  # most of the 0.47 s pause came out

    def test_skip_leaves_a_designed_pause(self):
        take(self.wav, [(0.50, 1.50), (2.50, 3.50)], 4.0)
        keep, cuts = tighten.tighten_keep([(0.45, 3.55)], self.wav, skip=[0])
        self.assertEqual(keep, [(0.45, 3.55)])

    def test_min_gap_must_leave_room_for_the_air(self):
        take(self.wav, [(0.50, 1.50)], 2.0)
        with self.assertRaises(ValueError):
            tighten.tighten_keep([(0.45, 1.55)], self.wav, min_gap=0.10, leave=0.10)


EDIT = '''"""lab edit"""
TITLE = "Lab"
STYLE = "hifi"
SRC = "{src}"

# ---- cut
KEEP = [
    (0.45, 3.55),    # line one: first half, pause, second half
    (4.05, 5.05),  # line two
]
FRAMES = {{"WIDE": (1080, 1920, 0, 0)}}
SHOTS = [(0.000, "WIDE"), (2.60, "WIDE"), (3.40, "WIDE")]
HOLD = 0.6
J_LEADS = None                      # per-join leads
CAPS = []
'''


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "proj")
        os.makedirs(self.project)
        self.wav = os.path.join(self.tmp, "take.wav")
        take(self.wav, [(0.50, 1.50), (2.50, 3.50), (4.10, 5.00)], 5.6)
        self.edit = os.path.join(self.project, "edit.py")
        with open(self.edit, "w") as fh:
            fh.write(EDIT.format(src=self.wav))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([PY, TIGHTEN, self.project, *args], capture_output=True, text=True)

    def load(self, path):
        ns = {}
        exec(read(path), ns)
        return ns

    def test_plan_mode_changes_nothing(self):
        before = read(self.edit)
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("CUT", r.stdout)
        self.assertEqual(read(self.edit), before)
        self.assertFalse(os.path.exists(os.path.join(self.project, "edit-pre-tighten-1.py")))

    def test_apply_rewrites_keep_and_j_leads_and_keeps_the_old_file(self):
        before = read(self.edit)
        r = self.run_cli("--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(os.path.join(self.project, "edit-pre-tighten-1.py")), before)
        ns = self.load(self.edit)
        self.assertEqual(len(ns["KEEP"]), 3)
        self.assertEqual(ns["KEEP"][0][0], 0.45)
        self.assertEqual(ns["KEEP"][-1], (4.05, 5.05))
        self.assertEqual(ns["J_LEADS"], [0.0, None])  # a straight cut inside line one; the kit's lead between lines
        text = read(self.edit)
        self.assertIn("# line one", text)
        self.assertIn("# line two", text)
        # SHOTS (output times) follow the cut: 2.60 sits in line one's second half and 3.40 in line two, so both
        # move up by the pause that came out; 0 stays 0
        gone = ns["KEEP"][1][0] - ns["KEEP"][0][1]
        self.assertEqual(ns["SHOTS"][0][0], 0.0)
        self.assertAlmostEqual(ns["SHOTS"][1][0], 2.60 - gone, places=3)
        self.assertAlmostEqual(ns["SHOTS"][2][0], 3.40 - gone, places=3)
        r2 = self.run_cli("--apply")                    # a second run finds nothing left to cut, writes nothing
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.project, "edit-pre-tighten-2.py")))

    def test_apply_adds_j_leads_when_edit_has_none(self):
        with open(self.edit, "w") as fh:
            fh.write(EDIT.format(src=self.wav).replace("J_LEADS = None                      # per-join leads\n", ""))
        r = self.run_cli("--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ns = self.load(self.edit)
        self.assertEqual(ns["J_LEADS"], [0.0, None])
        self.assertLess(read(self.edit).index("J_LEADS"), read(self.edit).index("FRAMES"))   # right under KEEP

    def test_apply_refuses_once_beats_exist(self):
        with open(self.edit, "a") as fh:
            fh.write('CAPS = [(0.5, "line one", "")]\n')
        before = read(self.edit)
        r = self.run_cli("--apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stdout + r.stderr)
        self.assertEqual(read(self.edit), before)


if __name__ == "__main__":
    unittest.main()
