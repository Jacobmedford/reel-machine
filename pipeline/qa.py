#!/usr/bin/env python3
"""QA a render. Nothing ships until all three pass.
  1. cuts: the last frame before and the first frame after every visual change (picture cuts, reframes, card in/out,
     end card), tiled 8 pairs per sheet into work/qa/cuts_<n>.jpg. Read them: no flash, no wrong frame, no doubled head.
  2. lip sync: for samples across every stretch where the speaker is on screen, the rendered frame is matched against
     the 4K source around the voice-synced source time. The match is made on the speaker: the parts of the frame that
     show the footage (not a page, a caption or a sticker laid over it) and that move in the 1.2 s around the sample
     (the face and head), weighted by how much they move. The whole-frame match is the fallback where nothing visible
     moves, and is printed beside the speaker match when the two disagree. Every sample must land within 2 frames of 0
     (a real slip is many frames: 0.5s is 15).
  3. loudness: -14 LUFS integrated, peak at or under -1.0 dBFS.
Plus a 720p phone copy with --phone. Run: PY pipeline/qa.py <project> renders/<file>.mp4 [--phone] [--full-frame]
  --full-frame   judge lip sync on whole frames only (the old check)
Each frame is decoded once: one pass over the render for the sheets, one for the sync samples, and one short decode
of the source per sample.
"""
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, load_edit, project_arg, q, timeline, wide  # noqa: E402
import build as B  # noqa: E402

SPAN = 0.6                # seconds searched either side of the voice-synced source time
TILE = 15                 # px tiles of the 135x240 match frame (9 x 16)
FOOTAGE = 0.6             # a tile shows the footage when it matches some source frame at least this well
MIN_MOVE = 8.0            # total movement (grey levels, summed over the seen tiles) below which the speaker match abstains
FACE_MARGIN = 0.004       # the speaker match is inconclusive when its peak beats every far offset by less than this
JOBS = 8
SHOWINFO = re.compile(r"\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:")
TIMEBASE = re.compile(r"config in time_base:\s*(\d+)/(\d+)")


def gray(path, t, vf, w=135, h=240):
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", path, "-frames:v", "1", "-vf", vf,
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(h, w).astype(float)


# ------------------------------------------------------------------ cut sheets
def cut_frames(E, TL):
    """the frame of every visual change: picture cuts, reframes, cards in and out, the end card"""
    events = set(TL["picture_cuts"]) | set(TL["reframes"])
    for c in E.CARDS:
        events |= {c[2], c[3]}
    if E.END_CARD:
        events.add(E.END_IN)
    return sorted({round(t * FPS) for t in events if 0 < t < E.TOTAL})


def sheet_rows(frames):
    """[(the frames on one sheet: before, after, before, after ...), (the events it shows)], 8 pairs a sheet"""
    pngs = [n for f in frames for n in (f - 1, f)]
    return [(pngs[i:i + 16], frames[r * 8:(r + 1) * 8]) for r, i in enumerate(range(0, len(pngs), 16))]


def select_expr(ns):
    return "+".join(f"eq(n\\,{n})" for n in ns)


def video_pts(path):
    """the video's frame timestamps in display order and its time base, from the packets (no decode)"""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=time_base:packet=pts", "-of", "csv=p=0", path], capture_output=True, text=True,
                         check=True).stdout.split()
    vals = [x.strip(",") for x in out]
    num, den = next(x for x in vals if "/" in x).split("/")
    return sorted(int(x) for x in vals if x.lstrip("-").isdigit()), (int(num), int(den))


def cut_sheets(project, render, E, TL, total=None):
    frames = cut_frames(E, TL)
    out = os.path.join(project, "work", "qa")
    sel = os.path.join(out, "sel")
    os.makedirs(sel, exist_ok=True)
    need = sorted({n for f in frames for n in (f - 1, f) if n >= 0 and (total is None or n < total)})
    if need:                                                   # one decode for every frame the sheets show
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", render, "-vf",
                        f"select={select_expr(need)},scale={320 if wide(E) else 180}:-2", "-fps_mode", "passthrough",
                        "-start_number", "0", os.path.join(sel, "%05d.png")], check=True)
        for i, n in enumerate(need):
            os.replace(os.path.join(sel, f"{i:05d}.png"), os.path.join(out, f"f{n}.png"))
    sheets = []
    for r, (row, fr) in enumerate(sheet_rows(frames)):
        row = [n for n in row if n in need]
        ins = sum((["-i", os.path.join(out, f"f{n}.png")] for n in row), [])
        sheet = os.path.join(out, f"cuts_{r}.jpg")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", f"hstack={len(row)}", sheet],
                       check=True)
        sheets.append((sheet, fr))
    return sheets


# ------------------------------------------------------------------ lip sync
def cam_scale(E, TL, t):
    """the #cam scale the build gives the footage at reel time t (settles, punch-ins, pushes), and whether it is moving"""
    tw = [(0.0, E.CAMERA.get("open", (1.04, 0.45))[1], E.CAMERA.get("open", (1.04, 0.45))[0], 1.0)]
    tw += [(s, 0.32, 1.045, 1.0) for s in B.settle_times(E, TL)]
    tw += [(s, 0.18, k, 1.0) for s, k in E.CAMERA.get("punch", [])]
    tw += [(a, B.T(E, b) - a, 1.0, k) for a, b, k in E.CAMERA.get("pushes", [])]
    for a, b, k in E.CAMERA.get("zooms", []):                       # lofi hard zooms: held, no motion
        tw += [(a, 1e-4, k, k), (B.T(E, b), 1e-4, 1.0, 1.0)]
    started = [w for w in tw if w[0] <= t + 1e-6]
    if not started:
        return 1.0, False
    s0, d, v0, v1 = max(started, key=lambda w: w[0])
    if t >= s0 + d:
        return v1, False
    return v0 + (v1 - v0) * ((t - s0) / d), True


def under_fx(E, t):
    """is t inside an effect that repaints the background (behind), moves the picture (cam) or covers it (over)?
    Whole-frame matching can't see the lips there; the cutout and footage copies are frame-exact anyway. Effects that
    span almost the whole video (camera-transitions) only act on the cuts, where no sample is taken."""
    for F in getattr(E, "FX", []):
        a, b = F["at"], B.T(E, F["end"])
        if F.get("layer", "top") in ("behind", "cam", "over") and b - a < 0.9 * E.TOTAL and a <= t < b:
            return True
    return False


def samples(E, TL):
    """two quiet moments in every on-camera piece: [(reel t, piece)]"""
    jobs = []
    for p in TL["pieces"]:
        a, b = p["out_start"], min(p["out_end"], TL["total_audio"])
        if b - a < 1.0:
            continue
        cands = [t for t in np.arange(a + 0.3, b - 0.3, 1 / FPS)
                 if B.visible(E, t) and not cam_scale(E, TL, t)[1] and not under_fx(E, t)]
        if not cands:
            continue
        for t in sorted({cands[len(cands) // 3], cands[(2 * len(cands)) // 3]}):
            jobs.append((round(float(t), 3), p))
    return jobs


def geometry(E, TL, t, p):
    """the source second you hear at t, and the crop of the source the scaled camera shows at t"""
    g = [k for k in TL["keep"] if k["out"] - 1e-6 <= t][-1]
    want = g["src_in"] + (t - g["out"])
    s, _ = cam_scale(E, TL, t)
    w, h, x, y = E.FRAMES[p["frame"]]
    (W, H), (ox, oy) = E.CANVAS, E.CAM_ORIGIN
    gw, gh = (240, 135) if wide(E) else (135, 240)
    cw, ch = w / s, h / s                                    # what the scaled camera shows of the crop
    cx, cy = x + (ox - ox / s) * w / W, y + (oy - oy / s) * h / H
    return want, f"crop={cw:.0f}:{ch:.0f}:{cx:.0f}:{cy:.0f},scale={gw}:{gh}", gw, gh


def offsets(span=SPAN):
    return np.arange(-span, span + 1e-6, 1 / FPS)


def seek_us(t):
    """the -ss ffmpeg is given for time t (written to 0.1 ms), in microseconds"""
    return int(round(float(f"{t:.4f}") * 1e6))


def first_at_or_after(pts, tb, target_us):
    """the frame an accurate -ss lands on: the first whose time is at or after the target, compared the way ffmpeg's
    trim does (the target rounded to the stream's time base)"""
    num, den = tb
    start = (2 * target_us * den + num * 1_000_000) // (2 * num * 1_000_000)     # round half up, in time-base ticks
    for i, p in enumerate(pts):
        if p >= start:
            return i
    return None


def window(src, start, dur, vf, gw, gh):
    """one decode of the source from start for dur seconds through vf: (grey frames, their pts, the time base)"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-copyts", "-ss", f"{start:.4f}", "-t",
                        f"{dur:.4f}", "-i", src, "-an", "-vf", vf + ",showinfo", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True)   # passthrough: a
    # phone's variable frame rate must not be evened out here (that drops or repeats frames), one frame per frame
    log = r.stderr.decode(errors="ignore")
    pts = [int(m) for m in SHOWINFO.findall(log)]
    tb = tuple(int(x) for x in TIMEBASE.search(log).groups())
    frames = np.frombuffer(r.stdout, np.uint8).reshape(-1, gh, gw).astype(float)
    if len(frames) != len(pts):
        raise RuntimeError(f"{src}: {len(frames)} frames but {len(pts)} timestamps")
    return frames, pts, tb


def source_frames(src, want, vf, gw, gh, span=SPAN):
    """the source frames the old per-offset seeks picked (one per offset), from a single decode"""
    targets = [seek_us(want + d) for d in offsets(span)]
    start = max(0.0, targets[0] / 1e6 - 0.1)
    frames, pts, tb = window(src, start, targets[-1] / 1e6 + 0.2 - start, vf, gw, gh)
    idx = [first_at_or_after(pts, tb, u) for u in targets]
    if None in idx:
        raise RuntimeError(f"{src}: no frame at or after {targets[idx.index(None)] / 1e6:.4f}s")
    return frames[idx]


def render_frames(render, times, gw, gh):
    """the render's frame at each sample time (the frame an -ss there lands on), from a single decode"""
    pts, tb = video_pts(render)
    ns = [first_at_or_after(pts, tb, seek_us(t)) for t in times]
    uniq = sorted(set(ns))
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", render, "-vf", f"select={select_expr(uniq)},scale={gw}:{gh}",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    frames = np.frombuffer(out, np.uint8).reshape(-1, gh, gw).astype(float)
    got = dict(zip(uniq, frames))
    return [got[n] for n in ns]


def full_match(r, F):
    """whole-frame normalized correlation of the render frame with every source frame"""
    r = (r - r.mean()) / r.std()
    return np.array([float((r * ((f - f.mean()) / f.std())).mean()) for f in F])


def tiles(a, tile=TILE):
    """[..., h, w] -> [..., rows, cols, tile*tile]"""
    h, w = a.shape[-2] // tile * tile, a.shape[-1] // tile * tile
    a = a[..., :h, :w]
    a = a.reshape(a.shape[:-2] + (h // tile, tile, w // tile, tile))
    a = np.swapaxes(a, -3, -2)
    return a.reshape(a.shape[:-2] + (tile * tile,))


def face_match(r, F, tile=TILE):
    """the speaker match: per-tile correlation with every source frame, kept where the render shows the footage (a
    tile matches some source frame) and weighted by how much that tile moves across the source frames (the face and
    head move, the room does not). None when nothing visible moves."""
    rt, Ft = tiles(r, tile), tiles(F, tile)
    rd, Fd = rt - rt.mean(-1, keepdims=True), Ft - Ft.mean(-1, keepdims=True)
    rs, Fs = np.sqrt((rd ** 2).mean(-1)), np.sqrt((Fd ** 2).mean(-1))
    flat = (rs < 1.0)[None] | (Fs < 1.0)                        # a flat tile (a card, a wall in shadow) says nothing
    c = np.where(flat, 0.0, (rd[None] * Fd).mean(-1) / np.maximum(rs[None] * Fs, 1e-9))
    move = tiles(F.std(0), tile).mean(-1)
    seen = c.max(0) >= FOOTAGE
    w = np.where(seen, move, 0.0)
    if w.sum() < MIN_MOVE:
        return None
    return (c * w[None]).sum((1, 2)) / w.sum(), {"tiles": int(seen.sum()), "move": round(float(w.sum()), 1)}


def best(curve, offs, margin):
    k = int(np.argmax(curve))
    far = [c for o, c in zip(offs, curve) if abs(o - offs[k]) > 0.1]
    note = "static (inconclusive)" if far and curve[k] - max(far) < margin else ""
    return round(float(offs[k]), 3), round(float(curve[k]), 3), note


def lip_sync(render, E, TL, span=SPAN, face=True):
    """For two quiet moments in every on-camera piece, decode the rendered frame and the source frames around the
    second you hear at that moment (the same frames the old per-offset seeks picked), crop the source the way the
    camera scale frames it, and find the best match on the speaker and on the whole frame. Offset 0 = in sync.
    Returns [dict(t, full=(offset, match, note), face=(offset, match, note) or None)]."""
    jobs = samples(E, TL)
    if not jobs:
        return []
    geo = [geometry(E, TL, t, p) for t, p in jobs]
    gw, gh = geo[0][2], geo[0][3]
    offs = offsets(span)
    with ThreadPoolExecutor(JOBS) as ex:
        rend = ex.submit(render_frames, render, [t for t, _ in jobs], gw, gh)
        srcs = list(ex.map(lambda g: source_frames(E.SRC, g[0], g[1], gw, gh, span), geo))
        rends = rend.result()
    rows = []
    for (t, _), r, F in zip(jobs, rends, srcs):
        row = dict(t=t, full=best(full_match(r, F), offs, 0.004), face=None)
        fm = face_match(r, F) if face else None
        if fm is not None:
            row["face"] = best(fm[0], offs, FACE_MARGIN)
        rows.append(row)
    return rows


def verdict(rows):
    """the speaker match where it is conclusive, else the whole frame; inconclusive samples are left out.
    Returns (worst |offset|, [(which, offset, match, note)])"""
    worst, used = 0.0, []
    for r in rows:
        kind, (d, c, note) = ("face", r["face"]) if r["face"] is not None and not r["face"][2] else ("full", r["full"])
        if not note:
            worst = max(worst, abs(d))
        used.append((kind, d, c, note))
    return worst, used


def loudness(render):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", render, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    s = r[r.rfind("Summary"):]
    i = float([l for l in s.splitlines() if l.strip().startswith("I:")][0].split()[1])
    pk = float([l for l in s.splitlines() if l.strip().startswith("Peak:")][0].split()[1])
    return i, pk


def phone_copy(render, E):
    ph = os.path.splitext(render)[0] + "-phone.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", render, "-vf", f"scale={1280 if wide(E) else 720}:-2",
                    "-c:v", "libx264", "-crf", "24", "-preset", "veryfast", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", ph], check=True)
    return ph


def main():
    project = project_arg()
    render = os.path.join(project, sys.argv[2]) if not os.path.isabs(sys.argv[2]) else sys.argv[2]
    E = load_edit(project)
    TL = timeline(project)
    B.setup(E, TL)
    ok = True
    with ThreadPoolExecutor(2) as bg:                        # the phone copy and loudness run beside the checks
        phone = bg.submit(phone_copy, render, E) if "--phone" in sys.argv else None
        loud = bg.submit(loudness, render)
        for sheet, fr in cut_sheets(project, render, E, TL, len(video_pts(render)[0])):
            print("cuts:", sheet, fr)
        rows = lip_sync(render, E, TL, face="--full-frame" not in sys.argv)
        worst, used = verdict(rows)
        for r, (kind, d, c, note) in zip(rows, used):
            flag = note or ("" if abs(d) <= 2.5 / FPS else "<-- OUT OF SYNC")
            fd, fc, _ = r["full"]
            also = f"  (whole frame {fd:+.3f}s {fc:.3f})" if kind == "face" and abs(fd - d) > 2.5 / FPS else ""
            print(f"sync: reel {r['t']:6.2f}s  offset {d:+.3f}s  match {c:.3f}  {kind}{'  ' + flag if flag else ''}{also}")
        if worst > 2.5 / FPS:       # +-2 frames is measurement noise (grades, overlays); a real slip is many frames
            ok = False
        i, pk = loud.result()
        print(f"loudness: {i} LUFS, peak {pk} dBFS")
        if abs(i + 14) > 0.5 or pk > -1.0:
            ok = False
            print("loudness OUT OF SPEC")
        if phone:
            ph = phone.result()
            print("phone copy", ph, f"{os.path.getsize(ph) / 1e6:.1f} MB")
    print("QA PASS (now read the cut sheets)" if ok else "QA FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
