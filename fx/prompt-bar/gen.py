#!/usr/bin/env python3
"""prompt-bar: write every appearance of the motif from one table.

The prompt bar is a motif: the same component comes back 3 or 4 times in a video, each time the speaker says what
they told the AI to do. This writes <project>/fx/<id>/fx.html + fx.js for every row of BEATS from the library
template next to this file: fx.html is copied as it is and fx.js gets the row's constants, so every appearance has
the same design, position and in and out move. It checks each word key against <project>/words.json, prints when
each beat lands, and prints the edit.FX entries to paste.

Run: PY gen.py <project>            fill in BEATS first; run it again whenever the cut or the template changes
     PY gen.py <project> --check    only check the word keys and print the times, write nothing
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# One row per appearance, keyed by its FX id.
#   at, end   the FX window on the output timeline (the bar opens at `at` and is gone by `end`)
#   text      what the bar types
#   type      (first, last): typing runs from the start of the first spoken word to the end of the last
#   send      the spoken word the send button presses on ('' = just after the typing)
#   done      the result that rolls in ('' = the bar sends and leaves); done_on = the word it lands on
#             ('' = half a second after the send)
BEATS = {
    "prompt1": dict(at=4.50, end=5.90, text="cut the pauses and add captions", type=("I", "typed"), send="one",
                    done="cut and captioned", done_on="sentence"),
    "prompt2": dict(at=14.62, end=16.15, text="make it moody", type=("Make", "moody"), send="", done=""),
}
LABELS = ["PROMPT", "SENT", "DONE"]     # the small label over the field: waiting, sent, done
OUT = 0.26                              # the bar starts closing this long before `end` (keep in step with fx.js T.out)

BEGIN = "// ---- constants: gen.py rewrites the lines between these two markers ----"
END = "// ---- end of constants ----"


def js(v):
    return json.dumps(v, ensure_ascii=False)


def block(b, t_line):
    return "\n".join([
        BEGIN,
        f"var TEXT = {js(b['text'])};   // the instruction the bar types",
        f"var TYPE = {js(list(b['type']))};   // typing runs from the start of the first word to the end of the second",
        f"var SEND_ON = {js(b.get('send', ''))};   // the send button presses on this word",
        f"var DONE_TEXT = {js(b.get('done', ''))};   // the result that rolls in; empty = the bar sends and leaves",
        f"var DONE_ON = {js(b.get('done_on', ''))};   // the word the result lands on; empty = T.run after the send",
        f"var LABELS = {js(LABELS)};   // the small label over the field: waiting, sent, done",
        t_line,
        END,
    ])


def norm(w):
    return re.sub(r"[^a-z0-9%$']", "", str(w).lower())


def find(words, w, after, before):
    """(start, end) of the first spoken word w at or after `after` and before `before` (as wordAt in fx.js)"""
    if not w:
        return None
    for s, e, text in words:
        if s >= after - 0.001 and norm(text) == norm(w):
            return (s, e) if s < before else None
    return None


def check(fid, b, words):
    a, z, notes = b["at"], b["end"], []
    t0 = find(words, b["type"][0], a, z)
    t1 = find(words, b["type"][-1], t0[0], z) if t0 else None
    if not t0 or not t1:
        notes.append(f"typing words {b['type']} not both spoken in {a}-{z}: the fallback times in fx.js apply")
    ty0, ty1 = (t0[0], t1[1]) if t0 and t1 else (a + 0.05, a + 0.60)
    s = find(words, b.get("send", ""), ty1 - 0.05, z)
    send = s[0] if s else ty1 + 0.08
    if b.get("send") and not s:
        notes.append(f"send word {b['send']!r} not spoken after the typing: it sends just after the typing")
    if send > z - OUT - 0.1:
        notes.append("the send lands after the bar starts closing: move `end` later")
    done = None
    if b.get("done"):
        d = find(words, b.get("done_on", ""), send + 0.05, z)
        done = d[0] if d else send + 0.5
        if done > z - OUT - 0.12:
            notes.append("no room for the result before the bar leaves: it sends and leaves (move `end` later)")
            done = None
    cps = len(b["text"]) / max(0.01, ty1 - ty0)
    if cps > 70:
        notes.append(f"typing runs at {cps:.0f} characters a second: give it longer words or a shorter text")
    print(f"{fid:<10} opens {a:.2f}  types {ty0:.2f}-{ty1:.2f} ({cps:.0f}/s)  sends {send:.2f}  "
          f"{'done ' + format(done, '.2f') + '  ' if done else ''}closes {z - OUT:.2f}  gone {z - OUT + 0.24:.2f}")
    for n in notes:
        print(f"{'':<10} WARNING {n}")


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    project = os.path.abspath(os.path.expanduser(args[0]))
    html = open(os.path.join(HERE, "fx.html"), encoding="utf-8").read()
    tpl = open(os.path.join(HERE, "fx.js"), encoding="utf-8").read()
    i, j = tpl.index(BEGIN), tpl.index(END) + len(END)
    t_line = next(ln for ln in tpl[i:j].splitlines() if ln.startswith("var T = "))
    wpath = os.path.join(project, "words.json")
    words = [(w["start"], w["end"], w["text"]) for w in json.load(open(wpath))] if os.path.exists(wpath) else []
    if not words:
        print(f"no {wpath}: word keys are not checked")
    library = os.path.realpath(os.path.dirname(HERE))
    for fid, b in BEATS.items():
        if words:
            check(fid, b, words)
        if "--check" in args:
            continue
        d = os.path.join(project, "fx", fid)
        if os.path.realpath(d).startswith(library + os.sep):
            raise SystemExit(f"{d} is inside the library ({library}): run gen.py on a project whose fx/ is its own folder")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "fx.html"), "w", encoding="utf-8") as f:
            f.write(html)
        with open(os.path.join(d, "fx.js"), "w", encoding="utf-8") as f:
            f.write(tpl[:i] + block(b, t_line) + tpl[j:])
    if "--check" not in args:
        print("\nwrote " + ", ".join(f"fx/{fid}/" for fid in BEATS) + f" in {project}\nedit.FX entries:")
        for fid, b in BEATS.items():
            print(f'    dict(id="{fid}", layer="top", at={b["at"]:.2f}, end={b["end"]:.2f}, '
                  f'note="prompt bar: {b["text"]}"),')


if __name__ == "__main__":
    main()
