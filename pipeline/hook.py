#!/usr/bin/env python3
"""Hook: the parts of render.py --hook that need no renderer (so they are tested on their own).

  hook_end   where the hook render stops: HOOK_END in edit.py, else the end of the first sentence plus the hold
  truncate   the built composition cut at that frame: the root, every clip and TOTAL end there; clips that start at
             or after it go, and so does the audio element (render.py lays the matching slice of master.wav back on)
  link_tree  public/ mirrored into work/hook/ with hard links: the renderer refuses symlinks that leave the project,
             and a mirror of links costs no disk
"""
import math
import os
import re
import shutil

FPS = 30
HOOK_MAX = 12.0          # a first "sentence" longer than this is not a hook: stop at the last word inside it (s)
DEFAULT = 3.0            # no words yet: the first three seconds
JOIN_SNAP = 0.35         # a cut this close after the sentence's last word is where its sound really ends (s)
END_MARKS = (".", "?", "!")
TAG = re.compile(r"<(video|audio)\b([^>]*)>(\s*</\1\s*>)?", re.I | re.S)


def _frame(t):
    return round(t * FPS) / FPS


def _up(t):
    return math.ceil(t * FPS - 1e-6) / FPS


def _down(t):
    return math.floor(t * FPS + 1e-6) / FPS


def first_sentence(words, cap=HOOK_MAX):
    """index of the first sentence's last word; with no sentence end inside the cap, of the last word inside it"""
    last = 0
    for k, w in enumerate(words):
        if w["end"] > cap + 1e-6:
            break
        last = k
        if w["text"].rstrip("\"')]”’").endswith(END_MARKS):
            return k
    return last


def hook_end(words, hold, total, override=None, joins=None):
    """where the hook render stops, on a 30 fps frame, never past total, never under one frame.
    override (HOOK_END in edit.py) wins. Else the end of the first sentence's last word plus hold; when the next line
    starts inside the hold (a tight cut), the hook stops at the sentence's own end instead, so it never ends inside a
    word. joins: the cut's audio joins (output seconds, timeline.json keep[].out): whisper's word times run a little
    off, so a join just after the last word (tighten.py cuts the pause there) is where the sentence really ends, and
    the hook ends on that cut."""
    one = 1 / FPS
    if override is not None:
        return min(max(_frame(override), one), total)
    if not words:
        return min(DEFAULT, total)
    k = first_sentence(words)
    t = words[k]["end"]
    nxt = words[k + 1]["start"] if k + 1 < len(words) else None
    near = [j for j in (joins or []) if words[k]["start"] <= j <= t + JOIN_SNAP]
    if near:
        cut = _frame(min(near, key=lambda j: abs(j - t)))
        end = cut if nxt is None or cut + hold > nxt else _frame(cut + hold)
    elif nxt is not None and t + hold > nxt:          # the next line starts inside the hold
        end = _up(t)
        if end > nxt:
            end = _down(nxt)
    else:
        end = _frame(t + hold)
        if nxt is not None and end > nxt:
            end = _down(nxt)
    return min(max(end, one), total)


def dur_attr(frames):
    """data-duration for a clip of this many frames: the renderer rounds duration x 30 up, so 137 frames is 4.5666"""
    return f"{math.floor(frames * 10000 / FPS + 1e-9) / 10000:.4f}"


def _attr(attrs, name):
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def _set(attrs, name, value):
    return re.sub(rf'(\b{name}=")[^"]*(")', rf"\g<1>{value}\g<2>", attrs, count=1)


def truncate(doc, end):
    """the composition HTML cut at `end` seconds (a frame time). Pure: returns the new document."""
    ef = round(end * FPS)

    def gone(attrs):
        """a dropped clip leaves a hidden stand-in with its id (no class, so no style paints it): an effect's script
        that looks the element up still finds one"""
        i = _attr(attrs, "id")
        return f'<div id="{i}" hidden></div>' if i else ""

    def media(m):
        tag, attrs, close = m.group(1).lower(), m.group(2), m.group(3)
        if tag == "audio" and close:
            return gone(attrs)                          # the sound is master.wav, laid on after the render
        s, d = _attr(attrs, "data-start"), _attr(attrs, "data-duration")
        if s is None or d is None:
            return m.group(0)
        sf = round(float(s) * FPS)                      # clip_start() writes 2 ms early: this is its frame
        if sf >= ef and close:
            return gone(attrs)
        if sf + math.ceil(float(d) * FPS - 1e-6) <= ef:
            return m.group(0)
        return f"<{m.group(1)}{_set(attrs, 'data-duration', dur_attr(max(1, ef - sf)))}>{close or ''}"
    out = TAG.sub(media, doc)
    root = re.search(r'<[a-z]+\b[^>]*\bdata-composition-id="[^"]*"[^>]*>', out)       # attributes in any order
    if not root or _attr(root.group(0), "data-duration") is None:
        raise ValueError("no composition root with a data-duration: is this a built index.html?")
    out = out[:root.start()] + _set(root.group(0), "data-duration", dur_attr(ef)) + out[root.end():]
    return re.sub(r"(\bTOTAL\s*=\s*)[0-9.]+", rf"\g<1>{end:.4f}", out, count=1)


def link_tree(src, dst, skip=()):
    """mirror src into dst: real folders, every file a hard link (a copy when linking fails, another disk). Nothing
    may ever open a linked file for writing: it is the original."""
    skip = {os.path.normpath(s) for s in skip}
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        dirs[:] = [d for d in dirs if os.path.normpath(os.path.join(rel, d)) not in skip]
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            r = os.path.normpath(os.path.join(rel, f))
            if r in skip:
                continue
            a, b = os.path.join(root, f), os.path.join(dst, r)
            try:
                os.link(a, b)
            except OSError:
                shutil.copy2(a, b)
