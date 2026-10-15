#!/usr/bin/env python3
"""Mix: the processed voice + SFX (+ an optional music bed) -> <project>/public/master.wav

edit.SOUND = dict(
    sfx=[(time, "name", gain_db[, max_len]), ...],   # a name: a file in <project>/audio, the creator's own sounds in
                                                     # $REEL_MACHINE_HOME/sfx (favorites/fav-*, library/index.json lib-*),
                                                     # or a kit sound (audio/SFX.md); looked up in that order.
                                                     # time is when the sound HITS: its loudest moment lands there.
                                                     # dict(at=, name=, db=, max_len=, align="start") places by its start.
    music=None,                                      # off by default. "audio/<track>.wav": a track the creator owns
                                                     # or made with a connected generator. Most creators add music
                                                     # in their posting app instead.
    sections=[dict(src=(15.43, 46.94), at=0.0, fade_in=0.02), ...],   # music seconds -> video time, so drops land
                                                     # on lines; default: the track from 0, faded out at the end
    tape_stop=dict(after=0, dur=0.36),               # optional: the music after section 0 winds down like a tape stop
    automation=[(31.85, 32.57, -60), ...],           # bed level changes in dB (a drop out, a lift)
    bed_db=-14.5,                                    # bed level under the voice
)
edit.CARD_SFX holds the card sounds from the card agents' beat reports (card start + beat time, same hit rule).
The voice sits on top; the bed is carved at 2.8k and side-chain ducked; master -14 LUFS, -1.5 dBTP. The master is
measured after loudnorm and aimed again until it lands within 0.2 LU of -14 (loudnorm's one pass can miss by more than
the render QA allows on speech with hard transients); a master outside the QA window stops here, before any render.
Run: PY pipeline/mix.py <project>
"""
import difflib
import json
import os
import subprocess
import sys
import wave

import numpy as np
from scipy.signal import butter, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HOME, KIT, load_edit, project_arg, timeline  # noqa: E402
import style as ST  # noqa: E402

SR = 48000
SFX_HOME = os.path.join(HOME, "sfx")     # the creator's sounds: favorites/ (fav-*) and library/index.json (lib-*)
SFX_EXTS = (".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac")
GOAL, TP = -14.0, -1.5                   # the master: integrated LUFS and loudnorm's true-peak ceiling (dBTP)


def measure(path):
    """(integrated LUFS, true peak dBFS) of a file, measured the way qa.py measures the render"""
    r = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    s = r[r.rfind("Summary"):].splitlines()
    first = lambda k: float(next(ln for ln in s if ln.strip().startswith(k)).split()[1])  # noqa: E731
    return first("I:"), first("Peak:")


def loudness_ok(i, pk):
    """the render QA's loudness check (qa.py): -14 LUFS within 0.5, true peak at or under -1.0 dBFS"""
    return abs(i - GOAL) <= 0.5 + 1e-9 and pk <= -1.0


def next_target(target, measured, goal=GOAL):
    """where to aim loudnorm next: moved by its miss, inside loudnorm's own range (-70 to -5); unchanged when the
    master already measures within 0.2 LU of the goal"""
    miss = goal - measured
    if abs(miss) <= 0.2 + 1e-9:
        return target
    return round(max(-70.0, min(-5.0, target + miss)), 2)


def normalize(inputs, graph, label, out, tries=3):
    """the mix graph (its last pad [label]) through loudnorm into `out` (16-bit, 48 kHz), aimed again by the measured
    miss until the master measures within 0.2 LU of -14, at most `tries` passes -> (LUFS, true peak, passes)"""
    target = GOAL
    for n in range(1, tries + 1):
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                        f"{graph};[{label}]loudnorm=I={target}:TP={TP}:LRA=9[out]", "-map", "[out]", "-ar", str(SR),
                        "-c:a", "pcm_s16le", out], check=True)
        i, pk = measure(out)
        aim = next_target(target, i)
        if aim == target:
            break
        target = aim
    return i, pk, n


def read(path):
    """any audio file ffmpeg can open (wav, mp3, m4a, 24-bit, any rate) -> float stereo at 48 kHz"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<i2").astype(np.float64).reshape(-1, 2).T / 32768


def write(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x.T * 32767).astype("<i2").tobytes())


def ramp(n, a, b):
    return np.linspace(a, b, max(n, 1))


def sfx_library():
    """the creator's sound library by name: SFX_HOME/library/index.json, a list of {"name": "lib-...", "path": ...}
    pointing at the files where they live (nothing is copied)"""
    p = os.path.join(SFX_HOME, "library", "index.json")
    if not os.path.exists(p):
        return {}
    with open(p) as fh:
        return {e["name"]: e["path"] for e in json.load(fh)}


def sfx_path(project, name):
    """a sound by name, looked up in <project>/audio, then SFX_HOME/favorites, then the library index, then the kit.
    The creator's catalog keeps names unique (fav-, lib- prefixes), so the order only lets a project file win."""
    favorites, kit = os.path.join(SFX_HOME, "favorites"), os.path.join(KIT, "audio", "sfx")

    def find(d):
        return next((p for p in (os.path.join(d, name + ext) for ext in SFX_EXTS) if os.path.exists(p)), None)

    p = find(os.path.join(project, "audio")) or find(favorites)
    if p:
        return p
    library = sfx_library()
    if name in library:
        if not os.path.exists(library[name]):
            raise SystemExit(f"sfx {name} is in {os.path.join(SFX_HOME, 'library', 'index.json')} but its file is "
                             f"gone: {library[name]}. Fix that entry, or point it at the file's new place.")
        return library[name]
    p = find(kit)
    if p:
        return p

    def names(d):
        return sorted({os.path.splitext(f)[0] for f in os.listdir(d) if f.lower().endswith(SFX_EXTS)}) \
            if os.path.isdir(d) else []
    have = dict(kit=names(kit), favorites=names(favorites), library=sorted(library))
    close = difflib.get_close_matches(name, [n for v in have.values() for n in v], n=5, cutoff=0.6)
    raise SystemExit(f"sfx not found: {name}." + (f" Did you mean: {', '.join(close)}?" if close else "")
                     + f"\nKit sounds: {', '.join(have['kit'])}"
                     + f"\nFavorites ({favorites}): {', '.join(have['favorites']) or 'none'}"
                     + f"\nLibrary ({len(have['library'])}, {os.path.join(SFX_HOME, 'library', 'index.json')}): "
                     + (', '.join(have['library']) or 'none'))


def hit_offset(x):
    """seconds from a sound's start to its loudest moment (10 ms RMS envelope), so it lands on the event"""
    m = np.abs(x).mean(axis=0) ** 2
    k = max(1, int(0.010 * SR))
    env = np.convolve(m, np.ones(k) / k, mode="same")
    return int(np.argmax(env)) / SR


def sfx_items(items):
    """tuples (time, name, db[, max_len]) and dicts -> (time, name, db, max_len, align)"""
    for it in items:
        if isinstance(it, dict):
            yield it["at"], it["name"], it.get("db", -12), it.get("max_len"), it.get("align", "hit")
        else:
            yield it[0], it[1], it[2], (it[3] if len(it) > 3 else None), "hit"


def main():
    project = project_arg()
    E = load_edit(project)
    S = E.SOUND
    TOTAL = timeline(project)["total"]
    N = int(TOTAL * SR)
    music = np.zeros((2, N))
    work = os.path.join(project, "work")
    os.makedirs(work, exist_ok=True)

    track = S.get("music") or S.get("score")
    if track and not os.path.exists(os.path.join(project, track)):
        raise SystemExit(f"music track not found: {track} (SOUND['music'] is project-relative; None for no music)")
    if track:
        score = read(os.path.join(project, track))
        if not S.get("sections"):
            S["sections"] = [dict(src=(0.0, min(TOTAL, score.shape[1] / SR)), at=0.0, fade_out=1.2)]

        def place(src_a, src_b, at, fade_in=0.0, fade_out=0.0):
            seg = score[:, int(src_a * SR):int(src_b * SR)].copy()
            if fade_in:
                k = int(fade_in * SR); seg[:, :k] *= ramp(k, 0, 1) ** 2
            if fade_out:
                k = int(fade_out * SR); seg[:, -k:] *= ramp(k, 1, 0) ** 2
            i = int(at * SR)
            seg = seg[:, :N - i]
            music[:, i:i + seg.shape[1]] += seg

        for sec in S["sections"]:
            place(sec["src"][0], sec["src"][1], sec["at"], sec.get("fade_in", 0.0), sec.get("fade_out", 0.0))
        if S.get("tape_stop"):
            # playback speed falls 1 -> 0 over dur, reading on from where the section ended
            ts = S["tape_stop"]
            sec = S["sections"][ts["after"]]
            T, end_at = ts["dur"], sec["at"] + (sec["src"][1] - sec["src"][0])
            n = int(T * SR)
            t = np.arange(n) / SR
            pos = sec["src"][1] + t - t * t / (2 * T)
            idx = pos * SR
            i0 = np.floor(idx).astype(int)
            fr = idx - i0
            tape = score[:, i0] * (1 - fr) + score[:, i0 + 1] * fr
            tape *= ramp(n, 1, 0) ** 0.6
            tape = np.vstack([sosfilt(butter(2, 3500, "low", fs=SR, output="sos"), c) for c in tape])
            music[:, int(end_at * SR):int(end_at * SR) + n] += tape
        auto = np.zeros(N)
        tt = np.arange(N) / SR
        for a, b, db in S.get("automation", []):
            auto[(tt >= a) & (tt < b)] = db
        music *= 10 ** (auto / 20)
        music = np.vstack([sosfilt(butter(2, 45, "high", fs=SR, output="sos"), c) for c in music])
    write(os.path.join(work, ".music_cut.wav"), music)

    sfx = np.zeros((2, N))
    cache = {}
    for t0, name, db, max_len, align in sfx_items(list(S.get("sfx", [])) + list(E.CARD_SFX)):
        if name not in cache:
            x = read(sfx_path(project, name))
            cache[name] = (x, hit_offset(x))
        x, hit = cache[name]
        s = x * 10 ** (db / 20)
        if max_len:                                # optional max length, with a short fade so runs end cleanly
            k = int(max_len * SR)
            s = s[:, :k].copy()
            f = min(int(0.08 * SR), s.shape[1])
            s[:, -f:] *= np.linspace(1, 0, f)
        if align == "hit" and not max_len:
            t0 -= hit
        i = int(round(t0 * SR))
        if i < 0:                                  # a hit near 0: drop the lead-in that would fall before the start
            s, i = s[:, -i:], 0
        s = s[:, :max(0, N - i)]
        sfx[:, i:i + s.shape[1]] += s
    write(os.path.join(work, ".sfx.wav"), sfx)

    # the pack's sound.sfx: "light" sits every effect 3 dB lower; "dense" means more effects, not louder ones
    pack = os.path.join(project, "style", "style.json")
    fx_db = -1.0 + (-3.0 if ST.load(pack if os.path.exists(pack) else None)["sound"].get("sfx") == "light" else 0.0)
    voice = os.path.join(project, "assets", "voice.wav")
    inputs = ["-i", voice, "-i", os.path.join(work, ".music_cut.wav"), "-i", os.path.join(work, ".sfx.wav")]
    graph = ("[0:a]aformat=channel_layouts=stereo,apad=whole_dur=%.4f,asplit=2[v][sc];"
             "[1:a]volume=%.1fdB,equalizer=f=2800:t=q:w=1.4:g=-3[m];"          # carve the voice's presence band out of the bed
             "[m][sc]sidechaincompress=threshold=0.04:ratio=4:attack=20:release=320:makeup=1[md];"
             "[2:a]volume=%.1fdB[fx];"
             "[v][md][fx]amix=inputs=3:normalize=0:duration=longest,"
             "atrim=0:%.4f[pre]" % (TOTAL, S.get("bed_db", -14.5), fx_db, TOTAL))
    i, pk, n = normalize(inputs, graph, "pre", os.path.join(project, "public", "master.wav"))
    print(f"wrote public/master.wav I: {i} LUFS Peak: {pk} dBFS" + (f" ({n} loudnorm passes)" if n > 1 else ""))
    if not loudness_ok(i, pk):
        sys.exit(f"public/master.wav measures {i} LUFS, true peak {pk} dBFS: the render QA needs -14 LUFS within 0.5 "
                 "and a true peak at or under -1.0. Lower the loudest sound effects in SOUND and mix again.")


if __name__ == "__main__":
    main()
