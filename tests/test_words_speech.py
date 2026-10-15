"""words.py and silence: a transcript with no words at all stops with "no speech found in <take>" (before any cut),
and a take with no words among takes that have them is named while the run goes on. The takes come from the
project's intake.json. main() runs end to end with Whisper replaced by canned words."""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import words as W  # noqa: E402


def word(src, text="hi"):
    return {"text": text, "start": src, "end": src + 0.2, "src": src}


THREE = [("a.mov", 0.0, 10.0), ("b.mov", 10.0, 20.0), ("c.mov", 20.0, 30.0)]


class NoSpeech(unittest.TestCase):
    def test_a_take_with_no_words_is_named(self):
        self.assertEqual(W.no_speech([word(1.0), word(21.0)], THREE, [(0.0, 30.0)]), ["b.mov"])

    def test_every_take_silent(self):
        self.assertEqual(W.no_speech([], THREE, [(0.0, 30.0)]), ["a.mov", "b.mov", "c.mov"])

    def test_a_take_only_partly_kept_is_not_judged(self):
        # after the cut KEEP holds only the good lines: a take cut down (or left out) says nothing about its sound
        self.assertEqual(W.no_speech([word(1.0)], THREE, [(0.5, 3.0), (20.5, 22.0)]), [])

    def test_a_word_at_a_take_start_belongs_to_that_take(self):
        self.assertEqual(W.no_speech([word(0.0), word(10.0), word(29.9)], THREE, [(0.0, 30.0)]), [])


class Takes(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="words-speech-")
        self.addCleanup(shutil.rmtree, self.project, True)
        self.src = os.path.join(self.project, "raw", "joined.mov")
        with open(os.path.join(self.project, "intake.json"), "w") as fh:
            json.dump({"version": 1, "source": "raw/joined.mov",
                       "takes": [{"name": "a.mov", "start": 0.0, "duration": 2.0},
                                 {"name": "b.mov", "start": 2.0, "duration": 1.5}]}, fh)

    def test_from_intake_json(self):
        self.assertEqual(W.takes(self.project, self.src), [("a.mov", 0.0, 2.0), ("b.mov", 2.0, 3.5)])

    def test_another_source_is_its_own_one_take(self):
        self.assertEqual(W.takes(self.project, "/clips/take.mov"), [("take.mov", 0.0, float("inf"))])

    def test_no_intake_json(self):
        os.remove(os.path.join(self.project, "intake.json"))
        self.assertEqual(W.takes(self.project, self.src), [("joined.mov", 0.0, float("inf"))])


class Main(unittest.TestCase):
    """words.main() on a project intake made, with Whisper's words canned (one list per kept range, by range start)"""

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="words-speech-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, "raw"))
        os.makedirs(os.path.join(self.project, "style"))
        with open(os.path.join(self.project, "style", "style.json"), "w") as fh:
            fh.write("{}")
        self.src = os.path.join(self.project, "raw", "joined.mov")
        with open(self.src, "wb") as fh:
            fh.write(b"\x00" * 4096)                         # Whisper is canned: the bytes are only hashed

    def project_with(self, takes, keep):
        with open(os.path.join(self.project, "intake.json"), "w") as fh:
            json.dump({"version": 1, "source": "raw/joined.mov",
                       "takes": [{"name": n, "start": s, "duration": d} for n, s, d in takes]}, fh)
        with open(os.path.join(self.project, "edit.py"), "w") as fh:
            fh.write(f'STYLE = "lofi"\nSRC = "{self.src}"\nKEEP = {keep!r}\n')

    def run_main(self, canned):
        fake = types.ModuleType("faster_whisper")
        fake.WhisperModel = lambda *a, **k: object()
        with mock.patch.dict(sys.modules, {"faster_whisper": fake}), \
                mock.patch.object(W, "transcribe", lambda model, E, g, work: canned.get(g["s"], [])), \
                mock.patch.object(sys, "argv", ["words.py", self.project]), \
                mock.patch("builtins.print") as said:
            W.main()
        return " ".join(str(c.args[0]) for c in said.call_args_list if c.args)

    def words_json(self):
        with open(os.path.join(self.project, "words.json")) as fh:
            return json.load(fh)

    def test_no_words_stops_with_the_take(self):
        self.project_with([("IMG_0001.mov", 0.0, 2.0)], [(0.0, 2.0)])
        with self.assertRaises(SystemExit) as e:
            self.run_main({})
        self.assertIn("no speech found in IMG_0001.mov", str(e.exception))
        self.assertEqual(self.words_json(), [])

    def test_words_pass(self):
        self.project_with([("IMG_0001.mov", 0.0, 2.0)], [(0.0, 2.0)])
        said = self.run_main({0.0: [[0.1, 0.5, "Hello."]]})
        self.assertEqual([w["text"] for w in self.words_json()], ["Hello."])
        self.assertNotIn("no speech", said)

    def test_a_silent_take_among_others_is_named_and_the_run_goes_on(self):
        self.project_with([("a.mov", 0.0, 2.0), ("b.mov", 2.0, 2.0)], [(0.0, 4.0)])
        said = self.run_main({0.0: [[0.1, 0.5, "Hello."]]})
        self.assertIn("no speech found in b.mov", said)
        self.assertNotIn("no speech found in a.mov", said)
        self.assertEqual(len(self.words_json()), 1)

    def test_without_intake_json_the_source_is_named(self):
        with open(os.path.join(self.project, "edit.py"), "w") as fh:
            fh.write(f'STYLE = "lofi"\nSRC = "{self.src}"\nKEEP = [(0.0, 2.0)]\n')
        with self.assertRaises(SystemExit) as e:
            self.run_main({})
        self.assertIn("no speech found in joined.mov", str(e.exception))


if __name__ == "__main__":
    unittest.main()
