#!/usr/bin/env python3
"""nle-timeline (built on the kit's nle-timeline): write fx.html (THIS video's editing timeline, drawn from its own
data) and strip.jpg (the thumbnails on V1). Rerun it after pasting the FX entry (so this effect's own block shows
selected), after the mix (the real waveform and the sound blips), and after any change to the cut, the captions or the
FX list:

  PY <project>/fx/<id>/gen.py [project]

Reads <project>/edit.py (CAPS, FX by layer, CARDS, BEHIND, CUT_WINDOWS, CAMERA, GRADES, BW, SOUND), timeline.json
(pieces, keep ranges), assets/voice.wav (the real waveform) and public/clean.mp4 (thumbnails, graded the way the
edit grades them: B&W beats, GRADES looks, the house grade). fx.js reads the geometry from fx.html.

Lanes, top to bottom (compositing order, as in the build): T1 the captions (one block per CAPS line, thesis lines in
the accent), V4 graphics above the speaker (cam / top / over FX, and the full-screen cards), V3 the speaker cutout
(CUT_WINDOWS), V2 behind-the-head graphics (behind FX, BEHIND), V1 the cut (one clip per piece: source file name,
thumbnails, camera keyframes), A1 the voice (one clip per kept line, so the J-cuts show), A2 sound effects when the
mix has them. Every block carries data-a / data-b (its window, seconds) so fx.js can flood them in from the playhead.
T1 is drawn from the hi-fi CAPS list: a lo-fi edit (no CAPS) leaves it empty.
"""
import importlib.util
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(HERE)              # this effect's own id: its block on V4 is drawn selected
PW = 1010                                   # panel width
X0, X1 = 88, 998                            # lane content, panel px
HEAD, RULER, TOP_GAP, BOT_PAD = 46, 20, 4, 5
LANE_H, LANE_GAP = 37, 3                    # 7 lanes fit 352 px: y 220-572, clear of the eyes
CLIP_H = LANE_H - 6                         # a V1 clip
THUMB_W = 17                                # one thumbnail as shown (9:16 at CLIP_H; stored at 2x)


def load_edit(project):
    spec = importlib.util.spec_from_file_location("edit", os.path.join(project, "edit.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pcm(path, sr=8000):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def envelope(a, n, t0, dur, sr=8000):
    seg = a[int(t0 * sr):int((t0 + dur) * sr)]
    bins = np.array_split(seg, max(1, n))
    return np.array([np.sqrt(np.mean(b * b)) if len(b) else 0.0 for b in bins])


def wave_svg(env, w, h):
    bw = w / max(1, len(env))
    bars = []
    for i, v in enumerate(env):
        bh = max(1.5, float(v) ** 0.75 * (h - 6))
        bars.append(f'<rect x="{i * bw + 0.4:.1f}" y="{(h - bh) / 2:.1f}" width="{max(1, bw - 1.1):.1f}" '
                    f'height="{bh:.1f}" rx="0.7"/>')
    return f'<svg width="{w:.1f}" height="{h}" fill="currentColor">{"".join(bars)}</svg>'


# ---- the edit's looks on the thumbnails (CSS filter maths, Filter Effects spec), so V1 shows what the video shows
def _mat_sat(s):
    return np.array([[0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s],
                     [0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s],
                     [0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s]])


def _mat_hue(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928],
                     [0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283],
                     [0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072]])


def _mat_sepia(a):
    full = np.array([[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]])
    return (1 - a) * np.eye(3) + a * full


def css_filter(rgb, spec):
    """apply a CSS filter list ('sepia(.06) saturate(.92) contrast(1.08)') to an HxWx3 float image in 0-1"""
    import re
    out = rgb.copy()
    for name, val in re.findall(r"([a-z-]+)\(([^)]*)\)", spec or ""):
        v = float(val.replace("deg", ""))
        if name == "sepia":
            out = out @ _mat_sepia(min(1, v)).T
        elif name == "saturate":
            out = out @ _mat_sat(v).T
        elif name == "grayscale":
            out = out @ ((1 - min(1, v)) * np.eye(3) + min(1, v) * _mat_sat(0)).T
        elif name == "hue-rotate":
            out = out @ _mat_hue(v).T
        elif name == "contrast":
            out = (out - 0.5) * v + 0.5
        elif name == "brightness":
            out = out * v
        out = np.clip(out, 0, 1)
    return out


def look_at(E, t, looks, house):
    for a, b in getattr(E, "BW", []) or []:
        if a <= t < b:
            return "grayscale(1) contrast(1.2) brightness(0.9)"
    for G in getattr(E, "GRADES", []) or []:
        if G[0] <= t < (G[1] if G[1] != "end" else 1e9):
            return looks.get(G[2], G[2])
    return house


def thumbs(project, E, pieces, px, house, looks):
    """one sprite: each clip's own thumbnails side by side (its first frame at its head, as an editor shows a clip),
    graded the way the edit grades that moment. Returns each clip's x offset in the sprite and the sprite width."""
    video = os.path.join(project, "public", "clean.mp4")
    tiles, offs = [], []
    for a, b in pieces:
        offs.append(len(tiles) * THUMB_W)
        w = (b - a) * px
        n = max(1, int(math.ceil(w / THUMB_W)))
        for k in range(n):
            tiles.append(min(b - 0.04, a + 0.02 + k * THUMB_W / px))
    im = Image.new("RGB", (len(tiles) * THUMB_W * 2, CLIP_H * 2))
    for k, t in enumerate(tiles):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                              f"scale={THUMB_W * 2}:{CLIP_H * 2}:force_original_aspect_ratio=increase,"
                              f"crop={THUMB_W * 2}:{CLIP_H * 2}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        if len(raw) == THUMB_W * 2 * CLIP_H * 2 * 3:
            arr = np.frombuffer(raw, np.uint8).reshape(CLIP_H * 2, THUMB_W * 2, 3).astype(np.float32) / 255
            arr = css_filter(arr, look_at(E, t, looks, house))
            im.paste(Image.fromarray((arr * 255 + 0.5).astype(np.uint8)), (k * THUMB_W * 2, 0))
    im.save(os.path.join(HERE, "strip.jpg"), quality=86)
    return offs, len(tiles) * THUMB_W


def t_end(v, total):
    return total if v == "end" else float(v)


def settle_times(E, TL):
    """the camera's settle keyframes, as pipeline/build.py places them: every visible picture cut or reframe and
    every card end, except where a punch-in or push starts"""
    C = getattr(E, "CAMERA", {}) or {}
    if "settles" in C:
        return C["settles"]
    starts = [p[0] for p in C.get("punch", [])] + [p[0] for p in C.get("pushes", [])]
    wins = [(c[2], c[3]) for c in E.CARDS]

    def visible(t):
        return not any(a - 1e-6 <= t + 0.001 < b - 1e-6 for a, b in wins)
    ends = [c[3] for c in E.CARDS if visible(c[3])]
    changes = [t for t in TL["picture_cuts"] + TL["reframes"] if visible(t)]
    return sorted({round(t, 3) for t in ends + changes if all(abs(t - p) > 0.02 for p in starts)})


def source_names(project, pieces_src):
    """each piece's source file (take-1.mov) from the joined source's offsets, when work/shared/edit-data.json has them"""
    p = os.path.join(project, "work", "shared", "edit-data.json")
    if not os.path.exists(p):
        return [""] * len(pieces_src)
    clips = sorted(json.load(open(p)).get("clips", []), key=lambda c: c["offset"])
    out = []
    for s in pieces_src:
        name = ""
        for c in clips:
            if c["offset"] <= s < c["offset"] + c["seconds"]:
                name = c["clip"]
        out.append(name)
    return out


TEMPLATE = """<!-- nle: THIS video's editing timeline (its captions, graphics, cards, cutout windows, the cut with its graded
     thumbnails and camera keyframes, the voice with its J-cuts) opens empty over the shot, floods in from the playhead
     on the words, holds with the playhead on the frame you are watching, then folds to a line. GENERATED by gen.py
     from the project's own files: edit gen.py or fx.js, not this file. -->
<div id="{{ID}}-box" data-span="%(span).4f" data-x0="%(x0)d" data-wpx="%(wpx)d" data-ph="%(ph)d" data-title="%(title)s" data-layout-allow-overlap data-layout-allow-occlusion>
<div id="{{ID}}-shadow"></div>
<div id="{{ID}}-panel" data-layout-allow-overflow data-layout-allow-overlap data-layout-allow-occlusion>
%(content)s
</div>
</div>
<style>
#{{ID}}-box { position:absolute; left:35px; top:220px; width:%(pw)dpx; height:%(ph)dpx; }
#{{ID}}-shadow { position:absolute; left:0; top:0; width:%(pw)dpx; height:%(ph)dpx; border-radius:10px;
  background:var(--c-dark); box-shadow:0 18px 40px color-mix(in srgb, var(--c-dark) 42%%, transparent),
  0 2px 8px color-mix(in srgb, var(--c-dark) 26%%, transparent); }
#{{ID}}-panel { position:absolute; left:0; top:0; width:%(pw)dpx; height:%(ph)dpx; border-radius:10px;
  overflow:hidden; background:var(--c-dark); font-family:var(--font-text); color:var(--c-light); }
#{{ID}} .{{ID}}-head { position:absolute; left:0; top:0; width:%(pw)dpx; height:%(head)dpx; border-bottom:1px solid var(--c-hair-dark); }
#{{ID}} .{{ID}}-tab { position:absolute; left:18px; top:11px; height:24px; padding:0 12px 0 26px; border-radius:var(--radius);
  background:color-mix(in srgb, var(--c-light) 8%%, var(--c-dark)); font-family:var(--font-mono); font-size:15px; line-height:24px;
  font-weight:500; color:color-mix(in srgb, var(--c-light) 86%%, transparent); white-space:nowrap; }
#{{ID}} .{{ID}}-tab i { position:absolute; left:10px; top:8px; width:8px; height:8px; border-radius:2px; background:var(--c-s2); }
#{{ID}}-tc { position:absolute; left:355px; width:300px; top:8px; text-align:center; font-family:var(--font-mono);
  font-size:28px; line-height:30px; font-weight:500; color:var(--c-accent); letter-spacing:.02em;
  font-variant-numeric:tabular-nums; white-space:nowrap; }
#{{ID}} .{{ID}}-tools { position:absolute; left:700px; top:12px; display:flex; gap:16px; opacity:.72; color:var(--c-light); }
#{{ID}} .{{ID}}-zoom { position:absolute; left:842px; top:23px; width:136px; height:2px; }
#{{ID}} .{{ID}}-zline { position:absolute; left:0; top:0; width:136px; height:2px; border-radius:1px;
  background:color-mix(in srgb, var(--c-light) 25%%, transparent); }
#{{ID}}-zknob { position:absolute; left:96px; top:-6px; width:14px; height:14px; border-radius:7px; background:var(--c-light); }
#{{ID}} .{{ID}}-ruler { position:absolute; left:0; top:%(head)dpx; width:%(pw)dpx; height:%(ruler)dpx; }
#{{ID}} .{{ID}}-tick { position:absolute; bottom:0; width:1.5px; background:color-mix(in srgb, var(--c-light) 34%%, transparent); }
#{{ID}} .{{ID}}-tlab { position:absolute; top:3px; font-family:var(--font-mono); font-size:12px; line-height:1;
  color:var(--c-muted-dark); white-space:nowrap; }
#{{ID}} .{{ID}}-lane { position:absolute; left:0; width:%(pw)dpx; height:%(lh)dpx; transform-origin:50%% 50%%; }
#{{ID}} .{{ID}}-lh { position:absolute; left:10px; top:0; width:70px; height:%(lh)dpx; border-radius:6px;
  background:color-mix(in srgb, var(--c-light) 7%%, var(--c-dark)); }
#{{ID}} .{{ID}}-lh span { position:absolute; left:11px; top:%(lht)dpx; font-family:var(--font-mono); font-size:15px; line-height:1;
  font-weight:500; color:color-mix(in srgb, var(--c-light) 82%%, transparent); }
#{{ID}} .{{ID}}-lh i { position:absolute; right:10px; top:%(lhi)dpx; width:8px; height:8px; border-radius:4px;
  background:color-mix(in srgb, var(--c-s2) 62%%, transparent); }
#{{ID}} .{{ID}}-lc { position:absolute; left:%(x0)dpx; top:0; width:%(wpx)dpx; height:%(lh)dpx; border-radius:6px;
  background:color-mix(in srgb, var(--c-light) 4%%, var(--c-dark)); overflow:hidden; }
#{{ID}} .{{ID}}-cap { position:absolute; top:%(capt)dpx; height:17px; border-radius:3px; background:var(--c-s3); }
#{{ID}} .{{ID}}-cap.{{ID}}-th { background:var(--c-accent); }
#{{ID}} .{{ID}}-fx { position:absolute; top:4px; height:%(fxh)dpx; border-radius:5px; overflow:hidden; }
#{{ID}} .{{ID}}-fx b { position:absolute; left:5px; top:4px; font-family:var(--font-mono); font-size:11px; line-height:1;
  font-weight:500; white-space:nowrap; color:var(--c-ink); }
#{{ID}} .{{ID}}-half b { top:1px; font-size:10px; }
#{{ID}} .{{ID}}-fxl { background:var(--c-light); }
#{{ID}} .{{ID}}-fxs { background:var(--c-s2); }
#{{ID}} .{{ID}}-cdk { background:var(--c-dark); box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-light) 70%%, transparent); }
#{{ID}} .{{ID}}-cdk b { color:var(--c-light); }
#{{ID}} .{{ID}}-clt { background:color-mix(in srgb, var(--c-light) 82%%, var(--c-s3)); }
#{{ID}} .{{ID}}-sel { position:absolute; left:0; top:0; right:0; bottom:0; border-radius:5px;
  box-shadow:inset 0 0 0 2.5px var(--c-accent); }
#{{ID}} .{{ID}}-cut { position:absolute; top:4px; height:%(fxh)dpx; border-radius:5px;
  background:color-mix(in srgb, var(--c-s2) 20%%, transparent);
  box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-s2) 80%%, transparent); }
#{{ID}} .{{ID}}-clip { position:absolute; top:3px; height:%(ch)dpx; border-radius:5px; overflow:hidden;
  background-color:color-mix(in srgb, var(--c-s2) 18%%, var(--c-dark)); background-image:url(fx/{{ID}}/strip.jpg);
  background-repeat:no-repeat; background-size:%(sw)dpx %(ch)dpx; }
#{{ID}} .{{ID}}-clip i { position:absolute; left:0; top:0; right:0; bottom:0; border-radius:5px;
  box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-s2) 85%%, transparent); }
#{{ID}} .{{ID}}-kf { position:absolute; top:%(kft)dpx; width:8px; height:8px; margin-left:-4px; }
#{{ID}} .{{ID}}-kf i { position:absolute; left:0; top:0; width:8px; height:8px; background:var(--c-s3);
  transform:rotate(45deg) scale(.74); box-shadow:0 0 0 1.25px var(--c-dark); }
#{{ID}} .{{ID}}-aud { position:absolute; top:3px; height:%(ch)dpx; border-radius:5px; overflow:hidden; }
#{{ID}} .{{ID}}-aud svg { position:absolute; left:0; top:0; }
#{{ID}} .{{ID}}-a1 { color:var(--c-s2); background:color-mix(in srgb, var(--c-s2) 16%%, transparent);
  box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-s2) 50%%, transparent); }
#{{ID}} .{{ID}}-sfx { position:absolute; top:7px; width:6px; height:%(sfxh)dpx; border-radius:3px; background:var(--c-light); }
#{{ID}}-ph { position:absolute; left:%(x0)dpx; top:%(head)dpx; width:2px; height:%(phh)dpx; margin-left:-1px; background:var(--c-accent); }
#{{ID}} .{{ID}}-phh { position:absolute; left:-7px; top:0; width:16px; height:18px; background:var(--c-accent);
  clip-path:polygon(0 0, 100%% 0, 100%% 62%%, 50%% 100%%, 0 62%%); }
</style>
"""

TOOLS = ('<svg width="20" height="20" viewBox="0 0 22 22"><path d="M5 3 L5 18 L9 14 L12 20 L14.5 19 L11.5 13 L17 13 Z" '
         'fill="currentColor"/></svg>'
         '<svg width="20" height="20" viewBox="0 0 22 22"><path d="M11 2 V20" stroke="currentColor" stroke-width="2"/>'
         '<path d="M11 6 L15 10 L11 14 L7 10 Z" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>'
         '<svg width="20" height="20" viewBox="0 0 22 22"><rect x="2" y="7" width="10" height="8" rx="4" fill="none" '
         'stroke="currentColor" stroke-width="1.8"/><rect x="10" y="7" width="10" height="8" rx="4" fill="none" '
         'stroke="currentColor" stroke-width="1.8"/></svg>')


def main():
    if os.path.exists(os.path.join(HERE, "preset.json")):
        sys.exit(f"{HERE} is the preset library: make an instance (pipeline/preset.py add) and run its copy")
    project = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(HERE))
    TL = json.load(open(os.path.join(project, "timeline.json")))
    E = load_edit(project)
    total = float(TL["total"])
    px = (X1 - X0) / total
    style = json.load(open(os.path.join(project, "style", "style.json")))
    house = style.get("grade") or ""
    # the named looks, same values as pipeline/build.py LOOKS
    looks = {"warm": "sepia(0.34) contrast(1.05) saturate(1.3) brightness(1.04) hue-rotate(-9deg)",
             "moody": "sepia(0.06) contrast(1.24) saturate(0.55) brightness(0.70) hue-rotate(4deg)"}

    def lx(t):
        return t * px

    def blk(cls, a, b, lane, inner="", style_extra="", minw=3.0, gap=1.5, extra=""):
        w = max(minw, (b - a) * px - gap)
        return (f'<div class="{{{{ID}}}}-b {cls}" data-lane="{lane}" data-a="{a:.3f}" data-b="{b:.3f}"{extra} '
                f'style="left:{lx(a):.1f}px;width:{w:.1f}px;{style_extra}">{inner}</div>')

    def stacked(items, lane, top=4, gap=2):
        """chips that overlap in time (FX on different layers, e.g. a cam look under an over-layer caption effect)
        stack in sub-rows of the lane, the way an editor would put them on separate tracks: only the chips that
        actually overlap split the lane's height, the rest stay full height, so no chip or label covers another"""
        h = LANE_H - 8
        order = sorted(range(len(items)), key=lambda i: (items[i][0], -items[i][1]))
        ends, row = [], [0] * len(items)
        for i in order:
            for r, e in enumerate(ends):
                if items[i][0] >= e - 1e-6:
                    row[i], ends[r] = r, items[i][1]
                    break
            else:
                row[i] = len(ends)
                ends.append(items[i][1])
        n, out = max(1, len(ends)), []
        for i, (a, b, cls, inner) in enumerate(items):
            over = any(j != i and a < items[j][1] - 1e-6 and items[j][0] < b - 1e-6 for j in range(len(items)))
            st = ""
            if over and n > 1:
                sh = (h - (n - 1) * 2) / n
                st, cls = f"top:{top + row[i] * (sh + 2):.1f}px;height:{sh:.1f}px;", cls + " {{ID}}-half"
            out.append(blk(cls, a, b, lane, inner, st, gap=gap))
        return out

    sound = getattr(E, "SOUND", {}) or {}
    FX = [F for F in getattr(E, "FX", []) if F.get("note")]
    lanes = []

    # T1: every caption line, thesis lines in the accent
    caps = []
    for i, c in enumerate(E.CAPS):
        a = float(c[0])
        b = t_end(c[3], total) if len(c) > 3 else (float(E.CAPS[i + 1][0]) if i + 1 < len(E.CAPS) else total)
        caps.append(blk("{{ID}}-cap" + (" {{ID}}-th" if c[2] == "thesis" else ""), a, min(b, total), "T1"))
    lanes.append(("T1", caps))

    # V4: graphics above the speaker and the full-screen cards; this effect's own block is selected
    v4 = []
    for F in FX:
        if F.get("layer", "top") in ("cam", "top", "over"):
            sel = '<i class="{{ID}}-sel"></i>' if F["id"] == SELF else ""
            v4.append((F["at"], t_end(F["end"], total), "{{ID}}-fx {{ID}}-fxl" + (" {{ID}}-self" if sel else ""),
                       f'<b>{F["id"]}</b>{sel}'))
    for c in getattr(E, "CARDS", []) or []:
        v4.append((c[2], c[3], "{{ID}}-fx " + ("{{ID}}-clt" if c[4] == "light" else "{{ID}}-cdk"), f"<b>{c[0]}</b>"))
    v4 = stacked(v4, "V4")
    if v4:
        lanes.append(("V4", v4))
    # V3: the cutout
    cw = stacked([(a, t_end(b, total), "{{ID}}-cut", "") for a, b in getattr(E, "CUT_WINDOWS", []) or []], "V3")
    if cw:
        lanes.append(("V3", cw))
    # V2: behind the head
    v2 = [(F["at"], t_end(F["end"], total), "{{ID}}-fx {{ID}}-fxs", f'<b>{F["id"]}</b>')
          for F in FX if F.get("layer") == "behind"]
    for B in getattr(E, "BEHIND", []) or []:
        a = B.get("at", min((it["at"] for it in B.get("items", [])), default=None))
        if a is not None and B.get("end") is not None:
            v2.append((a, t_end(B["end"], total), "{{ID}}-fx {{ID}}-fxs", f'<b>{B.get("kind", "behind")}</b>'))
    v2 = stacked(v2, "V2")
    if v2:
        lanes.append(("V2", v2))

    # V1: one clip per piece with its own graded thumbnails; the camera's keyframes along the bottom
    pieces = TL.get("pieces", [])
    offs, sw = thumbs(project, E, [(p["out_start"], p["out_end"]) for p in pieces], px, house, looks)
    names = source_names(project, [p["src"] for p in pieces])
    v1 = []
    for k, p in enumerate(pieces):
        a, b = p["out_start"], p["out_end"]
        v1.append(blk("{{ID}}-clip", a, b, "V1", "<i></i>", f"background-position:{-offs[k]:.1f}px 0", gap=2,
                      extra=f' data-k="clip" data-src="{names[k]}" data-frame="{p.get("frame", "")}"'))
    C = getattr(E, "CAMERA", {}) or {}
    keys = []
    for t in settle_times(E, TL):
        keys += [t, t + 0.32]
    for t, s in C.get("punch", []):
        keys += [t, t + 0.18]
    for a, b, s in C.get("pushes", []):
        keys += [a, t_end(b, total)]
    o = C.get("open")
    if o:
        keys += [0.0, o[1]]
    kept = []
    for t in sorted(set(round(min(k, total - 0.05), 3) for k in keys)):
        if not kept or (t - kept[-1]) * px >= 7:          # merge keys closer than a diamond
            kept.append(t)
    v1 += [f'<div class="{{{{ID}}}}-b {{{{ID}}}}-kf" data-lane="KF" data-a="{t:.3f}" data-b="{t:.3f}" '
           f'style="left:{lx(t):.1f}px"><i></i></div>' for t in kept]
    lanes.append(("V1", v1))

    # A1: the voice, one clip per kept line at its real place (the audio leads the picture: the J-cuts)
    voice = next((p for p in (os.path.join(project, "assets", "voice.wav"), os.path.join(project, "public", "master.wav"))
                  if os.path.exists(p)), None)
    track = pcm(voice) if voice else np.zeros(1, np.float32)
    a1, envs = [], []
    for k in TL.get("keep", []):
        a, d = k["out"], min(k["src_out"] - k["src_in"], total - k["out"])
        w = d * px - 2
        envs.append((a, d, w, envelope(track, max(4, int(w / 3.0)), a, d)))
    peak = max((float(e.max()) for _, _, _, e in envs if len(e)), default=1.0) or 1.0
    for a, d, w, env in envs:
        a1.append(f'<div class="{{{{ID}}}}-b {{{{ID}}}}-aud {{{{ID}}}}-a1" data-lane="A1" data-k="aud" data-a="{a:.3f}" '
                  f'data-b="{a + d:.3f}" style="left:{lx(a) + 1:.1f}px;width:{w:.1f}px">{wave_svg(env / peak, w, CLIP_H)}</div>')
    lanes.append(("A1", a1))

    # A2: one blip per sound effect, once the mix has them
    hits = [(s["at"] if isinstance(s, dict) else s[0]) for s in sound.get("sfx", []) or []]
    if hits:
        lanes.append(("A2", [f'<div class="{{{{ID}}}}-b {{{{ID}}}}-sfx" data-lane="A2" data-a="{t:.3f}" data-b="{t:.3f}" '
                             f'style="left:{lx(t):.1f}px"></div>' for t in hits]))

    # ---- assemble: header, ruler, lanes, playhead
    top0 = HEAD + RULER + TOP_GAP
    ph = top0 + len(lanes) * LANE_H + (len(lanes) - 1) * LANE_GAP + BOT_PAD
    H = ['<div class="{{ID}}-head">', '<div class="{{ID}}-tab"><i></i><span id="{{ID}}-title">sequence</span></div>',
         '<div id="{{ID}}-tc">00:00:00:00</div>', f'<div class="{{{{ID}}}}-tools">{TOOLS}</div>',
         '<div class="{{ID}}-zoom"><div class="{{ID}}-zline"></div><div id="{{ID}}-zknob"></div></div>', '</div>']
    ticks = []
    for s in range(0, int(total) + 1):
        hgt = 12 if s % 10 == 0 else (8 if s % 5 == 0 else 4)
        ticks.append(f'<div class="{{{{ID}}}}-tick" style="left:{X0 + lx(s):.1f}px;height:{hgt}px"></div>')
        if s % 10 == 0:
            ticks.append(f'<div class="{{{{ID}}}}-tlab" style="left:{X0 + lx(s) + 5:.1f}px">{s // 60}:{s % 60:02d}</div>')
    for mk in sound.get("marks", []) or []:
        ticks.append(f'<div class="{{{{ID}}}}-tick" style="left:{X0 + lx(mk[0]):.1f}px;height:14px"></div>')
    H.append(f'<div class="{{{{ID}}}}-ruler">{"".join(ticks)}</div>')
    for i, (name, items) in enumerate(lanes):
        H.append(f'<div class="{{{{ID}}}}-lane {{{{ID}}}}-l{i}" data-name="{name}" style="top:{top0 + i * (LANE_H + LANE_GAP)}px">'
                 f'<div class="{{{{ID}}}}-lh"><span>{name}</span><i></i></div><div class="{{{{ID}}}}-lc">')
        H += items
        H.append('</div></div>')
    H.append('<div id="{{ID}}-ph"><div class="{{ID}}-phh"></div></div>')
    html = TEMPLATE % dict(content="\n".join(H), title=os.path.basename(project.rstrip(os.sep)).replace('"', ''), span=total, x0=X0, wpx=X1 - X0, pw=PW, ph=ph, head=HEAD, ruler=RULER,
                           lh=LANE_H, ch=CLIP_H, phh=ph - HEAD - BOT_PAD, sw=sw, lht=(LANE_H - 15) // 2,
                           lhi=(LANE_H - 8) // 2, capt=(LANE_H - 17) // 2, fxh=LANE_H - 8, kft=LANE_H - 11, sfxh=LANE_H - 14)
    open(os.path.join(HERE, "fx.html"), "w", encoding="utf-8").write(html)
    n_caps, n_v1 = len(caps), len(pieces)
    print(f"fx.html: {len(lanes)} lanes ({', '.join(n for n, _ in lanes)}), {total:.2f}s at {px:.2f} px/s, panel {PW}x{ph}; "
          f"{n_caps} captions, {len(v4)} V4, {len(cw)} cutout, {len(v2)} V2, {n_v1} clips, {len(kept)} keyframes, "
          f"{len(a1)} voice clips, {len(hits)} sfx; strip.jpg {sw // THUMB_W} thumbnails")


if __name__ == "__main__":
    main()
