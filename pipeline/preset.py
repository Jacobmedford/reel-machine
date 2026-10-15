#!/usr/bin/env python3
"""Presets: approved effects and cards, used again by setting constants instead of rebuilding them.

A preset is a folder in a library: the effect's own files plus preset.json. Two libraries, read in this order:
  the creator's   $REEL_MACHINE_PRESETS, else $REEL_KIT_PRESETS, else HOME/presets: the ones they approved
  the kit's       KIT/presets: common devices that ship with the kit (presets/CATALOG.md)
A name found in both comes from the creator's, so their own version of a device always wins. Every per-video value
(words, cue words, times, labels, places, sizes) sits in ONE block of the effect's code, one JSON value per line:

    // PRESET CONSTANTS START
    var WORD = "NEVER";                        // what it is (comments live after the semicolon or on their own line)
    var T = {"push": 0.767, "stamp": "never"};  // a beat: seconds after A, or a spoken word ("never", "never-0.05")
    // PRESET CONSTANTS END

(fx.js for an effect, index.html for a card). `add` copies the preset into the project, writes the values you set into
that block and nothing else, fills the static HTML that has to carry a constant ([[NAME]] bindings, e.g. a clip's
data-start), runs the preset's generators (masks, timelines, captures) and prints what to paste into edit.py: the FX
entry (or the CARDS entry, or a lo-fi device's entry), the other edit.py lines the preset needs, and its approved sounds
at their real times.

Kinds: fx (an edit.FX folder, fx/<id>/), card (a full-screen card, cards/<id>/, with the project's pack files copied in;
render it yourself), device (a lo-fi edit.py entry such as BOXES, OVERLAYS, KARAOKE: nothing is copied).

Run: PY pipeline/preset.py list                         both libraries: where each comes from, kind, layer, length
     PY pipeline/preset.py show <preset>                what it does, its inputs, its constants and their defaults
     PY pipeline/preset.py add <project> <preset> --id <id> --at <s> --end <s|end> [--set KEY=VALUE ...]
                                                     [--note TEXT] [--replace] [--no-gen]
     PY pipeline/preset.py lint [<preset> ...]          check the libraries: blocks in sync, tokens only, no dashes
  --set KEY=VALUE   VALUE is JSON (380, true, null, [1, 2], {"a": 1}, "text"); anything that is not JSON is a string.
                    KEY.field=VALUE sets one field of an object, KEY.0=VALUE one item of a list. A beat in a cue
                    constant (preset.json "cues") takes a spoken word instead of seconds: --set T.stamp=never
  --replace         an existing fx/<id>/ (cards/<id>/) is renamed <id>-before-preset-<date>, never deleted
  --no-gen          copy and fill only; the printed commands run the generators later
"""
import argparse
import copy
import datetime
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FPS, HF, HOME, KIT, PY, VENDOR  # noqa: E402


def creator_library(env=os.environ):
    """the creator's library: $REEL_MACHINE_PRESETS, else $REEL_KIT_PRESETS (the old name), else HOME/presets"""
    lib = env.get("REEL_MACHINE_PRESETS") or env.get("REEL_KIT_PRESETS") or os.path.join(HOME, "presets")
    return os.path.expanduser(lib)


PRESETS = creator_library()                     # the creator's library, read first
KIT_PRESETS = os.path.join(KIT, "presets")      # the kit's own, read second: a name in both comes from the creator's
START, END = "// PRESET CONSTANTS START", "// PRESET CONSTANTS END"
LAYERS = {"fx": ("behind", "cam", "top", "over"), "card": ("card",), "device": ("BOXES", "OVERLAYS", "KARAOKE")}
NEVER_COPY = {"preset.json", "preview.jpg", ".DS_Store", "__pycache__"}
# the composition's own element ids (pipeline/build.py): an effect or card with one of these ids would collide with
# it, and a pack's CSS for it (#hook, #caps) would land on the effect
RESERVED = {"root", "main", "foot", "cam", "v", "behind", "mix", "caps", "end", "hook", "hook-tag", "fan", "fanclip", "fanrect"}
VAR = re.compile(r"var\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*")
BIND = re.compile(r"\[\[(@?[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\]\]")
CUE = re.compile(r"^(.*?)([+-]\d*\.?\d+)?$")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ------------------------------------------------------------------ the constants block
def block_span(text, where="fx.js"):
    """(start, end) of the block, its two marker lines included"""
    a = text.find(START)
    if a < 0 or text.find(START, a + 1) >= 0:
        raise SystemExit(f"{where}: needs exactly one '{START}' line")
    b = text.find(END, a)
    if b < 0:
        raise SystemExit(f"{where}: '{START}' has no '{END}' after it")
    a = text.rfind("\n", 0, a) + 1
    e = text.find("\n", b)
    return a, (len(text) if e < 0 else e + 1)


def parse_block(text, where="fx.js"):
    """[(name, value_start, value_end, value)] for every `var NAME = <JSON>;` in the block"""
    a, b = block_span(text, where)
    body = text.index("\n", text.find(START, a)) + 1
    stop = text.rfind("\n", 0, text.find(END, a)) + 1
    dec, out, pos = json.JSONDecoder(), [], body

    def line(p):
        return text.count("\n", 0, p) + 1
    while True:
        while pos < stop:                                   # whitespace and // comments between statements
            if text[pos].isspace():
                pos += 1
            elif text.startswith("//", pos):
                pos = text.find("\n", pos) + 1 or stop
            else:
                break
        if pos >= stop:
            break
        m = VAR.match(text, pos)
        if not m:
            raise SystemExit(f"{where}: line {line(pos)}: the block holds only `var NAME = <JSON>;` and // comments")
        name = m.group(1)
        try:
            value, vend = dec.raw_decode(text, m.end())
        except json.JSONDecodeError as e:
            raise SystemExit(f"{where}: line {line(m.end())}: {name} is not JSON ({e.msg}); quote every key and "
                             f"string with \", write 0.0667 not 2 / 30")
        k = vend
        while k < stop and text[k] in " \t":
            k += 1
        if k >= stop or text[k] != ";":
            raise SystemExit(f"{where}: line {line(vend)}: {name} must end with ';'")
        if any(n == name for n, *_ in out):
            raise SystemExit(f"{where}: {name} is set twice in the block")
        out.append((name, m.end(), vend, value))
        pos = k + 1
    return out


def constants(text, where="fx.js"):
    return {n: v for n, _, _, v in parse_block(text, where)}


def fmt(v, indent=""):
    """a JSON value as it sits in the block: one line when short, one item a line when long"""
    one = json.dumps(v, ensure_ascii=False)
    if len(one) <= 100 or not isinstance(v, (list, dict)) or not v:
        return one
    pad = indent + "  "
    if isinstance(v, list):
        return "[\n" + ",\n".join(pad + json.dumps(x, ensure_ascii=False) for x in v) + "\n" + indent + "]"
    return ("{\n" + ",\n".join(pad + json.dumps(k, ensure_ascii=False) + ": " + json.dumps(x, ensure_ascii=False)
                               for k, x in v.items()) + "\n" + indent + "}")


def write_block(text, values, where="fx.js"):
    """the text with each changed constant's value rewritten in place; comments, order and the code untouched"""
    out = text
    for name, a, b, old in reversed(parse_block(text, where)):
        if name in values and values[name] != old:
            ls = out.rfind("\n", 0, a) + 1
            indent = re.match(r"[ \t]*", out[ls:]).group(0)
            out = out[:a] + fmt(values[name], indent) + out[b:]
    return out


# ------------------------------------------------------------------ --set
def parse_set(s):
    """'KEY=VALUE' -> (KEY, value): JSON when it parses, else the text as a string"""
    if "=" not in s:
        raise SystemExit(f"--set {s}: write KEY=VALUE")
    k, v = s.split("=", 1)
    k = k.strip()
    try:
        return k, json.loads(v)
    except ValueError:
        return k, v.replace("\\n", "\n")                  # a typed \n is a line break (BOXES text)


def kind_of(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true/false"
    if isinstance(v, (int, float)):
        return "number"
    return {str: "string", list: "list", dict: "object"}.get(type(v), type(v).__name__)


def check_type(key, old, new, cue):
    a, b = kind_of(old), kind_of(new)
    if a == b or "null" in (a, b) or (cue and a == "number" and b == "string"):
        return
    raise SystemExit(f"{key}: expects a {a} like {json.dumps(old, ensure_ascii=False)[:80]}, "
                     f"got {json.dumps(new, ensure_ascii=False)[:80]}")


def apply_sets(values, sets, cues=()):
    """values (name -> default) with each KEY / KEY.path set; unknown names, fields and types stop with the valid ones"""
    out = copy.deepcopy(values)
    for key, new in sets.items():
        name, *path = key.split(".")
        if name not in out:
            valid = "\n".join(f"  {n} = {json.dumps(v, ensure_ascii=False)[:90]}" for n, v in values.items())
            raise SystemExit(f"--set {key}: this preset has no constant {name}. Its constants:\n{valid}")
        cue = name in cues
        if not path:
            check_type(key, out[name], new, cue)
            out[name] = new
            continue
        node = out[name]
        for i, p in enumerate(path):
            here = ".".join([name] + path[:i])
            if isinstance(node, dict):
                if p not in node:
                    raise SystemExit(f"--set {key}: {here} has no field {p!r}; its fields: {', '.join(node)}")
                slot = p
            elif isinstance(node, list):
                if not p.isdigit() or int(p) >= len(node):
                    raise SystemExit(f"--set {key}: {here} is a list of {len(node)}: use {here}.0 .. {here}.{len(node) - 1}")
                slot = int(p)
            else:
                raise SystemExit(f"--set {key}: {here} is a {kind_of(node)}, not an object or a list")
            if i == len(path) - 1:
                check_type(key, node[slot], new, cue)
                node[slot] = new
            else:
                node = node[slot]
    return out


# ------------------------------------------------------------------ spoken-word cues
def norm(w):
    return re.sub(r"[^a-z0-9%$']", "", str(w).lower())     # the same normalising as wordAt() in the composition


def load_words(project):
    p = os.path.join(project, "words.json")
    return read_json(p) if os.path.exists(p) else None


def cue(words, v, at, after=None):
    """a beat -> seconds after `at`: a number passes; 'word' / 'word+0.1' is the start of the first such spoken word at
    or after `after` (default `at`), nudged"""
    if not isinstance(v, str):
        return v
    m = CUE.match(v.strip())
    want, nudge = norm(m.group(1)), float(m.group(2) or 0)
    if words is None:
        raise SystemExit(f"cue {v!r}: the project has no words.json yet, so a beat can't key on a word")
    frm = at if after is None else after
    for w in words:
        if w["start"] >= frm - 0.001 and norm(w["text"]) == want:
            return round(w["start"] - at + nudge, 4)
    raise SystemExit(f"cue {v!r}: no spoken {m.group(1)!r} at or after {frm:.3f} in words.json")


def cues(words, v, at, after=None):
    """every cue in a value -> seconds after `at`; in a list each word is looked for after the beat before it, and
    from the window start when it isn't spoken again (a list need not be in spoken order)"""
    if isinstance(v, list):
        out, frm = [], after
        for x in v:
            try:
                r = cues(words, x, at, frm)
            except SystemExit:
                if frm is None or frm <= at:
                    raise
                r = cues(words, x, at, None)
            out.append(r)
            if isinstance(r, (int, float)) and not isinstance(r, bool):
                frm = at + r + 0.01                      # the next word starts after this one
        return out
    if isinstance(v, dict):
        return {k: cues(words, x, at, after) for k, x in v.items()}
    return cue(words, v, at, after)


def has_word(v):
    if isinstance(v, str):
        return True
    if isinstance(v, list):
        return any(has_word(x) for x in v)
    if isinstance(v, dict):
        return any(has_word(x) for x in v.values())
    return False


def path_get(values, path):
    name, *rest = path.split(".")
    if name not in values:
        raise KeyError(path)
    node = values[name]
    for p in rest:
        node = node[int(p)] if isinstance(node, list) else node[p]
    return node


# ------------------------------------------------------------------ helpers
def fnum(v):
    """a time or size as plain decimals: 3.9, 0.7333, 20"""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def pyval(v):
    if isinstance(v, bool) or v is None:
        return repr(v)
    if isinstance(v, (int, float)):
        return repr(round(v, 4)) if isinstance(v, float) else repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(pyval(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{json.dumps(k)}: {pyval(x)}" for k, x in v.items()) + "}"
    return repr(v)


def frames(at, end):
    return round(end * FPS) - round(at * FPS)


def total(project):
    p = os.path.join(project, "timeline.json")
    if not os.path.exists(p):
        raise SystemExit(f"--end end needs {p} (the cut's length)")
    return float(read_json(p)["total"])


def libraries():
    """[the creator's library, the kit's]: read in this order, so a name found in both comes from the creator's"""
    out = [PRESETS]
    if os.path.realpath(KIT_PRESETS) != os.path.realpath(PRESETS):
        out.append(KIT_PRESETS)
    return out


def in_library(lib):
    """the preset names in one library folder"""
    if not os.path.isdir(lib):
        return []
    return sorted(d for d in os.listdir(lib) if os.path.exists(os.path.join(lib, d, "preset.json")))


def names():
    """every preset name, each once, from both libraries"""
    return sorted({n for lib in libraries() for n in in_library(lib)})


def find(name):
    """the folder `name` is used from (the first library that has it), else None"""
    for lib in libraries():
        d = os.path.join(lib, name)
        if os.path.exists(os.path.join(d, "preset.json")):
            return d
    return None


def where(d):
    """'creator' or 'kit': which library a preset folder sits in"""
    return "creator" if os.path.dirname(os.path.abspath(d)) == os.path.abspath(PRESETS) else "kit"


def load(name):
    d = find(name)
    if d is None:
        have = ", ".join(names()) or "none yet"
        raise SystemExit(f"no preset {name!r} in {' or '.join(libraries())}. The presets: {have}")
    meta = read_json(os.path.join(d, "preset.json"))
    if meta.get("kind") not in LAYERS:
        raise SystemExit(f"{name}/preset.json: kind must be one of {', '.join(LAYERS)}")
    return d, meta


def block_file(meta):
    return meta.get("block") or ("index.html" if meta["kind"] == "card" else "fx.js")


def bind_files(meta):
    return meta.get("bind") or (["index.html"] if meta["kind"] == "card" else ["fx.html"])


def bind(text, values, builtins, words, at, cue_names, where):
    """[[NAME.path]] and [[@DUR]]-style built-ins in static files -> their values (a cue -> seconds after at)"""
    def sub(m):
        key = m.group(1)
        if key.startswith("@"):
            if key not in builtins:
                raise SystemExit(f"{where}: [[{key}]]: built-ins are {', '.join(sorted(builtins))}")
            v = builtins[key]
        else:
            try:
                v = path_get(values, key)
            except (KeyError, IndexError, ValueError):
                raise SystemExit(f"{where}: [[{key}]] names no constant")
            if key.split(".")[0] in cue_names:
                v = cues(words, v, at)
        if isinstance(v, bool) or v is None or isinstance(v, (list, dict)):
            raise SystemExit(f"{where}: [[{key}]] must be a number or a string, it is {kind_of(v)}")
        return fnum(v) if isinstance(v, (int, float)) else html.escape(str(v))
    return BIND.sub(sub, text)


def stamp_name(base):
    """<base>-before-preset-MM-DD-YY, then -2, -3 when taken"""
    day = datetime.date.today().strftime("%m-%d-%y")
    cand, n = f"{base}-before-preset-{day}", 2
    while os.path.exists(cand):
        cand, n = f"{base}-before-preset-{day}-{n}", n + 1
    return cand


# ------------------------------------------------------------------ generators
def gen_cmd(template, ctx):
    return [tok.format(**ctx) for tok in shlex.split(template)]


def run_gen(G, ctx, cwd):
    """run one generator (its fallback when it fails); True when something ran cleanly"""
    heavy = os.path.join(HOME, "bin", "heavy")
    for label, key in (("", "run"), ("fallback ", "fallback")):
        if not G.get(key):
            continue
        cmd = gen_cmd(G[key], ctx)
        if G.get("heavy") and os.path.exists(heavy):
            cmd = [heavy] + cmd
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()[-4:]
        if r.returncode == 0:
            print(f"  {label}ran  {' '.join(shlex.quote(c) for c in cmd)}")
            for ln in tail:
                print(f"       {ln}")
            return True
        print(f"  {label}FAILED ({r.returncode})  {' '.join(shlex.quote(c) for c in cmd)}")
        for ln in tail:
            print(f"       {ln}")
        if G.get("fallback") and key == "run":
            print(f"  using the fallback: {G.get('fallback_means', 'neutral output so the effect still renders')}")
    if G.get("required"):
        raise SystemExit(f"a required generator failed: {G['run']}. Fix it and rerun (the instance folder is "
                         f"written: rerun with --replace, or run the command above by hand)")
    return False


# ------------------------------------------------------------------ add
def entry_fx(meta, fid, at, end, note):
    e = f"dict(id={pyval(fid)}, layer={pyval(meta['layer'])}, at={pyval(at)}, end={pyval(end)}"
    return e + f", preset={pyval(meta['name'])}, note={pyval(note)})"


def entry_card(meta, cid, at, end, note):
    return f"({pyval(cid)}, {pyval('cards/' + cid + '.mp4')}, {pyval(at)}, {pyval(end)}, {pyval(meta.get('ground', 'dark'))}, {pyval(note)})"


def device_entries(meta, values, at, end, note, words):
    """a device's edit.py entries from its template: "@NAME.path" = a constant, "@at" / "@end" / "@note" = the window"""
    cue_names = set(meta.get("cues", []))
    resolved = {k: (cues(words, v, at) if k in cue_names and has_word(v) else v) for k, v in values.items()}

    def fill(t, item=None):
        if isinstance(t, str) and t.startswith("@"):
            key = t[1:]
            if key in ("at", "end", "note"):
                return {"at": at, "end": end, "note": note}[key]
            if key.startswith("item."):
                return path_get({"item": item}, key)
            return path_get(resolved, key)
        if isinstance(t, dict):
            return {k: fill(x, item) for k, x in t.items()}
        if isinstance(t, list):
            return [fill(x, item) for x in t]
        return t

    def render(d):
        if isinstance(d, dict):
            return "dict(" + ", ".join(f"{k}={pyval(v)}" for k, v in d.items()) + ")"
        return "(" + ", ".join(pyval(v) for v in d) + ")"
    if not meta.get("each"):
        return [render(fill(meta["entry"]))]
    items, out, t = copy.deepcopy(resolved[meta["each"]]), [], at        # a stack: each item hands on to the next
    chain = meta.get("chain", "until")
    hand = resolved.get(chain) if isinstance(resolved.get(chain), list) else None   # a constant: the hand-off beats
    base = resolved.get(meta.get("item_defaults")) if meta.get("item_defaults") else None
    if isinstance(base, dict):                                          # each item over the shared slot
        items = [dict(base, **it) for it in items]
    for k, it in enumerate(items):
        nxt = (hand[k] if hand is not None and k < len(hand) else None) if hand is not None else it.get(chain)
        stop = end if k == len(items) - 1 or nxt is None else round(at + nxt, 4)
        it.update(at=round(t, 4), end=stop)
        out.append(render(fill(meta["entry"], it)))
        t = stop if stop != "end" else t
    return out


def sfx_times(spec, values, at, end, words, cue_names):
    """an sfx 'at' -> absolute output seconds: a number (s after at), a constant path with an offset ('T.push+0.1'),
    '*' for every item of a list or object ('T.keys.*': one sound per key, nulls skipped), '@at' / '@end'.
    Returns (times, why none) so a path the instance doesn't have (a one-word callback) is skipped, not fatal"""
    if isinstance(spec, (int, float)):
        return [at + spec], None
    m = re.match(r"^\s*(@?[A-Za-z_][A-Za-z0-9_.*]*?)\s*([+-]\s*\d*\.?\d+)?\s*$", spec)
    if not m:
        raise SystemExit(f"sfx at {spec!r}: a number, a constant path (T.push+0.1, T.keys.*) or @at / @end")
    key, off = m.group(1), float((m.group(2) or "0").replace(" ", ""))
    if key == "@at":
        return [at + off], None
    if key == "@end":
        return [end + off], None
    name, *path = key.split(".")
    if name not in values:
        return [], f"no constant {name}"
    nodes = [cues(words, values[name], at) if name in cue_names else values[name]]
    for p in path:
        nxt = []
        for n in nodes:
            if p == "*":
                nxt += list(n.values()) if isinstance(n, dict) else list(n) if isinstance(n, list) else []
            elif isinstance(n, dict) and p in n:
                nxt.append(n[p])
            elif isinstance(n, list) and p.isdigit() and int(p) < len(n):
                nxt.append(n[int(p)])
        nodes = nxt
    times = [at + v + off for v in nodes if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return times, (None if times else f"{key} is not in this instance")


def add(project, name, fx_id, at, end, sets, note=None, replace=False, gen=True):
    """copy preset `name` into project as fx_id with `sets` written into its constants block; returns the entry"""
    project = os.path.abspath(os.path.expanduser(project))
    if not os.path.exists(os.path.join(project, "edit.py")):
        raise SystemExit(f"{project}: not a reel project (no edit.py)")
    src, meta = load(name)
    kind = meta["kind"]
    at = float(at)
    end_v = total(project) if end == "end" else float(end)
    end_out = "end" if end == "end" else end_v
    if kind == "card" and end == "end":
        raise SystemExit("a card needs a real end time (its length is frames / 30)")
    if end_v <= at:
        raise SystemExit(f"--end {end} is not after --at {at}")
    words = load_words(project)
    note = note or meta.get("note") or meta.get("what") or meta.get("does", "")
    cue_names = set(meta.get("cues", []))
    defaults = meta.get("constants", {})
    if kind != "device":
        text0 = read(os.path.join(src, block_file(meta)))
        block0 = constants(text0, f"{name}/{block_file(meta)}")
        if block0 != defaults:
            raise SystemExit(f"{name}: preset.json constants and the block in {block_file(meta)} disagree "
                             f"(run `preset.py lint {name}`)")
        defaults = block0
    values = apply_sets(defaults, sets, cue_names)
    for n in cue_names:                                    # every word cue must exist in this cut, now
        if has_word(values.get(n)):
            if words is None and kind == "fx":
                print(f"warning: {n} keys a beat on a spoken word but the project has no words.json yet: the effect "
                      f"finds it when the build runs (words.py first)")
            else:
                cues(words, values[n], at)
    if kind == "device":
        entries = device_entries(meta, values, at, end_out, note, words)
        print(f"{name}: {meta.get('does', '')}")
        report_sets(sets, values)
        print(f"paste into edit.py {meta.get('list', meta['layer'])}:")
        for e in entries:
            print(f"    {e},")
        report_needs(meta, dict(at=fnum(at), end=fnum(end_v), at_cut=fnum(max(at, 0.0334)), id=fx_id or ""),
                     values, at, end_v, words, cue_names)
        report_sfx(meta, values, at, end_v, words, cue_names)
        return entries[0] if len(entries) == 1 else ",\n".join(entries)

    if not fx_id or not re.match(r"^[a-z][a-z0-9_-]*$", fx_id) or "'" in fx_id:
        raise SystemExit(f"--id {fx_id!r}: lower case letters, digits, - and _ (it becomes HTML ids)")
    if fx_id in RESERVED:
        raise SystemExit(f"--id {fx_id}: the composition has its own #{fx_id} (and packs style it): pick another id, "
                         f"e.g. {fx_id}1 or {meta['name'].split('-')[0]}")
    where = "cards" if kind == "card" else "fx"
    dst = os.path.join(project, where, fx_id)
    if os.path.exists(dst):
        if not replace:
            raise SystemExit(f"{dst} exists. Pick another --id, or --replace to rename the old folder and start over")
        old = stamp_name(dst)
        os.rename(dst, old)
        print(f"renamed the old {where}/{fx_id}/ to {os.path.relpath(old, project)}/")
    if kind == "card":
        values = {k: (cues(words, v, at) if k in cue_names and has_word(v) else v) for k, v in values.items()}
    shutil.copytree(src, dst, ignore=lambda d, fs: [f for f in fs if f in NEVER_COPY or f.endswith(".pyc")])
    n_frames = frames(at, end_v)
    builtins = {"@DUR": n_frames / FPS, "@FRAMES": n_frames, "@AT": at, "@END": end_v, "@ID": fx_id}
    bf = os.path.join(dst, block_file(meta))
    write(bf, write_block(read(bf), values, block_file(meta)))
    for f in bind_files(meta):
        p = os.path.join(dst, f)
        if not os.path.exists(p):
            continue
        t = read(p)
        if f == block_file(meta):
            a, b = block_span(t, f)
            t = (bind(t[:a], values, builtins, words, at, cue_names, f) + t[a:b]
                 + bind(t[b:], values, builtins, words, at, cue_names, f))
        else:
            t = bind(t, values, builtins, words, at, cue_names, f)
        write(p, t)
    if kind == "card":
        pack_files(project, dst)
    write_provenance(dst, name, meta, src, sets, fx_id, at, end)
    print(f"{name} -> {os.path.relpath(dst, project)}/  ({kind}, {meta['layer']}, {n_frames} frames)")
    report_sets(sets, values)
    report_beats(meta, values, at, words, cue_names, kind)
    ctx = dict(py=PY, project=project, id=fx_id, dir=dst, at=fnum(at), end=fnum(end_v), kit=KIT, home=HOME)
    gens = meta.get("generators", [])
    if gens:
        print("generators:")
        for G in gens:
            if gen:
                run_gen(G, ctx, dst)
            else:
                print(f"  later  {' '.join(shlex.quote(c) for c in gen_cmd(G['run'], ctx))}")
    entry = entry_card(meta, fx_id, at, end_v, note) if kind == "card" else entry_fx(meta, fx_id, at, end_out, note)
    print(f"paste into edit.py {'CARDS' if kind == 'card' else 'FX'}:")
    print(f"    {entry},")
    report_needs(meta, dict(at=fnum(at), end=fnum(end_v), at_cut=fnum(max(at, 0.0334)), id=fx_id),
                 values, at, end_v, words, cue_names)
    report_sfx(meta, values, at, end_v, words, cue_names)
    if gens:
        for G in gens:
            if G.get("when"):
                print(f"rerun when {G['when']}: {' '.join(shlex.quote(c) for c in gen_cmd(G['run'], ctx))}")
    if kind == "card":
        hf = " ".join(HF)
        # GSAP inside the page first (a worker that loses the fetch renders the card frozen), the animation check after
        inl = f"{shlex.quote(PY)} {shlex.quote(os.path.join(KIT, 'pipeline', 'inline_vendor.py'))} index.html"
        chk = f"{shlex.quote(PY)} {shlex.quote(os.path.join(KIT, 'pipeline', 'animcheck.py'))} --page . {fx_id}.mp4"
        print(f"render the card (heavy): cd {shlex.quote(dst)} && {inl} && {hf} check && "
              f"{hf} render -q delivery --quiet -o {fx_id}.mp4 && {chk}")
        print(f"storyboard still: {inl} && {hf} snapshot --at {fnum(max(0.0, n_frames / FPS - 0.05))} --no-end "
              f"--describe false (save the frame as still.jpg)")
    return entry


def pack_files(project, dst):
    """a card renders on its own: the project's pack (brand.css + fonts) and the kit's card files beside it"""
    style = os.path.join(project, "style")
    if not os.path.exists(os.path.join(style, "brand.css")):
        raise SystemExit(f"{style}/brand.css is missing: build the project's pack first")
    shutil.copy(os.path.join(style, "brand.css"), os.path.join(dst, "brand.css"))
    if os.path.isdir(os.path.join(style, "fonts")):
        shutil.copytree(os.path.join(style, "fonts"), os.path.join(dst, "fonts"), dirs_exist_ok=True)
    for f in ("card.css", "hyperframes.json"):
        shutil.copy(os.path.join(KIT, "kit", f), os.path.join(dst, f))
    gsap = next((p for p in (os.path.join(project, "public", "vendor", "gsap.min.js"), os.path.join(VENDOR, "gsap.min.js"))
                 if os.path.exists(p)), None)
    if not gsap:
        raise SystemExit("no gsap.min.js in the project's public/vendor or the kit vendor folder")
    os.makedirs(os.path.join(dst, "vendor"), exist_ok=True)
    shutil.copy(gsap, os.path.join(dst, "vendor", "gsap.min.js"))


def write_provenance(dst, name, meta, src, sets, fid, at, end):
    sets_s = " ".join(f"--set {shlex.quote(k + '=' + (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)))}"
                      for k, v in sets.items())
    with open(os.path.join(dst, "PRESET.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {fid}: preset {name}\n\nMade {datetime.date.today():%m-%d-%y} by pipeline/preset.py from {src} "
                 f"({meta.get('from', '')}).\nThe per-video values are the block between the PRESET CONSTANTS markers in "
                 f"{block_file(meta)}.\n\nAgain with other values (the old folder is renamed, not deleted):\n\n"
                 f"    PY pipeline/preset.py add <project> {name} --id {fid} --at {fnum(at)} --end {end if end == 'end' else fnum(end)} "
                 f"{sets_s} --replace\n")


def report_sets(sets, values):
    if sets:
        print("set:")
        for k, v in sets.items():
            print(f"  {k} = {json.dumps(v, ensure_ascii=False)}")


def report_beats(meta, values, at, words, cue_names, kind):
    lengths = set(meta.get("lengths", []))                 # durations kept in a cue constant: not beats
    rows = []
    for n in sorted(cue_names):
        v = values.get(n)
        if v is None:
            continue
        try:
            r = cues(words, v, at) if has_word(v) else v
        except SystemExit as e:
            rows.append(f"  {n}: {e}")
            continue

        def walk(prefix, x, raw):
            if isinstance(x, dict):
                for k in x:
                    walk(f"{prefix}.{k}", x[k], raw.get(k) if isinstance(raw, dict) else None)
            elif isinstance(x, list):
                for i, y in enumerate(x):
                    walk(f"{prefix}.{i}", y, raw[i] if isinstance(raw, list) and i < len(raw) else None)
            elif isinstance(x, (int, float)) and not isinstance(x, bool) and prefix not in lengths:
                word = f" ({raw})" if isinstance(raw, str) else ""
                rows.append(f"  {prefix:<16} {fnum(x):>7}{word} -> {fnum(at + x)}")
        walk(n, r, v)
    if rows:
        unit = "card seconds" if kind == "card" else "s after A"
        print(f"beats ({unit}, A = {fnum(at)}):")
        for r in rows[:40]:
            print(r)
        if len(rows) > 40:
            print(f"  ... {len(rows) - 40} more")


class _Keep(dict):
    def __missing__(self, k):                              # an unknown {name} in a template prints as it is
        return "{" + k + "}"


def report_needs(meta, ctx, values=None, at=0.0, end=0.0, words=None, cue_names=()):
    """the other edit.py lines a preset needs: {at} {end} {at_cut} {id}, and {@T.cue} = a beat's output time"""
    needs = meta.get("needs", [])
    if needs:
        print("edit.py also needs:")
        for n in needs:
            def beat(m):
                times, why = sfx_times(m.group(1), values or {}, at, end, words, cue_names)
                return fnum(times[0]) if times else f"<{m.group(1)}: {why}>"
            n = re.sub(r"\{@([A-Za-z_][A-Za-z0-9_.]*(?:[+-]\d*\.?\d+)?)\}", beat, n)
            n = re.sub(r"\{=([A-Za-z_][A-Za-z0-9_.]*)\}",          # braces in a value survive the format below
                       lambda m: str(path_get(values or {}, m.group(1))).replace("{", "{{").replace("}", "}}"), n)
            print(f"    {n.format_map(_Keep(ctx))}")


def condition(spec, values):
    """'NAME=value' (equal as text), 'NAME' (set: not null, empty or false), '!NAME' (not set)"""
    spec = spec.strip()
    if "=" in spec:
        k, _, want = spec.partition("=")
        return str(values.get(k.strip())) == want.strip()
    if spec.startswith("!"):
        return not values.get(spec[1:].strip())
    return bool(values.get(spec))


def report_sfx(meta, values, at, end, words, cue_names):
    sfx = meta.get("sfx", [])
    if not sfx:
        return
    print("SOUND.sfx" + (" (CARD_SFX)" if meta["kind"] == "card" else "") + ": the approved sounds at this window's times")
    for s in sfx:
        if s.get("if") and not condition(s["if"], values):  # "ROLE=cta", "FOLLOW" (set), "!FRONT" (not set)
            continue
        times, why = sfx_times(s["at"], values, at, end, words, cue_names)
        if s.get("spread") and len(times) >= 2:             # one sound per item of a constant, evenly between
            n = len(values.get(s["spread"]) or [])            # the first and the last beat (as the effect spreads them)
            if n and n != len(times):
                a_, b_ = times[0], times[-1]
                times = [a_ + (b_ - a_) * i / (n - 1) if n > 1 else a_ for i in range(n)]
        if not times:
            print(f"    # skipped {s['name']} at {s['at']}: {why}")
        ml = s.get("max_len")
        if isinstance(ml, str):                             # "T.typed - ONSETS.0": a run as long as two beats apart
            a_, _, b_ = ml.partition(" - ")
            ta, _ = sfx_times(a_.strip(), values, at, end, words, cue_names)
            tb, _ = sfx_times(b_.strip(), values, at, end, words, cue_names)
            ml = round(ta[0] - tb[0], 3) if ta and tb and ta[0] > tb[0] else None
        for t in times:
            parts = [f"{t:.3f}".rstrip("0").rstrip("."), json.dumps(s["name"]), str(s.get("db", -18))]
            if ml:
                parts.append(fnum(ml))
            print(f"    ({', '.join(parts)}),   # {s.get('what', '')}")


# ------------------------------------------------------------------ lint
HEX = re.compile(r"(?:[:\s,(]|^)#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b(?![-{])")
RGB = re.compile(r"\b(?:rgba?|hsla?)\s*\(")
FONT = re.compile(r"font-family\s*:\s*(?!var\(|inherit)([^;}\"]+)")
NAMED = re.compile(r"(?:\b(?:color|background(?:-color)?|fill|stroke|border(?:-[a-z]+)*|outline|box-shadow|text-shadow)"
                   r"\s*[:=]\s*[\"']?[^;}\"'\n]*|\b(?:fill|stroke)=[\"'])\b(white|black|red|green|blue|gr[ae]y|yellow|orange|purple|pink)\b")
DASH = re.compile("[\u2014\u2013]")
# a space letter swapped for a plain space: an inline-block holding only a space has no width (use '\u00a0')
SPACE_LETTER = re.compile(r"===\s*(['\"]) \1\s*\?\s*(['\"]) \2")


def strip_comments(text, ext):
    if ext in (".py",):
        return re.sub(r"#[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"(?<![:\"'\\])//[^\n]*", "", text)


def lint(only=None):
    """problems in the libraries (empty = clean): blocks in sync with preset.json, tokens only, no em or en dashes.
    Each name is checked where it is used from (the creator's copy when both libraries have it)"""
    issues = []
    for name in (only or names()):
        try:
            d, meta = load(name)
        except SystemExit as e:
            issues.append(f"{name}: {e}")
            continue
        kind = meta["kind"]
        for k in ("name", "kind", "from", "layer", "does", "inputs", "constants", "typical_length"):
            if k not in meta:
                issues.append(f"{name}: preset.json has no {k!r}")
        if meta.get("name") != name:
            issues.append(f"{name}: preset.json name is {meta.get('name')!r}")
        if meta.get("layer") not in LAYERS.get(kind, ()):
            issues.append(f"{name}: layer {meta.get('layer')!r} is not one of {LAYERS.get(kind)}")
        if "signature" in meta and meta["signature"] not in (None, "reference reels"):
            issues.append(f"{name}: signature is null or \"reference reels\" (it names no person or handle)")
        if kind != "device":
            bf = os.path.join(d, block_file(meta))
            if not os.path.exists(bf):
                issues.append(f"{name}: no {block_file(meta)}")
                continue
            text = read(bf)
            try:
                block = constants(text, f"{name}/{block_file(meta)}")
            except SystemExit as e:
                issues.append(f"{name}: {e}")
                continue
            want = meta.get("constants", {})
            for k in sorted(set(block) | set(want)):
                if k not in block:
                    issues.append(f"{name}: preset.json constant {k} is not in the block")
                elif k not in want:
                    issues.append(f"{name}: block constant {k} is missing from preset.json constants")
                elif block[k] != want[k]:
                    issues.append(f"{name}: constant {k} differs between the block and preset.json")
            for c in meta.get("cues", []):
                if c not in block:
                    issues.append(f"{name}: cue {c} is not a constant")
                elif kind == "fx" and not re.search(rf"\b{c}\s*=\s*cues\(\s*{c}\s*\)", text):
                    issues.append(f"{name}: cue constant {c} is never resolved in fx.js ({c} = cues({c}))")
            for f in bind_files(meta):
                p = os.path.join(d, f)
                if os.path.exists(p):
                    t = read(p)
                    for m in BIND.finditer(t):
                        k = m.group(1)
                        if not k.startswith("@"):
                            try:
                                path_get(block, k)
                            except (KeyError, IndexError, ValueError):
                                issues.append(f"{name}/{f}: [[{k}]] names no constant")
            for G in meta.get("generators", []):
                script = next((tok for tok in shlex.split(G.get("run", "")) if tok.endswith((".py", ".mjs"))), None)
                if script and not os.path.exists(os.path.join(d, script)):
                    issues.append(f"{name}: generator {script} is not in the folder")
            if kind == "fx":
                for f in ("fx.js",) + (() if "fx.html" in meta.get("generated", []) else ("fx.html",)):
                    if not os.path.exists(os.path.join(d, f)):
                        issues.append(f"{name}: no {f}")
        for root, _, files in os.walk(d):
            for f in files:
                p = os.path.join(root, f)
                ext = os.path.splitext(f)[1].lower()
                if ext not in (".html", ".js", ".css", ".json", ".py", ".mjs", ".md", ".svg"):
                    continue
                rel = os.path.relpath(p, d)
                raw = read(p)
                if DASH.search(raw):
                    issues.append(f"{name}/{rel}: an em or en dash (use commas, colons, periods)")
                if "__WARP" in raw or "__WX" in raw:
                    issues.append(f"{name}/{rel}: a leftover per-video time warp")
                if ext in (".html", ".js", ".css", ".svg", ".mjs"):
                    code = strip_comments(raw, ext)
                    if HEX.search(code) or RGB.search(code) or NAMED.search(code):
                        issues.append(f"{name}/{rel}: a literal colour (use a token: var(--c-...))")
                    for m in FONT.finditer(code):
                        issues.append(f"{name}/{rel}: a font name ({m.group(1).strip()[:30]}): use var(--font-...)")
                    if SPACE_LETTER.search(code):
                        issues.append(f"{name}/{rel}: a space letter set as a plain space has no width in an "
                                      f"inline-block: write the no-break space as '\\u00a0'")
    return issues


# ------------------------------------------------------------------ list / show
def cmd_list():
    libs = libraries()
    print(f"creator  {libs[0]}" + ("" if os.path.isdir(libs[0]) else "  (none yet)"))
    if len(libs) > 1:
        print(f"kit      {libs[1]}")
    rows = []
    for n in names():
        d, m = load(n)
        over = " (the kit has one too: this copy is used)" if where(d) == "creator" and len(libs) > 1 \
            and n in in_library(libs[1]) else ""
        rows.append((n, where(d), m["kind"], m.get("layer", ""), m.get("typical_length", ""),
                     "signature" if m.get("signature") else "", m.get("does", "")[:70] + over))
    if not rows:
        print("no presets yet")
        return
    w = max(len(r[0]) for r in rows)
    for r in rows:
        print(f"{r[0]:<{w}}  {r[1]:<7} {r[2]:<6} {r[3]:<8} {r[4]:<12} {r[5]:<9} {r[6]}")


def cmd_show(name):
    d, m = load(name)
    print(f"{name} ({m['kind']}, {m.get('layer')}): {m.get('does', '')}")
    print(f"library: {where(d)} ({d})")
    for k in ("from", "use_when", "typical_length", "signature", "pairs_with", "modes"):
        if m.get(k):
            print(f"{k}: {m[k] if not isinstance(m[k], list) else ', '.join(map(str, m[k]))}")
    if m.get("inputs"):
        print("inputs:")
        for i in m["inputs"]:
            print(f"  - {i}")
    print("constants (defaults):")
    notes = m.get("notes", {})
    for k, v in m.get("constants", {}).items():
        print(f"  {k} = {json.dumps(v, ensure_ascii=False)[:110]}" + (f"\n      {notes[k]}" if k in notes else ""))
    if m.get("cues"):
        print(f"cues (seconds after A, or a spoken word): {', '.join(m['cues'])}")
    for G in m.get("generators", []):
        print(f"generator: {G['run']}  ({G.get('when', '')})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show")
    s.add_argument("preset")
    a = sub.add_parser("add")
    a.add_argument("project")
    a.add_argument("preset")
    a.add_argument("--id")
    a.add_argument("--at", type=float, required=True)
    a.add_argument("--end", required=True)
    a.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    a.add_argument("--note")
    a.add_argument("--replace", action="store_true")
    a.add_argument("--no-gen", action="store_true")
    li = sub.add_parser("lint")
    li.add_argument("presets", nargs="*")
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "show":
        cmd_show(args.preset)
    elif args.cmd == "lint":
        issues = lint(args.presets or None)
        for i in issues:
            print(i)
        print(f"{len(issues)} issue(s) in {len(args.presets or names())} preset(s)")
        sys.exit(1 if issues else 0)
    else:
        sets = dict(parse_set(s) for s in args.set)
        add(args.project, args.preset, args.id, args.at, args.end if args.end == "end" else float(args.end), sets,
            note=args.note, replace=args.replace, gen=not args.no_gen)


if __name__ == "__main__":
    main()
