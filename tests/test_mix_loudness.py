"""mix.py lands the master on the loudness QA checks (-14 LUFS within 0.5, true peak at or under -1.0 dBFS): the
target loudnorm is aimed at moves by its own miss until the measured master is within 0.2 LU, and a master that
still misses the QA window is refused at mix time, before any render. A small real mix proves it end to end."""
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import mix  # noqa: E402


class Aim(unittest.TestCase):
    def test_on_target_stays(self):
        self.assertEqual(mix.next_target(-14.0, -14.1), -14.0)

    def test_a_miss_moves_the_target_by_the_miss(self):
        self.assertAlmostEqual(mix.next_target(-14.0, -14.6), -13.4)
        self.assertAlmostEqual(mix.next_target(-14.0, -13.5), -14.5)

    def test_the_target_stays_in_loudnorms_range(self):
        self.assertEqual(mix.next_target(-6.0, -18.0), -5.0)      # far too quiet: aim up, at most -5
        self.assertEqual(mix.next_target(-69.0, -10.0), -70.0)    # far too loud: aim down, at least -70

    def test_the_qa_window(self):
        self.assertTrue(mix.loudness_ok(-14.0, -1.5))
        self.assertTrue(mix.loudness_ok(-14.5, -1.0))
        self.assertFalse(mix.loudness_ok(-14.6, -1.5))
        self.assertFalse(mix.loudness_ok(-14.0, -0.9))


class RealMix(unittest.TestCase):
    """loudnorm's one pass misses on speech with hard transients; aimed again, the master lands on -14"""

    def test_a_peaky_voice_lands_on_minus_14(self):
        sr = 48000
        t = np.arange(int(sr * 20)) / sr
        rng = np.random.default_rng(7)
        env = (np.sin(2 * np.pi * 0.7 * t) > -0.2).astype(float) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.1 * t) ** 2)
        voice = 0.08 * env * (np.sin(2 * np.pi * 180 * t) + 0.5 * rng.standard_normal(t.size))
        for k in range(0, t.size, sr // 2):                  # clicks a limiter has to catch
            voice[k:k + 40] += 0.9
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "in.wav")
        out = os.path.join(tmp, "out.wav")
        mix.write(src, np.vstack([voice, voice]))
        graph = "[0:a]anull[pre]"
        i, pk, tries = mix.normalize(["-i", src], graph, "pre", out)
        self.assertTrue(mix.loudness_ok(i, pk), (i, pk, tries))
        self.assertLessEqual(abs(i + 14.0), 0.2 + 1e-9, (i, tries))
        self.assertLessEqual(tries, 3)
        self.assertTrue(os.path.exists(out))
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,codec_name", "-of", "csv=p=0",
                            out], capture_output=True, text=True).stdout.strip()
        self.assertEqual(r, "pcm_s16le,48000")


if __name__ == "__main__":
    unittest.main()
