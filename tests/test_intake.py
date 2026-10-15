"""intake.py: takes in (ordered by when they were recorded), one source out (joined by copy, or re-encoded once when the
takes differ, HDR converted), posters, intake.json, then new.py. Pure parts first, then real runs on tiny generated
clips (testsrc2 + sine) in temp folders; the CLI runs in a temp REEL_KIT_HOME, never the creator's.
Also here: new.py in a folder intake made and --reseed, cut.py --source-cuts (the scan intake starts).
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(os.path.dirname(HERE), "pipeline")
sys.path.insert(0, PIPE)
import common  # noqa: E402
import intake as I  # noqa: E402


def info(name, **kw):
    d = dict(path="/x/" + name, name=name, duration=10.0, width=1080, height=1920, rotation=0, fps="30/1",
             vcodec="h264", pix_fmt="yuv420p", transfer="bt709", hdr=False, has_audio=True, acodec="aac",
             sample_rate=48000, recorded="2026-10-14T10:00:00Z")
    d.update(kw)
    return d


# ------------------------------------------------------------------ the pure parts
class Order(unittest.TestCase):
    def test_by_recording_time_then_name(self):
        a = info("b.mov", recorded="2026-10-14T10:05:00Z")
        b = info("a.mov", recorded="2026-10-14T10:01:00Z")
        c = info("c.mov", recorded=None)
        self.assertEqual([x["name"] for x in I.order([a, b, c])], ["a.mov", "b.mov", "c.mov"])


class Join(unittest.TestCase):
    def test_one_take_is_not_joined(self):
        self.assertEqual(I.plan_join([info("a.mov")])["mode"], "single")

    def test_matching_takes_are_copied(self):
        self.assertEqual(I.plan_join([info("a.mov"), info("b.mov")])["mode"], "copy")

    def test_any_difference_re_encodes_and_says_why(self):
        for diff in (dict(fps="60/1"), dict(width=720, height=1280), dict(vcodec="hevc"), dict(rotation=90),
                     dict(sample_rate=44100), dict(has_audio=False)):
            p = I.plan_join([info("a.mov"), info("b.mov", **diff)])
            self.assertEqual(p["mode"], "encode", diff)
            self.assertTrue(p["why"], diff)

    def test_hdr_is_converted_even_alone(self):
        p = I.plan_join([info("a.mov", transfer="arib-std-b67", hdr=True)])
        self.assertEqual(p["mode"], "encode")
        self.assertTrue(p["hdr"])

    def test_the_most_common_shape_wins(self):
        p = I.plan_join([info("a.mov"), info("b.mov"), info("c.mov", width=1920, height=1080)])
        self.assertEqual(p["size"], (1080, 1920))

    def test_a_take_without_sound_gets_a_silent_track_even_alone(self):
        for takes in ([info("a.mov", has_audio=False, acodec=None, sample_rate=None)],
                      [info("a.mov", has_audio=False, acodec=None, sample_rate=None),
                       info("b.mov", has_audio=False, acodec=None, sample_rate=None)]):
            p = I.plan_join(takes)
            self.assertEqual(p["mode"], "encode")
            self.assertTrue(any("sound" in w for w in p["why"]), p["why"])

    def test_a_copy_needs_the_same_channels_stream_order_and_decoder_setup(self):
        # ffmpeg's concat copy matches streams by index and keeps the first take's decoder setup for all of them
        for k, a, b in (("channels", 2, 1), ("streams", "v1a0", "v0a1"), ("vconfig", "MD5:aa", "MD5:bb"),
                        ("aconfig", "MD5:aa", "MD5:bb")):
            p = I.plan_join([info("a.mov", **{k: a}), info("b.mov", **{k: b})])
            self.assertEqual(p["mode"], "encode", k)
            self.assertTrue(p["why"], k)
        same = dict(channels=2, streams="v1a0", vconfig="MD5:aa", aconfig="MD5:cc")
        self.assertEqual(I.plan_join([info("a.mov", **same), info("b.mov", **same)])["mode"], "copy")


class Mode(unittest.TestCase):
    def test_4k_landscape_is_hifi(self):
        self.assertEqual(I.recommend_mode([info("a.mov", width=3840, height=2160)])[0], "hifi")

    def test_phone_vertical_1080_is_lofi(self):
        self.assertEqual(I.recommend_mode([info("a.mov")])[0], "lofi")


class FrameRate(unittest.TestCase):
    """the nominal rate of a take. A phone's timestamps wander: these are an iPhone's real numbers (30 fps takes that
    read 30/1 or 359/12 as their base rate and 29.999 or 29.916 on average); every one of them is 30 fps"""

    def test_an_iphone_take_is_30(self):
        for avg, base in (("858000/28601", "30/1"), ("922800/30847", "359/12"), ("260000/8691", "359/12")):
            self.assertEqual(I.nominal_fps(avg, base), "30/1", (avg, base))

    def test_standard_rates_stay_as_they_are(self):
        for r in ("30000/1001", "24000/1001", "25/1", "60/1", "60000/1001"):
            self.assertEqual(I.nominal_fps(r, r), r)

    def test_a_base_rate_far_from_the_average_is_not_trusted(self):
        self.assertEqual(I.nominal_fps("30/1", "120/1"), "30/1")
        self.assertEqual(I.nominal_fps("24/1", "30/1"), "30/1")          # a low-light phone take: still a 30 fps take

    def test_no_rate_at_all_is_the_kit_rate(self):
        self.assertEqual(I.nominal_fps("0/0", "0/0"), "30/1")


class Recorded(unittest.TestCase):
    def test_the_capture_time_wins_over_the_file_time(self):
        # an iPhone take sent by AirDrop: creation_time is when it was sent, creationdate when it was shot
        fmt = {"creation_time": "2026-10-14T02:57:09.000000Z",
               "com.apple.quicktime.creationdate": "2026-10-13T12:36:52-0700"}
        self.assertEqual(I.recorded(fmt, {}), "2026-10-13T19:36:52Z")

    def test_creation_time_then_the_video_stream(self):
        self.assertEqual(I.recorded({"creation_time": "2026-10-14T10:01:00.000000Z"}, {}), "2026-10-14T10:01:00Z")
        self.assertEqual(I.recorded({}, {"creation_time": "2026-10-14T10:02:00Z"}), "2026-10-14T10:02:00Z")

    def test_no_time_or_an_unset_clock_is_none(self):
        self.assertIsNone(I.recorded({}, {}))
        self.assertIsNone(I.recorded({"creation_time": "1970-01-01T00:00:00.000000Z"}, {}))
        self.assertIsNone(I.recorded({"creation_time": "1904-01-01T00:00:00Z"}, {}))
        self.assertIsNone(I.recorded({"creation_time": "not a date"}, {}))


class Layout(unittest.TestCase):
    def test_a_copy_puts_each_take_after_the_last_at_its_length(self):
        takes = [info("a.mov", duration=47.668333), info("b.mov", duration=52.401667)]
        self.assertEqual(I.layout(takes, dict(mode="copy", fps="30/1")), [(0.0, 47.668333), (47.668333, 52.401667)])

    def test_an_encode_makes_each_take_whole_frames(self):
        takes = [info("a.mov", duration=2.01), info("b.mov", duration=1.99), info("c.mov", duration=2.0)]
        got = I.layout(takes, dict(mode="encode", fps="30/1"))
        self.assertEqual([round(s * 30, 6) for s, _ in got], [0, 60, 120])
        self.assertEqual([round(d * 30, 6) for _, d in got], [60, 60, 60])

    def test_one_take(self):
        self.assertEqual(I.layout([info("a.mov", duration=5.5)], dict(mode="single", fps="30/1")), [(0.0, 5.5)])


class RawNames(unittest.TestCase):
    def test_same_names_get_numbered_and_joined_mov_stays_free(self):
        takes = [info("IMG_1.MOV", path="/a/IMG_1.MOV"), info("IMG_1.MOV", path="/b/IMG_1.MOV"),
                 info("joined.mov"), info("img_1-2.mov")]
        self.assertEqual(I.raw_names(takes), ["IMG_1.MOV", "IMG_1-2.MOV", "joined-2.mov", "img_1-2-2.mov"])


class HdrChains(unittest.TestCase):
    def test_the_best_conversion_this_ffmpeg_has_comes_first(self):
        names = lambda have: [n for n, _, _ in I.hdr_chains(have)]   # noqa: E731
        self.assertEqual(names({"zscale", "tonemap", "libplacebo", "colorspace"}),
                         ["zscale", "libplacebo", "colorspace"])
        self.assertEqual(names({"libplacebo", "colorspace"}), ["libplacebo", "colorspace"])
        self.assertEqual(names({"tonemap", "colorspace"}), ["colorspace"])        # this kit's build ffmpeg
        self.assertEqual(names(set()), [])

    def test_only_the_fallback_adds_a_note(self):
        notes = {n: note for n, _, note in I.hdr_chains({"zscale", "tonemap", "libplacebo", "colorspace"})}
        self.assertIsNone(notes["zscale"])
        self.assertIn("colorspace", notes["colorspace"])


# ------------------------------------------------------------------ real files
def slurp(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as fh:
        return fh.read()


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def clip(path, size=(180, 320), fps=30, seconds=2.0, audio=True, rate=48000, video=None, pix_fmt="yuv420p",
         vf=None, created=None):
    """a tiny take: testsrc2 (or another lavfi video) + a sine tone, H.264 + AAC"""
    w, h = size
    src = video or "testsrc2"
    args = ["-f", "lavfi", "-i", src + (":" if "=" in src else "=") + f"s={w}x{h}:r={fps}:d={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=f=440:r={rate}:d={seconds}"]
    if vf:
        args += ["-vf", vf]
    args += ["-c:v", "libx264", "-pix_fmt", pix_fmt] + (["-c:a", "aac"] if audio else [])
    if created:
        args += ["-metadata", f"creation_time={created}"]
    ffmpeg(*args, path)
    return path


def turned(src, dst):
    """src stored sideways: the same frames flagged to display turned 90 degrees, as a phone stores a portrait take
    (-display_rotation is ffmpeg 6.1 and later; older ones set the rotate tag)"""
    try:
        ffmpeg("-display_rotation", "90", "-i", src, "-c", "copy", dst)
    except subprocess.CalledProcessError:
        ffmpeg("-i", src, "-c", "copy", "-metadata:s:v:0", "rotate=90", dst)
    return dst


def ffprobe(path, entries, stream="v:0"):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries, "-of", "json",
                          path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    return (j.get("streams") or [{}])[0], j.get("format", {})


def frames_in(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return int(out.strip())


def picture(path, t, w, h, fmt="gray"):
    """the frame shown at t, as an array (gray: h x w; rgb24: h x w x 3)"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", path, "-frames:v", "1", "-s", f"{w}x{h}",
                          "-f", "rawvideo", "-pix_fmt", fmt, "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8)
    return a.reshape(h, w, 3) if fmt == "rgb24" else a.reshape(h, w)


def loudest(path, t, d):
    """the loudest sample (16-bit) between t and t + d"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-t", f"{d:.4f}", "-i", path, "-vn", "-ac", "1",
                          "-ar", "48000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return int(np.abs(np.frombuffer(raw, np.int16).astype(np.int32)).max())


class Clips(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="intake-")
        self.addCleanup(shutil.rmtree, self.d, True)

    def path(self, name):
        return os.path.join(self.d, name)


class Probe(Clips):
    def test_a_take(self):
        d = I.probe(clip(self.path("a.mov"), created="2026-10-13T19:02:11Z"))
        for k in ("path", "name", "duration", "width", "height", "rotation", "fps", "vcodec", "pix_fmt", "transfer",
                  "hdr", "has_audio", "acodec", "sample_rate", "recorded"):
            self.assertIn(k, d)
        self.assertEqual((d["name"], d["width"], d["height"], d["rotation"], d["fps"]), ("a.mov", 180, 320, 0, "30/1"))
        self.assertEqual((d["vcodec"], d["pix_fmt"], d["has_audio"], d["acodec"], d["sample_rate"]),
                         ("h264", "yuv420p", True, "aac", 48000))
        self.assertAlmostEqual(d["duration"], 2.0, delta=0.05)
        self.assertFalse(d["hdr"])
        self.assertEqual(d["recorded"], "2026-10-13T19:02:11Z")
        self.assertEqual(d["path"], self.path("a.mov"))

    def test_a_take_without_a_time_or_sound(self):
        d = I.probe(clip(self.path("a.mov"), audio=False))
        self.assertIsNone(d["recorded"])
        self.assertEqual((d["has_audio"], d["acodec"], d["sample_rate"]), (False, None, None))

    def test_a_sideways_take_reads_upright(self):
        flat = clip(self.path("flat.mov"), size=(320, 180))
        turned(flat, self.path("turned.mov"))
        d = I.probe(self.path("turned.mov"))
        self.assertEqual(d["rotation"] % 180, 90)
        self.assertEqual(I.shape(d), (180, 320))

    def test_hdr_is_read_from_the_transfer(self):
        d = I.probe(clip(self.path("hlg.mov"), pix_fmt="yuv420p10le",
                         vf="setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc"))
        self.assertEqual(d["transfer"], "arib-std-b67")
        self.assertTrue(d["hdr"])

    def test_not_a_video_is_none(self):
        with open(self.path("notes.txt"), "w") as fh:
            fh.write("what to say in take two\n")
        ffmpeg("-f", "lavfi", "-i", "testsrc2=s=64x64:d=1", "-frames:v", "1", self.path("still.jpg"))
        ffmpeg("-f", "lavfi", "-i", "sine=d=1", "-c:a", "aac", self.path("voice.m4a"))
        for name in ("notes.txt", "still.jpg", "voice.m4a", "missing.mov"):
            self.assertIsNone(I.probe(self.path(name)), name)


class JoinRun(Clips):
    def joined(self, *takes):
        infos = I.order([I.probe(t) for t in takes])
        plan = I.plan_join(infos)
        out = self.path("joined.mov")
        I.join(infos, plan, out)
        return infos, plan, out

    def test_matching_takes_join_by_copy(self):
        infos, plan, out = self.joined(clip(self.path("a.mov")), clip(self.path("b.mov")))
        self.assertEqual(plan["mode"], "copy")
        _, fmt = ffprobe(out, "format=duration")
        self.assertAlmostEqual(float(fmt["duration"]), sum(d["duration"] for d in infos), delta=1 / 30)
        self.assertEqual(frames_in(out), 120)

    def test_60_fps_with_30_re_encodes_at_the_common_rate(self):
        infos, plan, out = self.joined(clip(self.path("a.mov")), clip(self.path("b.mov"), fps=60))
        self.assertEqual((plan["mode"], plan["fps"]), ("encode", "30/1"))
        v, _ = ffprobe(out, "stream=r_frame_rate,avg_frame_rate")
        self.assertEqual((v["r_frame_rate"], v["avg_frame_rate"]), ("30/1", "30/1"))
        self.assertEqual(frames_in(out), 120)

    def test_a_landscape_take_among_vertical_ones_comes_out_vertical_with_padding(self):
        infos, plan, out = self.joined(clip(self.path("a.mov")), clip(self.path("b.mov")),
                                       clip(self.path("c.mov"), size=(320, 180)))
        self.assertEqual((plan["mode"], plan["size"]), ("encode", (180, 320)))
        v, _ = ffprobe(out, "stream=width,height")
        self.assertEqual((v["width"], v["height"]), (180, 320))
        start, _ = I.layout(infos, plan)[2]
        f = picture(out, start + 1.0, 180, 320)
        self.assertLess(f[:90].mean(), 20)                     # black above the landscape picture ...
        self.assertLess(f[-90:].mean(), 20)                    # ... and below it
        self.assertGreater(f[130:190].mean(), 40)              # the picture itself in the middle

    def test_a_take_without_sound_gets_silence(self):
        infos, plan, out = self.joined(clip(self.path("a.mov")), clip(self.path("b.mov"), audio=False))
        self.assertEqual(plan["mode"], "encode")
        a, _ = ffprobe(out, "stream=sample_rate,channels", "a:0")
        self.assertEqual((a["sample_rate"], a["channels"]), ("48000", 2))
        (s0, d0), (s1, d1) = I.layout(infos, plan)
        self.assertGreater(loudest(out, s0 + 0.2, d0 - 0.4), 1000)
        self.assertLess(loudest(out, s1 + 0.2, d1 - 0.4), 10)

    def test_takes_land_where_the_layout_says(self):
        for mode, fps2 in (("copy", 30), ("encode", 60)):
            colors = {"a.mov": "red", "b.mov": "lime", "c.mov": "blue"}
            takes = [clip(self.path(n), video="color=c=" + c, fps=fps2 if n == "b.mov" else 30)
                     for n, c in colors.items()]
            infos, plan, out = self.joined(*takes)
            self.assertEqual(plan["mode"], mode)
            want = {"red": 0, "lime": 1, "blue": 2}
            for d, (start, _) in zip(infos, I.layout(infos, plan)):
                rgb = picture(out, start + 0.5 / 30, 8, 8, "rgb24").reshape(-1, 3).mean(axis=0)
                self.assertEqual(int(np.argmax(rgb)), want[colors[d["name"]]], (mode, d["name"], rgb))

    def test_hdr_alone_is_converted_to_bt709_and_plays(self):
        hlg = clip(self.path("hlg.mov"), pix_fmt="yuv420p10le",
                   vf="setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc")
        infos, plan, out = self.joined(hlg)
        self.assertEqual((plan["mode"], plan["hdr"]), ("encode", True))
        v, _ = ffprobe(out, "stream=pix_fmt,color_primaries,color_transfer,color_space")
        self.assertEqual((v["pix_fmt"], v["color_primaries"], v["color_transfer"], v["color_space"]),
                         ("yuv420p", "bt709", "bt709", "bt709"))
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-f", "null", "-"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertTrue(any("HDR" in w for w in plan["why"]), plan["why"])

    def test_one_take_is_cloned(self):
        infos, plan, out = self.joined(clip(self.path("a.mov")))
        self.assertEqual(plan["mode"], "single")
        with open(out, "rb") as a, open(self.path("a.mov"), "rb") as b:
            self.assertEqual(a.read(), b.read())


# ------------------------------------------------------------------ the CLI, in a temp home
def make_home(root):
    """a creator's home with just enough for new.py: the default style pack (built) and the vendor folder"""
    home = os.path.join(root, "home")
    os.makedirs(os.path.join(home, "style", "fonts"))
    with open(os.path.join(home, "style", "style.json"), "w") as fh:
        json.dump({"modes": {"lofi": {"j_lead": 0.2}}}, fh)
    with open(os.path.join(home, "style", "brand.css"), "w") as fh:
        fh.write("/* the default pack, built */\n")
    with open(os.path.join(home, "style", "STYLE.md"), "w") as fh:
        fh.write("# test pack\n")
    os.makedirs(os.path.join(home, "vendor"))
    with open(os.path.join(home, "vendor", "gsap.min.js"), "w") as fh:
        fh.write("// gsap\n")
    return home


def env_for(home):
    env = dict(os.environ, REEL_KIT_HOME=home)
    env.pop("REEL_MACHINE_HOME", None)             # a newer name for the home must not point the test elsewhere
    return env


def run_py(home, script, *args):
    return subprocess.run([sys.executable, os.path.join(PIPE, script), *args], capture_output=True, text=True,
                          env=env_for(home))


def load(path):
    spec = types.ModuleType("edit")
    with open(path, encoding="utf-8") as fh:
        exec(compile(fh.read(), path, "exec"), spec.__dict__)
    return spec


class Cli(Clips):
    def setUp(self):
        super().setUp()
        self.home = make_home(self.d)
        self.takes = os.path.join(self.d, "takes")
        os.makedirs(self.takes)

    def intake(self, *args):
        r = run_py(self.home, "intake.py", *args)
        if os.path.realpath(common.HOME) != os.path.realpath(self.home):          # nothing lands in the real home
            self.assertFalse(os.path.exists(os.path.join(common.HOME, "projects", args[0])), args[0])
        return r, os.path.join(self.home, "projects", args[0])

    def read(self, project):
        with open(os.path.join(project, "intake.json")) as fh:
            return json.load(fh)

    def test_a_folder_of_takes(self):
        clip(os.path.join(self.takes, "z-first.mov"), created="2026-10-14T10:01:00Z")
        clip(os.path.join(self.takes, "a-second.mov"), created="2026-10-14T10:05:00Z")
        with open(os.path.join(self.takes, "notes.txt"), "w") as fh:
            fh.write("the script\n")
        with open(os.path.join(self.takes, ".DS_Store"), "wb") as fh:
            fh.write(b"\x00\x01")
        r, project = self.intake("_lab-t-vid", self.takes, "--title", "Test Video", "--no-start")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        j = self.read(project)
        self.assertEqual((j["version"], j["slug"], j["title"], j["source"]),
                         (1, "_lab-t-vid", "Test Video", "raw/joined.mov"))
        self.assertEqual(j["plan"]["mode"], "copy")
        self.assertEqual(j["plan"]["size"], [180, 320])
        self.assertEqual(j["plan"]["fps"], "30/1")
        self.assertEqual(j["recommended"]["mode"], "lofi")
        self.assertTrue(j["recommended"]["why"])
        self.assertEqual([t["name"] for t in j["takes"]], ["z-first.mov", "a-second.mov"])   # recorded, not named
        self.assertEqual(j["ignored"], ["notes.txt"])
        t0, t1 = j["takes"]
        self.assertEqual((t0["file"], t0["start"], t0["recorded"], t0["size"], t0["hdr"]),
                         ("raw/z-first.mov", 0.0, "2026-10-14T10:01:00Z", [180, 320], False))
        self.assertAlmostEqual(t1["start"], t0["duration"], places=3)
        for k, t in enumerate(j["takes"], 1):
            self.assertEqual(t["poster"], f"approvals/start/posters/{k:02d}.jpg")
            with open(os.path.join(project, t["poster"]), "rb") as fh:
                self.assertEqual(fh.read(2), b"\xff\xd8")                                  # a JPEG
            self.assertTrue(os.path.exists(os.path.join(project, t["file"])))
        self.assertTrue(os.path.exists(os.path.join(project, "raw", "joined.mov")))
        E = load(os.path.join(project, "edit.py"))
        self.assertEqual((E.STYLE, E.TITLE), ("lofi", "Test Video"))
        self.assertEqual(E.SRC, os.path.join(project, "raw", "joined.mov"))
        self.assertEqual(len(E.KEEP), 1)                                                     # the whole source: the
        self.assertEqual(E.KEEP[0][0], 0.0)                                                  # first transcript reads it
        self.assertAlmostEqual(E.KEEP[0][1], t1["start"] + t1["duration"], delta=1 / 30)
        self.assertFalse(os.path.exists(os.path.join(project, "work", "words.log")))           # --no-start
        self.assertIn("preview.py", r.stdout)
        self.assertIn("z-first.mov", r.stdout)

    def test_one_take_is_the_source(self):
        clip(os.path.join(self.takes, "only.mov"))
        r, project = self.intake("_lab-t-one", os.path.join(self.takes, "only.mov"), "--no-start")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        j = self.read(project)
        self.assertEqual((j["plan"]["mode"], j["source"]), ("single", "raw/only.mov"))
        self.assertFalse(os.path.exists(os.path.join(project, "raw", "joined.mov")))
        self.assertEqual(load(os.path.join(project, "edit.py")).SRC, os.path.join(project, "raw", "only.mov"))

    def test_the_poster_is_the_middle_of_the_take(self):
        # red, then green, then blue: the start of a take is often the walk to the camera, the middle is the take
        lavfi = [a for c, d in (("red", 0.6), ("lime", 0.8), ("blue", 0.6))
                 for a in ("-f", "lavfi", "-i", f"color=c={c}:s=180x320:r=30:d={d}")]
        take = os.path.join(self.takes, "rgb.mov")
        ffmpeg(*lavfi, "-f", "lavfi", "-i", "sine=f=440:r=48000:d=2", "-filter_complex",
               "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-pix_fmt",
               "yuv420p", "-c:a", "aac", take)
        r, project = self.intake("_lab-t-poster", take, "--no-start")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        rgb = picture(os.path.join(project, "approvals", "start", "posters", "01.jpg"), 0, 8, 8, "rgb24")
        self.assertEqual(int(np.argmax(rgb.reshape(-1, 3).mean(axis=0))), 1)

    def test_the_takes_are_never_changed(self):
        a = clip(os.path.join(self.takes, "a.mov"))
        before = (os.stat(a).st_mtime_ns, slurp(a, "rb"))
        r, _ = self.intake("_lab-t-safe", a, "--no-start")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual((os.stat(a).st_mtime_ns, slurp(a, "rb")), before)

    def test_a_given_mode_wins_and_the_recommendation_stays(self):
        clip(os.path.join(self.takes, "a.mov"))
        r, project = self.intake("_lab-t-show", self.takes, "--mode", "showcase", "--no-start")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(load(os.path.join(project, "edit.py")).STYLE, "showcase")
        self.assertEqual(self.read(project)["recommended"]["mode"], "lofi")

    def test_a_re_encode_is_named_with_its_reason(self):
        clip(os.path.join(self.takes, "a.mov"))
        clip(os.path.join(self.takes, "b.mov"), size=(320, 180))
        r, project = self.intake("_lab-t-mixed", self.takes, "--no-start")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        j = self.read(project)
        self.assertEqual(j["plan"]["mode"], "encode")
        self.assertTrue(j["plan"]["why"])
        self.assertIn(j["plan"]["why"][0], r.stdout)

    def test_a_started_project_is_refused(self):
        clip(os.path.join(self.takes, "a.mov"))
        r, project = self.intake("_lab-t-twice", self.takes, "--no-start")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        r, _ = self.intake("_lab-t-twice", self.takes, "--no-start")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("edit.py", r.stderr)

    def test_no_video_stops(self):
        with open(os.path.join(self.takes, "notes.txt"), "w") as fh:
            fh.write("x\n")
        r, project = self.intake("_lab-t-none", self.takes, "--no-start")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("notes.txt", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(project, "intake.json")))

    def test_a_bad_slug_stops(self):
        clip(os.path.join(self.takes, "a.mov"))
        for slug in ("../out", "a/b", ""):
            r = run_py(self.home, "intake.py", slug, self.takes, "--no-start")
            self.assertNotEqual(r.returncode, 0, slug)
        self.assertFalse(os.path.exists(os.path.join(self.d, "out")))


class Background(Clips):
    def test_the_jobs_are_the_first_transcript_and_the_source_cut_scan(self):
        jobs = dict(I.jobs("/p", "/py"))
        self.assertEqual(jobs["words"], ["/py", os.path.join(PIPE, "words.py"), "/p"])
        self.assertEqual(jobs["source-cuts"], ["/py", os.path.join(PIPE, "cut.py"), "/p", "--source-cuts"])

    def test_a_job_runs_on_its_own_and_logs(self):
        say = "import time; print('hi from the background', flush=True); time.sleep(1)"
        logs = I.start(self.d, [("hello", [sys.executable, "-c", say])])
        log = logs["hello"]
        self.assertEqual(log, os.path.join(self.d, "work", "hello.log"))
        proc = I.BACKGROUND[-1]
        self.assertNotEqual(os.getpgid(proc.pid), os.getpgid(0))     # its own session: closing intake leaves it be
        self.assertEqual(proc.wait(20), 0)
        self.assertIn("hi from the background", slurp(log))


# ------------------------------------------------------------------ new.py in an intake folder, --reseed
class New(Clips):
    def setUp(self):
        super().setUp()
        self.home = make_home(self.d)
        self.project = os.path.join(self.home, "projects", "lab")
        os.makedirs(os.path.join(self.project, "raw"))
        self.src = clip(os.path.join(self.project, "raw", "a.mov"))
        self.intake_json = os.path.join(self.project, "intake.json")
        with open(self.intake_json, "w") as fh:
            json.dump({"version": 1, "source": "raw/a.mov"}, fh)

    def new(self, *args):
        return run_py(self.home, "new.py", "lab", self.src, "Lab Video", *args)

    def test_a_folder_with_raw_and_intake_json_is_fine(self):
        before = slurp(self.intake_json), slurp(self.src, "rb")
        r = self.new("--mode", "lofi")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((slurp(self.intake_json), slurp(self.src, "rb")), before)
        self.assertEqual(load(os.path.join(self.project, "edit.py")).STYLE, "lofi")

    def test_quotes_in_a_title_or_a_take_name_still_make_a_working_edit_py(self):
        odd = os.path.join(self.project, "raw", 'take "one" \\ final.mov')
        shutil.copyfile(self.src, odd)
        title = 'Why I Quit "Hustle" \\ Culture'
        r = run_py(self.home, "new.py", "lab", odd, title, "--mode", "lofi")
        self.assertEqual(r.returncode, 0, r.stderr)
        E = load(os.path.join(self.project, "edit.py"))
        self.assertEqual((E.TITLE, E.SRC), (title, odd))

    def test_an_edit_py_is_refused_without_reseed(self):
        self.assertEqual(self.new("--mode", "lofi").returncode, 0)
        r = self.new("--mode", "hifi")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--reseed", r.stderr)
        self.assertEqual(load(os.path.join(self.project, "edit.py")).STYLE, "lofi")

    def test_reseed_switches_the_mode_and_keeps_keep_prompt_and_fixes(self):
        self.assertEqual(self.new("--mode", "hifi").returncode, 0)
        path = os.path.join(self.project, "edit.py")
        text = slurp(path)
        text = text.replace("KEEP = []", "KEEP = [\n    (0.10, 0.90),   # take one\n    (1.10, 1.90),\n]")
        text = text.replace('PROMPT = ""', 'PROMPT = "Claude, CapCut"')
        text = text.replace("FIXES = {}", 'FIXES = {"cloud": "Claude"}')
        text = text.replace("CAPS = []", 'CAPS = [(0.0, "Hello", "")]')
        text += "J_LEADS = [0.0]\n"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        style_md = os.path.join(self.project, "style", "STYLE.md")
        with open(style_md, "w") as fh:
            fh.write("# the pack this project wears\n")
        r = self.new("--mode", "lofi", "--reseed")
        self.assertEqual(r.returncode, 0, r.stderr)
        E = load(path)
        self.assertEqual(E.STYLE, "lofi")
        self.assertEqual(E.KEEP, [(0.10, 0.90), (1.10, 1.90)])
        self.assertEqual((E.PROMPT, E.FIXES, E.J_LEADS), ("Claude, CapCut", {"cloud": "Claude"}, [0.0]))
        self.assertEqual(E.CAPS, [])                                                # the rest is the new mode's
        self.assertTrue(hasattr(E, "KARAOKE"))
        self.assertIn("# take one", slurp(path))             # comments travel with KEEP
        old = os.path.join(self.project, f"edit-before-lofi-{datetime.date.today().strftime('%m-%d-%y')}.py")
        self.assertEqual(load(old).STYLE, "hifi")
        self.assertEqual(load(old).CAPS, [(0.0, "Hello", "")])
        self.assertEqual(slurp(style_md), "# the pack this project wears\n")   # the style is left alone

    def test_reseed_twice_keeps_both_old_files(self):
        self.assertEqual(self.new("--mode", "hifi").returncode, 0)
        self.assertEqual(self.new("--mode", "lofi", "--reseed").returncode, 0)
        r = self.new("--mode", "lofi", "--reseed")
        self.assertEqual(r.returncode, 0, r.stderr)
        stamp = datetime.date.today().strftime('%m-%d-%y')
        self.assertTrue(os.path.exists(os.path.join(self.project, f"edit-before-lofi-{stamp}.py")))
        self.assertTrue(os.path.exists(os.path.join(self.project, f"edit-before-lofi-{stamp}-2.py")))

    def test_a_sideways_take_seeds_upright_frames(self):
        flat = clip(self.path("flat.mov"), size=(320, 180))
        turned(flat, os.path.join(self.project, "raw", "turned.mov"))
        self.src = os.path.join(self.project, "raw", "turned.mov")
        r = self.new("--mode", "lofi")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(load(os.path.join(self.project, "edit.py")).FRAMES["WIDE"], (180, 320, 0, 0))


# ------------------------------------------------------------------ cut.py --source-cuts
class SourceCuts(Clips):
    def test_the_scan_runs_alone_and_caches(self):
        red = clip(self.path("red.mov"), video="color=c=red", seconds=1.0)
        blue = clip(self.path("blue.mov"), video="color=c=blue", seconds=1.0)
        with open(self.path("list.txt"), "w") as fh:
            fh.write(f"file '{red}'\nfile '{blue}'\n")
        src = self.path("cut.mov")
        ffmpeg("-f", "concat", "-safe", "0", "-i", self.path("list.txt"), "-c", "copy", src)
        project = self.path("proj")
        os.makedirs(project)
        with open(os.path.join(project, "edit.py"), "w") as fh:
            fh.write(f'STYLE = "lofi"\nSRC = "{src}"\nKEEP = []\nSHOTS = [(0.0, "WIDE")]\n'
                     'FRAMES = {"WIDE": (180, 320, 0, 0)}\n')
        r = subprocess.run([sys.executable, os.path.join(PIPE, "cut.py"), project, "--source-cuts"],
                           capture_output=True, text=True, env=env_for(make_home(self.path("h"))))
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(project, "work", "source_cuts.json")) as fh:
            cuts = json.load(fh)["cuts"]
        self.assertEqual(len(cuts), 1, cuts)
        self.assertAlmostEqual(cuts[0], 1.0, delta=1 / 30)
        self.assertFalse(os.path.exists(os.path.join(project, "assets", "aroll.mp4")))
        self.assertFalse(os.path.exists(os.path.join(project, "timeline.json")))


if __name__ == "__main__":
    unittest.main()
