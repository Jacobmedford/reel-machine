"""matte.py windows: which seconds need the cutout, merged into frame runs with a warm-up margin."""
import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
try:
    import matte as M  # noqa: E402
except SystemExit:                     # no PyTorch on this machine: the window helpers live in the module anyway
    M = None


@unittest.skipIf(M is None, "matte.py needs PyTorch to import")
class FrameRuns(unittest.TestCase):
    def test_margin_and_clamp(self):
        # 0.2 s margin = 6 frames each side, clamped to [0, total)
        self.assertEqual(M.frame_runs([(0.0334, 2.8667)], 2133, margin=0.2, gap=0.5), [(0, 93)])
        self.assertEqual(M.frame_runs([(70.0, 71.1)], 2133, margin=0.2, gap=0.5), [(2094, 2133)])

    def test_touching_and_close_windows_merge(self):
        runs = M.frame_runs([(3.9, 5.7), (5.7, 6.6), (12.7667, 13.4), (13.4, 15.7667)], 2133, margin=0.2, gap=0.5)
        self.assertEqual(runs, [(111, 204), (377, 480)])

    def test_far_windows_stay_apart(self):
        self.assertEqual(M.frame_runs([(10.0, 11.0), (20.0, 21.0)], 2133, margin=0.2, gap=0.5),
                         [(294, 336), (594, 636)])

    def test_gap_threshold(self):
        # runs (294, 336) and (351, ...) are 15 frames apart: merged at gap 0.5 s, apart at gap 0.4 s
        self.assertEqual(M.frame_runs([(10.0, 11.0), (11.9, 12.5)], 2133, margin=0.2, gap=0.5), [(294, 381)])
        self.assertEqual(M.frame_runs([(10.0, 11.0), (11.9, 12.5)], 2133, margin=0.2, gap=0.4),
                         [(294, 336), (351, 381)])

    def test_unsorted_and_overlapping(self):
        self.assertEqual(M.frame_runs([(20.0, 21.0), (10.0, 12.0), (11.0, 11.5)], 2133, margin=0.0, gap=0.0),
                         [(300, 360), (600, 630)])

    def test_nothing(self):
        self.assertEqual(M.frame_runs([], 2133), [])
        self.assertEqual(M.frame_runs([(80.0, 90.0)], 2133), [])        # past the end

    def test_every_frame_a_window_shows_is_covered(self):
        # the composition plays window (a, b) from frame round(a*30) for round(b*30) - round(a*30) frames; an FX mask
        # reads the same frames. All of them must be inside a run, with the margin on both sides.
        wins = [(0.0334, 2.8667), (3.9, 5.7), (5.7, 6.6), (12.7667, 13.4), (13.4, 15.7667), (17.9, 18.1333),
                (18.1333, 20.8333), (43.2, 45.0333), (54.1, 57.4667), (58.5333, 62.0333)]
        runs = M.frame_runs(wins, 2133, margin=0.2, gap=0.5)
        for a, b in wins:
            for f in range(round(a * 30) - 6, round(b * 30) + 6):
                if 0 <= f < 2133:
                    self.assertTrue(any(r0 <= f < r1 for r0, r1 in runs), f"frame {f} of window {a}-{b}")


@unittest.skipIf(M is None, "matte.py needs PyTorch to import")
class Windows(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)

    def fx(self, fid, text):
        os.makedirs(os.path.join(self.d, "fx", fid), exist_ok=True)
        with open(os.path.join(self.d, "fx", fid, "mkmask.py"), "w") as fh:
            fh.write(text)

    def test_cut_windows_and_fx_that_read_the_cutout(self):
        self.fx("hook", 'sub = os.path.join(pub, "subject.webm")\n')
        self.fx("cta", "print('no cutout here')\n")
        E = types.SimpleNamespace(CUT_WINDOWS=[(5.0, 6.0), (60.0, "end")],
                                  FX=[dict(id="hook", at=0.0, end=2.8667), dict(id="cta", at=40.0, end="end"),
                                      dict(id="gone", at=50.0, end=51.0)])
        self.assertEqual(M.cutout_windows(E, self.d, 71.1), [(5.0, 6.0), (60.0, 71.1), (0.0, 2.8667)])

    def test_none(self):
        E = types.SimpleNamespace(CUT_WINDOWS=[], FX=[])
        self.assertEqual(M.cutout_windows(E, self.d, 71.1), [])


if __name__ == "__main__":
    unittest.main()
