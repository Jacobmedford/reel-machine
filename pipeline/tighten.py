#!/usr/bin/env python3
"""Tighten: the no-dead-air rule on the first cut. Every pause of 0.18 s or more inside a kept line is cut down to
about 0.1 s of air (0.05 s after the last sound, 0.045 s before the next) with a straight cut, so the next phrase hits
right after the last one and the lips stay in sync across the jump.

Pauses come from a speech map of the source audio, never from whisper (its word times run 0.2 to 0.6 s off inside
continuous speech): a 10 ms RMS envelope (5 ms hop), broadband (70 Hz high-pass) plus a 4-8 kHz band that catches the
sibilants and breathy onsets a broadband floor hides. Speech is every frame 25 dB over the range's own noise floor
(its 8th percentile, capped at the take's typical floor + 6 dB so a range with no silence in it can't lift the floor
into the voice), runs closer than 0.1 s are one island, and each island grows up to 0.2 s through frames 15 dB over the
floor (soft word tails). A lip click before a word reads as speech on the high band: it makes a pause look shorter,
never longer, so the error is always the safe one. A pause that a designed sound will fill (a key press under a card)
is not dead air: --skip that line.

Run: PY pipeline/tighten.py <project> [--apply] [--force] [--skip 2,5] [--min-gap 0.18] [--leave 0.10]
  (no flag)  the plan: every pause, each cut it would make, the new KEEP and J_LEADS. Changes nothing.
  --apply    writes the plan into edit.py: KEEP (comments kept), J_LEADS (0 at every new cut, a straight cut; None at
             the joins between lines, the kit's own J-cut there) and SHOTS times moved with the cut. The old file stays
             as edit-pre-tighten-<n>.py. Refused once beats exist (CAPS, FX, CARDS, ...), whose output times would go
             stale, unless --force.
  --skip     KEEP indices (K00 = 0) whose pauses stay as they are
Then: PY pipeline/cut.py <project> --plan, the full cut, words.py, and preview.py first-cut for the pace check.
"""
import ast
import datetime
import io
import math
import os
import subprocess
import sys
import tokenize

import numpy as np
from scipy.signal import butter, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS  # noqa: E402

SR = 48000
HOP, WIN = 0.005, 0.010        # envelope hop and window (s)
MARGIN = 0.6                   # audio either side of a range, for its noise floor (s)
HI, LO, GROW = 25.0, 15.0, 0.20  # speech and soft-edge thresholds over the floor (dB); how far an edge may grow (s)
HF_EXTRA = 4.0                 # the 4-8 kHz band needs this much more (dB)
JOIN = 0.10                    # speech runs closer than this are one island (s)
MIN_ISLAND = 0.03              # shorter runs are noise (s)
FLOOR_SPREAD = 6.0             # a range's floor may sit at most this far over the take's median floor (dB)
GUARD = 0.04                   # a cut never lands closer than this to an onset or an offset (s)
MIN_PIECE = 2 / FPS            # never leave a piece under two frames
SHOW = 0.09                    # the plan lists every pause from this long, so near misses show (s)
BEATS = ("CAPS", "HOOK", "BEHIND", "CUT_WINDOWS", "BW", "CARDS", "FX", "OVERLAYS", "BOXES", "GRADES", "END_CARD",
         "CARD_SFX")

_HP = butter(4, 70, "highpass", fs=SR, output="sos")
_BAND = butter(4, [4000, 8000], "bandpass", fs=SR, output="sos")


# ------------------------------------------------------------------ the speech map
def _decode(path, a, b):
    """mono float samples of [a, b] seconds of any file ffmpeg reads (the source take, a WAV in the tests)"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.4f}", "-t", f"{b - a:.4f}", "-i", path, "-vn",
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def envelope(path, a, b):
    """(t, broadband dB, 4-8 kHz dB): 10 ms RMS every 5 ms over [a, b], t at each window's centre"""
    x = _decode(path, a, b)
    hop, win = int(HOP * SR), int(WIN * SR)
    if len(x) < win:
        x = np.pad(x, (0, win - len(x)))
    n = 1 + (len(x) - win) // hop
    starts = np.arange(n) * hop

    def env(y):
        cs = np.concatenate([[0.0], np.cumsum(y * y)])
        return 10 * np.log10(np.maximum(cs[starts + win] - cs[starts], 0.0) / win + 1e-12)
    return a + starts / SR + WIN / 2, env(sosfilt(_HP, x)), env(sosfilt(_BAND, x))


def floors(bb, hb):
    return float(np.percentile(bb, 8)), float(np.percentile(hb, 8))


def _runs(mask):
    """[first, last] index of every run of True"""
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return [[int(a), int(b) - 1] for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))]


def islands(t, bb, hb, floor, hfloor):
    """speech islands [(on, off)] from an envelope and its floors"""
    core = (bb > floor + HI) | (hb > hfloor + HI + HF_EXTRA)
    weak = (bb > floor + LO) | (hb > hfloor + LO + HF_EXTRA)
    merged = []
    for a, b in _runs(core):
        if merged and t[a] - t[merged[-1][1]] < JOIN:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in (m for m in merged if t[m[1]] - t[m[0]] >= MIN_ISLAND):
        a2, b2 = a, b
        while a2 > 0 and weak[a2 - 1] and t[a] - t[a2 - 1] <= GROW:
            a2 -= 1
        while b2 + 1 < len(t) and weak[b2 + 1] and t[b2 + 1] - t[b] <= GROW:
            b2 += 1
        on, off = float(t[a2]) - HOP / 2, float(t[b2]) + HOP / 2
        if out and on <= out[-1][1]:
            out[-1][1] = max(out[-1][1], off)
        else:
            out.append([on, off])
    return [(round(on, 4), round(off, 4)) for on, off in out]


def speech_islands(wav_path, start, end, floor=None):
    """the speech islands [(on, off)] (source seconds) that overlap [start, end] of an audio or video file.
    floor: (broadband dB, 4-8 kHz dB) to use instead of the range's own"""
    t, bb, hb = envelope(wav_path, max(0.0, start - MARGIN), end + MARGIN)
    fl = floor or floors(bb, hb)
    return [x for x in islands(t, bb, hb, *fl) if x[1] > start and x[0] < end]


# ------------------------------------------------------------------ the rule
def pads(leave, min_gap):
    """the air left at a cut, split 0.05 after the last sound / 0.045 before the next (for leave = 0.1)"""
    out, inn = 0.5 * leave, 0.45 * leave
    if inn < GUARD:
        raise ValueError(f"leave {leave}: at least {GUARD / 0.45:.2f} s, or a cut clips the next word")
    if min_gap < out + inn + 1 / FPS:
        raise ValueError(f"min_gap {min_gap}: a pause must be longer than the air it keeps plus a frame "
                         f"({out + inn + 1 / FPS:.3f} s for leave {leave})")
    return out, inn


def _up(x):
    return math.ceil(round(x * 1000, 6)) / 1000


def _down(x):
    return math.floor(round(x * 1000, 6)) / 1000


def split(s, e, isl, min_gap, pad_out, pad_in, skip=False):
    """one KEEP range -> its pieces and every pause in it (gap, the cut or why not)"""
    edges = [x for r in isl for x in r]
    clear = lambda x: all(abs(x - y) >= GUARD - 1e-9 for y in edges)          # noqa: E731
    pieces, pauses, a = [], [], s
    for (_, off), (on, _) in zip(isl, isl[1:]):
        gap = on - off
        p = dict(off=off, on=on, gap=round(gap, 3), cut=None, why="")
        if gap < min_gap - 1e-9:
            p["why"] = f"under {min_gap:g} s"
        elif skip:
            p["why"] = "skipped (--skip)"
        else:
            b = _up(max(off + pad_out, a + MIN_PIECE))                   # never leave a scrap under two frames
            nxt = _down(min(on - pad_in, e - MIN_PIECE))
            if nxt - b < 1 / FPS - 1e-9:
                p["why"] = "too short once the air is kept"
            elif not (clear(b) and clear(nxt)) or not (s < b < nxt < e):
                p["why"] = "no clean place to cut"
            else:
                pieces.append((a, b))
                p["cut"] = (b, nxt)
                a = nxt
        pauses.append(p)
    pieces.append((a, e))
    return pieces, pauses


def plan(keep, wav_path, min_gap=0.18, leave=0.10, skip=()):
    """the whole pass: {keep, cuts, line_of (old index of every new piece), lines (per range: islands, pauses)}"""
    pad_out, pad_in = pads(leave, min_gap)
    envs = [envelope(wav_path, max(0.0, s - MARGIN), e + MARGIN) for s, e in keep]
    fl = [floors(bb, hb) for _, bb, hb in envs]
    cap = (float(np.median([f[0] for f in fl])) + FLOOR_SPREAD, float(np.median([f[1] for f in fl])) + FLOOR_SPREAD) if fl else (0, 0)
    lines = []
    for i, ((s, e), (t, bb, hb), (f0, f1)) in enumerate(zip(keep, envs, fl)):
        isl = [x for x in islands(t, bb, hb, min(f0, cap[0]), min(f1, cap[1])) if x[1] > s and x[0] < e]
        pieces, pauses = split(s, e, isl, min_gap, pad_out, pad_in, skip=i in skip)
        lines.append(dict(i=i, s=s, e=e, islands=isl, pieces=pieces, pauses=pauses, floor=round(min(f0, cap[0]), 1)))
    new = [p for L in lines for p in L["pieces"]]
    cuts = [L["pieces"][k][1] for L in lines for k in range(len(L["pieces"]) - 1)]
    return dict(keep=new, cuts=cuts, lines=lines, line_of=[L["i"] for L in lines for _ in L["pieces"]])


def tighten_keep(keep, wav_path, min_gap=0.18, leave=0.10, skip=()):
    """KEEP (source seconds) -> (the new KEEP, the source time of every new in-line cut: the end of the piece before
    it). Where those cuts join, J_LEADS must be 0 (a straight cut)."""
    P = plan([tuple(r) for r in keep], wav_path, min_gap, leave, skip)
    return P["keep"], P["cuts"]


# ------------------------------------------------------------------ times on the output timeline
def starts(keep):
    out, t = [], 0.0
    for s, e in keep:
        out.append(t)
        t += e - s
    return out, t


def remap(t, old, new, line_of):
    """an output time on the old cut -> the same moment on the new one (inside a removed pause: on the cut)"""
    O, total = starts(old)
    N, total_new = starts(new)
    if t <= 0:
        return 0.0
    if t >= total - 1e-9:                                           # the hold after the last word
        return round(t - total + total_new, 4)
    i = max(k for k in range(len(old)) if O[k] <= t + 1e-9)
    src = old[i][0] + (t - O[i])
    js = [j for j, l in enumerate(line_of) if l == i]
    for j in js:
        a, b = new[j]
        if src < a - 1e-9:
            return round(N[j], 4)
        if src <= b + 1e-9:
            return round(N[j] + src - a, 4)
    j = js[-1]
    return round(N[j] + new[j][1] - new[j][0], 4)


def join_air(lines):
    """[(index of the line before the join, seconds of air at the join: its tail + the next line's head)]"""
    out = []
    for A, B in zip(lines, lines[1:]):
        if A["islands"] and B["islands"]:
            out.append((A["i"], max(0.0, A["e"] - A["islands"][-1][1]) + max(0.0, B["islands"][0][0] - B["s"])))
    return out


# ------------------------------------------------------------------ edit.py
def _comments(text):
    """{line number: comment text without '#'}"""
    out = {}
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            out[tok.start[0]] = tok.string[1:].strip()
    return out


def _assign(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
    return None


def _num(x):
    return f"{x:.3f}" if abs(round(x, 3) - x) < 1e-9 else repr(x)


def leads_after(E, P):
    """J_LEADS for the new KEEP: 0.0 at every new cut, the old join's own value (None: the kit's lead) elsewhere"""
    old = list(getattr(E, "J_LEADS", None) or [])
    L = P["line_of"]
    return [0.0 if L[j] == L[j + 1] else (old[L[j]] if old else None) for j in range(len(L) - 1)]


def apply(project, E, P, force=False):
    busy = [k for k in BEATS if getattr(E, k, None)] + (["SOUND"] if (getattr(E, "SOUND", None) or {}).get("sfx") else [])
    if busy and not force:
        sys.exit(f"edit.py already has {', '.join(busy)}: their times are on the output timeline and would go stale. "
                 "tighten.py is for the first cut, before beats. Rerun with --force to write KEEP anyway, then move "
                 "every output time yourself.")
    path = os.path.join(project, "edit.py")
    text = open(path, encoding="utf-8").read()
    tree = ast.parse(text)
    node = _assign(tree, "KEEP")
    try:
        literal = [tuple(r) for r in ast.literal_eval(node.value)] if node else None
    except ValueError:
        literal = None
    if literal != [tuple(r) for r in E.KEEP]:
        sys.exit("KEEP in edit.py isn't a plain list of (start, end) pairs: paste the KEEP and J_LEADS above by hand")
    lines = text.splitlines(keepends=True)
    notes = _comments(text)
    old_note = {k: notes.get(el.end_lineno, "") for k, el in enumerate(node.value.elts)}
    nl = "\n"
    when = datetime.date.today().strftime("%m-%d-%y")
    body = [f"# tighten.py {when}: {len(P['cuts'])} pauses of 0.18 s or more inside a line cut to about 0.1 s of air, "
            f"straight cuts there (J_LEADS 0){nl}",
            lines[node.lineno - 1][:node.col_offset] + "KEEP = [" + (f"   # {notes[node.lineno]}" if node.lineno in notes and node.lineno != node.value.elts[0].lineno else "") + nl]
    for j, (a, b) in enumerate(P["keep"]):
        k = P["line_of"][j]
        first = j == 0 or P["line_of"][j - 1] != k
        note = old_note[k] if first else ("  ... the rest of the line after a pause (a straight cut)")
        item = f"    ({_num(a)}, {_num(b)}),"
        body.append(item + (" " * max(1, 26 - len(item)) + f"# {note}" if note else "") + nl)
    body.append("]" + nl)
    J = leads_after(E, P)
    jl = (f"J_LEADS = [{', '.join('None' if x is None else _num(x) for x in J)}]   # 0: a straight cut inside a line "
          f"(lips stay in sync); None: the kit's J-cut between lines{nl}")
    edits = [(node.lineno - 1, node.end_lineno, body)]                    # (first line, end line, new lines)
    jnode = _assign(tree, "J_LEADS")
    if jnode:
        edits.append((jnode.lineno - 1, jnode.end_lineno, [jl]))
    else:
        body.append(jl)
    shots = _assign(tree, "SHOTS")
    moved = []
    if shots:
        try:
            ok = isinstance(shots.value, ast.List) and all(
                isinstance(el, ast.Tuple) and isinstance(el.elts[0], ast.Constant) for el in shots.value.elts)
        except (AttributeError, IndexError):
            ok = False
        if ok:
            for el in shots.value.elts:
                c = el.elts[0]
                moved.append((c.lineno, c.col_offset, c.end_col_offset,
                              f"{remap(float(c.value), list(E.KEEP), P['keep'], P['line_of']):.3f}"))
        else:
            print("NOTE: SHOTS isn't a plain list, so its times were not moved: check it against the new cut")
    for ln, c0, c1, val in sorted(moved, reverse=True):                   # in place, last first: offsets stay valid
        s = lines[ln - 1]
        lines[ln - 1] = s[:c0] + val + s[c1:]
    for a, b, new in sorted(edits, key=lambda x: x[0], reverse=True):
        lines[a:b] = new
    out = "".join(lines)
    n = 1
    while os.path.exists(os.path.join(project, f"edit-pre-tighten-{n}.py")):
        n += 1
    keep_old = os.path.join(project, f"edit-pre-tighten-{n}.py")
    with open(keep_old, "w", encoding="utf-8") as fh:
        fh.write(text)
    tmp = path + ".tighten-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(out)
    os.replace(tmp, path)
    from common import load_edit
    E2 = load_edit(project)
    if [tuple(r) for r in E2.KEEP] != P["keep"] or len(E2.J_LEADS) != len(E2.KEEP) - 1:
        os.replace(keep_old, path)
        sys.exit("the rewritten edit.py didn't read back as planned: the old one is restored, nothing changed")
    print(f"wrote {path} ({len(P['keep'])} ranges); the old one is {keep_old}")
    for name in (n.targets[0].id for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)):
        v = getattr(E2, name, None)                       # as edit.py reads now: lists built from KEEP are already right
        if name != "KEEP" and isinstance(v, (list, tuple)) and len(v) == len(E.KEEP) != len(P["keep"]):
            print(f"NOTE: {name} has {len(v)} entries, one per old KEEP range: give it one per piece now "
                  f"({len(P['keep'])}). Old range of each new piece: {P['line_of']}")


# ------------------------------------------------------------------ the plan, printed
def tc(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def report(E, P):
    O, total = starts(E.KEEP)
    print(f"tighten: pauses of 0.18 s or more inside a line, cut to about 0.1 s of air  ({E.SRC})")
    for L in P["lines"]:
        i, s, e = L["i"], L["s"], L["e"]
        print(f"  K{i:02d} src {s:8.3f}-{e:8.3f}  out {tc(O[i])}  {len(L['islands'])} speech islands, floor {L['floor']} dB")
        for p in L["pauses"]:
            if p["gap"] < SHOW and not p["cut"]:
                continue
            at = f"pause {p['gap']:.3f} s at src {p['off']:8.3f} (out {tc(O[i] + p['off'] - s)})"
            if p["cut"]:
                b, nxt = p["cut"]
                print(f"      {at}  CUT {b:.3f} | {nxt:.3f}  (-{nxt - b:.3f} s)")
            else:
                print(f"      {at}  keep: {p['why']}")
    air = [(i, a) for i, a in join_air(P["lines"]) if a >= 0.25]
    print("joins with 0.25 s of air or more (tail + head; not changed, pull KEEP in): " +
          (", ".join(f"K{i:02d}|K{i + 1:02d} {a:.2f} s" for i, a in air) if air else "none"))
    _, new_total = starts(P["keep"])
    print(f"{len(P['cuts'])} cuts: {len(E.KEEP)} -> {len(P['keep'])} ranges, audio {total:.3f} -> {new_total:.3f} s "
          f"(-{total - new_total:.3f} s)")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not os.path.isdir(os.path.expanduser(argv[0])):
        sys.exit(__doc__)
    project = os.path.abspath(os.path.expanduser(argv[0]))

    def opt(name, cast, default):
        return cast(argv[argv.index(name) + 1]) if name in argv else default
    skip = [int(x) for x in opt("--skip", str, "").split(",") if x.strip()]
    from common import load_edit
    E = load_edit(project)
    if not E.KEEP:
        sys.exit("KEEP is empty: set it from the transcript first (SKILL.md step 2)")
    try:
        P = plan([tuple(r) for r in E.KEEP], os.path.expanduser(E.SRC), opt("--min-gap", float, 0.18),
                 opt("--leave", float, 0.10), skip)
    except ValueError as err:
        sys.exit(str(err))
    report(E, P)
    if not P["cuts"]:
        print("nothing to cut: KEEP stays as it is")
        return
    J = leads_after(E, P)
    print("KEEP = [")
    for j, (a, b) in enumerate(P["keep"]):
        print(f"    ({_num(a)}, {_num(b)}),   # K{P['line_of'][j]:02d}")
    print("]")
    print(f"J_LEADS = [{', '.join('None' if x is None else _num(x) for x in J)}]")
    if "--apply" in argv:
        apply(project, E, P, force="--force" in argv)
    else:
        print("plan only: --apply writes it into edit.py")


if __name__ == "__main__":
    main()
