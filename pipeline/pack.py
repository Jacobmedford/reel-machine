#!/usr/bin/env python3
"""Packs: named style packs. A creator keeps one default look and any number of named ones; each project wears one.

  default ("harbor")  $REEL_MACHINE_HOME/style/, the pack install or onboarding writes. new.py uses it unless told
                      otherwise. `build harbor` (or `build default`) rebuilds it like any pack, unless it has its own
                      wrapper (style/apply-style.sh): then the wrapper owns its build and pack.py never rebuilds it.
  packs/<name>/       every other pack:
      style.json      the kit's schema (style.py DEFAULT), every field: start from the default pack's, change what the pack changes
      STYLE.md        the pack in words (onboarding/ONBOARDING.md template), with Hi-fi, Lo-fi and Showcase sections
      extra.css       optional: treatments the tokens cannot express, appended to brand.css after the tokens.
                      brand.css is inlined BEFORE kit/reel.css, so its rules need more weight (`html body .cap ...`)
      local-fonts/    optional: font files the pack ships itself, each family's licence beside them (OFL.txt);
                      one file serves every weight
      brand.css, fonts/   written by `build`, every time from scratch. Never edit them by hand.

Run: PY pipeline/pack.py list
     PY pipeline/pack.py build <name>             -> packs/<name>/brand.css + fonts/ (harbor: style/)
     PY pipeline/pack.py use <project> <name>     the project wears <name>; its old style/ is renamed, never deleted
Then rebuild the project (build.py) to see it. j_lead lives in the pack too: a new one only reaches the picture when
cut.py runs again (edit.J_LEAD and J_LEADS still win over any pack).

The kit ships four packs in its own packs/ folder (harbor, film, signal, terminal), all drawn in the Harbor palette:
     PY pipeline/pack.py install [--palette <file>] [--text-font "<family>"] [--no-boards]
          copies them into the home: harbor -> style/, the others -> packs/<name>/. A pack already in the home is kept
          as it is (never moved or overwritten). With a palette (and a text face) the copies wear the creator's
          colours; each is built and its board drawn (onboarding/board.py)
     PY pipeline/pack.py recolor <name> --palette <file> [--text-font "<family>"] [--no-boards]
          one installed pack in the creator's colours, from the kit's own copy of it (so the last palette wins
          whole); its old style.json and extra.css are kept in before-recolor-<MM-DD-YY>/, then rebuilt, board redrawn
     PY pipeline/pack.py lint [<name>|<folder> ...]
          every colour in style.json and extra.css must be a palette colour or an rgba() of one (no names: the kit's)
A palette file is {role: colour} with the keys of style.json's colors (series as a list), or a whole style.json.
The mapping is by role: a role the file leaves out keeps Harbor's colour, a colour a pack derives from another role
follows it (Signal's slab is the accent), and every rgba() keeps its own alpha.
"""
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as ST  # noqa: E402
from common import resolve_home  # noqa: E402

DEFAULT_NAMES = ("harbor", "default")            # the default pack, $REEL_MACHINE_HOME/style/
ROLES = ("display", "text", "mono", "caption")
KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # this repo
KIT_PACKS = os.path.join(KIT, "packs")           # the packs the kit ships, all drawn in Harbor (harbor is the default)
PACK_SOURCES = ("style.json", "STYLE.md", "extra.css")                 # what install copies (plus local-fonts/)
# the colour roles, most basic first: a colour that plays several roles moves with the first of them
ROLE_ORDER = ("light", "dark", "ink", "accent", "accent_on_light", "negative", "negative_on_light", "positive",
              "positive_on_light", "muted_light", "hair_light", "muted_dark", "hair_dark", "caption_box", "caption_ink",
              "caption_dim", "textbox_bg", "textbox_ink", "s1", "s2", "s3")
COLOR = re.compile(r"#(?P<hex>[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b"
                   r"|(?P<fn>rgba?)\(\s*(?P<r>\d{1,3})\s*,\s*(?P<g>\d{1,3})\s*,\s*(?P<b>\d{1,3})\s*"
                   r"(?:,\s*(?P<a>\d*\.?\d+%?)\s*)?\)", re.I)
PROPERTY = re.compile(r"\s*-{0,2}[A-Za-z][\w-]*\s*")                 # a declaration's property, before its colon
FAMILY = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .-]{0,63}")              # a font family name safe to write into CSS
COPY = ("style.json", "brand.css", "STYLE.md", "extra.css")     # what a project's style/ gets (plus fonts/)
GOOGLE_FILE = re.compile(r"^(?P<stem>[A-Za-z0-9]+)-(?P<style>normal|italic)-(?P<weight>\d+)\.ttf$")
WEIGHTS = {"thin": 100, "hairline": 100, "extralight": 200, "ultralight": 200, "light": 300, "regular": 400,
           "book": 400, "normal": 400, "medium": 500, "semibold": 600, "demibold": 600, "bold": 700,
           "extrabold": 800, "ultrabold": 800, "black": 900, "heavy": 900}


def home():
    """read on every call (not at import), so a test or a second HOME in the same process is honoured"""
    return resolve_home()


def default_dir():
    return os.path.join(home(), "style")


def names():
    """every pack this creator can use: the default first, then packs/ in name order (only folders with style.json)"""
    root = os.path.join(home(), "packs")
    named = sorted(n for n in (os.listdir(root) if os.path.isdir(root) else [])
                   if n not in DEFAULT_NAMES and os.path.exists(os.path.join(root, n, "style.json")))
    return [DEFAULT_NAMES[0]] + named


def _stop(msg):
    raise SystemExit(f"{msg}\nPacks: {', '.join(names())} (pipeline/pack.py list)")


def pack_dir(name=None):
    """a pack's folder. None, harbor or default -> $REEL_MACHINE_HOME/style; else packs/<name>. A name that is not a pack
    (or a folder without style.json) stops with the list of real ones: never a silent fall back to the default."""
    if name is None or name in DEFAULT_NAMES:
        d = default_dir()
        if not os.path.exists(os.path.join(d, "style.json")):
            _stop(f"no style pack at {d}: run onboarding first (onboarding/ONBOARDING.md), or point REEL_MACHINE_HOME at one")
        return d
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name or "") or ".." in name:
        _stop(f"'{name}' is not a pack name")
    d = os.path.join(home(), "packs", name)
    if not os.path.exists(os.path.join(d, "style.json")):
        _stop(f"no pack '{name}' (looked for {os.path.join(d, 'style.json')})")
    return d


def is_default(d):
    return os.path.abspath(d) == os.path.abspath(default_dir())


# ---------------------------------------------------------------- fonts
def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _file_family(path):
    """the family name inside a font file, or None"""
    try:
        from PIL import ImageFont
        return ImageFont.truetype(path, 12).getname()[0] or None
    except Exception:         # noqa: BLE001  (not a font PIL can read: fall back to the file name)
        return None


def local_fonts(pack, S):
    """local-fonts/*.ttf|otf -> [(family, file)]. A file whose name matches a family the pack uses (LeagueGothic-*
    for 'League Gothic') takes that family's name; any other takes the name inside the file (else the file name)"""
    d = os.path.join(pack, "local-fonts")
    files = sorted(f for f in (os.listdir(d) if os.path.isdir(d) else []) if f.lower().endswith((".ttf", ".otf")))
    used = {_norm(S["fonts"][r]["family"]): S["fonts"][r]["family"] for r in ROLES}
    out = []
    for f in files:
        base = re.split(r"[-_]", os.path.splitext(f)[0])[0]
        out.append((used.get(_norm(base)) or _file_family(os.path.join(d, f)) or base, f))
    return out


def local_faces(fonts):
    """@font-face rules for local files. One file per family serves every weight (100-900) in both styles, so the
    browser never fakes a bold or a slant; a family with several files maps each by its suffix (Bold, Italic...)"""
    by = {}
    for fam, f in fonts:
        by.setdefault(fam, []).append(f)
    rules = []
    for fam in sorted(by):
        for f in sorted(by[fam]):
            fmt = "opentype" if f.lower().endswith(".otf") else "truetype"
            src = f"font-family:'{fam}'; src:url('fonts/{f}') format('{fmt}');"
            if len(by[fam]) == 1:
                faces = [("normal", "100 900"), ("italic", "100 900")]
            else:
                suffix = _norm(os.path.splitext(f)[0].split("-", 1)[-1])
                weight = next((w for k, w in sorted(WEIGHTS.items(), key=lambda kv: -len(kv[0])) if k in suffix), 400)
                faces = [("italic" if "italic" in suffix else "normal", str(weight))]
            rules += [f"@font-face {{ {src} font-style:{st}; font-weight:{w}; font-display:block; }}" for st, w in faces]
    return rules


def _google_rule(family, name, style, weight):
    """the exact rule style.py writes for a downloaded Google font"""
    return (f"@font-face {{ font-family:'{family}'; src:url('fonts/{name}') format('truetype'); "
            f"font-style:{style}; font-weight:{weight}; font-display:block; }}")


def google_faces(S, fonts_dir, skip=()):
    """@font-face rules for the pack's Google Fonts families, offline first: a family whose files are already in this
    pack's fonts/ (or the default pack's: same files) needs no network. Only a family that is in neither goes to
    style.py's download, as onboarding does."""
    need = {}
    for r in ROLES:
        f = S["fonts"][r]
        if f["family"] not in skip:
            need.setdefault(f["family"], set()).add(("italic" if f["italic"] else "normal", str(f["weight"])))
    cache = os.path.join(default_dir(), "fonts")
    rules, missing = [], []
    for fam in sorted(need):
        stem = fam.replace(" ", "")

        def have(d):
            return {m.group("style", "weight"): n for n in (os.listdir(d) if os.path.isdir(d) else [])
                    for m in [GOOGLE_FILE.match(n)] if m and m.group("stem") == stem}
        got = have(fonts_dir)
        if not need[fam] <= set(got) and os.path.abspath(cache) != os.path.abspath(fonts_dir):
            for n in have(cache).values():
                if not os.path.exists(os.path.join(fonts_dir, n)):
                    shutil.copy(os.path.join(cache, n), os.path.join(fonts_dir, n))
            got = have(fonts_dir)
        if need[fam] <= set(got):
            rules += [_google_rule(fam, n, st, w) for (st, w), n in got.items()]
        else:
            missing.append(fam)
    if missing:          # style.font_faces walks all four roles: give every role a family that is missing
        sub = {r: S["fonts"][r] for r in ROLES if S["fonts"][r]["family"] in missing}
        filler = next(iter(sub.values()))
        rules += ST.font_faces(dict(S, fonts={r: sub.get(r, filler) for r in ROLES}), fonts_dir)
    return sorted(set(rules))


# ---------------------------------------------------------------- build, copy, use
def build(pack):
    """style.json (+ local fonts + extra.css) -> brand.css and fonts/, from scratch every time (twice = same bytes)"""
    pack = os.path.abspath(pack)
    sj = os.path.join(pack, "style.json")
    if not os.path.exists(sj):
        _stop(f"{pack} has no style.json: not a pack")
    S = ST.load(sj)
    fonts = os.path.join(pack, "fonts")
    os.makedirs(fonts, exist_ok=True)
    local = local_fonts(pack, S)
    for _, f in local:
        shutil.copyfile(os.path.join(pack, "local-fonts", f), os.path.join(fonts, f))
    faces = google_faces(S, fonts, skip={fam for fam, _ in local})
    parts = ["/* Generated by pipeline/pack.py from style.json, local-fonts/ and extra.css. Edit those, not this file. */",
             "\n".join(faces), ST.css_vars(S).rstrip("\n")]
    if local:
        parts.append("/* local fonts (local-fonts/, shipped with the pack): one file serves every weight */\n"
                     + "\n".join(local_faces(local)))
    extra = os.path.join(pack, "extra.css")
    if os.path.exists(extra):
        with open(extra, encoding="utf-8") as fh:
            parts.append("/* ---- extra.css: what the tokens cannot express ---- */\n" + fh.read().strip("\n"))
    out = os.path.join(pack, "brand.css")
    text = "\n\n".join(p for p in parts if p) + "\n"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    used = set(re.findall(r"""url\(\s*['"]?fonts/([^'")]+)""", text))
    for n in os.listdir(fonts):                     # fonts/ is generated: a file brand.css no longer uses is not kept,
        if n not in used and os.path.isfile(os.path.join(fonts, n)):   # so it never travels into a project
            os.remove(os.path.join(fonts, n))
    for w in ST.check(S):
        print("WARNING", w)
    return out


def stale(pack):
    """brand.css missing, or older than anything it is made from"""
    css = os.path.join(pack, "brand.css")
    if not os.path.exists(css):
        return True
    srcs = [os.path.join(pack, f) for f in ("style.json", "extra.css")] + glob.glob(os.path.join(pack, "local-fonts", "*"))
    return any(os.path.getmtime(s) > os.path.getmtime(css) for s in srcs if os.path.exists(s))


def ready(name=None):
    """a pack's folder, built and current. The default pack is never rebuilt here (its own build owns it): it only
    gets a plain style.py brand.css when it has none, as new.py always did"""
    d = pack_dir(name)
    if is_default(d):
        if not os.path.exists(os.path.join(d, "brand.css")):
            ST.write(ST.load(os.path.join(d, "style.json")), d)
    elif stale(d):
        build(d)
    return d


def copy_into(src, dest):
    """a pack -> a project's style/ (style.json, brand.css, STYLE.md, extra.css, fonts/): a copy, not a link, so the
    project renders the same after the pack changes"""
    os.makedirs(dest, exist_ok=True)
    for f in COPY:
        if os.path.exists(os.path.join(src, f)):
            shutil.copy(os.path.join(src, f), dest)
    if os.path.isdir(os.path.join(src, "fonts")):
        shutil.copytree(os.path.join(src, "fonts"), os.path.join(dest, "fonts"), dirs_exist_ok=True)


def _free(path):
    if not os.path.exists(path):
        return path
    k = 2
    while os.path.exists(f"{path}-{k}"):
        k += 1
    return f"{path}-{k}"


def _leads(style_json):
    try:
        with open(style_json) as fh:
            modes = json.load(fh).get("modes", {})
    except (OSError, ValueError):
        return {}
    return {m: v.get("j_lead") for m, v in modes.items() if isinstance(v, dict) and "j_lead" in v}


def use(project, name):
    """the project wears pack <name>: its style/ is renamed style-before-<name>-<MM-DD-YY>[-2...] and the pack copied in"""
    project = os.path.abspath(os.path.expanduser(project))
    if not os.path.isdir(project):
        raise SystemExit(f"no project folder at {project}")
    src = ready(name)                        # stops here, before anything moves, when the name is not a pack
    label = name or DEFAULT_NAMES[0]
    dest = os.path.join(project, "style")
    before, old = _leads(os.path.join(dest, "style.json")), None
    if os.path.exists(dest):
        old = _free(os.path.join(project, f"style-before-{label}-{time.strftime('%m-%d-%y')}"))
        os.rename(dest, old)
    copy_into(src, dest)
    print(f"{os.path.basename(project)} now wears {label} ({src})" + (f"; its old style is {old}" if old else ""))
    after = _leads(os.path.join(dest, "style.json"))
    moved = [f"{m} {before[m]} -> {after[m]}" for m in sorted(after) if m in before and before[m] != after[m]]
    if moved:
        print(f"j_lead changes ({', '.join(moved)}): the picture keeps its old joins until cut.py runs again "
              "(edit.J_LEAD / J_LEADS win over the pack)")
    return dest


# ---------------------------------------------------------------- colours: palette, lint, recolor
def _parse(c):
    """a colour string ('#rgb', '#rrggbb', 'rgb(r,g,b)', 'rgba(r,g,b,a)') -> its COLOR match, else None"""
    return COLOR.fullmatch(c.strip()) if isinstance(c, str) else None


def _rgb(m):
    h = m.group("hex")
    if h:
        h = "".join(ch * 2 for ch in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(min(255, int(m.group(k))) for k in "rgb")


def _hexed(rgb):
    return "#" + "".join(f"{v:02X}" for v in rgb)


def _alpha(m):
    a = m.group("a")
    return 1.0 if a is None else (float(a[:-1]) / 100 if a.endswith("%") else float(a))


def is_color(c):
    return _parse(c) is not None


def norm(c):
    """any colour form -> '#RRGGBB' (alpha set aside): the key colours are compared and moved by"""
    m = _parse(c)
    if not m:
        raise ValueError(f"not a colour: {c!r} (use #RRGGBB or rgba(r,g,b,a))")
    return _hexed(_rgb(m))


def _same(a, b):
    ma, mb = _parse(a), _parse(b)
    return bool(ma and mb) and _rgb(ma) == _rgb(mb) and abs(_alpha(ma) - _alpha(mb)) < 1e-6


def _ordered(roles):
    return [r for r in ROLE_ORDER if r in roles] + sorted(r for r in roles if r not in ROLE_ORDER)


def palette_of(style_json):
    """role -> colour, from a style.json's colors: every role that holds a string, the series as s1, s2, s3 (the
    names build.py's color() reads)"""
    C = (style_json or {}).get("colors") or {}
    series = C.get("series") if isinstance(C.get("series"), list) else []
    out = {k: v for k, v in C.items() if isinstance(v, str)}
    out.update({f"s{i + 1}": v for i, v in enumerate(series) if isinstance(v, str)})
    return out


def _strings(obj):
    """every string value in a JSON tree (keys are names, not values; '_' keys are the loader's notes)"""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if not str(k).startswith("_"):
                yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _map_strings(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {k: _map_strings(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_map_strings(v, fn) for v in obj]
    return obj


def css_values(css):
    """a stylesheet's declaration values (what follows a property's colon, up to its ; or }), comments dropped.
    Selectors never come out, so an id selector such as #add is never read as a colour"""
    css = re.sub(r"/\*.*?\*/", " ", css or "", flags=re.S)
    out, stmt, val, block, paren, quote = [], [], None, 0, 0, None
    for ch in css:
        if val is not None:                      # inside a value: it ends at a ; or } outside quotes and brackets
            if quote:
                quote = None if ch == quote else quote
            elif ch in "'\"":
                quote = ch
            elif ch == "(":
                paren += 1
            elif ch == ")":
                paren = max(0, paren - 1)
            elif not paren and ch in ";}":
                out.append("".join(val))
                val, stmt = None, []
                if ch == "}":
                    block = max(0, block - 1)
                continue
            val.append(ch)
        elif ch == "{":
            block, stmt = block + 1, []
        elif ch == "}":
            block, stmt = max(0, block - 1), []
        elif ch == ";":
            stmt = []
        elif ch == ":" and block and PROPERTY.fullmatch("".join(stmt)):
            val = []
        else:
            stmt.append(ch)
    if val is not None:
        out.append("".join(val))
    return out


def lint_colors(style_json, extra_css=""):
    """every colour in a pack's style.json values and extra.css that is neither one of its palette colours nor an
    rgba() of one, as #RRGGBB, each once, in the order they first appear. A pack that passes recolors whole"""
    allowed = {norm(v) for v in palette_of(style_json).values() if is_color(v)}
    stray = []
    for text in list(_strings(style_json)) + css_values(extra_css):
        for m in COLOR.finditer(text):
            h = _hexed(_rgb(m))
            if h not in allowed and h not in stray:
                stray.append(h)
    return stray


def recolor_text(text, mapping):
    """every #rgb, #rrggbb, rgb() and rgba() colour in text moved through mapping (old -> new, any colour form, case
    insensitive). A hex stays hex (the new colour as written, or its #RRGGBB when the new one is an rgba); an rgb() or
    rgba() keeps its own alpha. Colours the mapping does not name, and everything that is not a colour, stay put"""
    M = {norm(k): v for k, v in mapping.items()}
    if not M:
        return text

    def move(m):
        new = M.get(_hexed(_rgb(m)))
        if new is None:
            return m.group(0)
        nm = _parse(new)
        if not nm:
            raise ValueError(f"not a colour: {new!r} (use #RRGGBB or rgba(r,g,b,a))")
        if m.group("hex"):
            return new.strip() if nm.group("hex") else _hexed(_rgb(nm))
        r, g, b = _rgb(nm)
        return f"{m.group('fn')}({r},{g},{b}{'' if m.group('a') is None else ',' + m.group('a')})"
    return COLOR.sub(move, text)


def _moves(old, new):
    """old colour -> new colour for each role (both role -> colour), the most basic role first: one colour, one move.
    Colours that keep their rgb drop out"""
    moves = {}
    for r in _ordered(old):
        if is_color(old[r]) and is_color(new.get(r)):
            moves.setdefault(norm(old[r]), new[r])
    return {k: v for k, v in moves.items() if norm(v) != k}


def recolor_colors(harbor, authored, palette):
    """a pack's colours in a creator's palette, by role. All three are role -> colour (palette_of's form):
      harbor    the palette the kit draws its packs in
      authored  this pack's colours as the kit ships it (for a pack the kit does not ship: its own, with harbor = them)
      palette   the creator's colours
    A role the pack takes straight from Harbor gets the creator's colour for it. A role the pack points at another
    Harbor colour follows that colour with its own alpha (Signal's slab is the accent, Terminal's box the dark ground
    at 92%). A colour Harbor does not have takes the creator's colour for its role (Film's faded accent). A role the
    palette leaves out keeps the pack's colour, or follows the Harbor colour it is a shade of."""
    moves = _moves(harbor, {r: palette.get(r, c) for r, c in harbor.items()})
    new = {}
    for r, v in authored.items():
        if not is_color(v):
            new[r] = v
        elif r in palette and (_same(v, harbor.get(r)) or recolor_text(v, moves) == v):
            new[r] = palette[r]
        else:
            new[r] = recolor_text(v, moves)
    new.update({r: c for r, c in palette.items() if r not in new})       # roles the pack did not set
    return new


def load_palette(path):
    """a creator's palette file -> role -> colour (palette_of's form). The file holds {role: colour} with the keys of
    style.json's colors (series as a list), or is a whole style.json. Anything else stops here, before a file changes"""
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise SystemExit(f"palette {path}: {e}")
    if isinstance(data, dict) and isinstance(data.get("colors"), dict):
        data = data["colors"]
    if not isinstance(data, dict) or not data:
        raise SystemExit(f"palette {path}: expected {{role: colour}} with the keys of style.json's colors")
    roles = set(ST.DEFAULT["colors"])
    unknown = sorted(k for k in data if k not in roles)
    if unknown:
        raise SystemExit(f"palette {path}: unknown roles {', '.join(unknown)} (the roles: {', '.join(sorted(roles))})")
    for k, v in data.items():
        if (k == "series") != isinstance(v, list) or not all(is_color(c) for c in (v if isinstance(v, list) else [v])):
            raise SystemExit(f"palette {path}: {k} = {v!r} is not a colour (#RRGGBB or rgba(r,g,b,a)"
                             f"{'; series is a list of them' if k == 'series' else ''})")
    return palette_of({"colors": data})


# ---------------------------------------------------------------- install, recolor, boards
def kit_names():
    """the packs the kit ships (KIT_PACKS): harbor first, then the others by name"""
    have = sorted(n for n in (os.listdir(KIT_PACKS) if os.path.isdir(KIT_PACKS) else [])
                  if os.path.exists(os.path.join(KIT_PACKS, n, "style.json")))
    return [n for n in have if n == DEFAULT_NAMES[0]] + [n for n in have if n not in DEFAULT_NAMES]


def home_dir(name):
    """where pack <name> lives in the home folder (it may not exist yet)"""
    return default_dir() if name in DEFAULT_NAMES else os.path.join(home(), "packs", name)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _family(name):
    if not FAMILY.fullmatch(name or ""):
        raise SystemExit(f"--text-font '{name}' is not a font family name (letters, digits, spaces, dots, dashes)")
    return name


def _text_face(S, family, extra):
    """the creator's text face: fonts.text, and fonts.caption where it was the same face (Terminal keeps its mono
    captions); a quoted mention of the old face in extra.css follows"""
    fonts = S.setdefault("fonts", {})
    text = fonts.setdefault("text", dict(ST.DEFAULT["fonts"]["text"]))
    old, text["family"] = text.get("family"), family
    if isinstance(fonts.get("caption"), dict) and fonts["caption"].get("family") == old:
        fonts["caption"]["family"] = family
    if extra is not None and old:
        extra = re.sub(r"(['\"])" + re.escape(old) + r"\1", lambda m: m.group(1) + family + m.group(1), extra)
    return S, extra


def _apply(pack, kit_name, palette=None, text_font=None):
    """a pack folder in a creator's palette and/or text face. Colours by role (recolor_colors), from the kit's own
    copy of the pack when the kit ships it, so the result never depends on an earlier recolor; every colour that
    moved moves in extra.css and the rest of style.json too. Other settings stay as they are"""
    sj, ex = os.path.join(pack, "style.json"), os.path.join(pack, "extra.css")
    with open(sj, encoding="utf-8") as fh:
        S = json.load(fh)
    extra = _read(ex) if os.path.exists(ex) else None
    if palette:
        current = palette_of(S)
        kit_h, kit_p = (os.path.join(KIT_PACKS, n, "style.json") for n in (DEFAULT_NAMES[0], kit_name))
        if os.path.exists(kit_h) and os.path.exists(kit_p):
            harbor, authored = (palette_of(json.loads(_read(p))) for p in (kit_h, kit_p))
        else:
            harbor = authored = current
        new = recolor_colors(harbor, authored, palette)
        moves = _moves(current, new)
        S = {k: v if k == "colors" else _map_strings(v, lambda s: recolor_text(s, moves)) for k, v in S.items()}
        C = S.setdefault("colors", {})
        C.update({r: c for r, c in new.items() if not re.fullmatch(r"s\d+", r)})
        series = [new[f"s{i}"] for i in range(1, len(new) + 1) if f"s{i}" in new]
        if series:
            C["series"] = series
        if extra is not None:
            extra = recolor_text(extra, moves)
    if text_font:
        S, extra = _text_face(S, text_font, extra)
    _write(sj, json.dumps(S, indent=2, ensure_ascii=False) + "\n")
    if extra is not None:
        _write(ex, extra)


def draw_board(pack):
    """the pack's style board (onboarding/board.py --pack): its look rendered by the engine the videos use. Heavy (a
    render browser, six frames), so a failure is reported, never fatal: the pack itself is ready"""
    cmd = [sys.executable, os.path.join(KIT, "onboarding", "board.py"), "--pack", pack]
    r = subprocess.run(cmd)
    if r.returncode:
        print(f"WARNING the board for {pack} was not drawn (exit {r.returncode}): rerun {shlex.join(cmd)}")
    return r.returncode == 0


def install(palette=None, text_font=None, boards=True):
    """the kit's packs into the home folder: harbor -> style/ (the default look), the others -> packs/<name>/. A pack
    already in the home is kept as it is: install never moves or overwrites one (recolor changes an installed pack).
    The new copies wear the palette (palette_of form) and text face when given; each is built, then each board drawn.
    Returns the folders it made."""
    ship = kit_names()
    if not ship:
        raise SystemExit(f"no packs in {KIT_PACKS}: the kit ships them there (harbor, film, signal, terminal)")
    if text_font:
        _family(text_font)
    made = []
    for name in ship:
        dest = home_dir(name)
        if os.path.exists(os.path.join(dest, "style.json")):
            print(f"  {name:<10} kept as it is: {dest} already holds a pack"
                  + (" (pack.py recolor restyles it)" if palette or text_font else ""))
            continue
        src = os.path.join(KIT_PACKS, name)
        os.makedirs(dest, exist_ok=True)
        for f in PACK_SOURCES:
            if os.path.exists(os.path.join(src, f)):
                shutil.copy(os.path.join(src, f), os.path.join(dest, f))
        if os.path.isdir(os.path.join(src, "local-fonts")):
            shutil.copytree(os.path.join(src, "local-fonts"), os.path.join(dest, "local-fonts"), dirs_exist_ok=True)
        if palette or text_font:
            _apply(dest, name, palette, text_font)
        build(dest)
        made.append(dest)
        print(f"  {name:<10} installed: {dest}")
    if boards:
        for d in made:
            draw_board(d)
    return made


def recolor(name, palette=None, text_font=None, boards=True):
    """an installed pack in a creator's palette (palette_of form) and/or text face. The colours come from the kit's
    own copy of the pack when the kit ships it: recoloring twice equals once with the last palette, and a role that
    palette leaves out goes back to Harbor's colour. The pack's old style.json and extra.css are kept in
    before-recolor-<MM-DD-YY>[-2...]/; then it is rebuilt and its board redrawn. A default pack with its own build
    (apply-style.sh) is left to that build."""
    if not palette and not text_font:
        raise SystemExit('recolor needs --palette <file> and/or --text-font "<family>"')
    if text_font:
        _family(text_font)
    d = pack_dir(name)                        # stops with the list of packs, before anything changes
    keep = _free(os.path.join(d, f"before-recolor-{time.strftime('%m-%d-%y')}"))
    os.makedirs(keep)
    for f in ("style.json", "extra.css"):
        if os.path.exists(os.path.join(d, f)):
            shutil.copy(os.path.join(d, f), os.path.join(keep, f))
    _apply(d, DEFAULT_NAMES[0] if is_default(d) else name, palette, text_font)
    print(f"{name} restyled ({d}); its old style.json and extra.css are in {keep}")
    if is_default(d) and os.path.exists(os.path.join(d, "apply-style.sh")):
        print(f"{d} keeps its own build: run {os.path.join(d, 'apply-style.sh')} to bring brand.css up to date")
        return d
    build(d)
    if boards:
        draw_board(d)
    return d


def lint(targets=()):
    """stray colours (lint_colors) in each pack: pack folders or installed pack names; none -> the kit's own packs.
    Prints one line a pack; returns how many have a stray colour"""
    dirs = [t if os.path.exists(os.path.join(t, "style.json")) else pack_dir(t) for t in targets]
    dirs = dirs or [os.path.join(KIT_PACKS, n) for n in kit_names()]
    if not dirs:
        raise SystemExit(f"no packs to lint: {KIT_PACKS} holds none")
    bad = 0
    for d in dirs:
        ex = os.path.join(d, "extra.css")
        stray = lint_colors(json.loads(_read(os.path.join(d, "style.json"))), _read(ex) if os.path.exists(ex) else "")
        print(f"  {os.path.basename(os.path.normpath(d)):<12} "
              + (f"stray colours {', '.join(stray)}: move each onto a palette colour (or an rgba() of one)"
                 if stray else "clean"))
        bad += bool(stray)
    return bad


def _opt(a, flag):
    """the value after --flag in argv a, None when the flag is absent"""
    if flag not in a:
        return None
    i = a.index(flag)
    if i + 1 >= len(a) or a[i + 1].startswith("--"):
        raise SystemExit(f"{flag} needs a value")
    return a[i + 1]


def main():
    a = sys.argv[1:]
    if a[:1] == ["list"]:
        for n in names():
            d = pack_dir(n)
            state = "default" if is_default(d) else ("needs build" if stale(d) else "built")
            print(f"  {n:<12} {state:<12} {d}")
    elif a[:1] == ["build"] and len(a) == 2:
        d = pack_dir(a[1])                    # stops with the list of packs (or, for the default, onboarding first)
        wrapper = os.path.join(d, "apply-style.sh")
        if is_default(d) and os.path.exists(wrapper):
            raise SystemExit(f"the default pack ({d}) keeps its own build: run {wrapper} to bring brand.css up to date")
        print(build(d))
    elif a[:1] == ["use"] and len(a) == 3:
        use(a[1], a[2])
    elif a[:1] == ["install"]:
        pal = _opt(a, "--palette")
        install(palette=load_palette(pal) if pal else None, text_font=_opt(a, "--text-font"),
                boards="--no-boards" not in a)
    elif a[:1] == ["recolor"] and len(a) >= 2 and not a[1].startswith("--"):
        pal = _opt(a, "--palette")
        recolor(a[1], palette=load_palette(pal) if pal else None, text_font=_opt(a, "--text-font"),
                boards="--no-boards" not in a)
    elif a[:1] == ["lint"]:
        sys.exit(1 if lint([x for x in a[1:] if not x.startswith("--")]) else 0)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
