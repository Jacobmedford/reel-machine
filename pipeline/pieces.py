#!/usr/bin/env python3
"""Pieces: render a reel in beat-aligned pieces of about 5 seconds (the hook first), each cached under a hash of
everything that can change its pixels, so a note re-renders only the pieces it touches. Pieces are picture only:
they are joined with a stream copy and the one master.wav is laid over the whole picture, exactly as render.py does.
The note loop runs it through `render.py <project> <name> --pieces`: the plain render's gates around it (build, lint,
the seam checks, the animation check inside every piece not checked yet, QA, delivery), then a prune of this cache.

How a piece is rendered: pieces/driver.mjs freezes the built composition with the HyperFrames producer's own
distributed protocol (plan), then renders each dirty piece as a seek window over that one frozen composition
(renderChunk), so composition times are never rebased. Frames come out as lossless PNG and are encoded here with the
same x264 settings as `hyperframes render -q delivery`, plus one fixed GOP length so every piece carries the same
SPS/PPS and the join is a plain concat copy.

Work dir: <project>/work/render-pieces/: cache/<key>.mp4 + .json (the meta: window, frames, timings, the producer's
worker count, and "animcheck": "pass" once render.py checked the piece), the frozen plan (plan-<digest>/, about
1.5 GB), rejected/ (pieces that failed the animation check, never reused, kept 7 days), logs. cut.py's picture pieces
are a different cache and stay in work/pieces/.

Run: PY pipeline/pieces.py <project> plan                       the piece table: window, frames, cached or dirty
     PY pipeline/pieces.py <project> render [name] [--jobs 3]   build, render dirty pieces, assemble, mux
     PY pipeline/pieces.py <project> assemble [name]            join cached pieces only -> renders/<name>.mp4
     PY pipeline/pieces.py <project> check <render> [--ref <mp4>]   seam checks (frames, pts, black, PSNR)
     PY pipeline/pieces.py <project> verify [--jobs 3]          each seam rendered continuously, compared bit for bit
     PY pipeline/pieces.py <project> prune                      old plans, set-aside pieces older than 7 days,
                                                                 PNG leftovers, unused pieces over the budget
Options: --no-build (use public/index.html as it is), --force (re-render every piece), --keep-png,
         --strict (effects that reach shared layers count as global: safe, fewer cache hits).
Budget: unused cached pieces (not in the current table) may take REEL_MACHINE_PIECES_BUDGET MiB (default 1024); prune
evicts the least recently used beyond it.
Heavy: run `render` and `verify` through HOME/bin/heavy where there is one (they render); plan, assemble, check and
prune are light.
"""
import concurrent.futures as cf
import difflib
import glob
import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HF, KIT, PY, env, load_edit, project_arg, timeline  # noqa: E402
import cache as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "pieces", "driver.mjs")
FPS = 30
# the renderer's own work dir inside a project. cut.py keeps a different cache (its picture pieces and voices) in
# work/pieces/: the two never share a folder
WORK = os.path.join("work", "render-pieces")
HF_VERSION = next(a.split("@", 1)[1] for a in HF if a.startswith("hyperframes@"))

# planner: pieces about 5.5 s, never longer than 8 s, at least 3.5 s (the hook may be shorter)
TARGET, LO, HI = 5.5, 3.5, 8.0
# what an input costs when a piece edge cuts through it (a change to it then dirties two pieces)
CROSS_COST = {"fx": 6.0, "card": 6.0, "behind": 4.0, "grade": 3.0, "bw": 3.0, "push": 2.0, "cap": 1.0}

# `-q delivery` (ENCODER_PRESETS.high in the producer: x264 slow, crf 15, no B-frames, aq 3 / 0.8, deblock 1,1, bt709
# tags) plus one fixed GOP for every piece: the SPS depends on keyint, so equal settings give equal SPS/PPS and the
# concat copy is valid. Each piece starts on its own IDR because each piece is its own encode.
GOP = 250
X264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", "-bf", "0",
        "-g", str(GOP), "-keyint_min", "25",
        "-x264-params", "aq-mode=3:aq-strength=0.8:deblock=1,1:colorprim=bt709:transfer=bt709:colormatrix=bt709:open-gop=0",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
        "-video_track_timescale", "15360"]

# edit.py names that are time lists (sliced per piece), audio or storyboard only (never in a picture key), or
# reach the picture only through clean.mp4 / timeline.json (hashed per window). Anything else is a global setting:
# a change to it dirties every piece, which is the safe side.
SLICED = {"CAPS", "BOXES", "OVERLAYS", "BEHIND", "CUT_WINDOWS", "BW", "GRADES", "CAMERA", "FX", "CARDS", "ZOOMS"}
NOT_PICTURE = {"SOUND", "CARD_SFX", "NEEDS", "GENERATED", "PROMPT", "FIXES", "SRC", "MUSIC"}
VIA_MEDIA = {"KEEP", "J_LEADS", "J_LEAD", "SHOTS", "OUT", "FRAMES", "PROJECT", "TOTAL", "AUDIO_END", "END_IN",
             "WINDOWS", "S", "PIECES"}      # PIECES: the windows are in every key


# ------------------------------------------------------------------ pure helpers (tests/test_pieces.py)
def fr(t):
    """seconds -> the frame that holds t"""
    return int(round(t * FPS))


def end_of(t, total):
    return total if t == "end" else float(t)


def hook_end(words, total, hold=0.0):
    """end of the first sentence's last word plus the hold (the hook), or the first 3 s when no word ends a
    sentence; never past the end"""
    for w in words:
        if str(w.get("text", "")).rstrip().endswith((".", "!", "?")):
            return min(float(w["end"]) + hold, total)
    return min(3.0, total)


def candidates(picture_cuts, cards, total):
    """where a piece may end: on a hard picture cut or a card edge, frame-snapped, inside (0, total)"""
    ts = set()
    for t in list(picture_cuts) + [c for card in cards for c in (card[2], card[3])]:
        t = end_of(t, total)
        if 0 < fr(t) < fr(total):
            ts.add(fr(t))
    return sorted(ts)


def cross_cost(frame, spans):
    """what a piece edge at this frame costs: every span it cuts through (start < edge < end)"""
    return sum(CROSS_COST.get(kind, 1.0) for a, b, kind in spans if fr(a) < frame < fr(b))


def plan_pieces(total, cands, spans, hook, target=TARGET, lo=LO, hi=HI):
    """beat-aligned pieces as [(start_frame, end_frame)]: the first piece ends on the first candidate at or after
    the hook end (else at the hook end itself), the rest is a shortest path over the candidates: each piece within
    [lo, hi] seconds, cost = (length - target)^2 + what each edge cuts through. When no candidate fits a stretch
    (a long take with no cut), plain frame edges split it evenly so no piece ever exceeds `hi`."""
    n = fr(total)
    if n <= 0:
        raise ValueError("empty timeline")
    H = fr(hi)
    hf = min(max(fr(hook), 1), n)
    first = next((c for c in cands if c >= hf and (c - hf) <= H), hf)
    if first >= n:
        return [(0, n)]
    nodes = [first] + sorted({c for c in cands if first < c < n}) + [n]
    best = {first: (0.0, None)}
    reached = [first]                      # reached edges, increasing
    for b in nodes[1:]:
        cand = None
        for a in reversed(reached):
            L = (b - a) / FPS
            if L > hi + 1e-9:
                break
            if L < lo - 1e-9 and b != n:   # too short (the last piece may be short)
                continue
            c = best[a][0] + (L - target) ** 2 + (0.0 if b == n else cross_cost(b, spans))
            if cand is None or c < cand[0] - 1e-12:
                cand = (c, a)
        if cand is None and b - reached[-1] > H:     # a stretch with no cut: plain frame edges, evenly spaced
            prev = reached[-1]
            k = -(-(b - prev) // H)
            for j in range(1, k):
                mid = prev + round((b - prev) * j / k)
                best[mid] = (best[reached[-1]][0] + 1000.0, reached[-1])
                reached.append(mid)
            L = (b - reached[-1]) / FPS
            cand = (best[reached[-1]][0] + (L - target) ** 2, reached[-1])
        if cand is not None:
            best[b] = cand
            reached.append(b)
    if n not in best:
        raise ValueError("no piece plan")
    edges, x = [], n
    while x is not None:
        edges.append(x)
        x = best[x][1]
    edges = [0] + sorted(edges)
    return list(zip(edges[:-1], edges[1:]))


def spans_of(E, TL, total):
    """every input with a time span (start, end, kind): what the planner tries not to cut through"""
    out = []
    for F in getattr(E, "FX", []):
        out.append((F["at"], end_of(F["end"], total), "fx"))
    for c in getattr(E, "CARDS", []):
        out.append((c[2], end_of(c[3], total), "card"))
    for B in getattr(E, "BEHIND", []):
        a, b = behind_span(B, total)
        out.append((a, b, "behind"))
    for g in getattr(E, "GRADES", []):
        out.append((g[0], end_of(g[1], total), "grade"))
    for w in getattr(E, "BW", []):
        out.append((w[0], end_of(w[1], total), "bw"))
    for p in getattr(E, "CAMERA", {}).get("pushes", []):
        out.append((p[0], end_of(p[1], total), "push"))
    for a, b, _ in cap_spans(getattr(E, "CAPS", []), total):
        out.append((a, b, "cap"))
    return out


def behind_span(B, total):
    ats = [float(B["at"])] if "at" in B else []
    ats += [float(i["at"]) for i in B.get("items", []) if "at" in i]
    a = min(ats) if ats else 0.0
    return a, end_of(B.get("end", total), total)


def cap_spans(caps, total):
    """captions as (start, end, item): an explicit end, else up to the next caption"""
    out = []
    for i, c in enumerate(caps):
        a = float(c[0])
        if len(c) > 3:
            b = end_of(c[3], total)
        else:
            b = float(caps[i + 1][0]) if i + 1 < len(caps) else total
        out.append((a, b, c))
    return out


def generic_span(item, total):
    """a lo-fi device (BOXES, OVERLAYS) of unknown shape: dict at/start..end, or a tuple whose first number is the
    start and whose last number (or "end") is the end. None when no time can be read (then it counts as global)."""
    if isinstance(item, dict):
        a = item.get("at", item.get("start", item.get("t")))
        b = item.get("end", item.get("until"))
        if a is None:
            return None
        return float(a), end_of(b, total) if b is not None else float(a) + HI
    if isinstance(item, (list, tuple)):
        nums = [x for x in item if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if not nums:
            return None
        a = float(nums[0])
        b = total if "end" in item else (float(nums[-1]) if len(nums) > 1 and nums[-1] > a else a + HI)
        return a, b
    return None


def overlaps(a, b, t0, t1):
    """a span [a, b) shows on frames fr(a) .. fr(b) - 1 (the kit turns things on at q(a) and off at q(b), 2 ms early):
    does it touch the window's frames fr(t0) .. fr(t1) - 1"""
    return fr(a) < fr(t1) and max(fr(b), fr(a) + 1) > fr(t0)


def camera_events(C, total):
    """the camera as spans: each tween from its start for its length (settle 0.32 s, punch 0.18 s, push and zoom
    as written, the opening scale for its duration). After a tween the camera is back at scale 1."""
    ev = []
    o = C.get("open", (1.04, 0.45))
    ev.append(("open", 0.0, float(o[1]), list(o)))
    for t in C.get("settles", []):
        ev.append(("settle", float(t), float(t) + 0.32, t))
    for t, s in C.get("punch", []):
        ev.append(("punch", float(t), float(t) + 0.18, [t, s]))
    for p in C.get("pushes", []):
        ev.append(("push", float(p[0]), end_of(p[1], total), list(p)))
    for z in C.get("zooms", []):
        ev.append(("zoom", float(z[0]), end_of(z[1], total), list(z)))
    return ev


def window_inputs(E, TL, words, total, t0, t1):
    """every edit input whose time span touches [t0, t1): the per-piece part of the cache key (JSON-able)"""
    inp = {}
    inp["caps"] = [list(c) for a, b, c in cap_spans(getattr(E, "CAPS", []), total) if overlaps(a, b, t0, t1)]
    for name in ("BOXES", "OVERLAYS"):
        items = []
        for it in getattr(E, name, []) or []:
            sp = generic_span(it, total)
            if sp is None or overlaps(sp[0], sp[1], t0, t1):
                items.append(jsonable(it))
        inp[name.lower()] = items
    inp["behind"] = [jsonable(B) for B in getattr(E, "BEHIND", []) if overlaps(*behind_span(B, total), t0, t1)]
    for name in ("CUT_WINDOWS", "BW", "GRADES"):
        inp[name.lower()] = [list(w) for w in getattr(E, name, []) if overlaps(float(w[0]), end_of(w[1], total), t0, t1)]
    inp["camera"] = [[k, v] for k, a, b, v in camera_events(getattr(E, "CAMERA", {}), total) if overlaps(a, b, t0, t1)]
    inp["fx"] = [jsonable(F) for F in getattr(E, "FX", []) if overlaps(F["at"], end_of(F["end"], total), t0, t1)]
    inp["cards"] = [list(c) for c in getattr(E, "CARDS", []) if overlaps(c[2], end_of(c[3], total), t0, t1)]
    inp["cuts"] = [round(t, 4) for t in TL.get("picture_cuts", []) + TL.get("reframes", []) if t0 - 0.5 <= t < t1]
    inp["words"] = [[w["start"], w["end"], w["text"]] for w in words if w["start"] < t1 + 0.5 and w["end"] > t0 - 0.5]
    return inp


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, (int, str, bool)) or x is None:
        return x
    return repr(x)


def edit_globals(E):
    """every edit.py setting that is not a time list, audio-only or carried by the media: changes dirty everything"""
    out = {}
    for k in sorted(dir(E)):
        if not k.isupper() or k.startswith("_") or k in SLICED | NOT_PICTURE | VIA_MEDIA:
            continue
        v = getattr(E, k)
        if callable(v) or isinstance(v, type):
            continue
        out[k] = jsonable(v)
    return out


# kit layers an effect can reach outside its own wrapper: the footage and its grade, the camera, the captions
SHARED = ("#root", "#foot", "#cam", "#caps", "#hook", "#end", "#v", ".g", ".cap", ".capw", ".full", ".layer")


def coupled_selectors(js):
    """the shared kit layers an effect's code names (quoted selectors). Such an effect can change frames outside
    its own window, which a window key cannot see: `plan` lists them, --strict keys them into every piece"""
    return sorted({m.group(1) for m in re.finditer(r"['\"]([#.][A-Za-z][\w-]*)(?![\w-])", js) if m.group(1) in SHARED})


def piece_key(parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def media_windows(index_html, t0, t1):
    """which media frames a window shows: every <video>/<img> clip in the built composition that is live in
    [t0, t1), as (src, media_t0, media_t1). Media clips are mapped by data-start / data-media-start, so a window
    that plays clean.mp4 from 0:00 (a picture in picture) asks for those frames, not the window's own."""
    out = []
    for m in re.finditer(r"<video\b([^>]*)>", index_html):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        if "src" not in attrs or "data-start" not in attrs:
            continue
        s = float(attrs["data-start"])
        d = float(attrs.get("data-duration", "1e9"))
        ms = float(attrs.get("data-media-start", "0"))
        a, b = max(s, t0), min(s + d, t1)
        if a < b + 1.0 / FPS:
            out.append((attrs["src"], round(ms + (a - s), 4), round(ms + (b - s), 4)))
    return sorted(set(out))


def window_digest(packets, a, b):
    """digest of a media window from its packet table [(pts_time, is_key, hash)]: from the keyframe at or before a
    (decoding a frame needs its whole GOP) through the last packet before b (+1 frame)"""
    if not packets:
        return "none"
    start = 0
    for i, (t, key, _) in enumerate(packets):
        if t > a + 1e-6:
            break
        if key:
            start = i
    h = hashlib.sha256()
    for t, key, d in packets[start:]:
        if t >= b + 1.0 / FPS:
            break
        h.update(d.encode())
    return h.hexdigest()


def dirty(pieces, have):
    """indices of pieces whose key is not in the cache"""
    return [i for i, p in enumerate(pieces) if p["key"] not in have]


# a changed line holding one of these goes through the compiler's rewriting (media tags, fonts, links): re-plan
UNSAFE_HUNK = ("<video", "<img", "<audio", "<source", "<iframe", "<link", "<script src", "src=", "@font-face", "url(")


def transplant(old_pub, new_pub, old_compiled, context=3):
    """the edit between two built compositions (public/index.html before and after), applied to the old plan's
    compiled HTML. The producer's compile copies scripts, styles and markup verbatim and only rewrites media tags
    and fonts, so a note that changes timings, constants, captions or an effect's code moves into the compiled
    HTML line for line. Each changed hunk must be found exactly once with its surrounding lines; a hunk that
    touches media or fonts, or cannot be placed, returns None (then the composition is planned from scratch)."""
    a, b = old_pub.splitlines(keepends=True), new_pub.splitlines(keepends=True)
    hunks = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    out = old_compiled
    for n, (tag, i1, i2, j1, j2) in reversed(list(enumerate(hunks))):
        old, new = "".join(a[i1:i2]), "".join(b[j1:j2])
        if any(u in old or u in new for u in UNSAFE_HUNK):
            return None
        lo = hunks[n - 1][2] if n > 0 else 0                 # context never reaches into a neighbouring hunk
        hi = hunks[n + 1][1] if n + 1 < len(hunks) else len(a)
        for k in range(context, 16):
            pre, post = "".join(a[max(lo, i1 - k):i1]), "".join(a[i2:min(hi, i2 + k)])
            found = out.count(pre + old + post)
            if found == 1:
                out = out.replace(pre + old + post, pre + new + post, 1)
                break
            if found == 0 or (i1 - k <= lo and i2 + k >= hi):
                return None
        else:
            return None
    return out


# ------------------------------------------------------------------ I/O
def sha_file(path, cache={}):
    st = os.stat(path)
    k = (path, st.st_size, st.st_mtime_ns)
    if k not in cache:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        cache[k] = h.hexdigest()
    return cache[k]


def sha_tree(paths):
    """sha256 over files (sorted, by path relative to their root) for every path or folder given"""
    h = hashlib.sha256()
    for root in paths:
        files = [root] if os.path.isfile(root) else sorted(glob.glob(os.path.join(root, "**", "*"), recursive=True))
        for f in files:
            if os.path.isfile(f) and not f.endswith((".pyc", ".DS_Store")):
                h.update(os.path.relpath(f, os.path.dirname(root)).encode())
                h.update(sha_file(f).encode())
    return h.hexdigest()


def tool_version(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0].strip()
    except Exception:
        return "unknown"


def engine_digest():
    """the renderer and encoder: pinned HyperFrames, its Chrome build, ffmpeg, this code and the x264 settings"""
    chrome = sorted(os.path.basename(p) for p in glob.glob(os.path.expanduser("~/.cache/hyperframes/chrome/*/*")))
    return {"hyperframes": HF_VERSION, "chrome": chrome, "browser_path": os.environ.get("HYPERFRAMES_BROWSER_PATH", ""),
            "ffmpeg": tool_version(["ffmpeg", "-version"]), "x264": X264, "gop": GOP, "fps": FPS, "capture": "png",
            "gpu": "software", "driver": sha_file(DRIVER),
            "encode": hashlib.sha256(inspect.getsource(encode).encode()).hexdigest()}


def kit_digest():
    files = [os.path.join(HERE, f) for f in ("build.py", "common.py", "style.py")]
    files += sorted(glob.glob(os.path.join(KIT, "kit", "*.css")) + glob.glob(os.path.join(KIT, "kit", "*.js")))
    return sha_tree([f for f in files if os.path.exists(f)])


def brand_digest(project):
    pub = os.path.join(project, "public")
    parts = [os.path.join(pub, x) for x in ("brand.css", "fonts", "vendor", "hyperframes.json")]
    parts.append(os.path.join(project, "style", "style.json"))
    return sha_tree([p for p in parts if os.path.exists(p)])


def packet_table(path, cache_dir):
    """[(pts_time, is_key, sha256 of the packet)] for a media file. The table is cached by path, size, mtime and a
    hash of the first and last MB, so a file rewritten in place (a re-shot take under the same name) is re-read"""
    st = os.stat(path)
    with open(path, "rb") as f:
        head = f.read(1 << 20)
        f.seek(max(0, st.st_size - (1 << 20)))
        tail = f.read(1 << 20)
    tag = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}".encode() + head + tail).hexdigest()[:16]
    cp = os.path.join(cache_dir, f"{tag}.json")
    if os.path.exists(cp):
        return [tuple(x) for x in json.load(open(cp))]
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_data_hash", "sha256",
                        "-show_entries", "packet=pts_time,flags,data_hash", "-of", "csv=p=0", path],
                       capture_output=True, text=True, check=True)
    rows = []
    for line in r.stdout.splitlines():
        f = line.split(",")
        if len(f) < 3 or f[0] in ("", "N/A"):
            continue
        rows.append((float(f[0]), "K" in f[1], f[2]))
    rows.sort()
    os.makedirs(cache_dir, exist_ok=True)
    json.dump(rows, open(cp, "w"))
    return rows


class Project:
    def __init__(self, project, strict=False):
        self.project = project
        self.strict = strict
        self.E = load_edit(project)
        self.TL = timeline(project)
        self.total = float(self.TL["total"])
        self.frames = fr(self.total)
        self.pub = os.path.join(project, "public")
        self.work = os.path.join(project, WORK)
        self.cache = os.path.join(self.work, "cache")
        self.plan_dir = None            # the frozen plan this run rendered from (ensure_plan), kept by prune()
        wp = os.path.join(project, "words.json")
        self.words = json.load(open(wp)) if os.path.exists(wp) else []

    def pieces(self):
        """the piece table: windows (an edit.py PIECES list of edge seconds overrides the planner) and keys"""
        if getattr(self.E, "PIECES", None):
            edges = [0] + [fr(t) for t in self.E.PIECES if 0 < fr(t) < self.frames] + [self.frames]
            wins = list(zip(edges[:-1], edges[1:]))
        else:
            cands = candidates(self.TL.get("picture_cuts", []), getattr(self.E, "CARDS", []), self.total)
            hook = hook_end(self.words, self.total, float(getattr(self.E, "HOLD", 0.0)))
            wins = plan_pieces(self.total, cands, spans_of(self.E, self.TL, self.total), hook)
        html = open(os.path.join(self.pub, "index.html"), encoding="utf-8").read()
        self.coupled = {}
        for F in getattr(self.E, "FX", []):
            js = os.path.join(self.project, "fx", F["id"], "fx.js")
            sel = coupled_selectors(open(js, encoding="utf-8").read()) if os.path.exists(js) else []
            if sel:
                self.coupled[F["id"]] = sel
        common = {"engine": engine_digest(), "kit": kit_digest(), "brand": brand_digest(self.project),
                  "globals": edit_globals(self.E), "total_frames": self.frames}
        if self.strict:            # a coupled effect counts as global: a change to it re-renders everything
            common["coupled"] = {k: sha_tree([os.path.join(self.project, "fx", k)]) for k in sorted(self.coupled)}
        common_key = piece_key(common)
        pk_dir = os.path.join(self.work, "packets")
        tables = {}
        out = []
        for i, (a, b) in enumerate(wins):
            t0, t1 = a / FPS, b / FPS
            inp = window_inputs(self.E, self.TL, self.words, self.total, t0, t1)
            files = {}
            for F in inp["fx"]:
                d = os.path.join(self.project, "fx", F["id"])
                if os.path.isdir(d):
                    files[f"fx/{F['id']}"] = sha_tree([d])
            for c in inp["cards"]:
                p = os.path.join(self.pub, c[1])
                files[c[1]] = sha_file(p) if os.path.exists(p) else "missing"
            for B in inp["behind"]:
                for src in [B.get("src")] + [it.get("src") for it in B.get("items", [])]:
                    if src and os.path.exists(os.path.join(self.pub, src)):
                        files[src] = sha_file(os.path.join(self.pub, src))
            media = {}
            for src, ma, mb in media_windows(html, t0, t1):
                p = os.path.join(self.pub, src)
                if not os.path.exists(p):
                    media[f"{src}@{ma}-{mb}"] = "missing"
                elif os.path.getsize(p) < 32 << 20:          # small media (cards, floats): the whole file
                    media[f"{src}@{ma}-{mb}"] = sha_file(p)
                else:                                         # the footage and the cutout: the frames shown
                    if p not in tables:
                        tables[p] = packet_table(p, pk_dir)
                    media[f"{src}@{ma}-{mb}"] = window_digest(tables[p], ma, mb)
            key = piece_key({"common": common_key, "window": [a, b], "inputs": inp, "files": files, "media": media})
            out.append(dict(index=i, start=a, end=b, t0=round(t0, 4), t1=round(t1, 4), key=key,
                            fx=[F["id"] for F in inp["fx"]], cards=[c[0] for c in inp["cards"]]))
        return out

    def cached(self):
        return {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(self.cache, "*.mp4"))
                if os.path.exists(p[:-4] + ".json")}


def stage(pub, dst):
    """the composition without render leftovers (snapshots, renders, preview caches): symlinks the plan copies in"""
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for e in os.listdir(pub):
        if e in ("snapshots", "renders", ".transcode-cache", ".DS_Store") or e.endswith(".mp4") and e != "clean.mp4":
            continue
        os.symlink(os.path.join(pub, e), os.path.join(dst, e))
    return dst


def stage_digest(st):
    """identity of a staged composition: every file by content, the big media (footage, cutout) by size and mtime"""
    h = hashlib.sha256()
    for f in sorted(glob.glob(os.path.join(st, "**", "*"), recursive=True)):
        if os.path.isfile(f):
            s = os.stat(f)
            h.update(os.path.relpath(f, st).encode())
            h.update(sha_file(f).encode() if s.st_size < 32 << 20 else f"{s.st_size}|{s.st_mtime_ns}".encode())
    return h.hexdigest()[:20]


def node(args, log):
    env = dict(os.environ)
    env.setdefault("PRODUCER_MAX_WORKERS", "2")       # browser pages per piece; pieces run --jobs at a time
    r = subprocess.run(["node", DRIVER] + args, capture_output=True, text=True, env=env)
    with open(log, "a") as fh:
        fh.write(r.stderr)
    res = {"ok": False, "error": f"no result line (exit {r.returncode})"}
    for line in reversed(r.stdout.strip().splitlines()):      # the producer may print its own lines on stdout
        try:
            cand = json.loads(line)
        except ValueError:
            continue
        if isinstance(cand, dict) and "cmd" in cand:
            res = cand
            break
    with open(log, "a") as fh:
        fh.write(r.stdout)
    if r.returncode or not res.get("ok"):
        raise RuntimeError(f"driver {args[0]} failed: {res.get('error')} (log {log})")
    return res


def stage_files(st):
    """what a plan was made from: every staged file by content (big media by size and mtime)"""
    out = {}
    for f in sorted(glob.glob(os.path.join(st, "**", "*"), recursive=True)):
        if os.path.isfile(f):
            s = os.stat(f)
            out[os.path.relpath(f, st)] = sha_file(f) if s.st_size < 32 << 20 else f"{s.st_size}|{s.st_mtime_ns}"
    return out


def patch_plan(old_dir, new_dir, st):
    """turn the plan of the previous composition into the plan of this one without re-planning, when the only
    change is text in index.html that `transplant` can carry: every other staged file identical, so the compiled
    project, the extracted video frames and the audio are the same. The plan is re-sealed by `slices`."""
    src = old_dir + ".source"
    if not (os.path.exists(os.path.join(src, "files.json")) and os.path.exists(os.path.join(src, "index.html"))):
        return False
    before, now = json.load(open(os.path.join(src, "files.json"))), stage_files(st)
    if {k: v for k, v in before.items() if k != "index.html"} != {k: v for k, v in now.items() if k != "index.html"}:
        return False
    comp = os.path.join(old_dir, "compiled", "index.html")
    patched = transplant(open(os.path.join(src, "index.html"), encoding="utf-8").read(),
                         open(os.path.join(st, "index.html"), encoding="utf-8").read(),
                         open(comp, encoding="utf-8").read())
    if patched is None:
        return False
    os.rename(old_dir, new_dir)
    os.rename(src, new_dir + ".source")
    with open(os.path.join(new_dir, "compiled", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(patched)
    vj = os.path.join(new_dir, "meta", "videos.json")          # informational source paths name the plan folder
    if os.path.exists(vj):
        with open(vj, encoding="utf-8") as fh:                 # read it all before opening it for writing
            text = fh.read()
        with open(vj + ".part", "w", encoding="utf-8") as fh:
            fh.write(text.replace(old_dir, new_dir))
        os.replace(vj + ".part", vj)
    save_source(new_dir, st, now)
    return True


def save_source(plan_dir, st, files=None):
    src = plan_dir + ".source"
    os.makedirs(src, exist_ok=True)
    shutil.copy(os.path.join(st, "index.html"), os.path.join(src, "index.html"))
    json.dump(files or stage_files(st), open(os.path.join(src, "files.json"), "w"), indent=0)


def ensure_plan(P, log):
    """one frozen plan per built composition: reused while the composition is unchanged, patched when a note only
    changed index.html text (seconds), planned from scratch otherwise (about a minute)"""
    st = stage(P.pub, os.path.join(P.work, "stage"))
    dg = stage_digest(st)
    plan_dir = P.plan_dir = os.path.join(P.work, f"plan-{dg}")
    if os.path.exists(os.path.join(plan_dir, "plan.json")):
        return plan_dir, 0.0, "reused"
    t = time.time()
    olds = [d for d in glob.glob(os.path.join(P.work, "plan-*")) if os.path.isdir(d) and not d.endswith(".source")]
    if len(olds) == 1 and not os.environ.get("PIECES_NO_PATCH") and patch_plan(olds[0], plan_dir, st):
        return plan_dir, time.time() - t, "patched"
    for old in glob.glob(os.path.join(P.work, "plan-*")):          # one plan on disk at a time (about 1.5 GB)
        if os.path.isdir(old):
            shutil.rmtree(old, ignore_errors=True)
    res = node(["plan", st, plan_dir, "--format", "png-sequence"], log)
    if res["totalFrames"] != P.frames:
        raise SystemExit(f"plan has {res['totalFrames']} frames, timeline.json says {P.frames}")
    save_source(plan_dir, st)
    return plan_dir, time.time() - t, "planned"


def encode(png_dir, n, out):
    files = sorted(glob.glob(os.path.join(png_dir, "*.png")))
    if len(files) != n:
        raise RuntimeError(f"{png_dir}: {len(files)} frames, expected {n}")
    first = re.search(r"(\d+)\.png$", files[0])
    pattern = re.sub(r"\d+\.png$", f"%0{len(first.group(1))}d.png", files[0])
    tmp = out + ".part.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-start_number", str(int(first.group(1))),
                    "-i", pattern, "-frames:v", str(n), *X264, "-r", str(FPS), "-an", "-movflags", "+faststart", tmp],
                   check=True)
    got = count_frames(tmp)
    if got != n:
        raise RuntimeError(f"{tmp}: encoded {got} frames, expected {n}")
    os.replace(tmp, out)
    return files


def count_frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return int(r.stdout.strip())


def render_one(P, plan_dir, slot, piece, log, keep_png=False, tries=2):
    """one dirty piece: renderChunk -> PNG frames -> x264 -> cache/<key>.mp4 (+ .json). Retried once: a dropped
    script load (net::ERR_NETWORK_CHANGED) fails the producer's correctness check, and a rerun is cheap."""
    n = piece["end"] - piece["start"]
    png = os.path.join(P.work, "png", f"p{piece['index']:02d}")
    out = os.path.join(P.cache, piece["key"] + ".mp4")
    err = None
    for attempt in range(tries):
        shutil.rmtree(png, ignore_errors=True)
        t = time.time()
        try:
            res = node(["chunk", plan_dir, str(slot), png], log)
            tc = time.time() - t
            te = time.time()
            files = encode(png, n, out)
            meta = dict(piece, frames=n, capture_s=round(tc, 2), encode_s=round(time.time() - te, 2),
                        attempts=attempt + 1, captureMode=res.get("captureMode"), workers=res.get("workers"),
                        first_png=sha_file(files[0]), last_png=sha_file(files[-1]))
            json.dump(meta, open(out[:-4] + ".json", "w"), indent=1)
            if not keep_png:
                shutil.rmtree(png, ignore_errors=True)
            return meta
        except Exception as e:      # noqa: BLE001
            err = e
            print(f"  piece {piece['index']} attempt {attempt + 1} failed: {e}", flush=True)
    raise RuntimeError(f"piece {piece['index']} failed after {tries} attempts: {err}")


def render(P, jobs=3, force=False, keep_png=False):
    t_all = time.time()
    pieces = P.pieces()
    have = set() if force else P.cached()
    todo = dirty(pieces, have)
    print(f"{len(pieces)} pieces, {len(todo)} dirty: {[pieces[i]['index'] for i in todo]}", flush=True)
    timing = {"plan_s": 0.0, "plan": None, "pieces": []}
    if todo:
        os.makedirs(P.cache, exist_ok=True)
        log = os.path.join(P.work, "driver.log")
        plan_dir, tp, how = ensure_plan(P, log)
        timing.update(plan_s=round(tp, 1), plan=how)
        slices = [dict(index=k, startFrame=pieces[i]["start"], endFrame=pieces[i]["end"]) for k, i in enumerate(todo)]
        sp = os.path.join(P.work, "slices.json")
        json.dump(slices, open(sp, "w"))
        node(["slices", plan_dir, sp], log)
        t = time.time()
        with cf.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            futs = {ex.submit(render_one, P, plan_dir, k, pieces[i], log, keep_png): i for k, i in enumerate(todo)}
            for f in cf.as_completed(futs):
                m = f.result()
                timing["pieces"].append({k: m[k] for k in ("index", "frames", "capture_s", "encode_s", "attempts")})
                print(f"  piece {m['index']:2d} [{m['t0']:6.2f}, {m['t1']:6.2f})  {m['frames']:3d} frames  capture "
                      f"{m['capture_s']:5.1f}s  encode {m['encode_s']:5.1f}s", flush=True)
        timing["pieces_wall_s"] = round(time.time() - t, 1)
    timing["render_s"] = round(time.time() - t_all, 1)
    return pieces, timing


def assemble(P, pieces, name):
    """concat copy of the cached pieces (every piece starts on an IDR with the same SPS/PPS), then master.wav over
    the picture exactly as render.py lays it"""
    t = time.time()
    missing = [p["index"] for p in pieces if not os.path.exists(os.path.join(P.cache, p["key"] + ".mp4"))]
    if missing:
        raise SystemExit(f"pieces not rendered yet: {missing} (run render)")
    os.makedirs(os.path.join(P.project, "renders"), exist_ok=True)
    lst = os.path.join(P.work, "concat.txt")
    with open(lst, "w") as fh:
        for p in pieces:
            fh.write(f"file '{os.path.join(P.cache, p['key'] + '.mp4')}'\n")
    final = os.path.join(P.project, "renders", f"{name}.mp4")
    video = final.replace(".mp4", ".video.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    "-movflags", "+faststart", video], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", os.path.join(P.pub, "master.wav"), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest",
                    "-movflags", "+faststart", final], check=True)
    os.remove(video)
    json.dump([{k: p[k] for k in ("index", "start", "end", "key")} for p in pieces],
              open(final.replace(".mp4", ".pieces.json"), "w"), indent=1)
    return final, round(time.time() - t, 1)


# ------------------------------------------------------------------ the animation check's pass, pieces set aside
def meta_of(P, key):
    """a cached piece's meta (cache/<key>.json), {} when it has none"""
    return C.read_json(os.path.join(P.cache, key + ".json"), {}) or {}


def unchecked(P, pieces):
    """the pieces of the table whose cache meta lacks the animation check's pass (render.py --pieces checks these)"""
    return [p for p in pieces if meta_of(P, p["key"]).get("animcheck") != "pass"]


def mark_checked(P, keys):
    """write "animcheck": "pass" into each piece's meta: a later render reuses the piece without checking it again"""
    for k in keys:
        meta = meta_of(P, k)
        if meta:
            meta["animcheck"] = "pass"
            C.write_json(os.path.join(P.cache, k + ".json"), meta)


def set_aside(P, key, when=None):
    """a piece that failed the animation check leaves the cache for rejected/<key>-<YYYYmmdd-HHMMSS>.{mp4,json}
    (a -2, -3 suffix when that name is taken): never reused, so the next render renders it again. The new paths"""
    rej = os.path.join(P.work, "rejected")
    os.makedirs(rej, exist_ok=True)
    stem = f"{key}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(when))}"
    base, n = stem, 1
    while any(os.path.exists(os.path.join(rej, base + ext)) for ext in (".mp4", ".json")):
        n += 1
        base = f"{stem}-{n}"
    out = []
    for ext in (".mp4", ".json"):
        src = os.path.join(P.cache, key + ext)
        if os.path.exists(src):
            os.replace(src, os.path.join(rej, base + ext))
            out.append(os.path.join(rej, base + ext))
    return out


# ------------------------------------------------------------------ prune: the regenerable leftovers
REJECTED_DAYS = 7         # a piece set aside stays this long in rejected/ (to look at), then goes
BUDGET_MIB = 1024         # what cached pieces outside the current table may take (REEL_MACHINE_PIECES_BUDGET, MiB)
STAMP = re.compile(r"-(\d{8}-\d{6})(?:-\d+)?$")


def budget():
    """bytes the cache entries outside the current piece table may take: REEL_MACHINE_PIECES_BUDGET in MiB, default 1 GiB"""
    try:
        mib = float(env("PIECES_BUDGET", BUDGET_MIB))
    except ValueError:
        mib = BUDGET_MIB
    return int(max(0.0, mib) * (1 << 20))


def du(path):
    """bytes of a file or a folder, links not followed (a link counts nothing)"""
    if os.path.islink(path):
        return 0
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    return total


def _remove(path):
    """a link (the link alone, never what it points at), a file or a folder (links inside it are removed as links)"""
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def prune(P, pieces, budget, now=None):
    """the piece renderer's regenerable leftovers, only ever inside work/render-pieces/: every frozen plan (about
    1.5 GB each, with its .source) but the one the current table was rendered from (P.plan_dir; the newest when this
    run rendered nothing), pieces set aside more than REJECTED_DAYS ago, leftover PNG frame folders, and the least
    recently used cache entries (.mp4 + .json) outside the current table once those take more than budget bytes.
    The current table's entries count as used now. Returns what went: {plans, rejected, png, evicted, freed}"""
    now = time.time() if now is None else now
    out = dict(plans=0, rejected=0, png=0, evicted=0, freed=0)
    work = os.path.abspath(P.work)
    if not os.path.isdir(work):
        return out

    def drop(path, what=None):
        out["freed"] += du(path)
        _remove(path)
        if what:
            out[what] += 1

    def planned(d):
        pj = os.path.join(d, "plan.json")
        return os.path.getmtime(pj if os.path.exists(pj) else d)

    entries = sorted(glob.glob(os.path.join(work, "plan-*")))
    plans = [d for d in entries if os.path.isdir(d) and not os.path.islink(d) and not d.endswith(".source")]
    keep = os.path.abspath(P.plan_dir) if getattr(P, "plan_dir", None) else None
    if not (keep and os.path.isdir(keep)):
        keep = max(plans, key=planned) if plans else None
    for d in entries:
        if not os.path.isdir(d) or (keep and d in (keep, keep + ".source")):
            continue                                       # a file named plan-* is not a plan
        drop(d, None if d.endswith(".source") else "plans")

    rej = os.path.join(work, "rejected")
    if os.path.isdir(rej):
        old = {}
        for f in sorted(os.listdir(rej)):
            path, stem = os.path.join(rej, f), os.path.splitext(f)[0]
            m = STAMP.search(stem)
            try:
                when = time.mktime(time.strptime(m.group(1), "%Y%m%d-%H%M%S")) if m else os.path.getmtime(path)
            except ValueError:
                when = os.path.getmtime(path)
            if now - when > REJECTED_DAYS * 86400:
                old.setdefault(stem, []).append(path)
        for paths in old.values():
            for path in paths:
                drop(path)
            out["rejected"] += 1

    png = os.path.join(work, "png")
    if os.path.isdir(png) and not os.path.islink(png):        # frame folders, and the producer's <piece>.perf.json
        for d in sorted(os.listdir(png)):
            path = os.path.join(png, d)
            drop(path, "png" if os.path.isdir(path) and not os.path.islink(path) else None)
        try:
            os.rmdir(png)
        except OSError:
            pass

    cache = os.path.abspath(P.cache)
    if os.path.isdir(cache) and (cache + os.sep).startswith(work + os.sep):
        groups, current = {}, {p["key"] for p in pieces}
        for f in os.listdir(cache):
            path = os.path.join(cache, f)
            if os.path.isfile(path) and not os.path.islink(path):
                g = groups.setdefault(f.split(".", 1)[0], dict(size=0, used=0.0, files=[]))
                st = os.stat(path)
                g["size"] += st.st_size
                g["used"] = max(g["used"], st.st_mtime)
                g["files"].append(path)
        for k in current & groups.keys():                 # in the table now: last used now (the pruning order)
            for path in groups[k]["files"]:
                os.utime(path, (now, now))
        for k in C.lru_evict([(k, g["size"], g["used"]) for k, g in groups.items()], current, budget):
            for path in groups[k]["files"]:
                drop(path)
            out["evicted"] += 1
    return out


def prune_line(out):
    """what prune() removed, in one line"""
    def n(k, one, many):
        return f"{out[k]} {one if out[k] == 1 else many}"
    return (f"prune: {n('plans', 'old plan', 'old plans')}, {n('rejected', 'set-aside piece', 'set-aside pieces')} "
            f"older than {REJECTED_DAYS} days, {n('png', 'PNG folder', 'PNG folders')}, "
            f"{n('evicted', 'cache entry', 'cache entries')} over the budget removed, {out['freed'] / 1e6:.1f} MB freed")


# ------------------------------------------------------------------ seam checks
def pts_steps(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    pts = sorted(int(x) for x in r.stdout.split() if x.strip().lstrip("-").isdigit())
    return sorted({b - a for a, b in zip(pts, pts[1:])})


def black_intervals(path):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-an", "-vf", "blackdetect=d=0.03:pix_th=0.10", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]


def psnr_frames(path, ref):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-i", ref, "-lavfi", "[0:v][1:v]psnr=stats_file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    vals = []
    for line in r.stdout.splitlines():
        m = re.search(r"psnr_avg:(inf|[\d.]+)", line)
        if m:
            vals.append(float("inf") if m.group(1) == "inf" else float(m.group(1)))
    return vals


def seam_report(seams, frames_total, expected, steps, blacks, psnr, around=3, floor=40.0):
    """pure: the seam verdicts from measured numbers"""
    rows, ok = [], frames_total == expected and len(steps) == 1
    for s in seams:
        t = s / FPS
        near_black = [b for b in blacks if b[0] - 0.2 <= t <= b[1] + 0.2]
        win = [psnr[i] for i in range(max(0, s - around), min(len(psnr), s + around))] if psnr else []
        mn = min(win) if win else None
        good = not near_black and (mn is None or mn > floor)
        ok = ok and good
        rows.append(dict(frame=s, t=round(t, 4), black=bool(near_black), psnr_min=mn, ok=good))
    return ok, rows


def check(P, render_path, ref=None, pieces_json=None):
    pj = pieces_json or render_path.replace(".mp4", ".pieces.json")
    pieces = json.load(open(pj)) if os.path.exists(pj) else P.pieces()
    seams = [p["start"] for p in pieces[1:]]
    n = count_frames(render_path)
    steps = pts_steps(render_path)
    blacks = black_intervals(render_path)
    psnr = psnr_frames(render_path, ref) if ref else []
    ok, rows = seam_report(seams, n, P.frames, steps, blacks, psnr)
    print(f"frames {n} (expected {P.frames})   pts steps {steps}   black intervals {blacks or 'none'}")
    if psnr:
        fin = [v for v in psnr if v != float("inf")]
        print(f"PSNR vs {os.path.basename(ref)}: {len(psnr)} frames, min {min(psnr):.2f} dB, mean "
              f"{(sum(fin) / len(fin)) if fin else float('inf'):.2f} dB (finite), identical frames {psnr.count(float('inf'))}")
    for r in rows:
        print(f"  seam f{r['frame']:5d} t={r['t']:7.3f}  black {'YES' if r['black'] else 'no '}  "
              f"PSNR min (3 each side) {r['psnr_min'] if r['psnr_min'] is not None else '-'}  {'ok' if r['ok'] else 'FAIL'}")
    print("SEAMS OK" if ok else "SEAMS FAIL")
    return ok, dict(frames=n, steps=steps, blacks=blacks, rows=rows,
                    psnr_min=min(psnr) if psnr else None)


def frame_psnr(png, mp4, idx):
    """PSNR of one lossless frame against frame idx (-1 = last) of an encoded piece"""
    n = count_frames(mp4)
    i = n - 1 if idx < 0 else idx
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", png, "-i", mp4, "-lavfi",
                        f"[1:v]select=eq(n\\,{i}),format=yuv420p[b];[0:v]format=yuv420p[a];[a][b]psnr=stats_file=-",
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"psnr_avg:(inf|[\d.]+)", r.stdout)
    return None if not m else (float("inf") if m.group(1) == "inf" else float(m.group(1)))


# ------------------------------------------------------------------ verify: a continuous render across every seam
def verify(P, jobs=3):
    """render the two frames around every seam as ONE continuous window (frames s-1 and s in a single session) and
    compare their PNG bytes with the cached pieces' own edge frames (stored at render time): equal means the seam
    is pixel-exact with a render that never stopped there, and that every reused piece still matches the current
    composition at its edges (a cache key that missed an input shows up here). About one browser start per seam."""
    pieces = P.pieces()
    lack = dirty(pieces, P.cached())
    if lack:
        raise SystemExit(f"pieces not rendered yet: {lack} (run render)")
    metas = [json.load(open(os.path.join(P.cache, p["key"] + ".json"))) for p in pieces]
    log = os.path.join(P.work, "driver.log")
    plan_dir, tp, how = ensure_plan(P, log)
    seams = [p["start"] for p in pieces[1:]]
    sp = os.path.join(P.work, "slices.json")
    json.dump([dict(index=k, startFrame=s - 1, endFrame=s + 1) for k, s in enumerate(seams)], open(sp, "w"))
    node(["slices", plan_dir, sp], log)
    vdir = os.path.join(P.work, "verify")

    def one(k):
        d = os.path.join(vdir, f"s{k:02d}")
        for attempt in range(2):
            shutil.rmtree(d, ignore_errors=True)
            try:
                node(["chunk", plan_dir, str(k), d], log)
                f = sorted(glob.glob(os.path.join(d, "*.png")))
                return k, sha_file(f[0]), sha_file(f[1]), f[0], f[1]
            except Exception as e:      # noqa: BLE001
                err = e
        raise RuntimeError(f"seam {k}: {err}")
    t = time.time()
    with cf.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        res = sorted(ex.map(one, range(len(seams))))
    rows, ok = [], True
    for k, h_last, h_first, png_last, png_first in res:
        a = h_last == metas[k]["last_png"]
        b = h_first == metas[k + 1]["first_png"]
        ok = ok and a and b
        row = dict(seam=seams[k], prev_last_equal=a, next_first_equal=b)
        if not a:     # how far off: the fresh frame against the cached piece's encoded frame (x264 alone is ~45-50 dB)
            row["prev_last_psnr"] = frame_psnr(png_last, os.path.join(P.cache, pieces[k]["key"] + ".mp4"), -1)
        if not b:
            row["next_first_psnr"] = frame_psnr(png_first, os.path.join(P.cache, pieces[k + 1]["key"] + ".mp4"), 0)
        rows.append(row)
        print(f"  seam f{seams[k]:5d}: frame {seams[k] - 1} {'identical' if a else 'DIFFERS'} to piece {k}'s last, "
              f"frame {seams[k]} {'identical' if b else 'DIFFERS'} to piece {k + 1}'s first"
              + "".join(f"  {x} {row[x]} dB" for x in ("prev_last_psnr", "next_first_psnr") if x in row))
    shutil.rmtree(vdir, ignore_errors=True)
    print(f"VERIFY {'OK' if ok else 'FAIL'}: {len(seams)} seams, plan {how} {tp:.1f}s, renders {time.time() - t:.1f}s")
    return ok, rows


# ------------------------------------------------------------------ CLI
def show(P, pieces):
    have = P.cached()
    if P.coupled:
        print("  effects that reach shared layers (a change can show outside their window; --strict keys them "
              "into every piece): " + ", ".join(f"{k} {' '.join(v)}" for k, v in P.coupled.items()))
    for p in pieces:
        print(f"  {p['index']:2d}  [{p['t0']:6.2f}, {p['t1']:6.2f})  {p['end'] - p['start']:3d} frames  "
              f"{'cached' if p['key'] in have else 'DIRTY '}  {p['key'][:12]}  fx {','.join(p['fx']) or '-'}"
              f"{'  cards ' + ','.join(p['cards']) if p['cards'] else ''}")


def main():
    project = project_arg()
    args = sys.argv[2:]
    cmd = args[0] if args else "plan"
    rest = [a for a in args[1:] if not a.startswith("--")]
    opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d   # noqa: E731
    name = rest[0] if rest and cmd in ("render", "assemble") else f"{os.path.basename(project)}-pieces"
    if cmd == "render" and "--no-build" not in args:
        subprocess.run([PY, os.path.join(HERE, "build.py"), project], check=True)
    P = Project(project, strict="--strict" in args)
    if cmd == "plan":
        show(P, P.pieces())
    elif cmd == "render":
        t = time.time()
        pieces, timing = render(P, jobs=int(opt("--jobs", 3)), force="--force" in args, keep_png="--keep-png" in args)
        final, ta = assemble(P, pieces, name)
        timing.update(assemble_s=ta, total_s=round(time.time() - t, 1), output=final)
        json.dump(timing, open(final.replace(".mp4", ".timing.json"), "w"), indent=1)
        print(json.dumps({k: v for k, v in timing.items() if k != "pieces"}))
    elif cmd == "assemble":
        final, ta = assemble(P, P.pieces(), name)
        print(f"wrote {final} in {ta}s")
    elif cmd == "verify":
        ok, _ = verify(P, jobs=int(opt("--jobs", 3)))
        sys.exit(0 if ok else 1)
    elif cmd == "check":
        if not rest:
            sys.exit("usage: pieces.py <project> check <render.mp4> [--ref <monolithic.mp4>]")
        ok, _ = check(P, os.path.abspath(rest[0]), ref=opt("--ref"))
        sys.exit(0 if ok else 1)
    elif cmd == "prune":
        print(prune_line(prune(P, P.pieces(), budget())))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
