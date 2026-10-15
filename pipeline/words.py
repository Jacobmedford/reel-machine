#!/usr/bin/env python3
"""Words: per-range word timings with faster-whisper (word timestamps), mapped onto the output timeline.

Each kept range is transcribed on its own so word times stay honest across the cuts. edit.PROMPT should name the
people, products and numbers in the script; edit.FIXES maps known mishearings to the real word.
Writes <project>/words.json: [{text, start, end, src}] (start/end on the output timeline, src = source time).

Cache: work/words-cache/<take>.json, one file per take, named by a sha1 of the take's first 1 MB, size and mtime (a
re-shot take saved under the old name gets a new file). Inside, each range's words are kept under the Whisper
settings and the prompt that made them, so a KEEP change transcribes only the ranges that are new, and an edited
PROMPT transcribes again. To correct Whisper by hand, edit the range's entry there (the old work/whisper/
fw_ranges.json is still read: its entries are imported once, and again whenever it is edited later). New ranges are
transcribed REEL_MACHINE_WHISPER_WORKERS at a time (default 2), each on Whisper's usual 4 threads, so a fresh range gives
exactly the words a lone run would.
Run: PY pipeline/words.py <project>
No speech: a transcript with no words at all stops with "no speech found in <take>" (the takes come from intake.json),
before anything is cut; a take with no words among takes that have them is named and the run goes on.
"""
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import env, load_edit, project_arg  # noqa: E402
from cut import plan  # noqa: E402
import cache as C  # noqa: E402

MODEL, COMPUTE, THREADS = "medium", "int8", 4        # THREADS: faster-whisper's default, the one every cached range used
WORKERS = max(1, int(env("WHISPER_WORKERS", "2")))
CACHE_VERSION = 1


def range_key(g):
    """a kept range's name in the cache: its source seconds, written the way the first cache wrote them"""
    return f"{g['s']}-{g['e']}"


def settings_key(E):
    """everything besides the audio that shapes Whisper's words: the model, its options and the prompt"""
    return C.key("words", MODEL, COMPUTE, THREADS, "en", E.PROMPT or None,
                 dict(word_timestamps=True, vad_filter=False, condition_on_previous_text=False))


def words_from_segments(segments):
    """Whisper's segments -> [[start, end, text]] (range seconds), with "1" + ".6%" joined into "1.6%" """
    ws = []
    for s in segments:
        for w in s.words:
            t = w.word.strip()
            if ws and t[:1] in "-." and len(t) > 1 and t[1:2].isdigit():
                ws[-1][2] += t
                ws[-1][1] = round(w.end, 3)
                continue
            ws.append([round(w.start, 3), round(w.end, 3), t])
    return ws


def out_words(ws, g, fixes):
    """one range's cached words on the output timeline (a word that runs past the range end stops at it)"""
    return [{"text": fixes.get(t, t), "start": round(a + g["out"], 3),
             "end": round(min(b, g["e"] - g["s"]) + g["out"], 3), "src": round(a + g["s"], 3)} for a, b, t in ws]


def missing(segs, entries):
    """the kept ranges that have no words in the cache yet, each once"""
    seen, out = set(), []
    for g in segs:
        k = range_key(g)
        if k not in entries and k not in seen:
            seen.add(k)
            out.append(g)
    return out


def new_cache(src):
    fid = C.file_id(src)
    return {"version": CACHE_VERSION, "src": fid["path"], "size": fid["size"], "mtime_ns": fid["mtime_ns"],
            "legacy_mtime_ns": None, "settings": {}, "ranges": {}}


def import_legacy(cache, entries, legacy, src):
    """bring in the old cache's ranges (work/whisper/fw_ranges.json, keyed by range only): once, and again each time
    that file is edited (a hand fix there wins). Only when it was written after the take last changed."""
    if not os.path.exists(legacy) or not C.legacy_trusted(legacy, src):
        return 0
    m = os.stat(legacy).st_mtime_ns
    if cache.get("legacy_mtime_ns") == m:
        return 0
    old = C.read_json(legacy, {})
    entries.update(old)
    cache["legacy_mtime_ns"] = m
    return len(old)


def transcribe(model, E, g, work):
    """one kept range, exactly as the kit always did: 16 kHz mono from ffmpeg, the samples handed to Whisper"""
    wav = os.path.join(work, f"range-{threading.get_ident()}.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{g['s']:.3f}", "-to", f"{g['e']:.3f}", "-i", E.SRC,
                    "-ar", "16000", "-ac", "1", wav], check=True)
    sr, pcm = wavfile.read(wav)                   # samples, not a path: av 19 broke faster-whisper's decoder
    out, _ = model.transcribe(pcm.astype(np.float32) / 32768.0, language="en", word_timestamps=True, vad_filter=False,
                              initial_prompt=E.PROMPT or None, condition_on_previous_text=False)
    return words_from_segments(out)


def takes(project, src):
    """the takes in the source, [(name, start, end)] in source seconds, from the project's intake.json; without one
    (or once edit.SRC names another file), the source itself is the one take"""
    d = C.read_json(os.path.join(project, "intake.json"), {}) or {}
    src = os.path.expanduser(src)
    if d.get("source") and os.path.realpath(os.path.join(project, d["source"])) == os.path.realpath(src):
        return [(t["name"], t["start"], t["start"] + t["duration"]) for t in d.get("takes", [])]
    return [(os.path.basename(src), 0.0, float("inf"))]


def no_speech(words, takes, keep, slack=0.05):
    """the takes the kept ranges cover in full that got no word. A take only partly kept is not judged: its words may
    be in the part left out"""
    def covered(a, b):
        return any(s - slack <= a and b <= e + slack for s, e in keep)
    return [n for n, a, b in takes if covered(a, b) and not any(a - slack <= w["src"] < b for w in words)]


def main():
    project = project_arg()
    E = load_edit(project)
    t0 = time.time()
    segs, _ = plan(E)
    work = os.path.join(project, "work", "whisper")
    store = os.path.join(project, "work", "words-cache")
    path = os.path.join(store, f"{C.take_id(E.SRC)}.json")
    cache = C.read_json(path) or new_cache(E.SRC)
    skey = settings_key(E)
    cache["settings"][skey] = dict(model=MODEL, compute_type=COMPUTE, cpu_threads=THREADS, prompt=E.PROMPT or None)
    entries = cache["ranges"].setdefault(skey, {})
    imported = import_legacy(cache, entries, os.path.join(work, "fw_ranges.json"), E.SRC)
    todo = missing(segs, entries)
    if todo or imported or not os.path.exists(path):
        C.write_json(path, cache)
    if todo:
        from concurrent.futures import ThreadPoolExecutor
        from faster_whisper import WhisperModel
        os.makedirs(work, exist_ok=True)
        n = min(WORKERS, len(todo))
        print(f"transcribing {len(todo)} of {len(segs)} ranges with Whisper medium, {n} at a time (the very first "
              "run downloads it, about 1.5 GB) ...", flush=True)
        model = WhisperModel(MODEL, compute_type=COMPUTE, cpu_threads=THREADS, num_workers=n)
        lock = threading.Lock()

        def one(g):
            ws = transcribe(model, E, g, work)
            with lock:                                              # saved as it goes: an interrupted run keeps its work
                entries[range_key(g)] = ws
                C.write_json(path, cache)

        with ThreadPoolExecutor(n) as ex:
            list(ex.map(one, sorted(todo, key=lambda g: g["s"] - g["e"])))     # longest first: the pool drains evenly
    words = []
    for g in segs:
        words += out_words(entries[range_key(g)], g, E.FIXES)
    json.dump(words, open(os.path.join(project, "words.json"), "w"), indent=1)
    print(" ".join(f"{w['text']}@{w['start']:.2f}" for w in words))
    print(f"words: {len(segs)} ranges ({len(segs) - len(todo)} cached, {len(todo)} transcribed), {time.time() - t0:.1f}s")
    silent = no_speech(words, takes(project, E.SRC), E.KEEP)
    if segs and not words:
        name = ", ".join(silent) or os.path.basename(E.SRC)
        sys.exit(f"no speech found in {name}: the transcript is empty, so there is nothing to cut. Check that the take "
                 "has its sound and that it is the right take.")
    for name in silent:
        print(f"no speech found in {name}: the other takes have words, this one none (leave it out of KEEP)")


if __name__ == "__main__":
    main()
