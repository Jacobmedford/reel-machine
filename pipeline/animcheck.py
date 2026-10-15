#!/usr/bin/env python3
"""Animation check: refuse a render whose graphics did not animate.

A render splits the frames into contiguous runs, one per browser worker. A worker whose page lost its script (GSAP
never loaded, the composition's script stopped early) still renders its whole run, silently: the static page, every
effect layer stacked at its CSS default, no captions, no grade, no camera. On this kit's compositions that page is
9 to 13 dB PSNR away from the real one. This check catches it in seconds, before QA and delivery:

  1. probes     one moment in every worker's run (the renderer's own split, the most workers it would use), each
                where the edit has the most on screen (captions, effects, behind-head elements, boxes, the hook),
                never within 3 frames of a cut or of an element's in or out
  2. snapshots  the built composition at those moments, twice and at once: as built (the animated page) and with its
                script replaced by an empty timeline (the static page a worker without GSAP shows)
  3. verdict    the render's frames at the same moments, per 60 px tile: where the two pages differ (the animated
                area), does the render match the animated page or the static one?
  PASS when every probe that has an animated area matches the animated page. A probe where the two pages look the
  same (a calm moment) proves nothing and is skipped; when every probe is calm although the edit has something on
  screen there, the composition does not animate even in its own snapshot, and that fails too.
  A probe that matches neither is retried one frame either side (the renderer rounds a clip's frame its own way).

Pieces: a render joined from pieces (pieces.py, render.py --pieces) renders each piece on its own, and the producer
splits that piece's frames over the piece's own workers, so --pieces puts the probes inside each piece the same way
(one in every run of every split of the piece over 1 to its workers), each row named by its piece (slot p03.1).

Run: PY pipeline/animcheck.py <project> <render.mp4> [--workers N] [--keep]
     PY pipeline/animcheck.py <project> <render.mp4> --pieces [--keep]
     PY pipeline/animcheck.py --page <folder> <render.mp4> [--workers N] [--keep]
  The first checks a render of the project's composition (public/index.html), probes chosen from its edit.py;
  --pieces checks a render joined from pieces: the piece table from <render>.pieces.json, each piece's worker count
  from its cache meta (work/render-pieces/cache/<key>.json, 4 when it has none);
  --page checks a render of a composition folder of its own, such as a card (its index.html, vendor/ and files),
  one probe in the middle of every worker's run. Heavy: it takes two snapshots, so run it through HOME/bin/heavy
  where there is one (render.py calls it inside its own render). Exit 0 pass, 1 fail (the probe pictures, render |
  animated | static: <project>/work/animcheck/sheet.jpg, or <render>.animcheck.jpg with --page), 2 when it could
  not check. --workers: the most workers the render used (default: the renderer's own ceiling for this computer).
  --keep: keep the two snapshot folders.
"""
import concurrent.futures as cf
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, HF, load_edit, timeline  # noqa: E402

TILE = 60                 # px: about one caption word or one counter digit
INFORMATIVE = 12.0        # mean luma difference (0-255) of a tile where the animated and the static page differ
MIN_TILES = 4             # a probe with less animated area than this is a calm moment: it proves nothing
ANIMATED = 0.75           # share of the animated area the render must match to count as animated (or as static)
NEAR_EDGE = 3.5           # frames: no probe this close to a cut or to an element's in or out
STUB_MARK = "/* animcheck: the static page */"


# ------------------------------------------------------------------ where to look (pure)
def default_workers(cpus):
    """the most workers `hyperframes render` starts on its own (0.8.139: max(6, min(16, cpus // 8)))"""
    return max(6, min(16, cpus // 8))


def slots(n, workers):
    """the renderer's split of n frames over the workers: contiguous runs of ceil(n / workers), never empty"""
    w = max(1, min(workers, n))
    per = math.ceil(n / w)
    return [(i * per, min((i + 1) * per, n)) for i in range(w) if i * per < n]


def _T(E, t):
    return getattr(E, "END_IN", E.TOTAL) if t == "end" else float(t)


def _plain(s):
    return " ".join(re.sub(r"<[^>]+>", "", str(s)).replace("*", "").split())


def windows(E, words=None):
    """[(start, end, weight, what)]: when each element the timeline shows and hides is on screen"""
    out = []
    caps = list(getattr(E, "CAPS", None) or [])
    for i, c in enumerate(caps):
        b = _T(E, c[3]) if len(c) > 3 else (caps[i + 1][0] if i + 1 < len(caps) else E.TOTAL)
        out.append((float(c[0]), b, 2, f'caption "{_plain(c[1])}"'))
    if getattr(E, "STYLE", "hifi") in ("lofi", "showcase") and words:
        a = b = None
        for w in words:                                   # one window per spoken phrase (pauses of 0.35 s split)
            if a is not None and w["start"] - b > 0.35:
                out.append((a, b, 2, "word captions"))
                a = None
            a = w["start"] if a is None else a
            b = w["end"]
        if a is not None:
            out.append((a, b, 2, "word captions"))
    for F in getattr(E, "FX", None) or []:
        out.append((float(F["at"]), _T(E, F["end"]), 3, f"effect {F['id']}"))
    for B in getattr(E, "BEHIND", None) or []:
        items = B.get("items") or []
        a = B.get("at")
        if a is None and items:
            a = items[0]["at"] if isinstance(items[0], dict) else items[0][0]
        if a is None:
            continue
        b = _T(E, B["end"]) if B.get("end") is not None else float(a) + 1.0
        out.append((float(a), b, 2, f"behind the head: {B.get('kind', 'element')}"))
    for O in getattr(E, "BOXES", None) or []:
        out.append((float(O["at"]), _T(E, O["end"]), 2, "text box"))
    for O in getattr(E, "OVERLAYS", None) or []:
        out.append((float(O["at"]), _T(E, O["end"]), 2, "overlay"))
    H = getattr(E, "HOOK", None)
    if H and H.get("off"):
        out.append((0.0, float(H["off"]), 2, "hook"))
    if getattr(E, "END_CARD", None):
        out.append((E.END_IN, E.TOTAL, 2, "end card"))
    return [(a, b, w, what) for a, b, w, what in out if b > a]


def edges(E, TL, wins):
    """every moment the picture jumps: cuts, and each element's, card's, grade's and cutout's in and out"""
    e = set(TL.get("picture_cuts", []))
    for a, b, _, _ in wins:
        e |= {a, b}
    for c in getattr(E, "CARDS", None) or []:
        e |= {float(c[2]), _T(E, c[3])}
    for a, b in getattr(E, "BW", None) or []:
        e |= {float(a), _T(E, b)}
    for g in getattr(E, "GRADES", None) or []:
        e |= {float(g[0]), _T(E, g[1])}
    for a, b in getattr(E, "CUT_WINDOWS", None) or []:
        e |= {float(a), _T(E, b)}
    for p in (getattr(E, "CAMERA", None) or {}).get("punch", []):
        e.add(float(p[0]))
    return sorted(e)


def pick(slot, wins, eds):
    """the frame in [start, end) with the most on screen (each element at least 0.15 s in, 0.1 s before its out),
    not within NEAR_EDGE frames of an edge, nearest the slot's middle; the middle when every frame is near an edge"""
    s, e = slot
    mid = (s + e) // 2
    best = None
    for k in range(s, e):
        t = k / FPS
        if any(abs(t - x) < NEAR_EDGE / FPS - 1e-9 for x in eds):
            continue
        score = sum(w for a, b, w, _ in wins if a + min(0.15, (b - a) * 0.3) <= t <= b - min(0.1, (b - a) * 0.2))
        key = (-score, abs(k - mid), k)
        if best is None or key < best[0]:
            best = (key, k)
    return best[1] if best else mid


def window(slot, n, workers):
    """where a slot's probe may sit: near the slot's middle, so that two neighbouring probes are never further apart
    than the shortest run of a render that started fewer workers than its ceiling (the renderer may)"""
    s, e = slot
    if workers <= 1:
        return slot
    d = max(0, (math.ceil(n / (workers - 1)) - math.ceil(n / workers)) // 2)
    c = (s + e) // 2
    return max(s, c - d), min(e, c + d + 1)


def unprobed(frames, n, workers):
    """the first run, of any split of the n frames among 1 to `workers` workers, that holds no probe; else None"""
    for w in range(1, workers + 1):
        for s, e in slots(n, w):
            if not any(s <= k < e for k in frames):
                return s, e
    return None


def _cover(frames, n, workers, choose):
    """frames plus one more (choose(run)) for every run still without a probe, sorted"""
    gap = unprobed(frames, n, workers)
    while gap:
        frames = frames + [choose(gap)]
        gap = unprobed(frames, n, workers)
    return sorted(set(frames))


def _entry(k, S, wins):
    i = next(j for j, (s, e) in enumerate(S) if s <= k < e)
    t = k / FPS
    on = [what for a, b, _, what in wins if a <= t < b]
    return dict(slot=i + 1, first=S[i][0], last=S[i][1] - 1, frame=k, t=t, what=on, expect=bool(on))


def probes(E, TL, n, workers, words=None):
    """a probe in every worker's run, whatever number of workers up to `workers` the render started: one per slot of
    the finest split, at the busiest moment near the slot's middle, and one more for any run still without a probe.
    [{slot, first, last (the slot's frames), frame, t, what (on screen), expect (anything due on screen)}]"""
    wins = windows(E, words)
    eds = edges(E, TL, wins)
    S = slots(n, workers)
    frames = _cover([pick(window(sl, n, workers), wins, eds) for sl in S], n, workers, lambda r: pick(r, wins, eds))
    return [_entry(k, S, wins) for k in frames]


def piece_probes(E, TL, runs, words=None):
    """probes for a render joined from pieces (pieces.py): runs = [(start_frame, end_frame, workers, label)] in frames
    of the whole render. Each piece is rendered on its own and the producer splits the piece's frames over the piece's
    own workers in contiguous runs, the way a whole render splits all of them, so each piece gets inside it what
    probes() gives a whole render: a probe in every slot of the piece's finest split, at the busiest moment near the
    slot's middle, one more for any run of a smaller split still without one. Rows as probes() makes them, in frames
    of the whole render, plus the piece (`piece`, `piece_first`, `piece_last`); `slot` reads p03.1 (piece p03, slot 1)"""
    wins = windows(E, words)
    eds = edges(E, TL, wins)
    out = []
    for a, b, workers, label in runs:
        m, w = b - a, max(1, int(workers))

        def at(r, a=a):                                    # a run of the piece in frames of the whole render
            return a + r[0], a + r[1]

        S = slots(m, w)
        local = _cover([pick(at(window(sl, m, w)), wins, eds) - a for sl in S], m, w,
                       lambda r, at=at, a=a: pick(at(r), wins, eds) - a)
        G = [at(sl) for sl in S]
        for k in local:
            e = _entry(a + k, G, wins)
            out.append(dict(e, slot=f"{label}.{e['slot']}", piece=label, piece_first=a, piece_last=b - 1))
    return out


FALLBACK_WORKERS = 4      # a piece whose cache meta records no worker count


def piece_label(piece):
    """p03: how the check names a piece of the table ({index, start, end, key})"""
    return f"p{int(piece['index']):02d}"


def piece_runs(pieces, metas):
    """[(start, end, workers, label)] for pieces of the table, the workers from each piece's cache meta (the count
    the producer used for that piece), FALLBACK_WORKERS when a meta has none"""
    out = []
    for p in pieces:
        w = (metas.get(p["key"]) or {}).get("workers")
        out.append((int(p["start"]), int(p["end"]), int(w) if w else FALLBACK_WORKERS, piece_label(p)))
    return out


def render_runs(project, render):
    """the runs of a render joined from pieces: its <render>.pieces.json (pieces.py assemble writes it) and each
    piece's cache meta in work/render-pieces/cache/"""
    import pieces as PC
    render = render if os.path.isabs(render) else os.path.join(project, render)
    pj = os.path.splitext(render)[0] + ".pieces.json"
    if not os.path.exists(pj):
        raise ValueError(f"{os.path.basename(pj)} not found: --pieces checks a render joined from pieces "
                         "(pieces.py render or render.py --pieces)")
    with open(pj, encoding="utf-8") as fh:
        pieces = json.load(fh)
    metas = {}
    for p in pieces:
        mp = os.path.join(project, PC.WORK, "cache", p["key"] + ".json")
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as fh:
                metas[p["key"]] = json.load(fh)
    return piece_runs(pieces, metas)


# ------------------------------------------------------------------ the static page (pure)
SCRIPT = re.compile(r"<!--.*?-->|<script\b[^>]*>(?P<body>.*?)</script\s*>", re.I | re.S)


def static_stub(total, cid="main"):
    """the script that replaces the composition's own: one empty timeline as long as the composition, so the
    renderer has a timeline to seek and nothing moves"""
    return (f"<script>{STUB_MARK} window.__timelines = window.__timelines || {{}}; "
            f"window.__timelines['{cid}'] = gsap.timeline({{ paused: true }}).to({{}}, {{ duration: {total:.4f} }});</script>")


def static_page(doc):
    """the composition as a worker without GSAP shows it: every script that registers a timeline (the composition's
    own, with its effects) replaced by the empty timeline; the markup, the styles, the media and GSAP itself stay"""
    root = re.search(r'<[a-z]+\b[^>]*\bdata-composition-id="([^"]+)"[^>]*>', doc)
    dur = re.search(r'\bdata-duration="([0-9.]+)"', root.group(0)) if root else None
    if not dur:
        raise ValueError("no composition root with a data-duration: is this a built index.html?")
    hits = [m for m in SCRIPT.finditer(doc) if m.group("body") and "__timelines" in m.group("body")
            and not m.group("body").lstrip().startswith(STUB_MARK)]
    if not hits:
        raise ValueError("no script in the page registers a timeline (window.__timelines)")
    out, last = [], 0
    for j, m in enumerate(hits):
        out += [doc[last:m.start()], static_stub(float(dur.group(1)), root.group(1)) if j == 0 else ""]
        last = m.end()
    return "".join(out + [doc[last:]])


# ------------------------------------------------------------------ the verdict (pure)
def luma(a):
    a = a.astype(np.float32)
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def tiles(a, b, n=TILE):
    """mean absolute difference of two luma pictures, per n x n tile"""
    d = np.abs(a - b)
    h, w = d.shape[0] // n * n, d.shape[1] // n * n
    return d[:h, :w].reshape(h // n, n, w // n, n).mean(axis=(1, 3))


def verdict(R, S, F):
    """the render's frame R against the animated page S and the static page F (RGB arrays of one size).
    A tile of the animated area (S and F differ) matches S when the render is within half their difference of S,
    F the same way; the shares are weighted by that difference. animated / static: 75% or more of the area matches
    that page; neither: a render that matches no page; calm: no animated area here"""
    r, s, f = luma(R), luma(S), luma(F)
    sf, rs, rf = tiles(s, f), tiles(r, s), tiles(r, f)
    inf = sf > INFORMATIVE
    out = dict(area=round(float(inf.mean()), 3), match=None, static=None)
    if int(inf.sum()) < MIN_TILES:
        return dict(out, state="calm")
    w = sf[inf]
    share_s = float((w * (rs[inf] < 0.5 * w)).sum() / w.sum())
    share_f = float((w * (rf[inf] < 0.5 * w)).sum() / w.sum())
    state = "animated" if share_s >= ANIMATED else "static" if share_f >= ANIMATED else "neither"
    return dict(out, state=state, match=round(share_s, 3), static=round(share_f, 3),
                d_anim=round(float(rs[inf].mean()), 1), d_static=round(float(rf[inf].mean()), 1))


def decide(rows):
    """(ok, why) for the probes' verdicts"""
    bad = [r for r in rows if r["state"] in ("static", "neither")]
    if bad:
        where = lambda rs: ", ".join(f"{r['t']:.3f} s (frame {r['frame']})" for r in rs)  # noqa: E731
        parts = []
        static = [r for r in bad if r["state"] == "static"]
        other = [r for r in bad if r["state"] == "neither"]
        if static:
            parts.append(f"the render shows the static page, its graphics not animated, at {where(static)}")
        if other:
            parts.append(f"the render matches neither the animated nor the static page at {where(other)}")
        return False, "; ".join(parts) + (". A render worker that loses its script renders its whole run of frames "
                                          "like this, without an error: render again")
    if rows and all(r["state"] == "calm" for r in rows) and any(r["expect"] for r in rows):
        return False, ("the composition looks the same with and without its timeline at every probe, although the edit "
                       "has graphics there: its script stops early (open the page in the HyperFrames preview and read "
                       "the console)")
    n = sum(r["state"] == "animated" for r in rows)
    return True, (f"every probe with graphics shows them animated ({n} of {len(rows)})" if n else
                  "nothing animates at the probes (a calm edit): nothing to check")


# ------------------------------------------------------------------ media
def probe_video(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,nb_frames", "-of", "json", path], capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    n = s.get("nb_frames")
    if not str(n or "").isdigit():
        n = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True,
                           check=True).stdout.strip()
    return int(s["width"]), int(s["height"]), int(n)


def render_frame(path, k, size):
    """frame k of the render as RGB (seek half a frame early: the first frame at or after it is frame k)"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, (k - 0.5) / FPS):.4f}", "-i", path, "-frames:v",
                        "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    w, h = size
    return np.frombuffer(r.stdout, np.uint8)[: w * h * 3].reshape(h, w, 3)


def run_snapshots(dirs, times):
    """`hyperframes snapshot` in each folder, all at once: [(folder, exit code, output)]"""
    at = ",".join(f"{t:.4f}" for t in times)
    procs = []
    for d in dirs:
        log = open(os.path.join(d, "snapshot.log"), "w")
        procs.append((d, log, subprocess.Popen(HF + ["snapshot", "--at", at, "--no-end", "--describe", "false"],
                                               cwd=d, stdout=log, stderr=subprocess.STDOUT)))
    out = []
    for d, log, p in procs:
        code = p.wait()
        log.close()
        with open(os.path.join(d, "snapshot.log"), encoding="utf-8", errors="replace") as fh:
            out.append((d, code, fh.read()))
    return out


def read_snapshots(d, n):
    from PIL import Image
    snaps = os.path.join(d, "snapshots")
    files = sorted((f for f in os.listdir(snaps) if re.match(r"frame-\d+", f)) if os.path.isdir(snaps) else [],
                   key=lambda f: int(re.match(r"frame-(\d+)", f).group(1)))
    if len(files) != n:
        raise RuntimeError(f"{d}: the snapshot wrote {len(files)} frames for {n} times")
    return [np.asarray(Image.open(os.path.join(snaps, f)).convert("RGB")) for f in files]


def sheet(path, rows, frames):
    """render | animated | static for each probe that failed, a third of full size"""
    from PIL import Image, ImageDraw
    bands = []
    for r, (R, S, F) in zip(rows, frames):
        band = Image.fromarray(np.concatenate([R, S, F], axis=1)).resize((R.shape[1], R.shape[0] // 3))
        ImageDraw.Draw(band).text((12, 10), f"{r['t']:.3f} s  {r['state']}  (render | animated | static)",
                                  fill=(255, 64, 64))
        bands.append(np.asarray(band))
    Image.fromarray(np.concatenate(bands, axis=0)).save(path, quality=85)


# ------------------------------------------------------------------ the check
def even_probes(n, workers):
    """--page: no edit to read, so the middle of every slot (and of any run of a smaller split still without one)"""
    S = slots(n, workers)
    return [_entry(k, S, []) for k in _cover([(s + e) // 2 for s, e in S], n, workers, lambda r: (r[0] + r[1]) // 2)]


def run(pub, render, P, n, work, sheet_path, label, keep=False, scope=None):
    """the two snapshots of the page in pub at the probes P (in two link trees under work), the render's frames, a
    verdict per probe, the table; the probe pictures to sheet_path when it fails. (ok, rows). scope: what the probes
    cover, for the first line (default: one per render worker run)"""
    import hook as H
    t0 = time.time()
    w, h, _ = probe_video(render)
    with open(os.path.join(pub, "index.html"), encoding="utf-8") as fh:
        doc = fh.read()
    shutil.rmtree(work, ignore_errors=True)                 # links only: removing them never touches the originals
    dirs = [os.path.join(work, "animated"), os.path.join(work, "static")]
    try:
        for d, page in zip(dirs, (doc, static_page(doc))):
            H.link_tree(pub, d, skip=("index.html", "snapshots"))
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
                fh.write(page)
        t1 = time.time()
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(render_frame, render, p["frame"], (w, h)) for p in P]
            res = run_snapshots(dirs, [p["t"] for p in P])
            R = [f.result() for f in futs]
        t_snap = time.time() - t1
        for d, code, log in res:
            if code:
                raise RuntimeError(f"hyperframes snapshot failed in {d}:\n{log[-1500:]}")
        S, F = read_snapshots(dirs[0], len(P)), read_snapshots(dirs[1], len(P))
    finally:
        for d in dirs:
            if not keep:
                shutil.rmtree(d, ignore_errors=True)
    rows, pics = [], []
    for p, r, s, f in zip(P, R, S, F):
        v = verdict(r, s, f)
        if v["state"] in ("static", "neither"):              # the renderer rounds a clip's frame its own way
            lo, hi = max(0, p.get("piece_first", 0)), min(n - 1, p.get("piece_last", n - 1))  # a piece's own frames
            for k in (p["frame"] - 1, p["frame"] + 1):
                if lo <= k <= hi:
                    rk = render_frame(render, k, (w, h))
                    vk = verdict(rk, s, f)
                    if vk["state"] == "animated":
                        v, r = dict(vk, shifted=k - p["frame"]), rk
                        break
        rows.append(dict(p, **v))
        pics.append((r, s, f))
    ok, why = decide(rows)
    print(f"animcheck: {label}, {n} frames, {len(P)} probes "
          + (scope or f"(one per render worker run, up to {len(P)} workers)"))
    print("  probe  time      frame  verdict    animated area  matches  on screen")
    for r in rows:
        m = "-" if r["match"] is None else f"{r['match']:.0%}"
        print(f"  {r['slot']:<5}  {r['t']:7.3f}s  {r['frame']:<5}  {r['state']:<9}  {r['area']:>12.0%}  {m:>7}  "
              f"{', '.join(r['what']) or '-'}" + (f"  (frame {r['shifted']:+d})" if r.get("shifted") else ""))
    if not ok:
        bad = [(r, x) for r, x in zip(rows, pics) if r["state"] in ("static", "neither")] or list(zip(rows, pics))
        os.makedirs(os.path.dirname(sheet_path), exist_ok=True)
        sheet(sheet_path, [r for r, _ in bad], [x for _, x in bad])
    print(f"animcheck {'PASS' if ok else 'FAIL'}: {why}. {time.time() - t0:.1f} s (snapshots {t_snap:.1f} s)")
    if not ok:
        print(f"  the probe pictures: {sheet_path} (render | animated | static)")
    return ok, rows


def check(project, render, workers=None, keep=False, runs=None):
    """(ok, rows) for one render of the project's built composition (public/index.html), probes from its edit.
    runs (a render joined from pieces): [(start_frame, end_frame, workers, label)], the probes go inside each of those
    pieces instead (piece_probes); an empty list checks nothing and passes"""
    if runs is not None and not runs:
        print("animcheck: no pieces to check")
        return True, []
    import build as B
    E = load_edit(project)
    TL = timeline(project)
    B.setup(E, TL)
    render = render if os.path.isabs(render) else os.path.join(project, render)
    n = probe_video(render)[2]
    wp = os.path.join(project, "words.json")
    words = json.load(open(wp, encoding="utf-8")) if os.path.exists(wp) else None
    scope = None
    if runs is None:
        P = probes(E, TL, n, workers or default_workers(os.cpu_count() or 8), words)
    else:
        for a, b, _, label in runs:
            if not 0 <= a < b <= n:
                raise ValueError(f"piece {label} (frames {a}-{b - 1}) is not inside the render's {n} frames: "
                                 "the piece table does not belong to this render")
        P = piece_probes(E, TL, runs, words)
        scope = f"in {len(runs)} piece{'s' if len(runs) != 1 else ''} (one per worker run inside each piece)"
    work = os.path.join(project, "work", "animcheck")
    ok, rows = run(os.path.join(project, "public"), render, P, n, work, os.path.join(work, "sheet.jpg"),
                   os.path.relpath(render, project), keep, scope=scope)
    if ok and not keep:
        shutil.rmtree(work, ignore_errors=True)
    return ok, rows


def check_page(page, render, workers=None, keep=False):
    """(ok, rows) for a render of a composition folder of its own (a card: index.html, vendor/, its files); the
    snapshot folders sit beside it, never inside it, and go when the check ends; the probe pictures of a failure are
    <render>.animcheck.jpg"""
    import tempfile
    page = os.path.abspath(page)
    render = render if os.path.isabs(render) else os.path.join(page, render)
    n = probe_video(render)[2]
    P = even_probes(n, workers or default_workers(os.cpu_count() or 8))
    work = tempfile.mkdtemp(prefix=f".animcheck-{os.path.basename(page)}-", dir=os.path.dirname(page))
    try:
        return run(page, render, P, n, work, os.path.splitext(render)[0] + ".animcheck.jpg",
                   os.path.relpath(render, os.path.dirname(page)), keep)
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def main():
    a = sys.argv[1:]
    page = "--page" in a
    if page:
        a = a[:a.index("--page")] + a[a.index("--page") + 1:]
    pieces = "--pieces" in a
    if len(a) < 2 or a[0].startswith("-") or (page and pieces):
        sys.exit("usage: animcheck.py <project> <render.mp4> [--workers N] [--keep]\n"
                 "       animcheck.py <project> <render.mp4> --pieces [--keep]\n"
                 "       animcheck.py --page <folder> <render.mp4> [--workers N] [--keep]")
    workers = int(a[a.index("--workers") + 1]) if "--workers" in a else None
    target, render = os.path.abspath(os.path.expanduser(a[0])), os.path.expanduser(a[1])
    try:
        if page:
            ok, _ = check_page(target, render, workers=workers, keep="--keep" in a)
        else:
            ok, _ = check(target, render, workers=workers, keep="--keep" in a,
                          runs=render_runs(target, render) if pieces else None)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        print(f"animcheck could not check this render: {e}", file=sys.stderr)
        sys.exit(2)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
