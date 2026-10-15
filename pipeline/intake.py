#!/usr/bin/env python3
"""Intake: the creator's takes in, one source out, and the project started.

  1. Every file given (or in a folder given) is probed; anything that is not a video (notes, stills, sound files) is
     listed as ignored. The takes are ordered by when they were recorded, then by name.
  2. They are cloned into <home>/projects/<slug>/raw/ (a copy-on-write clone where the disk can make one): the
     creator's own files are never changed.
  3. One source. One take is used as it is (raw/<take>). Several are joined into raw/joined.mov: the picture by
     stream copy when the takes match (codec, size, frame rate, rotation, sound, encoder setup), else everything
     re-encoded once, each take fitted to the most common shape (black bars) at the most common frame rate, with a
     silent track for a take that has no sound. HDR is converted to standard range. Every re-encode says why.
  4. A poster per take, its middle frame (approvals/start/posters/01.jpg ...), and intake.json: the takes in order,
     where each starts in the source, the join plan, the recommended mode.
  5. new.py with the recommended mode (or --mode), KEEP set to the whole source, then in the background the first
     transcript (words.py) and the scan for cuts already in the source (cut.py --source-cuts), each logging to
     work/<job>.log. --no-start skips the background jobs.
Run: PY pipeline/intake.py <slug> <clip or folder> [...] [--title "Title"] [--mode hifi|lofi|showcase] [--no-start]
Then: PY pipeline/preview.py <project> start
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, HOME, KIT, PY  # noqa: E402
import cache as C  # noqa: E402

HDR_TRANSFERS = ("arib-std-b67", "smpte2084")
MODES = ("hifi", "lofi", "showcase")
STANDARD_FPS = ("24000/1001", "24/1", "25/1", "30000/1001", "30/1", "48/1", "50/1", "60000/1001", "60/1", "100/1",
                "120/1", "240/1")
STILLS = ("image2", "gif", "apng", "webp", "tty")       # containers of one picture (or text art): never a take
JOINED = "joined.mov"
SLUG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
SOUND_IN = "aresample=48000:async=1:min_hard_comp=0.001:first_pts=0,aformat=sample_fmts=fltp:sample_rates=48000:" \
           "channel_layouts=stereo"                   # from the take's own start: a late or early sound stays in sync
SOUND_OUT = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
BT709 = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"   # ffmpeg 8 tags from the frames
DIFFS = (("channels", "the takes differ in sound channels"),        # a stream copy keeps the first take's sound setup,
         ("streams", "the takes store picture and sound in a different order"),     # matches streams by position
         ("vconfig", "the takes were encoded with different video settings"),       # and decodes every take with
         ("aconfig", "the takes were encoded with different sound settings"))       # the first take's decoder setup


# ------------------------------------------------------------------ reading a take
def _seconds(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _ratio(r):
    try:
        x = float(Fraction(str(r)))
    except (ValueError, ZeroDivisionError):
        return None
    return x if x > 0 else None


def nominal_fps(avg, base):
    """a take's frame rate by its standard name. A phone's timestamps wander (an iPhone's 30 fps takes read 30/1 or
    359/12 as their base rate and 29.999 or 29.916 on average), so a standard base rate is kept while the average
    agrees with it, else the average is rounded to whole frames per second"""
    x, b = _ratio(avg), _ratio(base)
    if base in STANDARD_FPS and (not x or 2 / 3 < x / b < 3 / 2):
        return base
    if x:
        n = round(x)
        if n and abs(x - n) < 0.02 * x:
            return f"{n}/1"
        f = Fraction(x).limit_denominator(1001)
        return f"{f.numerator}/{f.denominator}"
    return f"{FPS}/1"


def _utc(text):
    try:
        d = datetime.fromisoformat(str(text).strip())
    except ValueError:
        return None
    d = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d.year >= 1980 else None


def recorded(fmt_tags, video_tags):
    """when a take was shot, as UTC (2026-10-13T19:02:11Z), or None. An iPhone's capture time
    (com.apple.quicktime.creationdate) comes first: its creation_time is when the file was written, so an AirDrop or
    an export restamps it. Then the container's creation_time, then the video stream's. A clock never set (1904,
    1970) is no time."""
    for t in (fmt_tags.get("com.apple.quicktime.creationdate"), fmt_tags.get("creation_time"),
              video_tags.get("creation_time")):
        s = _utc(t) if t else None
        if s:
            return s
    return None


def _rotation(v):
    """the degrees a take is turned for display (a phone often stores a portrait take sideways with this flag)"""
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            return int(round(float(sd["rotation"]))) % 360
    try:
        return int(round(float((v.get("tags") or {}).get("rotate", 0)))) % 360
    except ValueError:
        return 0


def probe(path):
    """one file -> what intake needs to know about it, or None when it isn't a video ffprobe can read (notes, a still,
    a sound file, a song with cover art). The last five keys serve the stream copy only: start for copy_args, the
    other four for plan_join."""
    path = os.path.abspath(os.path.expanduser(path))
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                        "-show_data_hash", "md5", path], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout) if r.returncode == 0 else {}
    except ValueError:
        j = {}
    fmt, streams = j.get("format") or {}, j.get("streams") or []
    kind = fmt.get("format_name", "")
    pictures = [s for s in streams
                if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    duration = _seconds(fmt.get("duration")) or (_seconds(pictures[0].get("duration")) if pictures else None)
    if not pictures or not duration or kind in STILLS or kind.endswith("_pipe"):
        return None
    v = pictures[0]
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    transfer = v.get("color_transfer") or ""
    return dict(path=path, name=os.path.basename(path), duration=duration, width=int(v["width"]),
                height=int(v["height"]), rotation=_rotation(v),
                fps=nominal_fps(v.get("avg_frame_rate"), v.get("r_frame_rate")), vcodec=v.get("codec_name"),
                pix_fmt=v.get("pix_fmt"), transfer=transfer, hdr=transfer in HDR_TRANSFERS, has_audio=a is not None,
                acodec=a.get("codec_name") if a else None,
                sample_rate=int(a["sample_rate"]) if a and a.get("sample_rate") else None,
                recorded=recorded(fmt.get("tags") or {}, v.get("tags") or {}),
                start=_seconds(fmt.get("start_time")) or 0.0, channels=a.get("channels") if a else None,
                streams=f"v{v.get('index')}a{a.get('index') if a else '-'}", vconfig=v.get("extradata_hash"),
                aconfig=a.get("extradata_hash") if a else None)


# ------------------------------------------------------------------ deciding
def order(infos):
    """by when each take was recorded (recorded(): the capture time, else creation_time), then by name; takes with
    no time go last"""
    return sorted(infos, key=lambda d: (d["recorded"] is None, d["recorded"] or "", d["name"]))


def shape(d):
    """(width, height) as displayed: a 90 or 270 degree rotation swaps them"""
    return (d["height"], d["width"]) if d["rotation"] % 180 else (d["width"], d["height"])


def plan_join(infos):
    """how the takes become one source: single (one take, used as it is), copy (the picture by stream copy) or encode
    (once, to the most common shape and frame rate), with every reason for an encode in why"""
    size = Counter(shape(d) for d in infos).most_common(1)[0][0]
    fps = Counter(d["fps"] for d in infos).most_common(1)[0][0]
    hdr = any(d["hdr"] for d in infos)
    why = []
    if hdr:
        why.append("shot with HDR on: converted to standard range (the shoot guide says HDR off)")
    if not any(d["has_audio"] for d in infos):
        why.append("no sound in " + ("the take" if len(infos) == 1 else "any take") + ": a silent track is added")
    if len(infos) == 1:
        return dict(mode="encode" if why else "single", size=size, fps=fps, hdr=hdr, why=why)
    for k in ("vcodec", "pix_fmt", "fps", "rotation", "acodec", "sample_rate", "has_audio"):
        if len({d[k] for d in infos}) > 1:
            why.append(f"the takes differ in {k}")
    for k, what in DIFFS:
        if len({d.get(k) for d in infos}) > 1:
            why.append(what)
    if len({shape(d) for d in infos}) > 1:
        why.append("the takes differ in size or orientation: each fits the most common shape")
    return dict(mode="encode" if why else "copy", size=size, fps=fps, hdr=hdr, why=why)


def recommend_mode(infos):
    w, h = shape(infos[0])
    if max(w, h) >= 3840:
        return "hifi", "4K: usually a camera on a tripod or desk (hi-fi); say lo-fi if it was handheld"
    return "lofi", "1080p or a phone shape: usually a selfie in hand (lo-fi); say hi-fi if it sat on a tripod"


def frames(d, plan):
    """a take's length in whole frames at the plan's rate (an encode makes each take exactly this long)"""
    return max(1, round(d["duration"] * _ratio(plan["fps"])))


def layout(infos, plan):
    """where each take sits in the source: [(start, duration)] in seconds. A copy puts each take right after the
    last at its container length (as ffmpeg's concat does); an encode makes each one whole frames"""
    if plan["mode"] == "encode":
        rate, n = _ratio(plan["fps"]), [frames(d, plan) for d in infos]
        return [(sum(n[:k]) / rate, n[k] / rate) for k in range(len(n))]
    out, t = [], 0.0
    for d in infos:
        out.append((t, d["duration"]))
        t += d["duration"]
    return out


def raw_names(infos):
    """each take's name in raw/: its own, numbered when two share one (as macOS sees names: case aside); joined.mov
    stays free for the join"""
    used, out = {JOINED.lower()}, []
    for d in infos:
        stem, ext = os.path.splitext(d["name"])
        name, k = d["name"], 2
        while name.lower() in used:
            name, k = f"{stem}-{k}{ext}", k + 1
        used.add(name.lower())
        out.append(name)
    return out


# ------------------------------------------------------------------ making the source
def clone(src, dst):
    """src -> dst as a copy-on-write clone where the disk can make one (APFS, Btrfs, XFS: instant, no extra space),
    else a plain copy; written next to dst, then renamed"""
    tmp = dst + ".part"
    cmd = ["cp", "-c", src, tmp] if sys.platform == "darwin" else ["cp", "--reflink=auto", src, tmp]
    if subprocess.run(cmd, capture_output=True).returncode:
        shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


@lru_cache(maxsize=None)
def filters():
    """the filters this ffmpeg has"""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return frozenset(p[1] for p in (ln.split() for ln in out.splitlines()) if len(p) > 2 and "->" in p[2])


def hdr_chains(have):
    """the HDR to standard range (BT.709) conversions this ffmpeg can run, best first: [(name, filter chain, note)].
    The note goes into the plan's why when that one is used: only the last resort has one."""
    out = []
    if {"zscale", "tonemap"} <= set(have):
        out.append(("zscale", "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
                              "zscale=t=bt709:m=bt709:r=tv,format=yuv420p", None))
    if "libplacebo" in have:
        out.append(("libplacebo", "libplacebo=tonemapping=auto:colorspace=bt709:color_primaries=bt709:"
                                  "color_trc=bt709:range=tv:format=yuv420p", None))
    if "colorspace" in have:
        out.append(("colorspace", "colorspace=all=bt709:iall=bt2020:itrc=bt2020-10:format=yuv420p:dither=fsb",
                    "this ffmpeg has no tone mapper (zscale or libplacebo): a plain colorspace conversion, so bright "
                    "parts may clip and colors look flat"))
    return out


def _quote(path):
    return "'" + path.replace("'", "'\\''") + "'"


def copy_args(infos, listing):
    """every ffmpeg argument but the output for the copy join. The picture: ffmpeg's concat demuxer, stream copy
    (-copyts, or the first take's sound priming delays the whole picture). The sound: each take decoded on its own,
    so its encoder delay is dropped, which a stream copy can't do (an iPhone take's sound would land 44 ms later at
    every join), then joined sample-exact at the same offsets as the picture"""
    args, fc = ["-copyts", "-f", "concat", "-safe", "0", "-i", listing], []
    for k, d in enumerate(infos):
        if d.get("start"):
            args += ["-itsoffset", f"{-d['start']:.6f}"]          # -copyts: each take's own clock from 0, by hand
        args += ["-vn", "-i", d["path"]]
        fc.append(f"[{k + 1}:a:0]{SOUND_IN},apad,atrim=end={d['duration']:.6f}[a{k}]")
    fc.append("".join(f"[a{k}]" for k in range(len(infos))) + f"concat=n={len(infos)}:v=0:a=1[a]")
    return args + ["-filter_complex", ";".join(fc), "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", *SOUND_OUT]


def encode_args(infos, plan, chain=None):
    """every ffmpeg argument but the output for the encode join: each take fitted to plan size (black bars), at
    plan fps from its own first frame, exactly frames() long, HDR takes through chain first; sound at 48 kHz stereo,
    a silent track for a take with none, as long as its picture; H.264 crf 14 + AAC 320k, tagged BT.709"""
    (W, H), rate = plan["size"], plan["fps"]
    args, fc = [], []
    for i, d in enumerate(infos):
        n = frames(d, plan)
        secs = n / _ratio(rate)
        args += ["-i", d["path"]]
        fc.append(f"[{i}:v:0]" + (chain + "," if d["hdr"] and chain else "")
                  + f"scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                  f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={rate}:start_time=0,format=yuv420p,"
                  f"tpad=stop_mode=clone:stop_duration={secs:.6f},trim=end_frame={n}[v{i}]")
        sound = f"[{i}:a:0]{SOUND_IN}" if d["has_audio"] else \
            "anullsrc=channel_layout=stereo:sample_rate=48000,aformat=sample_fmts=fltp"
        fc.append(f"{sound},apad,atrim=end={secs:.6f}[a{i}]")
    fc.append("".join(f"[v{i}][a{i}]" for i in range(len(infos))) + f"concat=n={len(infos)}:v=1:a=1[vc][a]")
    fc.append(f"[vc]{BT709}[v]")
    return args + ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "14",
                   "-preset", "medium", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                   "-colorspace", "bt709", "-color_range", "tv", *SOUND_OUT]


def _ffmpeg(args, out):
    """ffmpeg into a temporary file next to out, then renamed: a failed run never leaves half a source"""
    tmp = out + ".part"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-f", "mov", tmp], capture_output=True, text=True)
    if r.returncode == 0:
        os.replace(tmp, out)
    elif os.path.exists(tmp):
        os.remove(tmp)
    return r


def join(infos, plan, out):
    """the takes (in order) -> one source at out, as plan says: single clones the one take; copy joins the picture by
    stream copy and the sound sample-exact (copy_args); encode re-encodes once (encode_args), an HDR one with the
    best conversion this ffmpeg has. A copy ffmpeg refuses becomes an encode; plan["mode"] and plan["why"] then say
    so, and the conversion's note joins why"""
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if plan["mode"] == "single":
        clone(infos[0]["path"], out)
        return plan
    if plan["mode"] == "copy":
        with tempfile.TemporaryDirectory(prefix="intake-") as d:
            listing = os.path.join(d, "takes.txt")
            with open(listing, "w") as fh:
                fh.write("".join(f"file {_quote(t['path'])}\n" for t in infos))
            r = _ffmpeg(copy_args(infos, listing), out)
        if r.returncode == 0:
            return plan
        plan["mode"] = "encode"
        said = (r.stderr.strip().splitlines() or ["?"])[-1]
        plan["why"].append(f"the takes could not be joined by stream copy ({said}): re-encoded")
    chains = [(None, None, None)]
    if plan["hdr"]:
        chains = hdr_chains(filters()) or [("none", None, "this ffmpeg can't convert HDR: colors will look washed out")]
    for k, (_, chain, note) in enumerate(chains):
        r = _ffmpeg(encode_args(infos, plan, chain), out)
        if r.returncode == 0:
            if note:
                plan["why"].append(note)
            return plan
        if k == len(chains) - 1:
            sys.exit(f"ffmpeg could not join the takes:\n{r.stderr[-1500:]}")


def poster(source, at, out):
    """the frame of source at `at` seconds -> out, a JPEG at most 640 px a side (at the take's start if `at` has no
    frame)"""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".part.jpg"
    for t in (at, 0.0):
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", source, "-frames:v", "1", "-vf",
                            "scale=w='min(640,iw)':h='min(640,ih)':force_original_aspect_ratio=decrease", "-q:v", "4",
                            tmp], capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp):
            os.replace(tmp, out)
            return
    sys.exit(f"could not take a poster frame from {source} at {at:.2f} s:\n{r.stderr[-800:]}")


# ------------------------------------------------------------------ the project
def gather(paths):
    """the files to look at: each file given, and the files in each folder given (in name order, not its subfolders,
    hidden files skipped). Returns (files, ignored names)"""
    files, ignored, seen = [], [], set()

    def add(p):
        key = os.path.realpath(p)
        if key not in seen:
            seen.add(key)
            files.append(p)

    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isdir(p):
            for n in sorted(os.listdir(p)):
                q = os.path.join(p, n)
                if n.startswith("."):
                    continue
                if os.path.isdir(q):
                    ignored.append(n + "/")
                else:
                    add(q)
        elif os.path.isfile(p):
            add(p)
        else:
            sys.exit(f"not found: {p}")
    return files, ignored


def keep_whole(project, total):
    """KEEP in the new edit.py = the whole source, so the first transcript (SKILL.md step 2) can start right away"""
    path = os.path.join(project, "edit.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text, n = re.subn(r"(?m)^KEEP = \[\]", f"KEEP = [(0.000, {math.floor(total * 1000) / 1000:.3f})]   # the whole "
                      "source, for the first transcript: set the ranges to keep from it", text, count=1)
    if not n:
        print("NOTE: KEEP in edit.py isn't the starter's empty list, so it was left as it is")
        return False
    with open(path + ".part", "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(path + ".part", path)
    return True


def jobs(project, py):
    """what intake starts in the background: the first transcript and the scan for cuts already in the source"""
    pipe = os.path.join(KIT, "pipeline")
    return [("words", [py, os.path.join(pipe, "words.py"), project]),
            ("source-cuts", [py, os.path.join(pipe, "cut.py"), project, "--source-cuts"])]


BACKGROUND = []                                  # the processes start() began (for a caller that wants to wait)


def start(project, todo):
    """each (name, command) on its own in the background, still running after intake returns, logging to
    <project>/work/<name>.log. Returns {name: log path}"""
    work = os.path.join(project, "work")
    os.makedirs(work, exist_ok=True)
    logs = {}
    for name, cmd in todo:
        logs[name] = os.path.join(work, f"{name}.log")
        with open(logs[name], "w") as fh:
            BACKGROUND.append(subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                               cwd=project, start_new_session=True))
    return logs


def tc(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    opts = {"--title": None, "--mode": None}
    for flag in opts:
        if flag in a:
            i = a.index(flag)
            if i + 1 >= len(a):
                sys.exit(f"{flag} needs a value\n\n{__doc__}")
            opts[flag] = a[i + 1]
            del a[i:i + 2]
    background = "--no-start" not in a
    a = [x for x in a if x != "--no-start"]
    if any(x.startswith("--") for x in a) or len(a) < 2:
        sys.exit(__doc__)
    slug, paths, mode = a[0], a[1:], opts["--mode"]
    if not SLUG.fullmatch(slug) or ".." in slug:
        sys.exit(f"'{slug}' can't name a project folder: use letters, numbers, - and _ (like my-first-reel)")
    if mode is not None and mode not in MODES:
        sys.exit(f"--mode {mode}: the modes are {', '.join(MODES)}")
    title = opts["--title"] or re.sub(r"[-_]+", " ", slug).strip().title() or slug
    project = os.path.join(HOME, "projects", slug)
    if os.path.exists(os.path.join(project, "edit.py")):
        sys.exit(f"{project} is already a project (it has edit.py): give these takes a new slug")

    files, ignored = gather(paths)
    takes = []
    for f in files:
        d = probe(f)
        if d:
            takes.append(d)
        else:
            ignored.append(os.path.basename(f))
    if not takes:
        sys.exit("no video to take in" + (f" (not a video: {', '.join(ignored)})" if ignored else "")
                 + ": a take is a video file ffmpeg can read")
    takes = order(takes)

    t0 = time.time()
    raw = os.path.join(project, "raw")
    os.makedirs(raw, exist_ok=True)
    names = raw_names(takes)
    local = []
    for d, name in zip(takes, names):
        clone(d["path"], os.path.join(raw, name))
        local.append(dict(d, path=os.path.join(raw, name)))
    plan = plan_join(local)
    if plan["mode"] == "single":
        source = local[0]["path"]
    else:
        source = os.path.join(raw, JOINED)
        how = "the picture by stream copy" if plan["mode"] == "copy" else "re-encoded once"
        print(f"joining {len(local)} takes into raw/{JOINED} ({how}) ...", flush=True)
        join(local, plan, source)
    spans = layout(local, plan)
    total = spans[-1][0] + spans[-1][1]
    got = probe(source)
    if not got or abs(got["duration"] - total) > len(spans) / _ratio(plan["fps"]) + 1e-3:
        sys.exit(f"{source} came out {got['duration'] if got else 0:.3f} s long, but its takes add up to {total:.3f} s "
                 "(one frame per take is allowed): the takes' starts would be wrong, so intake stops here")

    rows = []
    for k, (d, name, (s, n)) in enumerate(zip(local, names, spans), 1):
        rel = f"approvals/start/posters/{k:02d}.jpg"
        poster(source, s + n / 2, os.path.join(project, rel))          # mid-take: past the walk-in to the camera
        rows.append(dict(name=d["name"], file=f"raw/{name}", start=round(s, 3), duration=round(n, 3),
                         recorded=d["recorded"], size=list(shape(d)), hdr=d["hdr"], poster=rel))
    rec, rec_why = recommend_mode(local)
    C.write_json(os.path.join(project, "intake.json"), {
        "version": 1, "slug": slug, "title": title, "source": os.path.relpath(source, project),
        "plan": dict(plan, size=list(plan["size"])), "recommended": {"mode": rec, "why": rec_why},
        "takes": rows, "ignored": ignored})

    use = mode or rec
    py = PY if os.path.exists(PY) else sys.executable
    new = [py, os.path.join(KIT, "pipeline", "new.py"), slug, source, title, "--mode", use]
    r = subprocess.run(new, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{r.stdout}{r.stderr}\nnew.py stopped (above). The takes and intake.json are in {project}: fix "
                 f"that, then run it again:\n  {' '.join(new)}")
    keep_whole(project, got["duration"])
    logs = start(project, jobs(project, py)) if background else {}

    print(f"{slug}: {len(local)} take{'s' if len(local) > 1 else ''}, {tc(total)} in all, in the order they were "
          "recorded:")
    for k, t in enumerate(rows, 1):
        print(f"  {k:02d}  {t['name']:<28} {tc(t['duration']):>7}  starts {tc(t['start']):>7}"
              f"  recorded {t['recorded'] or 'unknown'}")
    how = {"single": f"the source is the take itself (raw/{names[0]})",
           "copy": f"joined into raw/{JOINED}: the picture by stream copy, the sound joined sample-exact",
           "encode": f"re-encoded into {os.path.relpath(source, project)}, because:"}[plan["mode"]]
    print(how + "".join(f"\n  - {w}" for w in plan["why"]))
    if ignored:
        print(f"ignored (not a video): {', '.join(ignored)}")
    print(f"recommended mode: {rec} ({rec_why})")
    print(f"project: {project}  (edit.py in {use}{', as asked' if mode else ''}; {time.time() - t0:.1f} s)")
    if logs:
        print("started in the background: the first transcript (" + os.path.relpath(logs["words"], project)
              + ") and the scan for cuts already in the source (" + os.path.relpath(logs["source-cuts"], project) + ")")
    else:
        print(f"not started (--no-start): {py} {os.path.join(KIT, 'pipeline', 'words.py')} {project}  and  "
              f"{py} {os.path.join(KIT, 'pipeline', 'cut.py')} {project} --source-cuts")
    print(f"next: {py} {os.path.join(KIT, 'pipeline', 'preview.py')} {project} start")


if __name__ == "__main__":
    main()
