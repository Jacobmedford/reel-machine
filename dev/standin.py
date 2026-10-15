#!/usr/bin/env python3
"""Dev only: a stand-in "talking head" drawn from code, so the effects library can be built, tested and previewed
without anyone's real footage. A flat room (a lit window, a dark frame, a desk) and a flat figure that sways a
little. Nothing in it is a person: it is a placeholder, and it looks like one.

  video <out.mp4> [seconds]        1080x1920 30fps H.264 with a silent stereo track
  matte <aroll.mp4> <subject.webm> the figure keyed out of a cut of that video -> VP9 + alpha (the cutout)
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

W, H, FPS = 1080, 1920, 30
WALL, WINDOW, SASH, FRAME, ART, DESK, DESK_EDGE = "#8B867D", "#E4DFD4", "#B9B3A8", "#4E4239", "#A47E5C", "#4A3B30", "#5C4A3C"
FIGURE = (31, 42, 54)                     # the one slate-blue in the scene: keyed out for the cutout
SHADE = (43, 56, 70)                      # the figure's near side, a flat second tone


def room():
    im = Image.new("RGB", (W, H), WALL)
    d = ImageDraw.Draw(im)
    d.rectangle((70, 250, 470, 860), fill=WINDOW)                       # a lit window, upper left (light behind the head)
    d.rectangle((262, 250, 278, 860), fill=SASH)
    d.rectangle((70, 548, 470, 562), fill=SASH)
    d.rectangle((720, 360, 990, 700), fill=FRAME)                       # a framed print, upper right (dark)
    d.rectangle((748, 388, 962, 672), fill=ART)
    d.rectangle((0, 1490, W, H), fill=DESK)                             # the desk
    d.rectangle((0, 1490, W, 1504), fill=DESK_EDGE)
    return im


def figure(d, t):
    """head and shoulders, swaying slowly (a function of time only, so any frame can be redrawn exactly)"""
    dx = 10 * math.sin(2 * math.pi * t / 4.3)
    dy = 4 * math.sin(2 * math.pi * t / 2.9)
    cx, cy = 540 + dx, 770 + dy
    d.ellipse((cx - 430, cy + 350, cx + 430, cy + 1010), fill=FIGURE)                      # shoulders
    d.rectangle((cx - 430, cy + 680, cx + 430, H), fill=FIGURE)
    d.rounded_rectangle((cx - 58, cy + 130, cx + 58, cy + 400), radius=28, fill=FIGURE)    # neck
    d.ellipse((cx - 140, cy - 185, cx + 140, cy + 185), fill=FIGURE)                       # head
    d.pieslice((cx - 140, cy - 185, cx + 140, cy + 185), 270, 450, fill=SHADE)            # the near side, a second tone
    return cx, cy


def video(out, seconds):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    base = room()
    n = int(seconds * FPS)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                            "-t", f"{seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium",
                            "-c:a", "aac", "-shortest", out], stdin=subprocess.PIPE)
    for k in range(n):
        im = base.copy()
        figure(ImageDraw.Draw(im), k / FPS)
        enc.stdin.write(im.tobytes())
    enc.stdin.close()
    enc.wait()
    print(f"{out}: {n} frames")


def matte(aroll, out):
    """key the slate figure out of the cut: it is the only colour of its kind in the room"""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", aroll], capture_output=True, text=True).stdout
    n = int(probe.strip())
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", aroll, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0",
                            "-crf", "20", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-auto-alt-ref", "0",
                            out], stdin=subprocess.PIPE)
    ref = np.array([FIGURE, SHADE], dtype=np.float32)
    for _ in range(n):
        f = np.frombuffer(dec.stdout.read(W * H * 3), np.uint8).reshape(H, W, 3)
        dist = np.min(np.linalg.norm(f[None].astype(np.float32) - ref[:, None, None, :], axis=3), axis=0)
        a = np.clip((26 - dist) / 10, 0, 1)
        enc.stdin.write(np.dstack([f, (a * 255).astype(np.uint8)]).tobytes())
    enc.stdin.close()
    enc.wait()
    dec.wait()
    print(f"{out}: {n} frames keyed")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "video":
        video(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 32.0)
    elif len(sys.argv) >= 4 and sys.argv[1] == "matte":
        matte(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
