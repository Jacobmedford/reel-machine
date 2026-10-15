#!/usr/bin/env python3
"""Matte (optional upgrade): the speaker cut out with Robust Video Matting (temporal, soft alpha)
-> <project>/assets/subject.webm (VP9 + alpha) and public/. Smoother edges than cutout.py (which segments every frame
on its own and can shimmer at hair edges), worth it for lo-fi videos where things sit behind the speaker a lot.
Needs PyTorch: `python3 setup/setup.py --matte` installs it. The model is GPL-3.0 and is downloaded on first use,
never committed to this repo.

The alpha comes from RVM; the colour is the a-roll's own pixels, so the cutout matches the footage underneath.
Only where the cutout is used: edit.CUT_WINDOWS, plus the window of any FX whose files read public/subject.webm (its
mask generator), each widened by MARGIN on both sides and merged when closer than MERGE_GAP. Those frames are read
back and encoded; every other frame is transparent, so subject.webm keeps the a-roll's exact frame count and timing.
RVM is recurrent (each frame's matte depends on every frame before it), so the model still sees the take from the first
frame to the end of the last window, exactly as a full run does, and the alpha inside the windows is the full run's.
Outside the windows it runs RVM's segmentation pass, the same backbone and decoder (the state comes from the decoder)
without the full-resolution refiner, and nothing is read back or packed; the VP9 encoder gets transparent frames, and
nothing after the last window is decoded at all. No windows: nothing to matte, and the step is skipped. A rerun with
the same a-roll (path, size, mtime), the same windows and the same model is skipped too (work/matte-cache.json).
Model: $REEL_MACHINE_HOME/models/rvm_resnet50_fp32.torchscript (github.com/PeterL1n/RobustVideoMatting, release v1.0.0).
Run: PY pipeline/matte.py <project> [--full] [--from S --to S --out work/x.webm]
  --full       matte every frame (the old behaviour)
  --from/--to  a range, for tests
"""
import math
import os
import queue
import subprocess
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, MODELS, load_edit, project_arg  # noqa: E402
import cache as C  # noqa: E402

MODEL = os.path.join(MODELS, "rvm_resnet50_fp32.torchscript")
MODEL_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50_fp32.torchscript"
MODEL_SHA256 = "072adec3c75a1af773ec35d8b595612f8e3472b7a4b8a210684432b493376852"   # v1.0.0, 108,063,684 bytes
MARGIN = 0.2              # seconds matted before and after each window: the recurrent state settles there
MERGE_GAP = 0.5           # windows closer than this are one run (the state carries across, as in a full matte)
MATTE_VERSION = "matte-windows-2"   # bump when the recipe changes: the next run mattes again


def need_torch():
    try:
        import torch
    except ImportError:
        sys.exit("matte.py needs PyTorch: run `python3 setup/setup.py --matte`, or use pipeline/cutout.py instead")
    return torch


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_model():
    """the RVM model is loaded as code, so one already on disk must match the pinned checksum too: a file that differs
    is set aside (<name>.mismatch-<MM-DD-YY>, never deleted) and the next ensure_model() fetches it again"""
    if os.path.exists(MODEL) and sha256(MODEL) != MODEL_SHA256:
        aside, n = MODEL + time.strftime(".mismatch-%m-%d-%y"), 2
        while os.path.exists(aside):                 # a second mismatch the same day keeps the first one too
            aside, n = MODEL + time.strftime(f".mismatch-%m-%d-%y-{n}"), n + 1
        os.replace(MODEL, aside)
        print(f"the RVM model on disk did not match its checksum: set aside as {aside}", flush=True)


def ensure_model():
    """the RVM model, checked if it is here, else downloaded once and kept only when its bytes match the checksum"""
    verify_model()
    if not os.path.exists(MODEL):
        import urllib.request
        os.makedirs(os.path.dirname(MODEL), exist_ok=True)
        print("downloading the RVM model (GPL-3.0, ~100 MB) once ...", flush=True)
        part = MODEL + ".part"
        try:
            urllib.request.urlretrieve(MODEL_URL, part)
            if sha256(part) != MODEL_SHA256:
                sys.exit(f"the RVM model from {MODEL_URL} does not match its checksum, so it was not kept: "
                         "use pipeline/cutout.py instead")
            os.replace(part, MODEL)
        finally:
            if os.path.exists(part):
                os.remove(part)


W, H = 1080, 1920
DOWNSAMPLE = 0.4          # RVM's internal resolution for a 1080x1920 portrait: detail at the hair and cap brim


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def count(path, packets=False):
    """frames in a video: decoded, or (a-roll, VP9 without alt-ref frames) its packet count, which needs no decode"""
    what = "packets" if packets else "frames"
    return subprocess.run(["ffprobe", "-v", "error", f"-count_{what}", "-select_streams", "v:0", "-show_entries",
                           f"stream=nb_read_{what}", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()


def frames(project):
    return count(os.path.join(project, *project_out(project)), packets=True)


def project_out(project):
    return arg("--out", "assets/subject.webm").split("/")


def reads_cutout(fx_dir):
    """does this FX folder have a file that reads the cutout (a mask generator, a clone)?"""
    if not os.path.isdir(fx_dir):
        return False
    for name in sorted(os.listdir(fx_dir)):
        p = os.path.join(fx_dir, name)
        if os.path.isfile(p) and os.path.splitext(name)[1] in (".py", ".js", ".mjs", ".html"):
            with open(p, errors="ignore") as fh:
                if "subject.webm" in fh.read():
                    return True
    return False


def cutout_windows(E, project, total):
    """seconds where the cutout is seen or read: CUT_WINDOWS, then the window of every FX whose files read it"""
    def end(t):
        return total if t == "end" else float(t)
    wins = [(float(a), end(b)) for a, b in E.CUT_WINDOWS]
    wins += [(float(F["at"]), end(F["end"])) for F in getattr(E, "FX", [])
             if reads_cutout(os.path.join(project, "fx", F["id"]))]
    return wins


def frame_runs(wins, total_frames, fps=FPS, margin=MARGIN, gap=MERGE_GAP):
    """windows in seconds -> sorted [(first frame, end frame)) with the margin on both sides, merged when they touch
    or sit closer than gap, clamped to the video"""
    runs = []
    for a, b in sorted(wins):
        f0 = max(0, math.floor((a - margin) * fps + 1e-6))
        f1 = min(total_frames, math.ceil((b + margin) * fps - 1e-6))
        if f1 <= f0:
            continue
        if runs and f0 - runs[-1][1] <= round(gap * fps):
            runs[-1][1] = max(runs[-1][1], f1)
        else:
            runs.append([f0, f1])
    return [tuple(r) for r in runs]


def reader(cmd, size, q):
    """decode in a thread: frames wait in a short queue while the model works"""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        q.put(buf)
    q.put(None)
    p.wait()


def writer(enc, q, err):
    """feed the encoder in a thread; after a failure keep draining so the model loop never blocks"""
    while True:
        buf = q.get()
        if buf is None:
            return
        if not err:
            try:
                enc.stdin.write(buf)
            except OSError as e:
                err.append(e)


def main():
    project = project_arg()
    t0 = time.time()
    src = os.path.join(project, "assets", "aroll.mp4")
    out = os.path.join(project, *project_out(project))
    a, b = arg("--from"), arg("--to")
    if a or b or "--full" in sys.argv:
        total, runs = None, [(None, None)]                              # one run: the range, or every frame
    else:
        E = load_edit(project)
        total = int(count(src, packets=True))
        runs = frame_runs(cutout_windows(E, project, total / FPS), total)
        if not runs:
            print("matte: no CUT_WINDOWS and no effect reads the cutout: nothing to matte")
            return
        print("matte windows (frames):", ", ".join(f"{f0}-{f1 - 1}" for f0, f1 in runs),
              f"= {sum(f1 - f0 for f0, f1 in runs)} of {total}", flush=True)
    stamp_path = os.path.join(project, "work", "matte-cache.json")
    verify_model()                                 # before the key: a set-aside model must not key an old matte
    mkey = C.key(MATTE_VERSION, C.file_id(src), runs, C.file_id(MODEL) if os.path.exists(MODEL) else None, DOWNSAMPLE,
                 C.ffmpeg_version(), project_out(project), a, b)
    old = C.read_json(stamp_path, {})
    if old.get("key") == mkey and C.same_file(out, old):
        print(f"matte: unchanged (same a-roll, same windows) -> {out}")
        publish(project, out, a, b)
        return
    torch = need_torch()
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    ensure_model()
    model = torch.jit.load(MODEL, map_location=dev).eval()
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0",
                            "-crf", "18", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2", "-auto-alt-ref", "0",
                            out], stdin=subprocess.PIPE)
    wq, err = queue.Queue(8), []
    wt = threading.Thread(target=writer, args=(enc, wq, err), daemon=True)
    wt.start()
    blank = bytes(W * H * 4)                                            # transparent: outside the windows
    if total is None:
        cmd, keep = ["ffmpeg", "-v", "error", *(["-ss", a] if a else []), *(["-to", b] if b else []), "-i", src], None
    else:
        last = runs[-1][1]                                              # nothing after the last window is needed
        cmd, keep = ["ffmpeg", "-v", "error", "-i", src, "-frames:v", str(last)], np.zeros(last, bool)
        for f0, f1 in runs:
            keep[f0:f1] = True
    cmd += ["-fps_mode", "passthrough"]                                 # frame n out is frame n of the a-roll, always
    dq = queue.Queue(8)
    rt = threading.Thread(target=reader, args=(cmd + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"], W * H * 3, dq),
                          daemon=True)
    rt.start()
    n, matted, rec = 0, 0, [None] * 4                                   # one recurrent state from frame 0, as in a full run
    with torch.no_grad():
        while True:
            buf = dq.get()
            if buf is None:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            x = torch.from_numpy(rgb).to(dev).permute(2, 0, 1)[None].float() / 255
            if keep is None or keep[n]:
                _, pha, *rec = model(x, *rec, DOWNSAMPLE)
                alpha = (pha[0, 0].clamp(0, 1) * 255).round().byte().cpu().numpy()
                wq.put(np.dstack([rgb, alpha]).tobytes())
                matted += 1
            else:
                # outside the windows only the recurrent state is needed: RVM's own segmentation pass runs the same
                # backbone and decoder (the state comes out of the decoder) and skips the full-resolution refiner
                _, *rec = model(x, *rec, DOWNSAMPLE, True)
                wq.put(blank)
                if n % 8 == 7 and dev.type == "mps":
                    torch.mps.synchronize()                             # bound the queue of frames in flight
            n += 1
            if n % 150 == 0:
                print(f"  {n} frames  {n / (time.time() - t0):.1f} fps", flush=True)
    rt.join()
    if total is not None:
        if n != last:
            sys.exit(f"matte: the a-roll gave {n} frames, {last} needed: re-run cut.py, then this")
        while n < total:
            wq.put(blank)
            n += 1
    wq.put(None)
    wt.join()
    enc.stdin.close()
    enc.wait()
    if err or enc.returncode:
        sys.exit(f"matte: the encoder failed ({err[0] if err else enc.returncode})")
    print(f"matte: {matted} frames kept, {n} written in {time.time() - t0:.0f}s -> {out}")
    C.write_json(stamp_path, C.stamp(out, mkey))
    publish(project, out, a, b)
    if not a and not b:
        print(f"aroll frames {n} / matte frames {frames(project)}")


def publish(project, out, a, b):
    """the composition reads public/subject.webm: a copy of the full-length matte"""
    if not a and not b:
        import shutil
        shutil.copy(out, os.path.join(project, "public", "subject.webm"))


if __name__ == "__main__":
    main()
