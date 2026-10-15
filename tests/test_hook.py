"""hook.py: where the hook render stops, and the composition cut there (pure functions, no renderer)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import hook  # noqa: E402

FPS = 30


def w(text, a, b):
    return {"text": text, "start": a, "end": b}


def on_frame(t):
    return abs(t * FPS - round(t * FPS)) < 1e-6


# the opening of a real take as whisper heard it (its times run a little late)
CET = [w("I", 0.0, 0.2), w("didn't", 0.2, 0.52), w("edit", 0.52, 0.76), w("a", 0.76, 1.08), w("single", 1.08, 1.42),
       w("second", 1.42, 1.82), w("of", 1.82, 2.18), w("this", 2.18, 2.46), w("video.", 2.46, 2.76),
       w("Claude", 3.178, 3.378), w("did.", 3.378, 3.478), w("No", 3.585, 3.965)]


class HookEnd(unittest.TestCase):
    def test_sentence_end_plus_hold_on_a_frame(self):
        words = [w("Hello", 0.0, 0.4), w("there.", 0.4, 1.0), w("Next", 2.0, 2.3)]
        self.assertAlmostEqual(hook.hook_end(words, 0.5, 10.0, None), 1.5)
        t = hook.hook_end(words, 0.31, 10.0, None)
        self.assertTrue(on_frame(t), t)
        self.assertAlmostEqual(t, 1.3)

    def test_a_hold_that_runs_into_the_next_line_stops_at_the_sentence_end(self):
        words = [w("Hello", 0.0, 0.4), w("there.", 0.4, 1.01), w("Next", 1.2, 1.5)]
        t = hook.hook_end(words, 0.5, 10.0, None)
        self.assertAlmostEqual(t, 31 / FPS)                  # the first frame after "there." ends: the word whole
        self.assertLessEqual(t, 1.2)                         # never into "Next"

    def test_never_ends_inside_a_word(self):
        for hold in (0.0, 0.1, 0.25, 0.4, 0.6, 1.3):
            t = hook.hook_end(CET, hold, 71.1, None)
            self.assertTrue(on_frame(t))
            for x in CET:
                self.assertFalse(x["start"] + 1e-6 < t < x["end"] - 1e-6, f"hold {hold}: {t} is inside {x}")

    def test_a_cut_after_the_sentence_is_where_its_sound_ends(self):
        # tighten.py cut the pause after "video." at 2.858 (output time): whisper's 2.76 is a little early
        t = hook.hook_end(CET, 0.4, 71.1, None, joins=[2.858, 3.585])
        self.assertAlmostEqual(t, 86 / FPS)                  # on the cut (frame 86): every frame before it, none after
        t = hook.hook_end(CET, 0.0, 71.1, None, joins=[9.0])  # a join far away changes nothing
        self.assertAlmostEqual(t, round(2.76 * FPS) / FPS)

    def test_clamped_to_the_video(self):
        words = [w("Short.", 0.0, 2.5)]
        self.assertAlmostEqual(hook.hook_end(words, 0.6, 2.9, None), 2.9)

    def test_hook_end_override_wins_on_a_frame_and_clamped(self):
        self.assertAlmostEqual(hook.hook_end(CET, 0.4, 71.1, 3.9), 3.9)
        self.assertAlmostEqual(hook.hook_end(CET, 0.4, 71.1, 3.91), 3.9)
        self.assertAlmostEqual(hook.hook_end(CET, 0.4, 71.1, 99.0), 71.1)
        self.assertAlmostEqual(hook.hook_end(CET, 0.4, 71.1, 0.0), 1 / FPS)

    def test_question_and_exclamation_and_quotes_end_a_sentence(self):
        for last in ("why?", "now!", 'said."', "done.)"):
            words = [w("So", 0.0, 0.3), w(last, 0.3, 0.9), w("Then", 3.0, 3.4)]
            self.assertAlmostEqual(hook.hook_end(words, 0.0, 10.0, None), 0.9, msg=last)

    def test_no_sentence_end_stops_inside_the_cap(self):
        words = [w(f"w{k}", k * 0.5, k * 0.5 + 0.4) for k in range(60)]      # 30 s with no full stop
        t = hook.hook_end(words, 0.0, 30.0, None)
        self.assertLessEqual(t, hook.HOOK_MAX + 1e-6)
        self.assertGreater(t, hook.HOOK_MAX - 1.0)

    def test_no_words_takes_the_first_seconds(self):
        self.assertAlmostEqual(hook.hook_end([], 0.4, 71.1, None), 3.0)
        self.assertAlmostEqual(hook.hook_end([], 0.4, 2.0, None), 2.0)


DOC = '''<div id="root" data-composition-id="main" data-start="0" data-duration="71.1000" data-fps="30" data-width="1080" data-height="1920">
  <video id="v" class="full g" src="clean.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="71.1000" data-track-index="1"></video>
  <video id="s0" class="full g" src="subject.webm" muted playsinline data-start="0.0313" data-media-start="0.0343" data-duration="2.8333" data-track-index="2"></video>
  <video id="s1" class="full g" src="subject.webm" muted playsinline data-start="3.8980" data-media-start="3.9010" data-duration="1.8000" data-track-index="3"></video>
  <audio id="mix" src="master.wav" data-start="0" data-duration="71.1000" data-track-index="10" data-volume="1"></audio>
  <video id="c1" class="full" src="cards/c1.mp4" muted playsinline data-start="6.5980" data-duration="2.8667" data-media-start="0" data-track-index="20"></video>
  <div id="odo" class="layer fx"><video id="odo-v0" class="odo-vid g" src="clean.mp4" muted playsinline
       data-start="3.0647" data-media-start="3.0677" data-duration="3.0667" data-track-index="370">
  </video></div>
  <img id="pl1" class="plate" src="media/sheet.jpg">
</div>
<script src="vendor/gsap.min.js"></script>
<script>
(function () {
  var FPS = 30, TOTAL = 71.1000;
  var tl = gsap.timeline({ paused: true });
  tl.set({}, {}, TOTAL);
})();
</script>
'''


def attrs(doc, id_):
    m = re.search(rf'<[a-z]+\b[^>]*(?<![\w-])id="{id_}"[^>]*>', doc, re.S)
    return dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(0))) if m else None


class Truncate(unittest.TestCase):
    def setUp(self):
        self.out = hook.truncate(DOC, 3.9)

    def test_root_and_total_end_at_the_hook(self):
        self.assertEqual(attrs(self.out, "root")["data-duration"], "3.9000")
        self.assertIn("TOTAL = 3.9000;", self.out)
        self.assertIn("tl.set({}, {}, TOTAL);", self.out)

    def test_clips_across_the_end_are_cut_there(self):
        self.assertEqual(attrs(self.out, "v")["data-duration"], "3.9000")
        a = attrs(self.out, "odo-v0")                        # a multi-line tag inside an effect
        self.assertEqual(a["data-duration"], "0.8333")             # starts on frame 92: 25 frames to 117
        self.assertEqual(a["data-media-start"], "3.0677")

    def test_clips_inside_the_hook_are_untouched(self):
        self.assertIn('id="s0" class="full g" src="subject.webm" muted playsinline data-start="0.0313" '
                      'data-media-start="0.0343" data-duration="2.8333"', self.out)

    def test_clips_from_the_end_on_and_the_audio_are_gone(self):
        for gone in ("s1", "c1", "mix"):
            self.assertIsNone(re.search(rf'<(video|audio) id="{gone}"', self.out), gone)
            # a hidden stand-in keeps the id, so an effect's script that looks the element up still finds one
            self.assertIn(f'<div id="{gone}" hidden></div>', self.out)
        self.assertNotIn("master.wav", self.out)
        self.assertNotIn("cards/c1.mp4", self.out)
        self.assertEqual(self.out.count("<video"), self.out.count("</video>"))
        self.assertEqual(self.out.count("<audio"), self.out.count("</audio>"))
        self.assertIn('id="pl1"', self.out)                  # untimed elements stay

    def test_frame_counts_round_up_the_way_the_renderer_reads_them(self):
        for frames in (1, 85, 95, 117, 137, 2133):
            d = float(hook.dur_attr(frames))
            import math
            self.assertEqual(math.ceil(d * FPS - 1e-9), frames, (frames, d))

    def test_the_root_is_found_whatever_its_attribute_order(self):
        doc = DOC.replace('<div id="root" data-composition-id="main" data-start="0" data-duration="71.1000"',
                          '<div data-duration="71.1000" id="root" data-start="0" data-composition-id="main"')
        self.assertEqual(attrs(hook.truncate(doc, 3.9), "root")["data-duration"], "3.9000")

    def test_cutting_twice_changes_nothing_more(self):
        self.assertEqual(hook.truncate(self.out, 3.9), self.out)



class InHook(unittest.TestCase):
    """render.in_hook: what the hook page says is on screen"""
    def test_only_what_starts_inside_the_hook_plain_text(self):
        import types
        import render
        E = types.SimpleNamespace(
            HOOK=dict(h1='I <span class="em">never</span> edit', h2="this"), STYLE="hifi", BW=[(2.0, 3.0)],
            FX=[dict(id="hook", at=0.0, note="Hook type"), dict(id="later", at=9.0, note="Later")],
            CARDS=[("c1", "cards/c1.mp4", 6.6, 9.4, "dark", "the prompt")],
            BEHIND=[dict(kind="titles", items=[], end=3.0), dict(kind="plate", at=9.0)],
            CAPS=[(0.5, "x", ""), (5.0, "y", "")])
        said = render.in_hook(E, 3.9)
        self.assertEqual(said[0], "The hook text: I never edit / this.")
        self.assertIn("Hook type", said)
        self.assertNotIn("Later", said)
        self.assertFalse(any("c1" in x or "plate" in x for x in said))
        self.assertIn("1 caption.", said)


if __name__ == "__main__":
    unittest.main()
