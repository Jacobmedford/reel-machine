#!/usr/bin/env python3
"""Cut: one 4K take -> the J-cut talking-head picture, the processed voice and timeline.json.

  - trims the dead air (edit.KEEP = audio ranges in source seconds)
  - J-cuts every join: the next line's audio leads its picture by J_LEAD
  - reframes the 4K into 9:16 shots (edit.FRAMES crops, edit.SHOTS on the output timeline), so every picture cut
    is also a framing change (a fake two-camera shoot); hide reframes under cards where you can
  - proves lip sync before it encodes anything: every picture piece must read the same source second as the
    audio playing over it (a join that rounds down to its frame once put 7s of picture 0.48s behind the voice)
Writes <project>/assets/aroll.mp4 (edit.CANVAS, 1080x1920 by default, 30fps CFR, keyframe every 10), assets/voice.wav (-16 LUFS), timeline.json.
Incremental: each picture piece is encoded once into work/pieces/ (closed 10-frame GOPs, no B-frames, crf 14)
under a key of the source's path, size and modification time plus the piece's exact seek, frame count, crop, canvas
and fps, and the pieces are joined by stream copy. A rerun encodes only the pieces whose key changed (a framing change
re-encodes that piece; a KEEP change re-encodes the pieces whose frames moved). The voice is made once per KEEP and
kept there too, so going back to an earlier KEEP costs a copy. REEL_MACHINE_JOBS sets how many pieces encode at once (default 2).
Run: PY pipeline/cut.py <project> [--plan]   (--plan prints the pieces and the sync table only)
     PY pipeline/cut.py <project> --source-cuts   (only the scan for hard cuts already in the source, cached in
     work/source_cuts.json; intake.py starts it in the background, so the first cut finds it done)
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, env, load_edit, project_arg, q  # noqa: E402
import cache as C  # noqa: E402

CACHE_VERSION = "cut-pieces-1"           # bump when the piece or voice recipe changes: every cached piece is remade
TIMESCALE = str(FPS * 512)               # 15360: every frame and every edit-list entry is a whole number of ticks
PIECE_CODEC = ["-c:v", "libx264", "-crf", "14", "-preset", "medium", "-g", "10", "-keyint_min", "10",
               "-pix_fmt", "yuv420p",    # the a-roll's own settings: pieces are the final picture, joined by copy
               "-bf", "0",               # no B-frames: a piece of 1 or 2 frames reorders differently, and its join
               # left decode timestamps uneven (ffmpeg then repeats and drops frames when it reads the a-roll back)
               "-video_track_timescale", TIMESCALE, "-movie_timescale", TIMESCALE]   # (mp4's default 1/1000 s edit
               # list rounds each piece's length to the millisecond, and the joins then drift by up to 10 ticks)
JOBS = max(1, int(env("JOBS", "2")))   # measured: 2 and 3 tie, 1 and 4 are 30% slower
KEEP_SPARE = 2.0                         # unused cached pieces may take up to this many times the a-roll's size


def source_cuts(E):
    """hard cuts already in the source: a phone app export (Edits, CapCut) is often pre-cut in the pauses.
    Frame-difference spikes at 90x160, cached in <project>/work/source_cuts.json"""
    import numpy as np
    path = os.path.join(E.PROJECT, "work", "source_cuts.json")
    d = C.read_json(path, {})
    if not os.path.exists(E.SRC) and d.get("src") == E.SRC:
        return d["cuts"]                                            # source moved away: --plan still reads the cache
    fid = C.file_id(E.SRC)
    if d.get("src") == E.SRC:
        if d.get("size") == fid["size"] and d.get("mtime_ns") == fid["mtime_ns"]:
            return d["cuts"]
        if "size" not in d and C.legacy_trusted(path, E.SRC):      # written before the cache recorded the source
            C.write_json(path, dict(d, size=fid["size"], mtime_ns=fid["mtime_ns"]), indent=None)
            return d["cuts"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", E.SRC, "-vf", f"fps={FPS},scale=90:160,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, 160, 90).astype(np.float32)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    cuts = [round((k + 1) / FPS, 4) for k in range(len(d))
            if d[k] > 18 and d[k] > 3 * np.median(d[max(0, k - 15):k + 15])]
    C.write_json(path, {"src": E.SRC, "size": fid["size"], "mtime_ns": fid["mtime_ns"], "cuts": cuts}, indent=None)
    return cuts


def leads(E):
    """the J-cut lead of every join. J_LEAD, unless the source already has a hard cut in that pause: then the
    outgoing picture runs right up to the source cut and stops there (a frame of the next take never shows), even if
    that puts the picture change a frame or two before the voice (an L-cut). Without this, a pre-cut phone take
    double-cuts at every join (a stutter on every join). edit.J_LEADS overrides, join by join: a number is that join's
    lead, None keeps this rule there (tighten.py writes 0 at the straight cuts it makes inside a line, None between)."""
    fixed = getattr(E, "J_LEADS", None)
    if fixed and len(fixed) != len(E.KEEP) - 1:
        sys.exit(f"J_LEADS has {len(fixed)} entries for {len(E.KEEP) - 1} joins: one per join between KEEP ranges")
    if fixed and all(x is not None for x in fixed):
        return list(fixed)
    cuts, out = source_cuts(E), []
    for k, ((_, e), (s, _)) in enumerate(zip(E.KEEP, E.KEEP[1:])):
        if fixed and fixed[k] is not None:
            out.append(fixed[k])
            continue
        near = [c for c in cuts if e - E.J_LEAD <= c <= e + E.J_LEAD + 1e-3]
        lead = E.J_LEAD
        if near:
            lead = min(E.J_LEAD, near[0] - e - 0.5 / FPS)
            if s + lead < near[-1] - 1e-3:
                sys.exit(f"join at source {e}: the next line's picture would start before the source cut at {near[-1]}; move KEEP")
        out.append(round(lead, 4))
    return out


def snap_shots(E, segs):
    """a framing change written next to a join belongs ON the join (leads move joins off the J_LEAD grid), and one
    written next to a hard cut already inside a kept line belongs on that cut (else: a cut, then a reframe a few
    frames later)"""
    joins = [q(g["vout"]) for g in segs[1:]]
    inside = [q(g["vout"] + c - g["vs"]) for g in segs for c in source_cuts(E) if g["vs"] < c < g["ve"]]
    out = []
    for t, f in E.SHOTS:
        j = min(joins, key=lambda x: abs(x - t)) if joins else t
        c = min(inside, key=lambda x: abs(x - t)) if inside else t
        if abs(j - t) <= E.J_LEAD + 0.15:          # leads run about -0.15 .. J_LEAD
            t = j
        elif abs(c - t) <= 0.3:
            t = c
        out.append((t, f))
    return out


def plan(E):
    """audio follows KEEP exactly; each picture join lands its lead later (leads())"""
    segs, off = [], 0.0
    n = len(E.KEEP)
    L = leads(E) if n > 1 else []
    for i, (s, e) in enumerate(E.KEEP):
        lin = L[i - 1] if i > 0 else 0.0
        lout = L[i] if i < n - 1 else E.HOLD
        segs.append(dict(s=s, e=e, out=off, vs=s + lin, ve=e + lout, vout=off + lin))
        off += e - s
    return segs, off


def pieces(E, segs):
    """split the picture at every join and SHOTS boundary -> [(out_start, out_end, src_start, framing)]"""
    total = segs[-1]["vout"] + (segs[-1]["ve"] - segs[-1]["vs"])
    bounds = sorted(set([q(g["vout"]) for g in segs] + [q(t) for t, _ in E.SHOTS] + [q(total)]))
    out = []
    for a, b in zip(bounds, bounds[1:]):
        g = [g for g in segs if q(g["vout"]) - 1e-6 <= a][-1]          # match on the frame-snapped join
        src = g["vs"] + (a - g["vout"])
        fr = [f for t, f in E.SHOTS if q(t) <= a + 1e-6][-1]
        out.append((a, b, src, fr))
    return out, total


def sync_table(segs, pcs):
    """picture source vs audio source at the start of every piece; returns the worst offset in seconds"""
    worst = 0.0
    rows = []
    for a, b, src, fr in pcs:
        g = [g for g in segs if g["out"] - 1e-6 <= a][-1]
        gp = [g for g in segs if q(g["vout"]) - 1e-6 <= a][-1]          # the segment the picture comes from
        note = ""
        if gp is not g and gp["out"] - a <= max(gp["out"] - gp["vout"], 0) + 1.0 / FPS:
            g, note = gp, "  (L-cut: picture a frame or two ahead of its line)"   # a lead under one frame or negative
        asrc = g["s"] + (a - g["out"])
        if a < segs[-1]["out"] + (segs[-1]["e"] - segs[-1]["s"]):      # only while someone is talking
            worst = max(worst, abs(src - asrc))
        rows.append(f"  {a:8.3f}-{b:8.3f} {fr:6s} picture {src:8.3f}  audio {asrc:8.3f}  offset {src - asrc:+.3f}{note}")
    return worst, rows


def piece_args(E, src, n, fr):
    """the ffmpeg arguments for one picture piece, all but the output: straight from the 4K original, exact frame count,
    encoded at the a-roll's final settings so the pieces join by stream copy"""
    w, h, x, y = E.FRAMES[fr]
    W, H = E.CANVAS
    return ["-ss", f"{src - 0.3 / FPS:.4f}", "-i", E.SRC, "-an",   # a third of a frame early: lands ON the frame, not one late
            "-vf", f"crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,fps={FPS},setsar=1,setpts=N/{FPS}/TB",
            "-frames:v", str(n), *PIECE_CODEC]                       # setpts: every piece starts at 0, a frame a tick


def piece_key(src_id, args):
    """a piece's cache key: the source (path, size, mtime), its exact ffmpeg arguments (seek, frame count, crop,
    canvas, fps, codec settings) and the ffmpeg build"""
    return C.key(CACHE_VERSION, C.ffmpeg_version(), src_id, args)


def voice_filter(segs):
    """keep ranges with 20-30ms fades at each join, then the voice chain"""
    fc, n = "", len(segs)
    for i, g in enumerate(segs):
        d = g["e"] - g["s"]
        fc += (f"[0:a]atrim={g['s']:.4f}:{g['e']:.4f},asetpts=PTS-STARTPTS,"
               f"afade=t=in:d=0.02,afade=t=out:st={d - 0.03:.4f}:d=0.03[a{i}];")
    fc += "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[ac];"
    # HPF 80, light denoise, -2 dB @250 (boxiness), +2 dB @3.2k (presence), 3:1 comp, limiter, -16 LUFS
    fc += ("[ac]highpass=f=80,afftdn=nr=8:nf=-45,equalizer=f=250:t=q:w=1.2:g=-2,"
           "equalizer=f=3200:t=q:w=1.0:g=2,acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2,"
           "alimiter=limit=0.89:level=false,loudnorm=I=-16:TP=-2:LRA=9,aresample=48000[ao]")
    return fc


def voice_args(E, segs):
    return ["-i", E.SRC, "-filter_complex", voice_filter(segs), "-map", "[ao]", "-ac", "2", "-c:a", "pcm_s16le"]


def ffmpeg_to(args, out, fmt):
    """run ffmpeg into a temporary file next to out, then rename: a failed run never leaves a half-written file"""
    tmp = out + ".part"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-f", fmt, tmp], check=True)
    os.replace(tmp, out)


def packets(path):
    """video frame count from the packet count (no decode): every packet is one frame in an H.264 a-roll"""
    out = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return out.strip()


def packet_times(text):
    """ffprobe's csv lines "pts,dts" -> [(pts, dts)], negative decode times kept, unknown ones skipped"""
    out = []
    for line in text.split():
        parts = line.strip(",").split(",")
        if len(parts) == 2 and all(p.lstrip("-").isdigit() for p in parts):
            out.append((int(parts[0]), int(parts[1])))
    return out


def uneven(rows, frames, tick):
    """what is wrong with a joined a-roll's timestamps, or "" when it has the planned frame count, starts at pts 0
    and every presentation and decode timestamp steps exactly one frame (tick)"""
    pts, dts = sorted(p for p, _ in rows), [d for _, d in rows]
    steps = {b - a for a, b in zip(pts, pts[1:])} | {b - a for a, b in zip(dts, dts[1:])}
    if len(pts) != frames or (pts and pts[0] != 0) or steps - {tick}:
        return f"{len(pts)} frames, first pts {pts[0] if pts else None}, steps {sorted(steps)}"
    return ""


def timing(path):
    """the a-roll's packet timestamps (no decode)"""
    return packet_times(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                        "packet=pts,dts", "-of", "csv=p=0", path], capture_output=True, text=True).stdout)


def join_list(names):
    """the concat demuxer's list: piece names relative to the list file (hex names, nothing to quote)"""
    return "".join(f"file '{n}'\n" for n in names)


def prune(store, used, budget):
    """drop the least recently used pieces (and voices) that are not in this cut once the unused ones outgrow the
    budget"""
    entries = []
    for name in os.listdir(store):
        if name.endswith((".mp4", ".wav")):
            st = os.stat(os.path.join(store, name))
            entries.append((name, st.st_size, st.st_mtime))
    gone = C.lru_evict(entries, set(used), budget)
    for name in gone:
        os.remove(os.path.join(store, name))
    return len(gone)


def main():
    project = project_arg()
    E = load_edit(project)
    if "--source-cuts" in sys.argv:
        cuts = source_cuts(E)
        print(f"source cuts: {len(cuts)} already in the source ({os.path.join(project, 'work', 'source_cuts.json')})")
        return
    segs, total_audio = plan(E)
    E.SHOTS = snap_shots(E, segs)
    print("leads", [round(g["vout"] - g["out"], 3) for g in segs[1:]])
    pcs, total = pieces(E, segs)
    worst, rows = sync_table(segs, pcs)
    print("\n".join(rows))
    if worst > 0.5 / FPS:
        sys.exit(f"LIP SYNC: a picture piece is {worst:.3f}s off its audio. Fix KEEP/SHOTS before cutting.")
    print("lip sync: every piece reads the same source second as its audio")
    if "--plan" in sys.argv:
        return
    import time
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    assets, work = os.path.join(project, "assets"), os.path.join(project, "work")
    store = os.path.join(work, "pieces")
    os.makedirs(assets, exist_ok=True)
    os.makedirs(store, exist_ok=True)
    src_id = C.file_id(E.SRC)
    manifest_path = os.path.join(work, "cut-cache.json")
    manifest = C.read_json(manifest_path, {})
    aroll, voice = os.path.join(assets, "aroll.mp4"), os.path.join(assets, "voice.wav")

    # ---- picture: every piece cut straight from the 4K original once, exact frame counts, kept in work/pieces/
    jobs = []
    for a, b, src, fr in pcs:
        n = round((b - a) * FPS)
        args = piece_args(E, src, n, fr)
        jobs.append((piece_key(src_id, args) + ".mp4", args, n))
    names = [name for name, _, _ in jobs]
    akey = C.key(CACHE_VERSION, names)
    aroll_done = manifest.get("aroll", {}).get("key") == akey and C.same_file(aroll, manifest.get("aroll"))
    todo = {} if aroll_done else {name: (args, n) for name, args, n in jobs
                                  if not os.path.exists(os.path.join(store, name))}

    # ---- voice: made once per KEEP (kept in work/pieces/ too, so going back to an earlier KEEP costs a copy)
    vargs = voice_args(E, segs)
    vkey = C.key(CACHE_VERSION, C.ffmpeg_version(), src_id, vargs)
    vname = f"voice-{vkey}.wav"
    voice_done = manifest.get("voice", {}).get("key") == vkey and C.same_file(voice, manifest.get("voice"))
    voice_kept = os.path.exists(os.path.join(store, vname))

    def encode(name):
        args, n = todo[name]
        ffmpeg_to(args, os.path.join(store, name), "mp4")
        got = packets(os.path.join(store, name))
        if got != str(n):
            print(f"piece {name[:12]}: {got} frames, {n} planned (the source ended early?)")

    with ThreadPoolExecutor(JOBS) as ex:
        vjob = None if voice_done or voice_kept else ex.submit(ffmpeg_to, vargs, os.path.join(store, vname), "wav")
        list(ex.map(encode, sorted(todo, key=lambda k: -todo[k][1])))      # longest first: the pool drains evenly
        if vjob:
            vjob.result()
    if not voice_done:
        shutil.copyfile(os.path.join(store, vname), voice + ".part")
        os.replace(voice + ".part", voice)
    now = time.time()
    have = [name for name in names + [vname] if os.path.exists(os.path.join(store, name))]
    for name in have:
        os.utime(os.path.join(store, name), (now, now))                 # last used: the pruning order

    # ---- join by stream copy (no second encode); skipped when the same pieces made the a-roll already
    if not aroll_done:
        with open(os.path.join(store, "join.txt"), "w") as fh:
            fh.write(join_list(names))
        ffmpeg_to(["-f", "concat", "-safe", "0", "-i", os.path.join(store, "join.txt"), "-c", "copy",
                   "-movie_timescale", TIMESCALE, "-movflags", "+faststart"], aroll, "mp4")
        bad = uneven(timing(aroll), sum(k for _, _, k in jobs), int(TIMESCALE) // FPS)
        if bad:
            sys.exit(f"aroll.mp4 came out uneven ({bad}): delete work/pieces/ and run cut.py again")
        manifest["aroll"] = C.stamp(aroll, akey)
    if not voice_done:
        manifest["voice"] = C.stamp(voice, vkey)
    C.write_json(manifest_path, manifest)
    budget = KEEP_SPARE * sum(os.path.getsize(os.path.join(store, n)) for n in set(have))
    pruned = prune(store, have, budget)

    cuts = [q(g["vout"]) for g in segs[1:]]
    reframes = [q(t) for t, _ in E.SHOTS[1:] if all(abs(q(t) - c) > 1e-6 for c in cuts)]
    json.dump({"fps": FPS, "total_audio": round(total_audio, 4), "total": round(q(total), 4),
               "keep": [dict(src_in=g["s"], src_out=g["e"], out=round(g["out"], 4),
                             picture_out=round(g["vout"], 4)) for g in segs],
               "picture_cuts": cuts, "reframes": reframes,
               "shots": [dict(t=q(t), frame=f) for t, f in E.SHOTS],
               "pieces": [dict(out_start=a, out_end=b, src=round(s, 4), frame=f) for a, b, s, f in pcs]},
              open(os.path.join(project, "timeline.json"), "w"), indent=1)
    fr = packets(aroll)
    print(f"audio {total_audio:.3f}s  picture {total:.3f}s ({round(q(total) * FPS)} frames expected, aroll has {fr})")
    print("picture cuts", cuts)
    print("reframes", reframes)
    print(f"pieces: {len(names)} ({len(names) - len(todo)} cached, {len(todo)} encoded"
          f"{f', {pruned} old ones pruned' if pruned else ''}), voice "
          f"{'unchanged' if voice_done else 'from the cache' if voice_kept else 'made'}, "
          f"{time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
