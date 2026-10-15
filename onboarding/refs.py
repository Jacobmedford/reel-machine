#!/usr/bin/env python3
"""Inspiration analyzer: the 2-3 reels a creator loves, turned into evidence for writing their style pack.

Onboarding step for a creator with no brand guide. Each reel is measured (pacing, speech, sound, motion, colour)
and drawn as contact sheets, because type, caption treatment and layout can only be judged by looking. The agent
reads summary.md, then the images, then writes style.json + STYLE.md (schema: pipeline/style.py, kit/TOKENS.md).

Run:  .venv/bin/python onboarding/refs.py <out_dir> <url-or-file> [<url-or-file> ...]

Per reel N (input order), in <out_dir>/ref<N>/:
  source.mp4                  the reel: downloaded with yt-dlp (best mp4 up to 1080p) or a link/copy of your file
  sheet-<k>.jpg               contact sheet pages: a frame every second, 6 per row, time burned in (agents read these)
  captions-<k>.jpg            the caption zone (y 45-85% of the frame) every 0.5 s, larger, so the type reads
  sheet.jpg, captions.jpg     the same frames as one tall image each, for a person to scroll
  metrics.json                size, cuts, shot length, speech pace and pauses, loudness, music bed, motion, palette
  words.json, transcript.txt  what is said, with word timings (faster-whisper "small")
plus <out_dir>/summary.md: the reels side by side, every image path, and what to look for in the images.

Needs ffmpeg and ffprobe on PATH, and the kit's .venv (numpy, scipy, pillow, faster-whisper, yt-dlp).
Instagram usually wants a login for downloads: when a link fails, save the reel to your computer and pass the file.
"""
import argparse
import collections
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.cluster.vq import kmeans2
from scipy.ndimage import median_filter

# ---------------------------------------------------------------- knobs
MAX_SECONDS = 180          # analyse at most the first 3 minutes of an input (reels are shorter; keeps runs bounded)
SCENE_CUT = 0.3            # ffmpeg scene score at or above which a frame starts a new shot (hard cut)
MERGE_CUTS = 0.2           # cuts closer than this (flash frames, two-frame transitions) count once

# Jump cuts (same framing, the speaker jumps) barely move ffmpeg's scene score, and neither do caption changes, so
# a second detector looks for the moment many small grid cells change at once against their own recent history.
GREY_SHORT_SIDE = 72       # the grey analysis stream: short side in px
CELL = 4                   # grid cell size in that stream (px)
DUP_LEVEL = 0.35           # mean grey change below which a frame is a repeat (pulldown, frame-rate conversion)
SPIKE_WINDOW = 6           # frames either side that make a cell's baseline
SPIKE_CELL_MIN = 6.0       # a cell spikes when its change is >= this many grey levels ...
SPIKE_CELL_REL = 3.0       # ... and >= this many times its baseline
SPIKE_FRAC = 0.18          # a jump/pop when at least this share of all cells spike in the same frame ...
SPIKE_ALONE = 1.5          # ... and at least this many times the share in the frames either side (a gesture builds up)
SPIKE_GAP = 0.3            # at most one jump/pop per this many seconds

MOTION_FPS = 15            # motion energy compares frames ~1/15 s apart, whatever the frame rate
MOTION_CALM, MOTION_BUSY = 2.5, 5.0   # mean grey change (0-255) per 1/15 s: below calm, above busy

THUMB_W, SHEET_COLS = 270, 6           # contact sheet: one frame a second, 6 per row, 270 px wide each
CAP_TOP, CAP_SPAN = 0.45, 0.40         # caption sheet: the band y 45%-85% of the frame ...
CAP_W, CAP_COLS = 480, 3               # ... every 0.5 s, 480 px wide, 3 per row
PAGE_MAX_H = 1500                      # a page an agent can read without it being shrunk to mush
GUTTER, HEADER_H = 6, 30

WHISPER_MODEL = "small"
GAP_MIN, GAP_TRIM = 0.35, 0.12         # music bed: pauses >= GAP_MIN s, trimmed at both ends, are "gaps"
BED_YES, BED_NO = -20.0, -30.0         # gap level minus speech level (dB): above -> a bed, below -> none, between faint
FLOOR_YES, FLOOR_NO = -22.0, -28.0     # tight edits without pauses: the quietest 5% of the talking, minus speech level
BED_NOTE = "level only: loud outdoor or crowd ambience reads as a bed too; the sheet shows where it was filmed"

DL_FORMAT_SORT = ["res:1080", "vcodec:h264", "ext:mp4:m4a"]   # best up to 1080p (short side), h264, mp4


class Skip(Exception):
    """this input can't be used; the message is the one line the user sees"""


def say(msg):
    print(msg, flush=True)


def fmt_t(t, half=False):
    """seconds -> m:ss (or m:ss.s for half-second labels)"""
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}" if half else f"{int(m)}:{int(s):02d}"


# ---------------------------------------------------------------- inputs: links are downloaded, files are linked
def looks_like_url(s):
    return bool(re.match(r"^[a-z][a-z0-9+.-]*://", s, re.I) or re.match(r"^(www\.)?[\w-]+(\.[\w-]+)+/\S", s))


class _YtdlpLog:
    """keep yt-dlp quiet; remember its errors so the user gets one clear line instead"""
    def __init__(self):
        self.errors = []

    def debug(self, msg):
        pass

    info = warning = debug

    def error(self, msg):
        self.errors.append(msg)


def download(url, ref):
    """url -> ref/source.mp4 with yt-dlp. Raises Skip with the line to show when it can't."""
    import yt_dlp
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = "https://" + url
    log = _YtdlpLog()
    opts = {
        "format": "bv*+ba/b", "format_sort": DL_FORMAT_SORT, "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "outtmpl": os.path.join(ref, "source.%(ext)s"), "noplaylist": True, "playlist_items": "1",
        "overwrites": True, "quiet": True, "no_warnings": True, "noprogress": True, "logger": log,
        "socket_timeout": 30, "retries": 2,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:                                           # DownloadError, network, extractor bugs
        reason = (log.errors[-1] if log.errors else str(e)).replace("ERROR: ", "")
        reason = re.sub(r"^\[[^\]]+\]\s*([\w-]+:\s*)?", "", reason).strip()
        if re.search(r"log ?in|logged|cookies|sign in|private|rate.?limit|authenticat", reason, re.I):
            site = "Instagram" if "instagram." in url else "this site"
            reason = f"{site} wants a login"
        raise Skip(f"couldn't download {url} ({reason[:110]}). Save the reel to your computer "
                   f"(any downloader or a screen recording works) and pass the file path instead.")
    if info and info.get("entries"):                               # a post with several videos: the first one
        info = next((e for e in info["entries"] if e), info)
    path = os.path.join(ref, "source.mp4")
    if not os.path.exists(path):
        got = [f for f in os.listdir(ref) if f.startswith("source.") and not f.endswith((".json", ".part"))]
        if not got:
            raise Skip(f"couldn't download {url} (no video file came back). Save the reel to your computer and "
                       f"pass the file path instead.")
        path = os.path.join(ref, got[0])
    info = info or {}
    return path, {"title": info.get("title"), "uploader": info.get("uploader") or info.get("channel"),
                  "url": info.get("webpage_url") or url}


def link_file(path, ref):
    """a local file -> ref/source<ext>: a hard link when the disk allows (no copy, survives the original moving)"""
    dst = os.path.join(ref, "source" + (os.path.splitext(path)[1].lower() or ".mp4"))
    if os.path.exists(dst) and os.path.samefile(path, dst):
        return dst
    if os.path.lexists(dst):
        os.remove(dst)
    try:
        os.link(path, dst)
    except OSError:                                                  # another disk, or links not allowed
        shutil.copy2(path, dst)
    return dst


def resolve(item, ref, n):
    """one command-line input -> (local video path, source info). Re-runs reuse what is already there."""
    os.makedirs(ref, exist_ok=True)
    stamp = os.path.join(ref, "source.json")
    old = json.load(open(stamp)) if os.path.exists(stamp) else {}
    local = os.path.expanduser(item)
    if (old.get("input") == item and old.get("kind") == "url" and old.get("file")
            and os.path.exists(os.path.join(ref, old["file"]))):
        return os.path.join(ref, old["file"]), old                    # downloaded on an earlier run
    if old.get("input") != item:                                      # a different reel now: clear the old one
        for f in os.listdir(ref):
            if f.startswith("source.") or f in ("words.json", "transcript.txt", "metrics.json"):
                os.remove(os.path.join(ref, f))
    if os.path.isfile(local):
        path, meta = link_file(os.path.abspath(local), ref), {"title": os.path.basename(local)}
        kind = "file"
    elif looks_like_url(item):
        say(f"ref{n}: downloading {item}")
        path, meta = download(item, ref)
        kind = "url"
    else:
        raise Skip(f"no such file: {item}")
    meta = {"input": item, "kind": kind, "file": os.path.basename(path), **meta}
    json.dump(meta, open(stamp, "w"), indent=1)
    return path, meta


# ---------------------------------------------------------------- probe
def _rate(r):
    try:
        a, b = (r or "0/0").split("/")
        return float(a) / float(b) if float(b) else None
    except ValueError:
        return None


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True)
    if r.returncode:
        raise Skip(f"ffprobe can't read {os.path.basename(path)} ({(r.stderr.strip().splitlines() or ['?'])[-1]})")
    data = json.loads(r.stdout)
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")), None)
    if v is None:
        raise Skip(f"{os.path.basename(path)} has no video in it")
    w, h = int(v["width"]), int(v["height"])
    rot = int(float((v.get("tags") or {}).get("rotate", 0) or 0))
    for sd in v.get("side_data_list") or []:
        rot = int(sd.get("rotation", rot) or rot)
    if abs(rot) % 180 == 90:                                         # phone files: ffmpeg rotates frames on decode
        w, h = h, w
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    if dur <= 0:
        raise Skip(f"{os.path.basename(path)} has no duration (is it a still image?)")
    fps = _rate(v.get("avg_frame_rate")) or _rate(v.get("r_frame_rate")) or 30.0
    return {"duration_s": round(dur, 3), "width": w, "height": h, "fps": round(fps, 3),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


# ---------------------------------------------------------------- picture: one decode, four branches
def scan_video(src, V, limit, work):
    """Decode once and split four ways:
      scene   ffmpeg scene score per frame -> hard cuts
      grey    a tiny grey stream piped to numpy -> jump cuts / pops and motion energy
      thumbs  a frame every second (contact sheet)
      caps    the caption band every 0.5 s (caption sheet)"""
    src = os.path.abspath(src)                                        # ffmpeg runs inside the work folder
    w, h = V["width"], V["height"]
    s = GREY_SHORT_SIDE
    gw, gh = (s, 2 * round(s * h / w / 2)) if h >= w else (2 * round(s * w / h / 2), s)
    gfps = V["fps"] if V["fps"] <= 31 else 30.0                     # 60 fps sources are halved; VFR made constant
    graph = (f"[0:v:0]split=4[a][b][c][d];"
             f"[a]scale={THUMB_W}:-2,select='eq(n,0)+gte(scene,{SCENE_CUT})',metadata=print:file=scenes.txt[sc];"
             f"[b]fps={gfps},scale={gw}:{gh}:flags=area,format=gray[g];"
             f"[c]fps=1,scale={THUMB_W}:-2[th];"
             f"[d]fps=2,crop=iw:ih*{CAP_SPAN}:0:ih*{CAP_TOP},scale={CAP_W}:-2[cp]")
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-t", f"{limit:.3f}", "-i", src,
           "-filter_complex", graph,
           "-map", "[sc]", "-f", "null", "-",
           "-map", "[g]", "-f", "rawvideo", "pipe:1",
           "-map", "[th]", "-q:v", "2", "th_%05d.jpg",
           "-map", "[cp]", "-q:v", "2", "cp_%05d.jpg"]
    with open(os.path.join(work, "ffmpeg.log"), "w+") as err:
        proc = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=err)
        grey = read_grey(proc.stdout, gw, gh, gfps)
        if proc.wait():
            err.seek(0)
            last = (err.read().strip().splitlines() or ["?"])[-1]
            raise Skip(f"ffmpeg couldn't decode {os.path.basename(src)} ({last})")

    cuts = []
    scenes = os.path.join(work, "scenes.txt")
    if os.path.exists(scenes):
        # frame 0 always passes (an ffmpeg output that gets no frames at all is an error); every later frame is a cut
        stamps = [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", open(scenes).read())][1:]
        for t in stamps:
            if not (cuts and t - cuts[-1] < MERGE_CUTS):
                cuts.append(round(t, 3))
    thumbs = sorted(f for f in os.listdir(work) if f.startswith("th_"))
    caps = sorted(f for f in os.listdir(work) if f.startswith("cp_"))
    thumbs = [(i * 1.0, os.path.join(work, f)) for i, f in enumerate(thumbs) if i * 1.0 < limit]
    caps = [(i * 0.5, os.path.join(work, f)) for i, f in enumerate(caps) if i * 0.5 < limit]
    return cuts, grey, thumbs, caps


def read_grey(pipe, gw, gh, gfps):
    """Stream the grey frames, keeping only small arrays: the per-cell change between distinct frames (for jumps and
    pops) and the change across ~1/15 s (motion energy)."""
    size = gw * gh
    ch, cw = gh // CELL, gw // CELL
    step = max(1, round(gfps / MOTION_FPS))
    ring = collections.deque(maxlen=step + 1)
    prev, cells, cell_t, energy = None, [], [], []
    i = 0
    while True:
        buf = pipe.read(size)
        if len(buf) < size:
            break
        f = np.frombuffer(buf, np.uint8).reshape(gh, gw).astype(np.float32)
        t = i / gfps
        ring.append(f)
        if len(ring) == step + 1:
            energy.append((t, float(np.abs(f - ring[0]).mean())))
        if prev is None:
            prev = f
        else:
            d = np.abs(f - prev)
            if d.mean() >= DUP_LEVEL:                                # a repeated frame is not a change
                cells.append(d[:ch * CELL, :cw * CELL].reshape(ch, CELL, cw, CELL).mean(axis=(1, 3)).ravel())
                cell_t.append(t)
                prev = f
        i += 1
    return {"cells": np.array(cells), "cell_t": np.array(cell_t), "energy": energy, "step_s": step / gfps}


def jumps_and_pops(grey, cuts):
    """Frames where >= SPIKE_FRAC of a 4 px grid changes at once, each cell measured against its own change over the
    frames either side, and clearly more than the frames next to it. Catches same-framing jump cuts (which ffmpeg's
    scene score misses) and also on-screen pops (a big word or graphic landing in one frame); the two can't be told
    apart from pixels alone. Camera stutter (a frozen frame, then a catch-up) in raw or old footage counts too."""
    D, T = grey["cells"], grey["cell_t"]
    if len(D) < 2 * SPIKE_WINDOW + 1:
        return []
    fp = np.ones((2 * SPIKE_WINDOW + 1, 1), bool)
    fp[SPIKE_WINDOW] = False                                         # the baseline excludes the frame itself
    base = median_filter(D, footprint=fp, mode="nearest")
    frac = (D >= np.maximum(SPIKE_CELL_MIN, SPIKE_CELL_REL * base)).mean(axis=1)
    beside = np.maximum(np.r_[0.0, frac[:-1]], np.r_[frac[1:], 0.0])
    ok = (frac >= SPIKE_FRAC) & (frac >= SPIKE_ALONE * beside)
    picked = []
    for i in np.argsort(-frac):
        if ok[i] and all(abs(T[i] - T[j]) > SPIKE_GAP for j in picked):
            picked.append(i)
    return [round(float(T[i]), 3) for i in sorted(picked) if all(abs(T[i] - c) > MERGE_CUTS for c in cuts)]


def pacing(cuts, extra, dur):
    bounds = [0.0] + cuts + [dur]
    shots = [b - a for a, b in zip(bounds, bounds[1:]) if b - a > 0]
    per_min = lambda n: round(n / dur * 60, 1) if dur else None       # noqa: E731
    return ({"threshold": SCENE_CUT, "count": len(cuts), "per_min": per_min(len(cuts)),
             "avg_shot_s": round(float(np.mean(shots)), 2), "median_shot_s": round(float(np.median(shots)), 2),
             "longest_shot_s": round(max(shots), 2), "first_cut_s": cuts[0] if cuts else None, "times": cuts},
            {"count": len(extra), "per_min": per_min(len(extra)), "times": extra,
             "note": "same-framing jump cuts or one-frame on-screen pops; check the sheet at these times"})


def motion(grey, cuts, dur):
    """mean grey change across ~1/15 s, frames that straddle a hard cut left out (cuts are counted already)"""
    span = grey["step_s"] + 0.04
    vals = [(t, v) for t, v in grey["energy"] if not any(t - span < c <= t + 0.04 for c in cuts)]
    if not vals:
        return {"energy": None, "label": "unknown"}
    e = float(np.mean([v for _, v in vals]))
    secs = collections.defaultdict(list)
    for t, v in vals:
        secs[int(t)].append(v)
    label = "calm" if e < MOTION_CALM else "busy" if e > MOTION_BUSY else "medium"
    return {"energy": round(e, 2), "label": label, "p90": round(float(np.percentile([v for _, v in vals], 90)), 2),
            "scale": f"calm < {MOTION_CALM} <= medium <= {MOTION_BUSY} < busy",
            "per_second": [round(float(np.mean(secs[s])), 1) if secs.get(s) else 0.0 for s in range(int(dur) + 1)]}


# ---------------------------------------------------------------- colour
def _lab(rgb):
    """sRGB 0-255 -> CIELAB (D65), so clusters follow what the eye sees"""
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def _clusters(rgb, k, total):
    """k-means in Lab -> [(hex, share of total, lab centre)], near-duplicates (dE < 8) folded together"""
    lab = _lab(rgb)
    k = max(1, min(k, len(rgb) // 20))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                               # empty clusters are fine here
        try:
            _, labels = kmeans2(lab, k, minit="++", rng=7, iter=25)  # SciPy >= 1.15
        except TypeError:
            _, labels = kmeans2(lab, k, minit="++", seed=7, iter=25)
    out = []
    for j in np.argsort(-np.bincount(labels, minlength=k)):
        m = labels == j
        if not m.any():
            continue
        centre, share = lab[m].mean(0), m.sum() / total
        rgb_mean = rgb[m].mean(0)
        for o in out:
            if np.linalg.norm(o[2] - centre) < 8:
                o[1] += share
                break
        else:
            out.append(["#%02X%02X%02X" % tuple(int(round(x)) for x in rgb_mean), share, centre])
    return sorted(out, key=lambda o: -o[1])


def palette(thumbs):
    """Rough palette from the 1 fps frames. Skin (YCbCr box + hue) is left out so the face doesn't swamp it;
    accents are the saturated colours, clustered on their own so a small highlight colour still shows up."""
    px = []
    for _, p in thumbs:
        im = Image.open(p).convert("RGB")
        px.append(np.asarray(im.resize((54, max(1, round(54 * im.height / im.width))), Image.BOX)).reshape(-1, 3))
    if not px:
        return {}
    rgb = np.concatenate(px).astype(np.float32)
    y = 0.299 * rgb[:, 0] + 0.587 * rgb[:, 1] + 0.114 * rgb[:, 2]
    cb = 128 - 0.168736 * rgb[:, 0] - 0.331264 * rgb[:, 1] + 0.5 * rgb[:, 2]
    cr = 128 + 0.5 * rgb[:, 0] - 0.418688 * rgb[:, 1] - 0.081312 * rgb[:, 2]
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    hue = 60 * (g - b) / (r - np.minimum(g, b) + 1e-6)              # hue in degrees where red is the top channel
    skin = ((y > 40) & (cb >= 77) & (cb <= 127) & (cr >= 133) & (cr <= 173)    # the classic YCbCr skin box ...
            & (r >= g) & (r >= b) & (hue >= -20) & (hue <= 35))                 # ... minus golds and ochres (40-50)
    rest = rgb[~skin]
    if len(rest) < 50:
        return {"skin_share": round(float(skin.mean()), 3), "colors": [], "accents": []}
    rng = np.random.default_rng(7)
    sample = rest[rng.choice(len(rest), min(len(rest), 40000), replace=False)]
    main = _clusters(sample, 8, len(sample))[:6]
    lab = _lab(sample)
    sat = sample[np.hypot(lab[:, 1], lab[:, 2]) >= 35]
    accents = []
    if len(sat) >= 0.002 * len(sample):
        main_labs = [m[2] for m in main]
        for hx, share, c in _clusters(sat, 4, len(sample)):
            if share >= 0.002 and all(np.linalg.norm(c - m) >= 12 for m in main_labs):
                accents.append({"hex": hx, "share": round(float(share), 3)})
    return {"skin_share": round(float(skin.mean()), 3),
            "colors": [{"hex": hx, "share": round(float(s), 3)} for hx, s, _ in main],
            "accents": accents[:3],
            "note": "shares are of the non-skin pixels; accents are saturated colours too small for the top 6"}


# ---------------------------------------------------------------- sound
def audio_pcm(src, limit):
    """mono 16 kHz float32 samples (what whisper wants; enough for levels too)"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-t", f"{limit:.3f}", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "s16le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0 if r.returncode == 0 else None


def loudness(src, limit):
    """EBU R128: integrated loudness, loudness range, true peak"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-t", f"{limit:.3f}", "-i", src, "-vn",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    tail = r.stderr.rsplit("Summary:", 1)[-1]
    def get(pat):
        m = re.search(pat, tail)
        v = float(m.group(1)) if m else None
        return v if v is not None and np.isfinite(v) else None
    return {"integrated_lufs": get(r"I:\s+(-?[\d.]+) LUFS"), "range_lu": get(r"LRA:\s+(-?[\d.]+) LU"),
            "true_peak_dbfs": get(r"Peak:\s+(-?[\d.inf]+) dBFS")}


class Whisper:
    """faster-whisper, loaded once for every reel in the run"""
    model = None

    @classmethod
    def get(cls):
        if cls.model is None:
            from faster_whisper import WhisperModel
            kw = dict(device="cpu", compute_type="int8", cpu_threads=min(8, os.cpu_count() or 4))
            try:
                cls.model = WhisperModel(WHISPER_MODEL, local_files_only=True, **kw)
            except Exception:
                say(f"  downloading the speech model ({WHISPER_MODEL}, about 500 MB, first run only)")
                cls.model = WhisperModel(WHISPER_MODEL, **kw)
        return cls.model


def transcribe(pcm):
    segs, info = Whisper.get().transcribe(pcm, word_timestamps=True, vad_filter=True,
                                          condition_on_previous_text=False)
    words, lines = [], []
    for s in segs:
        lines.append(s.text.strip())
        for w in s.words or []:
            if w.word.strip():
                words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
    return {"language": info.language, "language_probability": round(info.language_probability, 2),
            "words": words, "lines": lines}


def speech_stats(W, dur):
    words = W["words"]
    if not words:
        return {"language": None, "words": 0, "wpm": None, "note": W.get("error") or "no speech found"}
    a, b = words[0]["start"], words[-1]["end"]
    gaps = [(n["start"] - p["end"], p["end"]) for p, n in zip(words, words[1:])]
    longest = max(gaps, default=(0.0, None))
    hook = []
    for w in words:                                                   # the first sentence, or the first ~4 s
        if (w["start"] > a + 4.0 and len(hook) >= 4) or len(hook) >= 20:
            break
        hook.append(w["text"])
        if w["text"][-1:] in ".?!" and len(hook) >= 3:
            break
    return {"language": W["language"], "words": len(words), "speech_span_s": [a, b],
            "wpm": round(len(words) / max(b - a, 1e-3) * 60), "talk_share": round((b - a) / dur, 2),
            "longest_pause_s": round(max(longest[0], 0.0), 2), "longest_pause_at_s": longest[1],
            "pauses_over_0_5s": sum(1 for g, _ in gaps if g >= 0.5), "hook": " ".join(hook)}


def music_bed(pcm, words, dur):
    """A bed keeps the quiet moments loud. Compare the median level in the pauses between words with the median
    level while words are spoken: clean voice sits 30+ dB over its pauses, voice over a bed within ~20 dB.
    A tight edit has no pauses to listen to; then the quietest 5% of the talking stands in (the breaths and the
    gaps between syllables: near silence for a clean voice, the bed's level under a bed)."""
    if pcm is None or len(pcm) < 1600:
        return {"music_bed": "unknown", "note": "no audio"}
    sr, hop, win = 16000, 320, 640                                   # 20 ms hops, 40 ms windows
    n = 1 + max(0, (len(pcm) - win) // hop)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    level = 20 * np.log10(np.sqrt(np.mean(pcm[idx] ** 2, axis=1) + 1e-12) + 1e-9)
    t = (np.arange(n) * hop + win / 2) / sr
    if not words:
        overall = round(float(np.median(level)), 1)
        return {"music_bed": "music only" if overall > -40 else "silent", "overall_rms_db": overall,
                "note": "no speech, so nothing to compare"}
    talk = np.zeros(n, bool)
    for w in words:
        talk |= (t >= w["start"]) & (t <= w["end"])
    gap = np.zeros(n, bool)
    for p, q in zip(words, words[1:]):
        if q["start"] - p["end"] >= GAP_MIN:
            gap |= (t >= p["end"] + GAP_TRIM) & (t <= q["start"] - GAP_TRIM)
    gap &= ~talk
    speech = float(np.median(level[talk]))
    secs = round(gap.sum() * hop / sr, 1)
    out = {"speech_rms_db": round(speech, 1), "gap_seconds": secs}
    if secs >= 1.0:
        diff = round(float(np.median(level[gap])) - speech, 1)
        verdict = "yes" if diff >= BED_YES else "no" if diff <= BED_NO else "faint"
        return {"music_bed": verdict, "method": "pauses", "gap_vs_speech_db": diff, **out,
                "scale": f"pause level minus speech level: >= {BED_YES:g} dB a bed, <= {BED_NO:g} dB none",
                "note": BED_NOTE}
    span = (t >= words[0]["start"]) & (t <= words[-1]["end"])
    if span.sum() * hop / sr < 3.0:
        return {"music_bed": "unknown", **out, "note": "too little speech to judge"}
    diff = round(float(np.percentile(level[span], 5)) - speech, 1)
    verdict = "yes" if diff >= FLOOR_YES else "no" if diff <= FLOOR_NO else "faint"
    return {"music_bed": verdict, "method": "floor (tight edit, few pauses)", "gap_vs_speech_db": diff, **out,
            "scale": f"quietest 5% of the talking minus speech level: >= {FLOOR_YES:g} dB a bed, "
                     f"<= {FLOOR_NO:g} dB none", "note": BED_NOTE}


# ---------------------------------------------------------------- contact sheets
def _font(size):
    try:
        return ImageFont.load_default(size=size)                      # Pillow >= 10.1: a scalable built-in face
    except TypeError:
        return ImageFont.load_default()


def tile(frames, cols, title, half=False, rows=None):
    """[(t, jpg)] -> [(page, first t, last t)]: a grid, `rows` per page (None: everything on one tall image).
    Each tile carries its time; each page a header saying what it is."""
    if not frames:
        return []
    first = Image.open(frames[0][1])
    tw, th = first.size
    per_page = cols * rows if rows else len(frames)
    chunks = [frames[i:i + per_page] for i in range(0, len(frames), per_page)]
    if (rows and len(chunks) > 1 and len(chunks[-1]) <= cols         # a last row on its own joins the page before,
            and HEADER_H + (rows + 1) * (th + GUTTER) + GUTTER <= 1.25 * PAGE_MAX_H):   # if that page stays readable
        last = chunks.pop()
        chunks[-1] = chunks[-1] + last
    f_label, f_head = _font(15 if tw < 400 else 18), _font(17)
    pages = []
    for p, chunk in enumerate(chunks, 1):
        r = -(-len(chunk) // cols)
        size = (cols * tw + (cols + 1) * GUTTER, HEADER_H + r * th + (r + 1) * GUTTER)
        page = Image.new("RGB", size, (20, 20, 20))
        d = ImageDraw.Draw(page)
        span = f"{fmt_t(chunk[0][0], half)}-{fmt_t(chunk[-1][0], half)}"
        d.text((GUTTER + 2, 7), f"{title}  |  page {p}/{len(chunks)}  |  {span}" if rows else f"{title}  |  {span}",
               font=f_head, fill=(200, 200, 200))
        for i, (t, path) in enumerate(chunk):
            x = GUTTER + (i % cols) * (tw + GUTTER)
            y = HEADER_H + GUTTER + (i // cols) * (th + GUTTER)
            page.paste(Image.open(path).convert("RGB").resize((tw, th)), (x, y))
            label = fmt_t(t, half)
            l, tp, rr, b = d.textbbox((0, 0), label, font=f_label)
            d.rectangle([x, y, x + rr - l + 8, y + b - tp + 8], fill=(0, 0, 0))
            d.text((x + 4 - l, y + 4 - tp), label, font=f_label, fill=(255, 255, 255))
        pages.append((page, chunk[0][0], chunk[-1][0]))
    return pages


def write_sheets(ref, n, thumbs, caps):
    for f in os.listdir(ref):                                         # pages from an earlier run of a longer reel
        if re.match(r"(sheet|captions)(-\d+)?\.jpg$", f):
            os.remove(os.path.join(ref, f))
    out = {}
    for key, frames, cols, half, what in (("sheet", thumbs, SHEET_COLS, False, "every 1 s"),
                                          ("captions", caps, CAP_COLS, True, "caption zone y 45-85%, every 0.5 s")):
        if not frames:
            continue
        th = Image.open(frames[0][1]).size[1]
        rows = max(1, (PAGE_MAX_H - HEADER_H) // (th + GUTTER))
        pages = []
        for p, (im, a, b) in enumerate(tile(frames, cols, f"ref{n}  {what}", half, rows), 1):
            name = f"{key}-{p}.jpg"
            im.save(os.path.join(ref, name), quality=88)
            pages.append({"file": name, "from_s": a, "to_s": b})
        full = tile(frames, cols, f"ref{n}  {what}", half)[0][0]
        if full.size[1] <= 60000:                                     # JPEG's limit is 65535 px
            full.save(os.path.join(ref, f"{key}.jpg"), quality=85)
        out[key] = {"full": f"{key}.jpg" if full.size[1] <= 60000 else None, "pages": pages}
    return out


# ---------------------------------------------------------------- one reel
def analyse(n, src, meta, ref, pool):
    t0 = time.time()
    V = probe(src)
    limit = min(V["duration_s"], MAX_SECONDS)
    say(f"ref{n}: {meta.get('title') or meta['file']}  ({V['width']}x{V['height']}, {V['fps']:g} fps, "
        f"{V['duration_s']:.1f}s)")
    if V["duration_s"] > MAX_SECONDS:
        say(f"  long video: only the first {fmt_t(MAX_SECONDS)} is analysed")
    pcm_job = pool.submit(audio_pcm, src, limit) if V["has_audio"] else None
    lufs_job = pool.submit(loudness, src, limit) if V["has_audio"] else None

    with tempfile.TemporaryDirectory(prefix="refs-") as work:
        cuts, grey, thumbs, caps = scan_video(src, V, limit, work)
        extra = jumps_and_pops(grey, cuts)
        cut_m, extra_m = pacing(cuts, extra, limit)
        motion_m = motion(grey, cuts, limit)
        colour = palette(thumbs)
        images = write_sheets(ref, n, thumbs, caps)

    pcm = pcm_job.result() if pcm_job else None
    words_path = os.path.join(ref, "words.json")
    sig = [os.path.getsize(src), int(os.path.getmtime(src)), limit, WHISPER_MODEL]
    W = json.load(open(words_path)) if os.path.exists(words_path) else {}
    if W.get("source_sig") != sig:                                    # transcribe once; re-runs reuse it
        W = {"language": None, "language_probability": None, "words": [], "lines": []}
        if pcm is not None and len(pcm) and float(np.abs(pcm).max()) > 1e-4:
            try:
                W = transcribe(pcm)
                W["source_sig"] = sig
            except Exception as e:                                    # no model and no network, say
                say(f"  speech skipped: {type(e).__name__}: {str(e)[:120]}")
                W["error"] = f"speech model unavailable ({type(e).__name__})"
        else:
            W["source_sig"] = sig                                     # silent or no audio: nothing to redo
        json.dump(W, open(words_path, "w"), indent=1)
        with open(os.path.join(ref, "transcript.txt"), "w") as fh:
            fh.write("\n".join(W["lines"]) + "\n")
    audio_m = {**(lufs_job.result() if lufs_job else {}), **music_bed(pcm, W["words"], limit)}

    M = {"ref": n, "source": meta, "video": {**V, "analysed_s": round(limit, 3)},
         "cuts": cut_m, "jumps_or_pops": extra_m, "speech": speech_stats(W, limit), "audio": audio_m,
         "motion": motion_m, "palette": colour, "images": images, "runtime_s": round(time.time() - t0, 1)}
    json.dump(M, open(os.path.join(ref, "metrics.json"), "w"), indent=1)
    sp = M["speech"]
    say(f"  {cut_m['count']} cuts ({cut_m['per_min']}/min, median shot {cut_m['median_shot_s']}s), "
        f"{extra_m['count']} jumps/pops, {sp.get('wpm') or '-'} wpm, music bed {audio_m.get('music_bed', '-')}, "
        f"{audio_m.get('integrated_lufs', '-')} LUFS, motion {motion_m['label']}  [{M['runtime_s']}s]")
    return M


# ---------------------------------------------------------------- summary.md
CHECKLIST = """\
## What to look for in the images

Read every sheet page first (the whole reel, one frame a second), then the caption pages: at least the first two of
each reel (the hook and the first lines), and more wherever the sheet shows the captions changing. `sheet.jpg` and
`captions.jpg` hold the same frames as one tall image each: a person can scroll them, but an image viewer shrinks
them until the type is unreadable, so read the pages. To see one moment at full size:
`ffmpeg -ss <seconds> -i <ref>/source.mp4 -frames:v 1 frame.png`.

- **Caption font**: serif, sans, or display (condensed, rounded, slab, script, handwritten). Weight (regular, bold,
  black). Italic or not. Does a second face appear for emphasis (a serif italic word inside sans captions)?
- **Caption case**: UPPERCASE, lowercase, or Sentence case.
- **Caption treatment**: a box behind the text (colour, opacity, corner radius), plain text with a shadow, or an
  outline/stroke.
- **Caption rhythm**: word-by-word (one word at a time, or the current word highlighted in colour, in a box, or
  scaled up) or a phrase at once. Words per caption, lines per caption.
- **Caption position**: centre, lower third, or top. Does it move or stay put?
- **Emphasis**: which words get colour, size, a different font, a strike, an emoji.
- **Text boxes**: Instagram-style native text boxes (hook, CTA), titles at the top, a header that stays on screen.
- **Overlays**: screenshots, UI, stickers, arrows, logos, picture-in-picture, words behind the speaker's head.
- **Camera**: zooms and punch-ins (the framing jumps between neighbouring frames), slow push-ins, black and white
  moments, flashes, transitions.
- **B-roll vs talking head**: roughly what share of frames show the speaker. `palette.skin_share` gives a rough hint.
- **Colours**: the grade (warm, cool, contrasty, flat), the caption box and highlight colours, card and text box
  grounds. The palette hexes are starting points; trust what you see in the frames.

## Mapping to style.json
- fonts.caption / fonts.text / fonts.display: the caption font, the text box font, the emphasis face (closest
  Google Fonts family).
- captions.hifi.box / captions.lofi.box, captions.hifi.uppercase: box or no box, case. captions.*.y: where they sit
  (1920 px tall frame: 45% = 864, 64% = 1236, 69% = 1318).
- colors.caption_box / caption_ink / caption_dim: the box, its text, and the not-yet-spoken words (word-by-word).
  colors.accent: the highlight colour. colors.textbox_bg / textbox_ink: the native text box.
- motion: "punchy" for busy motion, frequent cuts or hard zooms; "calm" for calm motion and long shots.
- sound.music: a bed in most references means yes (unless the sheet shows street or crowd footage, where the
  "bed" may be ambience). sound.sfx is not measured: light, normal, or dense by feel (normal if unsure).
- grade: the CSS filter closest to the look (warm, cool, contrasty, or "none").

## Mapping to modes (how each mode edits for this creator; every field in kit/STYLE_PACK.md)
Decide all three modes from the same evidence, so hi-fi, lo-fi and showcase all feel like the same creator.
- Caption rhythm -> modes.lofi.captions: "word-by-word" (current word lights up), "phrase" (the line lands at once),
  "single" (one word on screen at a time); words per caption -> max_words / max_chars. modes.hifi.captions:
  "phrases" (2-4 words), "words" (one at a time) or "lines" (a full sentence).
- The opening text -> modes.hifi.hook: "two-line" (a plain line over a big display line), "one-line" (one big
  line), "none" (the first caption carries it).
- Camera -> modes.hifi.camera: "settle" (a small settle on every cut, slow pushes), "zooms" (hard punch-ins on key
  phrases), "still" (no camera moves). modes.lofi.zooms: true when punch-ins show up.
- Black and white moments -> modes.*.bw. Native text boxes -> modes.lofi.text_boxes. Screenshots or UI on top of
  the speaker -> modes.lofi.overlays; things behind the head -> modes.lofi.backdrops / modes.hifi.behind_head
  ("often", "sometimes", "never"). Full-screen graphics -> modes.hifi.cards.
- Transitions (whips, zooms, spins, pushes) -> modes.showcase.transitions, only the ones you see (all of them is the
  default); how one big word is treated (stamped letter by letter, slammed in, scaled up) -> modes.showcase.
  emphasis_word; how busy -> modes.showcase.density.
- How the cuts sound: audio that changes exactly with the picture -> j_lead 0.0-0.1; the next voice arriving a
  beat before its picture (J-cuts) -> 0.3.
"""


def write_summary(out, results):
    ok = [r for r in results if "metrics" in r]
    L = ["# Inspiration reels", "",
         f"{len(ok)} of {len(results)} reels analysed. Every number comes from `ref<N>/metrics.json`; the images are "
         f"where type, captions and layout are judged.", ""]
    if ok:
        L += ["| reel | length | cuts/min | shot avg / median | jumps+pops/min | wpm | longest pause | music bed "
              "| loudness | motion |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in ok:
            M = r["metrics"]
            c, j, s, a, m, v = M["cuts"], M["jumps_or_pops"], M["speech"], M["audio"], M["motion"], M["video"]
            bed = a.get("music_bed", "-") + (f" ({a['gap_vs_speech_db']:+.0f} dB)" if "gap_vs_speech_db" in a else "")
            lufs = f"{a['integrated_lufs']:.1f} LUFS" if a.get("integrated_lufs") is not None else "-"
            L.append(f"| ref{M['ref']} | {v['analysed_s']:.0f}s | {c['per_min']} | {c['avg_shot_s']} / "
                     f"{c['median_shot_s']}s | {j['per_min']} | {s.get('wpm') or '-'} | "
                     f"{str(s['longest_pause_s']) + 's' if s.get('longest_pause_s') is not None else '-'} | {bed} | "
                     f"{lufs} | {m['label']} ({m['energy']}) |")
        L += ["", f"cuts: ffmpeg scene score >= {SCENE_CUT} (hard cuts, framing changes, cards). jumps+pops: "
                  "same-framing jump cuts ffmpeg misses, or one-frame on-screen pops; tell them apart in the sheet. "
                  f"motion: mean picture change per 1/{MOTION_FPS} s (calm < {MOTION_CALM} <= medium <= {MOTION_BUSY} "
                  f"< busy). music bed: level in the pauses against level while talking (bed >= {BED_YES:g} dB, "
                  f"none <= {BED_NO:g} dB; a tight edit without pauses uses the quietest 5% of the talking). It "
                  f"hears level, not music: loud outdoor or crowd ambience also reads as a bed.", ""]
    for r in results:
        title = (r.get("metrics") or {}).get("source", {}).get("title")
        L.append(f"## ref{r['n']}" + (f": {title}" if title else ""))
        if "metrics" not in r:
            L += [f"Not analysed: {r['error']}", ""]
            continue
        M = r["metrics"]
        src, v, s, pal, im = M["source"], M["video"], M["speech"], M["palette"], M["images"]
        ref = os.path.join(out, f"ref{r['n']}")
        who = f" by {src['uploader']}" if src.get("uploader") else ""
        L.append(f"- source: {src['input']}{who}")
        L.append(f"- video: {v['width']}x{v['height']}, {v['fps']:g} fps, {v['duration_s']:.1f}s"
                 + (f" (first {v['analysed_s']:.0f}s analysed)" if v["analysed_s"] < v["duration_s"] else ""))
        if s.get("words"):
            L.append(f"- speech: {s['words']} words, language {s['language']}, hook: \"{s['hook']}\"")
        if pal.get("colors"):
            L.append("- palette: " + ", ".join(f"{c['hex']} {c['share']:.0%}" for c in pal["colors"])
                     + ("; accents: " + ", ".join(f"{c['hex']} {c['share']:.1%}" for c in pal["accents"])
                        if pal.get("accents") else "") + f"; skin {pal['skin_share']:.0%} of pixels")
        L.append(f"- images, in {ref}{os.sep}")
        for key, what in (("sheet", "sheet pages, a frame every 1 s"), ("captions", "caption pages, every 0.5 s")):
            if key in im:
                half = key == "captions"
                L.append(f"  - {what}: " + ", ".join(
                    f"{p['file']} ({fmt_t(p['from_s'], half)}-{fmt_t(p['to_s'], half)})" for p in im[key]["pages"]))
        if im.get("sheet", {}).get("full"):
            L.append(f"  - the whole reel on one image: {im['sheet']['full']} (rhythm at a glance, too small for type)")
        L.append("- data, same folder: metrics.json, words.json, transcript.txt")
        L.append("")
    L.append(CHECKLIST)
    path = os.path.join(out, "summary.md")
    with open(path, "w") as fh:
        fh.write("\n".join(L))
    return path


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Measure 2-3 inspiration reels and draw contact sheets for the agent "
                                             "that writes the style pack.")
    ap.add_argument("out_dir", help="where ref1/, ref2/ ... and summary.md go")
    ap.add_argument("inputs", nargs="+", help="reel links (Instagram, TikTok, YouTube ...) or video files")
    args = ap.parse_args()
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        sys.exit(f"needs {' and '.join(missing)} on PATH (macOS: brew install ffmpeg; Linux: apt install ffmpeg)")
    out = os.path.abspath(os.path.expanduser(args.out_dir))
    os.makedirs(out, exist_ok=True)

    results, todo = [], []
    for n, item in enumerate(args.inputs, 1):                        # fetch everything first: failures show early
        ref = os.path.join(out, f"ref{n}")
        try:
            src, meta = resolve(item, ref, n)
            todo.append((n, src, meta, ref))
            results.append({"n": n})
        except Skip as e:
            say(f"ref{n}: {e}")
            results.append({"n": n, "error": str(e)})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for n, src, meta, ref in todo:
            r = results[n - 1]
            try:
                r["metrics"] = analyse(n, src, meta, ref, pool)
            except Skip as e:
                say(f"ref{n}: {e}")
                r["error"] = str(e)
            except Exception as e:                                    # a file nothing above expected
                say(f"ref{n}: analysis failed ({type(e).__name__}: {str(e)[:160]})")
                r["error"] = f"analysis failed ({type(e).__name__}: {e})"

    path = write_summary(out, results)
    done = sum(1 for r in results if "metrics" in r)
    say(f"summary: {path}")
    if not done:
        sys.exit(1)


if __name__ == "__main__":
    main()
