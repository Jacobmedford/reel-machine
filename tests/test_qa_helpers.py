"""qa.py helpers: cut-sheet frames in one pass, frame choice for a seek, sample planning, the full-frame and the
speaker-only (face) correlation, the verdict."""
import os
import sys
import types
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import qa  # noqa: E402


class CutSheets(unittest.TestCase):
    def E(self, **kw):
        E = types.SimpleNamespace(CARDS=[("c1", "cards/c1.mp4", 6.6, 9.4667, "dark", "")], END_CARD=None, END_IN=71.1,
                                  TOTAL=71.1)
        for k, v in kw.items():
            setattr(E, k, v)
        return E

    def test_event_frames(self):
        TL = {"picture_cuts": [2.8666666666666667, 3.9, 6.6], "reframes": [5.0]}
        self.assertEqual(qa.cut_frames(self.E(), TL), [86, 117, 150, 198, 284])

    def test_end_card_and_bounds(self):
        TL = {"picture_cuts": [0.0, 71.1], "reframes": []}
        self.assertEqual(qa.cut_frames(self.E(CARDS=[], END_CARD="x", END_IN=70.0), TL), [2100])

    def test_sheet_rows_match_the_old_layout(self):
        frames = list(range(10, 200, 10))                          # 19 events -> 38 frames -> 16 + 16 + 6
        rows = qa.sheet_rows(frames)
        self.assertEqual([len(r[0]) for r in rows], [16, 16, 6])
        self.assertEqual(rows[0][0][:4], [9, 10, 19, 20])
        self.assertEqual(rows[1][1], frames[8:16])
        self.assertEqual(rows[2][1], frames[16:24])

    def test_select_expression(self):
        self.assertEqual(qa.select_expr([3, 7, 11]), "eq(n\\,3)+eq(n\\,7)+eq(n\\,11)")


class FrameChoice(unittest.TestCase):
    def test_seek_string_in_microseconds(self):
        self.assertEqual(qa.seek_us(50.43), 50430000)
        self.assertEqual(qa.seek_us(0.033333), 33300)               # written to 0.1 ms like the -ss string
        self.assertEqual(qa.seek_us(12.34567), 12345700)

    def test_first_frame_at_or_after_cfr(self):
        pts = [k * 20 for k in range(100)]                          # 30 fps in 1/600
        self.assertEqual(qa.first_at_or_after(pts, (1, 600), qa.seek_us(0.0333)), 1)
        self.assertEqual(qa.first_at_or_after(pts, (1, 600), qa.seek_us(0.1)), 3)     # exactly on frame 3
        # ffmpeg rounds the seek to the stream's time base first (measured: a seek up to 0.8 ms past a 1/600 frame
        # still lands on that frame), so 0.1001 s is tick 60 = frame 3 and 0.1009 s is tick 61 = frame 4
        self.assertEqual(qa.first_at_or_after(pts, (1, 600), qa.seek_us(0.1001)), 3)
        self.assertEqual(qa.first_at_or_after(pts, (1, 600), qa.seek_us(0.1009)), 4)

    def test_first_frame_at_or_after_vfr(self):
        pts = [0, 27, 55, 84, 112]                                  # a phone's 21 fps-ish take in 1/600
        self.assertEqual(qa.first_at_or_after(pts, (1, 600), qa.seek_us(0.045)), 1)
        self.assertEqual(qa.first_at_or_after(pts, (1, 600), qa.seek_us(0.046)), 2)
        self.assertIsNone(qa.first_at_or_after(pts, (1, 600), qa.seek_us(0.2)))

    def test_offsets_are_the_old_ones(self):
        o = qa.offsets(0.6)
        self.assertEqual(len(o), 37)
        self.assertAlmostEqual(o[0], -0.6)
        self.assertAlmostEqual(o[-1], 0.6)


def z(a):
    return (a - a.mean()) / a.std()


class Correlation(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.bg = rng.uniform(40, 200, (240, 135))                   # a textured, static room
        self.K = 37
        self.F = []
        for k in range(self.K):                                     # a "face" that changes every frame
            f = self.bg.copy()
            f[60:150, 30:105] = rng.uniform(0, 255, (90, 75))
            self.F.append(f)
        self.F = np.array(self.F)

    def test_full_match_is_the_old_formula(self):
        r = self.F[18] + 3.0
        old = [float((z(r) * ((f - f.mean()) / f.std())).mean()) for f in self.F]
        self.assertEqual(list(qa.full_match(r, self.F)), old)

    def test_face_match_finds_the_frame(self):
        curve, info = qa.face_match(self.F[18], self.F)
        self.assertEqual(int(np.argmax(curve)), 18)
        self.assertGreater(info["tiles"], 0)

    def test_face_match_ignores_overlays_and_captions(self):
        r = self.F[18].copy()
        r[0:75, :] = 255.0                                          # a page laid over the top of the frame
        r[60:90, 0:135] = np.linspace(0, 255, 135)[None, :]         # and a graphic over part of the face
        r[180:210, 10:125] = 20.0                                   # a caption box
        curve, _ = qa.face_match(r, self.F)
        self.assertEqual(int(np.argmax(curve)), 18)

    def test_face_match_needs_motion(self):
        still = np.array([self.bg] * self.K)
        self.assertIsNone(qa.face_match(self.bg, still))

    def test_face_match_needs_visible_footage(self):
        r = np.full((240, 135), 128.0)
        r[::2, :] = 0                                               # a graphic over everything
        self.assertIsNone(qa.face_match(r, self.F))


class Samples(unittest.TestCase):
    def test_two_quiet_moments_per_visible_piece(self):
        E = types.SimpleNamespace(WINDOWS=[(5.0, 8.0, "dark")], CAMERA={}, FX=[], TOTAL=10.0, MODE={})
        TL = {"pieces": [dict(out_start=0.0, out_end=4.0, frame="W"), dict(out_start=4.0, out_end=9.0, frame="C"),
                         dict(out_start=9.0, out_end=9.5, frame="W")], "total_audio": 9.5,
              "picture_cuts": [], "reframes": []}
        with mock.patch.object(qa, "cam_scale", lambda E, TL, t: (1.0, False)):
            got = qa.samples(E, TL)
        self.assertEqual([round(t, 3) for t, _ in got], [1.433, 2.567, 4.767, 8.233])
        self.assertEqual([p["frame"] for _, p in got], ["W", "W", "C", "C"])


class Verdict(unittest.TestCase):
    def test_face_result_wins_and_inconclusive_is_skipped(self):
        rows = [dict(t=1.0, full=(0.267, 0.505, ""), face=(0.0, 0.97, "")),
                dict(t=2.0, full=(0.033, 0.9, ""), face=None),
                dict(t=3.0, full=(0.5, 0.4, "static (inconclusive)"), face=None)]
        worst, used = qa.verdict(rows)
        self.assertAlmostEqual(worst, 0.033)
        self.assertEqual([u[0] for u in used], ["face", "full", "full"])

    def test_a_real_slip_fails(self):
        rows = [dict(t=1.0, full=(0.5, 0.95, ""), face=(0.5, 0.98, ""))]
        worst, _ = qa.verdict(rows)
        self.assertGreater(worst, 2.5 / 30)


if __name__ == "__main__":
    unittest.main()
