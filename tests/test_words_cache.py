"""words.py cache: range keys, the take cache, the legacy import, which ranges still need Whisper, the mapping onto
the output timeline (pure functions with fake word lists)."""
import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import cache as C  # noqa: E402
import words as W  # noqa: E402


def seg(s, e, out):
    return dict(s=s, e=e, out=out, vs=s, ve=e, vout=out)


class Word:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class RangeKeys(unittest.TestCase):
    def test_key_format_is_the_old_one(self):
        # the old cache (work/whisper/fw_ranges.json) used f"{s}-{e}": legacy entries must line up
        self.assertEqual(W.range_key(seg(50.52, 53.378, 0)), "50.52-53.378")
        self.assertEqual(W.range_key(seg(151.69, 155.0, 3)), "151.69-155.0")

    def test_settings_key_follows_the_prompt(self):
        a = W.settings_key(types.SimpleNamespace(PROMPT="Claude, CapCut"))
        self.assertEqual(a, W.settings_key(types.SimpleNamespace(PROMPT="Claude, CapCut")))
        self.assertNotEqual(a, W.settings_key(types.SimpleNamespace(PROMPT="Claude, CapCut, Edits")))
        self.assertEqual(W.settings_key(types.SimpleNamespace(PROMPT="")),
                         W.settings_key(types.SimpleNamespace(PROMPT=None)))     # both mean no prompt


class Tokens(unittest.TestCase):
    def test_words_from_segments(self):
        segs = [types.SimpleNamespace(words=[Word(" I", 0.0, 0.2), Word(" grew", 0.2, 0.5), Word(" 1", 0.5, 0.7),
                                             Word(".6%", 0.7, 0.9)]),
                types.SimpleNamespace(words=[Word(" today.", 1.0, 1.4)])]
        self.assertEqual(W.words_from_segments(segs),
                         [[0.0, 0.2, "I"], [0.2, 0.5, "grew"], [0.5, 0.9, "1.6%"], [1.0, 1.4, "today."]])

    def test_words_from_segments_rounds_like_before(self):
        segs = [types.SimpleNamespace(words=[Word(" a", 0.12345, 0.67891)])]
        self.assertEqual(W.words_from_segments(segs), [[0.123, 0.679, "a"]])


class Mapping(unittest.TestCase):
    def test_out_words_matches_the_old_formula(self):
        g = seg(10.0, 12.0, 5.5)
        ws = [[0.0, 0.4, "Hello"], [0.5, 2.3, "world."]]                # the last word runs past the range end
        self.assertEqual(W.out_words(ws, g, {"Hello": "hello"}), [
            {"text": "hello", "start": 5.5, "end": 5.9, "src": 10.0},
            {"text": "world.", "start": 6.0, "end": 7.5, "src": 10.5}])

    def test_missing(self):
        segs = [seg(1.0, 2.0, 0), seg(3.0, 4.5, 1.0), seg(5.0, 6.0, 2.5)]
        self.assertEqual([W.range_key(g) for g in W.missing(segs, {"1.0-2.0": [], "5.0-6.0": []})], ["3.0-4.5"])
        self.assertEqual(W.missing(segs, {"1.0-2.0": [], "3.0-4.5": [], "5.0-6.0": []}), [])

    def test_missing_lists_a_repeated_range_once(self):
        segs = [seg(1.0, 2.0, 0), seg(1.0, 2.0, 1.0)]
        self.assertEqual(len(W.missing(segs, {})), 1)


class TakeCache(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.src = os.path.join(self.d, "take.mov")
        with open(self.src, "wb") as fh:
            fh.write(b"\x00" * 4096)
        self.legacy = os.path.join(self.d, "fw_ranges.json")

    def age(self, path, seconds):
        t = os.path.getmtime(self.src) + seconds
        os.utime(path, (t, t))

    def test_take_id_changes_with_the_take(self):
        a = C.take_id(self.src)
        self.assertEqual(a, C.take_id(self.src))
        st = os.stat(self.src)
        with open(self.src, "r+b") as fh:
            fh.write(b"\x01")                                     # same size, new bytes in the first MB
        os.utime(self.src, ns=(st.st_atime_ns, st.st_mtime_ns))    # and the old mtime: only the content differs
        self.assertNotEqual(a, C.take_id(self.src))

    def test_new_cache_records_the_source(self):
        c = W.new_cache(self.src)
        fid = C.file_id(self.src)
        self.assertEqual((c["size"], c["mtime_ns"]), (fid["size"], fid["mtime_ns"]))
        self.assertEqual(c["ranges"], {})

    def test_legacy_entries_are_imported_when_trusted(self):
        C.write_json(self.legacy, {"1.0-2.0": [[0.0, 0.5, "Hi"]]})
        self.age(self.legacy, 10)
        c = W.new_cache(self.src)
        entries = {}
        self.assertEqual(W.import_legacy(c, entries, self.legacy, self.src), 1)
        self.assertEqual(entries, {"1.0-2.0": [[0.0, 0.5, "Hi"]]})
        self.assertEqual(W.import_legacy(c, entries, self.legacy, self.src), 0)     # once per legacy file version

    def test_legacy_older_than_the_take_is_ignored(self):
        C.write_json(self.legacy, {"1.0-2.0": [[0.0, 0.5, "Hi"]]})
        self.age(self.legacy, -100)
        entries = {}
        self.assertEqual(W.import_legacy(W.new_cache(self.src), entries, self.legacy, self.src), 0)
        self.assertEqual(entries, {})

    def test_a_hand_edit_to_the_legacy_file_wins(self):
        C.write_json(self.legacy, {"1.0-2.0": [[0.0, 0.5, "Hi"]]})
        self.age(self.legacy, 10)
        c, entries = W.new_cache(self.src), {}
        W.import_legacy(c, entries, self.legacy, self.src)
        entries["3.0-4.0"] = [[0.0, 0.3, "new"]]
        C.write_json(self.legacy, {"1.0-2.0": [[0.0, 0.5, "I"]]})    # corrected by hand later
        self.age(self.legacy, 20)
        self.assertEqual(W.import_legacy(c, entries, self.legacy, self.src), 1)
        self.assertEqual(entries, {"1.0-2.0": [[0.0, 0.5, "I"]], "3.0-4.0": [[0.0, 0.3, "new"]]})

    def test_no_legacy_file(self):
        self.assertEqual(W.import_legacy(W.new_cache(self.src), {}, self.legacy, self.src), 0)


if __name__ == "__main__":
    unittest.main()
