"""onboarding/board.py: the showcase frame's big word reads on the ground under it. With no clip (the board that
pack.py install draws) the ground is the pack's dark colour, so the word is set in the light colour; on a frame of
footage each letter is light or ink against the picture under it."""
import os
import re
import shutil
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(KIT, "onboarding"))
sys.path.insert(0, os.path.join(KIT, "pipeline"))
import board  # noqa: E402

S = {"fonts": {"display": {"family": "League Gothic", "italic": False, "weight": 400}}}
FONT = os.path.join(KIT, "packs", "harbor", "local-fonts", "LeagueGothic-Regular.ttf")


def colours(markup):
    """the colour token of each letter span, in order"""
    return re.findall(r'<span style="color:var\((--c-[a-z]+)\)">[^<]</span>', markup)


class SplitWord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reel-machine-board-")
        self.pack = os.path.join(self.tmp, "pack")
        os.makedirs(os.path.join(self.pack, "fonts"))
        shutil.copy(FONT, os.path.join(self.pack, "fonts", "LeagueGothic-Regular.ttf"))     # as pack.py build leaves it

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_without_a_clip_the_word_is_light_on_the_dark_ground(self):
        out = board.split_word(S, self.pack, "NEVER", 250, 250, None)
        self.assertIn("color:var(--c-light)", out)
        self.assertIn("NEVER", out)
        self.assertNotIn("--c-ink", out)

    def test_without_a_clip_or_a_font_file_the_word_is_still_light(self):
        bare = os.path.join(self.tmp, "bare")
        os.makedirs(bare)
        self.assertIn("color:var(--c-light)", board.split_word(S, bare, "NEVER", 250, 250, None))

    def test_on_a_frame_each_letter_follows_the_picture_under_it(self):
        frame = os.path.join(self.tmp, "frame.jpg")
        im = Image.new("RGB", (1080, 1920), "black")
        im.paste((255, 255, 255), (0, 0, 540, 1920))                  # light on the left, dark on the right
        im.save(frame)
        got = colours(board.split_word(S, self.pack, "NEVER", 250, 250, frame))
        self.assertEqual(len(got), 5)
        self.assertEqual((got[0], got[-1]), ("--c-ink", "--c-light"))


if __name__ == "__main__":
    unittest.main()
