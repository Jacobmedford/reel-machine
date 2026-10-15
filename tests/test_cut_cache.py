"""cut.py piece cache: keys, piece commands, the voice chain, the join list, pruning, the source-cuts cache."""
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import cache as C  # noqa: E402
import cut  # noqa: E402


def edit(**kw):
    E = types.SimpleNamespace(KEEP=[(1.0, 3.5), (4.2, 6.0), (7.123, 9.0)], J_LEAD=0.3, J_LEADS=[0.3, 0.0], HOLD=0.4,
                              SHOTS=[(0.0, "WIDE"), (2.5, "CLOSE"), (4.3, "WIDE")], PROJECT="/nonexistent",
                              SRC="/clips/take.mov", CANVAS=(1080, 1920),
                              FRAMES={"WIDE": (2160, 3840, 0, 0), "CLOSE": (1350, 2400, 700, 360)})
    for k, v in kw.items():
        setattr(E, k, v)
    return E


SRC_ID = {"path": "/clips/take.mov", "size": 1000, "mtime_ns": 5}


class PlanUnchanged(unittest.TestCase):
    """the plan, the pieces and the sync table are the lip-sync contract: pinned to the values the kit gave before
    the cache existed"""

    def test_plan_pieces_and_sync_rows(self):
        with mock.patch.object(cut, "source_cuts", lambda E: [3.43, 8.2]):
            E = edit()
            segs, _ = cut.plan(E)
            E.SHOTS = cut.snap_shots(E, segs)
            pcs, total = cut.pieces(E, segs)
            worst, rows = cut.sync_table(segs, pcs)
        self.assertEqual(E.SHOTS, [(0.0, "WIDE"), (2.8, "CLOSE"), (4.3, "WIDE")])
        self.assertEqual(pcs, [(0.0, 2.8, 1.0, "WIDE"), (2.8, 4.3, 4.5, "CLOSE"), (4.3, 6.566666666666666, 7.123, "WIDE")])
        self.assertEqual(total, 6.577)
        self.assertEqual(worst, 0.0)
        self.assertEqual(rows, [
            "     0.000-   2.800 WIDE   picture    1.000  audio    1.000  offset +0.000",
            "     2.800-   4.300 CLOSE  picture    4.500  audio    4.500  offset +0.000",
            "     4.300-   6.567 WIDE   picture    7.123  audio    7.123  offset +0.000"])


class PieceArgs(unittest.TestCase):
    def test_same_seek_crop_and_count_as_before(self):
        a = cut.piece_args(edit(), 4.5, 45, "CLOSE")
        self.assertEqual(a[:5], ["-ss", "4.4900", "-i", "/clips/take.mov", "-an"])
        # the old picture chain picks the frames; setpts after it only renumbers them from 0 (exact joins)
        self.assertEqual(a[a.index("-vf") + 1], "crop=1350:2400:700:360,scale=1080:1920:flags=lanczos,fps=30,setsar=1,"
                                                 "setpts=N/30/TB")
        self.assertEqual(a[a.index("-frames:v") + 1], "45")

    def test_pieces_carry_the_aroll_settings(self):
        a = cut.piece_args(edit(), 1.0, 10, "WIDE")
        for flag, val in (("-c:v", "libx264"), ("-crf", "14"), ("-g", "10"), ("-keyint_min", "10"), ("-bf", "0"),
                          ("-pix_fmt", "yuv420p"), ("-video_track_timescale", "15360"), ("-movie_timescale", "15360")):
            self.assertEqual(a[a.index(flag) + 1], val)


class PieceKey(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(C, "ffmpeg_version", lambda: "ffmpeg version test")
        p.start()
        self.addCleanup(p.stop)

    def key(self, src_id=SRC_ID, **kw):
        E = edit(**{k: v for k, v in kw.items() if k in ("CANVAS", "FRAMES", "SRC")})
        return cut.piece_key(src_id, cut.piece_args(E, kw.get("src", 4.5), kw.get("n", 45), kw.get("fr", "CLOSE")))

    def test_stable(self):
        self.assertEqual(self.key(), self.key())

    def test_source_size_and_mtime_change_the_key(self):
        self.assertNotEqual(self.key(), self.key(dict(SRC_ID, size=1001)))
        self.assertNotEqual(self.key(), self.key(dict(SRC_ID, mtime_ns=6)))
        self.assertNotEqual(self.key(), self.key(dict(SRC_ID, path="/clips/other.mov")))

    def test_range_crop_canvas_change_the_key(self):
        base = self.key()
        self.assertNotEqual(base, self.key(src=4.6))
        self.assertNotEqual(base, self.key(n=46))
        self.assertNotEqual(base, self.key(fr="WIDE"))
        self.assertNotEqual(base, self.key(CANVAS=(1920, 1080)))
        self.assertNotEqual(base, self.key(FRAMES={"CLOSE": (1350, 2400, 702, 360)}))

    def test_a_sub_millisecond_seek_difference_is_the_same_piece(self):
        # the seek is written to 0.1 ms like the kit always did: the same command, the same piece
        self.assertEqual(self.key(src=4.50001), self.key(src=4.50002))

    def test_ffmpeg_build_changes_the_key(self):
        base = self.key()
        with mock.patch.object(C, "ffmpeg_version", lambda: "ffmpeg version other"):
            self.assertNotEqual(base, self.key())


class Voice(unittest.TestCase):
    def test_voice_chain_is_byte_identical_to_the_old_one(self):
        segs, _ = cut.plan(edit(KEEP=[(1.0, 3.5), (4.2, 6.0)], J_LEADS=[0.3]))
        self.assertEqual(cut.voice_filter(segs), (
            "[0:a]atrim=1.0000:3.5000,asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st=2.4700:d=0.03[a0];"
            "[0:a]atrim=4.2000:6.0000,asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st=1.7700:d=0.03[a1];"
            "[a0][a1]concat=n=2:v=0:a=1[ac];[ac]highpass=f=80,afftdn=nr=8:nf=-45,equalizer=f=250:t=q:w=1.2:g=-2,"
            "equalizer=f=3200:t=q:w=1.0:g=2,acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2,"
            "alimiter=limit=0.89:level=false,loudnorm=I=-16:TP=-2:LRA=9,aresample=48000[ao]"))

    def test_voice_args_follow_keep(self):
        a = cut.voice_args(edit(), cut.plan(edit())[0])
        b = cut.voice_args(edit(), cut.plan(edit(KEEP=[(1.0, 3.4), (4.2, 6.0), (7.123, 9.0)]))[0])
        self.assertNotEqual(a, b)
        self.assertEqual(a[-4:], ["-ac", "2", "-c:a", "pcm_s16le"])


class EvenJoin(unittest.TestCase):
    """the joined a-roll is checked before it is used: a join that left uneven timestamps made a plain ffmpeg read
    of the a-roll repeat and drop frames (and the matte drift a frame behind the picture)"""

    def rows(self, n, delay=0):
        return [(k * 512, (k - delay) * 512) for k in range(n)]

    def test_packet_times_keep_negative_dts(self):
        self.assertEqual(cut.packet_times("0,-1024\n2048,-512\n1024,0\nN/A,N/A\n"), [(0, -1024), (2048, -512), (1024, 0)])

    def test_even(self):
        self.assertEqual(cut.uneven(self.rows(30), 30, 512), "")
        self.assertEqual(cut.uneven(self.rows(30, delay=2), 30, 512), "")        # a steady decode delay is fine

    def test_wrong_count(self):
        self.assertIn("29 frames", cut.uneven(self.rows(29), 30, 512))

    def test_late_start(self):
        rows = [(p + 512, d + 512) for p, d in self.rows(30)]
        self.assertIn("first pts 512", cut.uneven(rows, 30, 512))

    def test_millisecond_edit_list_step(self):
        rows = self.rows(30)
        rows[10:] = [(p - 10, d - 10) for p, d in rows[10:]]                  # a 10-tick short piece
        self.assertIn("502", cut.uneven(rows, 30, 512))

    def test_uneven_decode_timestamps(self):
        dts = [0, 512, 1024, 2560, 2561, 2562, 3072, 3584]                    # what a 2-frame B-frame piece left
        rows = [(k * 512, d) for k, d in enumerate(dts)]
        self.assertIn("1536", cut.uneven(rows, 8, 512))


class JoinAndPrune(unittest.TestCase):
    def test_join_list(self):
        self.assertEqual(cut.join_list(["ab.mp4", "cd.mp4"]), "file 'ab.mp4'\nfile 'cd.mp4'\n")

    def test_lru_keeps_used_and_recent(self):
        entries = [("used.mp4", 50, 1.0), ("new.mp4", 40, 9.0), ("mid.mp4", 40, 5.0), ("old.mp4", 40, 2.0)]
        self.assertEqual(C.lru_evict(entries, {"used.mp4"}, 80), ["old.mp4"])
        self.assertEqual(C.lru_evict(entries, {"used.mp4"}, 0), ["new.mp4", "mid.mp4", "old.mp4"])
        self.assertEqual(C.lru_evict(entries, {"used.mp4", "old.mp4"}, 1000), [])

    def test_prune_removes_only_unused_pieces(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for i, name in enumerate(("a.mp4", "b.mp4", "c.mp4", "join.txt")):
            with open(os.path.join(d, name), "wb") as fh:
                fh.write(b"x" * 10)
            os.utime(os.path.join(d, name), (1000 + i, 1000 + i))
        self.assertEqual(cut.prune(d, ["a.mp4"], 10), 1)       # room for one unused piece: the newer (c) stays
        self.assertEqual(sorted(os.listdir(d)), ["a.mp4", "c.mp4", "join.txt"])


class SourceCuts(unittest.TestCase):
    """the source-cuts cache must not survive a re-shot take saved under the same name"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        os.makedirs(os.path.join(self.d, "work"))
        self.src = os.path.join(self.d, "take.mov")
        with open(self.src, "wb") as fh:
            fh.write(b"take one")
        self.cache = os.path.join(self.d, "work", "source_cuts.json")
        self.E = types.SimpleNamespace(PROJECT=self.d, SRC=self.src)

    def write(self, data, age):
        with open(self.cache, "w") as fh:
            json.dump(data, fh)
        t = os.path.getmtime(self.src) + age
        os.utime(self.cache, (t, t))

    def no_decode(self):
        return mock.patch.object(cut.subprocess, "run", side_effect=AssertionError("decoded the source"))

    def test_matching_identity_is_used(self):
        fid = C.file_id(self.src)
        self.write({"src": self.src, "size": fid["size"], "mtime_ns": fid["mtime_ns"], "cuts": [1.5]}, 10)
        with self.no_decode():
            self.assertEqual(cut.source_cuts(self.E), [1.5])

    def test_legacy_cache_newer_than_the_source_is_trusted_and_upgraded(self):
        self.write({"src": self.src, "cuts": [2.5]}, 10)
        with self.no_decode():
            self.assertEqual(cut.source_cuts(self.E), [2.5])
        self.assertEqual(C.read_json(self.cache)["size"], os.path.getsize(self.src))

    def test_reshot_take_is_measured_again(self):
        fid = C.file_id(self.src)
        self.write({"src": self.src, "size": fid["size"], "mtime_ns": fid["mtime_ns"], "cuts": [1.5]}, 10)
        time.sleep(0.01)
        with open(self.src, "wb") as fh:
            fh.write(b"take two, longer")
        with self.no_decode():
            with self.assertRaises(AssertionError):
                cut.source_cuts(self.E)

    def test_legacy_cache_older_than_the_source_is_not_trusted(self):
        self.write({"src": self.src, "cuts": [2.5]}, -100)
        with self.no_decode():
            with self.assertRaises(AssertionError):
                cut.source_cuts(self.E)


if __name__ == "__main__":
    unittest.main()
