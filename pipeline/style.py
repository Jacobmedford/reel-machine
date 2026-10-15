#!/usr/bin/env python3
"""Style pack: every look decision in one file, so the engine and the cards stay style-free.

The pack lives OUTSIDE the skill folder (updates never overwrite it): $REEL_MACHINE_HOME/style/ (default ~/reel-machine/style/)
  style.json   the pack (schema below; onboarding writes it)
  STYLE.md     the same pack in words: what the captions, cards and motion should feel like
  brand.css    generated from style.json: CSS variables + @font-face (never edit by hand)
  fonts/       the pack's fonts, downloaded from Google Fonts
Run: PY pipeline/style.py [path/to/style.json] [--out DIR]   -> brand.css + fonts/ next to style.json (or DIR)
"""
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import resolve_home  # noqa: E402

HOME = resolve_home()
STYLE_DIR = os.path.join(HOME, "style")

# A neutral default: what you get before onboarding has made a pack. Onboarding always replaces it.
DEFAULT = {
    "version": 1,
    "creator": {"name": "", "handle": "", "site": ""},
    "checks": {},                                    # {check name: why}: a contrast check this pack answers on purpose
    "fonts": {
        "display": {"family": "Inter Tight", "italic": False, "weight": 800},   # hook line 2, emphasis words, big figures
        "text": {"family": "Inter", "italic": False, "weight": 700},          # captions, labels, text boxes
        "mono": {"family": "JetBrains Mono", "italic": False, "weight": 500},  # numbers, units, axes, kickers
        "caption": {"family": "Inter", "italic": False, "weight": 800},       # lo-fi word-by-word captions
    },
    "colors": {
        "light": "#F6F5F1",            # light ground; text on dark
        "dark": "#121314",             # dark ground
        "ink": "#121314",              # text on light
        "muted_light": "#6E6D69",      # secondary text on light
        "muted_dark": "rgba(246,245,241,.58)",
        "hair_light": "#D6D4CE",       # hairlines on light
        "hair_dark": "rgba(246,245,241,.22)",
        "accent": "#4F7BFF",           # emphasis on dark (the one colour that means "look here")
        "accent_on_light": "#2A57E0",
        "negative": "#FF5A5F", "negative_on_light": "#C42B31",   # losses, "no", down
        "positive": "#35C47C", "positive_on_light": "#1C8A52",   # gains, "yes", up
        "series": ["#4F7BFF", "#35C47C", "#FF5A5F"],             # up to three data series
        "caption_box": "rgba(18,19,20,.86)", "caption_ink": "#FFFFFF", "caption_dim": "rgba(255,255,255,.45)",
        "textbox_bg": "#FFFFFF", "textbox_ink": "#111111",        # the Instagram-style text box (lo-fi hook / CTA)
    },
    "grounds": {"grid": False, "radius": 6},                     # card backgrounds: graph paper or flat; corner radius
    "captions": {
        "hifi": {"box": True, "uppercase": False, "size": 56, "y": 1236},
        "lofi": {"box": True, "size": 66, "y": 1318},
    },
    # how each mode edits for this creator (kit/STYLE_PACK.md has every value and how to read it off a brand or
    # an inspiration video). The engine applies j_lead, camera and the lo-fi caption settings; agents read the rest.
    "modes": {
        "hifi": {"hook": "two-line", "captions": "phrases", "emphasis": ["thesis", "big", "strike"],
                 "behind_head": "often", "cards": "often", "camera": "settle", "bw": True, "j_lead": 0.30},
        "lofi": {"captions": "word-by-word", "max_words": 4, "max_chars": 24, "text_boxes": True,
                 "overlays": "often", "backdrops": "often", "zooms": True, "bw": True, "j_lead": 0.30},
        "showcase": {"emphasis_word": "stamp", "transitions": ["whip", "zoom", "spin", "push", "drop", "reveal"],
                     "density": "high", "motif": "", "j_lead": 0.30},
    },
    "grade": "contrast(1.04) saturate(1.0)",                      # CSS filter on the footage; "none" for straight
    "motion": "calm",                                             # calm | punchy (settles vs hard zooms)
    "sound": {"sfx": "normal", "music": "none"},                  # sfx: light | normal | dense
    "end_card": False,
}


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path=None):
    path = path or os.path.join(STYLE_DIR, "style.json")
    S = merge(DEFAULT, json.load(open(path)) if os.path.exists(path) else {})
    S["_path"] = path if os.path.exists(path) else None
    return S


def font_stack(f, generic):
    return f"'{f['family']}', {generic}"


def css_vars(S):
    F, C, G = S["fonts"], S["colors"], S["grounds"]
    s1, s2, s3 = (C["series"] + ["#888888"] * 3)[:3]
    lines = [
        f"--font-display: {font_stack(F['display'], 'serif')}; --display-style: {'italic' if F['display']['italic'] else 'normal'}; --display-weight: {F['display']['weight']};",
        f"--font-text: {font_stack(F['text'], 'sans-serif')}; --text-weight: {F['text']['weight']};",
        f"--font-mono: {font_stack(F['mono'], 'monospace')};",
        f"--font-caption: {font_stack(F['caption'], 'sans-serif')}; --caption-style: {'italic' if F['caption']['italic'] else 'normal'}; --caption-weight: {F['caption']['weight']};",
        f"--c-light: {C['light']}; --c-dark: {C['dark']}; --c-ink: {C['ink']};",
        f"--c-muted-light: {C['muted_light']}; --c-muted-dark: {C['muted_dark']};",
        f"--c-hair-light: {C['hair_light']}; --c-hair-dark: {C['hair_dark']};",
        f"--c-accent: {C['accent']}; --c-accent-light: {C['accent_on_light']};",
        f"--c-neg: {C['negative']}; --c-neg-light: {C['negative_on_light']};",
        f"--c-pos: {C['positive']}; --c-pos-light: {C['positive_on_light']};",
        f"--c-s1: {s1}; --c-s2: {s2}; --c-s3: {s3};",
        f"--c-box: {C['caption_box']}; --c-box-ink: {C['caption_ink']}; --c-box-dim: {C['caption_dim']};",
        f"--c-tb-bg: {C['textbox_bg']}; --c-tb-ink: {C['textbox_ink']};",
        f"--radius: {G['radius']}px;",
    ]
    def grid(stroke, op):
        if not G["grid"]:
            return ""
        s = stroke.replace("#", "%23")
        return ("background-image:url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='54' height='54'%3E"
                f"%3Cpath d='M54 0V54M0 54H54' fill='none' stroke='{s}' stroke-width='1.2' opacity='{op}'/%3E%3C/svg%3E\");")
    hair_l = C["hair_light"] if C["hair_light"].startswith("#") else "#999999"
    light_hex = C["light"] if C["light"].startswith("#") else "#FFFFFF"
    return (":root {\n  " + "\n  ".join(lines) + "\n}\n"
            f".ground-light {{ background-color: var(--c-light); color: var(--c-ink); {grid(hair_l, '.55')} }}\n"
            f".ground-dark {{ background-color: var(--c-dark); color: var(--c-light); {grid(light_hex, '.06')} }}\n")


# ---------------------------------------------------------------- fonts from Google Fonts (TTF, downloaded once)
UA = "Wget/1.21"      # Google serves plain TTF files to this agent


def _fetch_css(family, pairs):
    axis = ";".join(f"{i},{w}" for i, w in sorted(pairs))
    url = f"https://fonts.googleapis.com/css2?family={urllib.parse.quote_plus(family)}:ital,wght@{axis}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    except urllib.error.HTTPError:
        return None


def font_faces(S, outdir):
    """download every family the pack uses (the weights the kit needs) -> [@font-face rules]"""
    want = {}
    for role in ("display", "text", "mono", "caption"):
        f = S["fonts"][role]
        pairs = want.setdefault(f["family"], set())
        for w in (400, 500, 600, 700, 800, f["weight"]):
            pairs.add((0, w))
            if f["italic"]:
                pairs.add((1, w))
    os.makedirs(outdir, exist_ok=True)
    rules = []
    for family, pairs in want.items():
        css = _fetch_css(family, pairs)
        if css is None:                       # a static family without some weights: ask one by one, keep what exists
            css = "".join(_fetch_css(family, {p}) or "" for p in sorted(pairs))
        if not css:
            print(f"warning: no font files for '{family}' (is it on Google Fonts?)")
            continue
        for block in re.findall(r"@font-face\s*{[^}]*}", css):
            style = re.search(r"font-style:\s*(\w+)", block).group(1)
            weight = re.search(r"font-weight:\s*(\d+)", block).group(1)
            src = re.search(r"url\((https://[^)]+\.ttf)\)", block)
            if not src:
                continue
            name = f"{family.replace(' ', '')}-{style}-{weight}.ttf"
            path = os.path.join(outdir, name)
            if not os.path.exists(path):
                urllib.request.urlretrieve(src.group(1), path)
            rules.append(f"@font-face {{ font-family:'{family}'; src:url('fonts/{name}') format('truetype'); "
                         f"font-style:{style}; font-weight:{weight}; font-display:block; }}")
    return sorted(set(rules))


def write(S, outdir, fonts=True):
    """brand.css (+ fonts/) into outdir: the composition, every card and the storyboard link the same file"""
    os.makedirs(outdir, exist_ok=True)
    faces = font_faces(S, os.path.join(outdir, "fonts")) if fonts else []
    with open(os.path.join(outdir, "brand.css"), "w") as fh:
        fh.write("/* Generated from style.json by pipeline/style.py. Edit style.json, not this file. */\n")
        fh.write("\n".join(faces) + "\n" + css_vars(S))
    return os.path.join(outdir, "brand.css")


def rgba(c, over=(107, 107, 107)):
    """'#RGB', '#RRGGBB' or 'rgba(r,g,b,a)' -> (r, g, b), composited over `over` when it has alpha"""
    c = c.strip()
    if c.startswith("#"):
        h = c[1:]
        h = "".join(ch * 2 for ch in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(([^)]*)\)", c)
    if not m:
        raise ValueError(f"colour not understood: {c} (use #RRGGBB or rgba(r,g,b,a))")
    v = [float(x) for x in m.group(1).replace("/", ",").split(",") if x.strip()]
    a = v[3] if len(v) > 3 else 1.0
    return tuple(round(v[i] * a + over[i] * (1 - a)) for i in range(3))


def _lum(rgb):
    ch = [x / 255 for x in rgb]
    ch = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _lab(rgb):
    ch = [x / 255 for x in rgb]
    ch = [((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in ch]
    X = (0.4124 * ch[0] + 0.3576 * ch[1] + 0.1805 * ch[2]) / 0.95047
    Y = 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    Z = (0.0193 * ch[0] + 0.1192 * ch[1] + 0.9505 * ch[2]) / 1.08883
    f = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (X, Y, Z)]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def distance(a, b):
    """CIE76 delta E: under ~30 two colours read as the same family on a phone"""
    return sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b))) ** 0.5


def check(S):
    """warnings for a pack that will read badly: low contrast, or meanings that look alike"""
    C, out = S["colors"], []
    light, dark = rgba(C["light"]), rgba(C["dark"])
    pairs = [("ink on light", C["ink"], light, 7), ("light text on dark", C["light"], dark, 7),
             ("caption text on its box", C["caption_ink"], rgba(C["caption_box"]), 4.5),
             ("accent words inside the caption box", C["accent"], rgba(C["caption_box"]), 3),
             ("text box ink on its background", C["textbox_ink"], rgba(C["textbox_bg"]), 4.5),
             ("accent on dark", C["accent"], dark, 3), ("accent_on_light on light", C["accent_on_light"], light, 3),
             ("negative on dark", C["negative"], dark, 3), ("negative_on_light on light", C["negative_on_light"], light, 3),
             ("positive on dark", C["positive"], dark, 3), ("positive_on_light on light", C["positive_on_light"], light, 3)]
    answered = S.get("checks") or {}                # {check name: why the pack does this on purpose}
    for name, fg, bg, need in pairs:
        if name in answered:
            continue
        r = contrast(rgba(fg, bg), bg)
        if r < need:
            out.append(f"{name}: contrast {r:.1f}:1, needs {need}:1")
    for a, b in (("accent", "negative"), ("accent_on_light", "negative_on_light"), ("positive", "negative")):
        d = distance(rgba(C[a]), rgba(C[b]))
        if d < 30:
            out.append(f"{a} and {b} look alike (delta E {d:.0f}): emphasis and losses would read the same; move one")
    return out


def install(S, dest):
    """copy the pack's brand.css + fonts/ into a composition or card folder"""
    import shutil
    src = os.path.dirname(S["_path"]) if S.get("_path") else STYLE_DIR
    if not os.path.exists(os.path.join(src, "brand.css")):
        write(S, src)
    shutil.copy(os.path.join(src, "brand.css"), os.path.join(dest, "brand.css"))
    shutil.copytree(os.path.join(src, "fonts"), os.path.join(dest, "fonts"), dirs_exist_ok=True)


if __name__ == "__main__":
    argv, out, pack = sys.argv[1:], None, None
    while argv:
        a = argv.pop(0)
        if a == "--out":
            out = argv.pop(0)
        else:
            pack = a
    pack = pack or os.path.join(STYLE_DIR, "style.json")
    S = load(pack)
    print(write(S, out or os.path.dirname(os.path.abspath(pack))))
    for w in check(S):
        print("WARNING", w)
