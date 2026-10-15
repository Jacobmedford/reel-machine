#!/usr/bin/env python3
"""video-card helper: find the moments of a recording that MOVE, so every chapter in the card shows movement (you
AND the screen), never a near-still. Then cut them into clips and print the <video> tags for fx.html.

Energy is frame-difference energy: the mean absolute change between consecutive frames (grayscale, downscaled), per
frame, over the whole frame or over the regions you name. A window that holds a hard cut is skipped (a cut is not
movement). Windows are in source seconds.

  PY energy.py <recording> [--len S] [--top N] [--gap S] [--region x,y,w,h ...]
      the N best non-overlapping windows of S seconds, most movement first (default 4 windows of 3 s)
  add --cut <folder>         writes clip-1.mp4 .. clip-N.mp4 there: muted H.264 at 30 fps, cover-cropped to 960x540
  add --tags A B [--rate R] [--play T]
                             prints the poster + clip <video> tags for fx.html, for an effect shown from A to B
                             (the edit.FX at / end). Each clip runs the whole window at R x speed (default 2), so a
                             window is (B - A) * R seconds long; --play is when the play press lands (the poster
                             holds the frame clip 1 opens on). The tags time themselves from wherever the effect
                             sits ({{START+..}}, {{DUR}}: the build fills them in). Paste them over the tags in fx.html.
  add --copies               with --tags: copies of the project's clean.mp4 at those moments instead of clip files
                             (pass <project>/public/clean.mp4 as the recording). Their media start is {{SYNC+..}}, an
                             offset from the effect's start, so it points at the same moments only while the effect
                             stays where it is: rerun after moving it. (The library's own placeholders are copies in
                             sync with the main picture, {{SYNC}} at 1x, which exist wherever the effect sits.)
  add --keep-cuts            don't skip windows with a hard cut (a page switch in a screen recording can look like one)

--region takes fractions of the frame, x,y,w,h in 0..1: a webcam box, the screen. With several, a window counts
only as much as its stillest region, so it has to move everywhere you named.
Example (a screen recording with the webcam bottom right, effect at 23.9 to 25.6):
  PY fx/video-card/energy.py walkthrough.mov --top 4 --region 0,0,0.75,1 --region 0.75,0.6,0.25,0.4 \\
     --cut <project>/fx/video-card --tags 23.9 25.6 --rate 2
"""
import json
import os
import subprocess
import sys

import numpy as np

FPS = 30


def arg(name, default=None, n=1):
    a = sys.argv
    if name not in a:
        return default
    i = a.index(name)
    return a[i + 1] if n == 1 else a[i + 1:i + 1 + n]


def regions():
    out, a = [], sys.argv
    for i, x in enumerate(a):
        if x == "--region":
            out.append([float(v) for v in a[i + 1].split(",")])
    return out or [[0.0, 0.0, 1.0, 1.0]]


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate", "-of", "json", path], capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den)


def energy(path):
    """per-frame difference energy for each region, and the whole-frame difference (for cut detection)"""
    w0, h0, fps = probe(path)
    W = 192
    H = max(2, round(W * h0 / w0 / 2) * 2)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", f"scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    boxes = [(int(x * W), int(y * H), max(1, int(w * W)), max(1, int(h * H))) for x, y, w, h in regions()]
    prev, per, whole = None, [], []
    while True:
        b = p.stdout.read(W * H)
        if len(b) < W * H:
            break
        f = np.frombuffer(b, np.uint8).astype(np.int16).reshape(H, W)
        if prev is None:
            per.append([0.0] * len(boxes))
            whole.append(0.0)
        else:
            d = np.abs(f - prev)
            per.append([float(d[y:y + h, x:x + w].mean()) for x, y, w, h in boxes])
            whole.append(float(d.mean()))
        prev = f
    p.wait()
    return np.array(per), np.array(whole), fps


def cuts_in(whole):
    """a hard cut is a one-frame spike far above the motion on both sides of it (a scroll or a gesture stays high
    for several frames, so it never counts)"""
    cut = np.zeros(len(whole), bool)
    if "--keep-cuts" in sys.argv:
        return cut
    for i in range(1, len(whole)):
        side = [whole[max(1, i - 5):i], whole[i + 1:i + 6]]
        local = max([float(np.median(s)) for s in side if len(s)] or [0.0])
        cut[i] = whole[i] > max(4.0, 5.0 * local)
    return cut


def windows(per, whole, fps, length, top, gap):
    n = max(1, int(round(length * fps)))
    med = float(np.median(whole[1:])) if len(whole) > 1 else 0.0
    cut = cuts_in(whole)
    cum = np.vstack([np.zeros(per.shape[1]), np.cumsum(per, axis=0)])
    cuts = np.concatenate([[0], np.cumsum(cut)])
    scored = []
    for s in range(0, len(per) - n + 1):                    # a window shows frames s .. s + n - 1
        if cuts[s + n] - cuts[s + 1] > 0:                   # a cut lands inside this window
            continue
        scored.append((float(((cum[s + n] - cum[s + 1]) / max(1, n - 1)).min()), s))   # only the changes inside it
    scored.sort(reverse=True)
    picked = []
    for score, s in scored:
        if all(abs(s - t) >= n + gap * fps for _, t in picked):
            picked.append((score, s))
        if len(picked) == top:
            break
    return picked, n, med, int(cut.sum())


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    src = sys.argv[1]
    tags = arg("--tags", None, 2)
    rate = float(arg("--rate", 2))
    if tags:
        A, B = float(tags[0]), float(tags[1])
    length = float(arg("--len", (B - A) * rate if tags else 3.0))
    top = int(arg("--top", 4))
    per, whole, fps = energy(src)
    picked, n, med, ncuts = windows(per, whole, fps, length, top, float(arg("--gap", 0.5)))
    print(f"{src}: {len(per)} frames at {fps:g} fps, median energy {med:.2f}, {ncuts} cut(s) skipped")
    print(f"best {len(picked)} windows of {length:.2f} s (energy = the stillest region's mean):")
    for k, (score, s) in enumerate(picked):
        print(f"  {k + 1}. {s / fps:8.3f} - {(s + n) / fps:8.3f}   energy {score:.2f}")
    if not picked:
        sys.exit("no window without a cut: try a shorter --len")
    starts = [s / fps for _, s in picked]

    out = arg("--cut")
    if out:
        os.makedirs(out, exist_ok=True)
        for k, t in enumerate(starts):
            dst = os.path.join(out, f"clip-{k + 1}.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-t", f"{length + 3 / FPS:.3f}", "-an",
                            "-vf", f"scale=960:540:force_original_aspect_ratio=increase,crop=960:540,fps={FPS}",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", dst],
                           check=True)
            print(f"  wrote {dst}")

    if tags:
        play = float(arg("--play", A + 0.45))
        copies = "--copies" in sys.argv
        n = len(starts)
        srcs = ["clean.mp4"] * n if copies else [f"fx/{{{{ID}}}}/clip-{k + 1}.mp4" for k in range(n)]
        opens = (round(play * FPS) - round(A * FPS) - 1) / FPS * rate   # clip 1 opens this far in at the play press
        hold = max(0.0, opens - (play - A) * 0.1)                       # the poster creeps at 0.1x and arrives there

        def rel(x):                                                     # +0.0333 / -13.9 / '' for none
            return "" if abs(x) < 1e-6 else f"{x:+.4f}".rstrip("0").rstrip(".")

        def media(k, into):                                             # clip k (0-based), `into` seconds in
            if copies:                                                  # a moment of clean.mp4, from the effect's start
                return "{{SYNC" + rel(round((starts[k] + into) * FPS) / FPS - A) + "}}"
            return f"{round(into * FPS) / FPS + 0.001:.4f}"             # an offset into the clip file
        rows = [("poster", srcs[0], 0, media(0, hold), 0.1, 0)]
        rows += [(f"v{k + 1}", srcs[k], k + 1, media(k, 0.0), rate, k + 1) for k in range(n)]
        print("\n<video> tags for fx.html (each runs the effect's window, one frame apart, and shows only in its chapter):")
        for vid, s, f, m, r, t in rows:
            print(f'    <video id="{{{{ID}}}}-{vid}" class="{{{{ID}}}}-v" src="{s}" muted playsinline '
                  f'data-start="{{{{START{rel(f / FPS)}}}}}" data-media-start="{m}" data-duration="{{{{DUR}}}}" '
                  f'data-playback-rate="{r:g}" data-track-index="{{{{T{t}}}}}"></video>')
        if copies:
            print("  (media starts are offsets from the effect's start: rerun if the effect moves)")


if __name__ == "__main__":
    main()
