#!/usr/bin/env python3
"""nle-timeline: write fx.html (an editing timeline drawn from THIS video's own data) and strip.jpg (its thumbnails).
Run it in your copy of the effect after the cut, and again after the mix or any change to the FX list:

  PY <project>/fx/<id>/gen.py [project]

Reads <project>/timeline.json (the cut: pieces, keep ranges, picture cuts), words.json (captions), edit.py (FX by
layer, BEHIND, CUT_WINDOWS, CAMERA keyframes, SOUND: sfx, music, marks), assets/voice.wav or public/master.wav (the
voice waveform) and public/clean.mp4 (thumbnails). Writes fx.html and strip.jpg next to this file. fx.js is written
by hand and reads the panel's geometry from fx.html, so it never needs regenerating.

Lanes, top to bottom, each only when it has something on it: T1 captions, V4 graphics (cam / top / over FX), V3 the
cutout (CUT_WINDOWS), V2 behind-the-head graphics, V1 the cut (thumbnails, transitions on the picture cuts, camera
keyframes), A1 voice, A2 music, A3 sound effects. FX entries without a note (helpers, the transitions) stay off the
graphics lanes. When the voice is silent (no mix yet, or a test project like the lab), A1 is drawn from words.json
timing instead, as a stand-in, and the script says so: rerun it after the mix for the real waveform.
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
PW = 980                        # panel width
X0, X1 = 92, 964                # the lanes' content area, panel px
HEAD, RULER = 56, 36            # header and ruler heights
LANE_H, LANE_GAP = 60, 8
THUMB_W, THUMB_H = 30, 52       # one thumbnail as shown (stored at 2x in strip.jpg)


def load_edit(project):
    spec = importlib.util.spec_from_file_location("edit", os.path.join(project, "edit.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rnd(i):
    v = math.sin(i * 12.9898 + 78.233) * 43758.5453
    return v - math.floor(v)


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def envelope(a, n, t0, dur, sr=8000):
    """RMS of a mono 8 kHz track in n bins over [t0, t0 + dur], normalised 0-1"""
    seg = a[int(t0 * sr):int((t0 + dur) * sr)]
    bins = np.array_split(seg, max(1, n))
    r = np.array([np.sqrt(np.mean(b * b)) if len(b) else 0.0 for b in bins])
    return r / (r.max() or 1)


def words_envelope(words, n, t0, dur):
    """a stand-in voice waveform from word timing: energy inside each word, a syllable or two of shape, near-silence
    between words. Seeded, so it never changes between runs"""
    out = []
    for k in range(n):
        t = t0 + (k + 0.5) * dur / n
        v = 0.03 + 0.05 * rnd(k + 7)
        for i, w in enumerate(words):
            if w["start"] <= t < w["end"]:
                f = (t - w["start"]) / max(0.05, w["end"] - w["start"])
                syl = 1 + int(rnd(i + 3) * 2.2)                      # one to three syllables
                shape = abs(math.sin(math.pi * f * syl)) ** 0.6
                v = (0.45 + 0.5 * rnd(i + 11)) * (0.35 + 0.65 * shape) * (0.8 + 0.2 * rnd(k * 3 + 1))
                break
        out.append(v)
    return np.array(out)


def wave_svg(env, w, h):
    bw = w / max(1, len(env))
    bars = []
    for i, v in enumerate(env):
        bh = max(1.5, float(v) ** 0.75 * (h - 6))
        bars.append(f'<rect x="{i * bw + 0.4:.1f}" y="{(h - bh) / 2:.1f}" width="{max(1, bw - 1.2):.1f}" '
                    f'height="{bh:.1f}" rx="0.8"/>')
    return f'<svg width="{w:.1f}" height="{h}" fill="currentColor">{"".join(bars)}</svg>'


def strip(project, total, px):
    """one thumbnail per THUMB_W px of timeline, side by side in one image: the V1 clips each show their part of it"""
    step = THUMB_W / px
    n = int(math.ceil(total / step))
    video = os.path.join(project, "public", "clean.mp4")
    im = Image.new("RGB", (n * THUMB_W * 2, THUMB_H * 2))
    for k in range(n):
        t = min(total - 0.05, (k + 0.5) * step)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                              f"scale={THUMB_W * 2}:{THUMB_H * 2}:force_original_aspect_ratio=increase,"
                              f"crop={THUMB_W * 2}:{THUMB_H * 2}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        if len(raw) == THUMB_W * 2 * THUMB_H * 2 * 3:
            im.paste(Image.frombytes("RGB", (THUMB_W * 2, THUMB_H * 2), raw), (k * THUMB_W * 2, 0))
    im.save(os.path.join(HERE, "strip.jpg"), quality=80)
    return n * THUMB_W


def t_end(v, total):
    return total if v == "end" else float(v)


TEMPLATE = """<!-- nle-timeline: an editing timeline built from this video's own data (its cut, captions, cutout windows, FX
     layers, camera keyframes, waveforms, sound effects) piles up on the words, a playhead tears across, then it folds
     to a line and away. GENERATED by gen.py from the project's edit.py, timeline.json, words.json and audio: edit
     gen.py or fx.js, not this file. -->
<div id="{{ID}}-box" data-span="%(span).4f" data-x0="%(x0)d" data-wpx="%(wpx)d" data-layout-allow-overlap data-layout-allow-occlusion>
<div id="{{ID}}-shadow"></div>
<div id="{{ID}}-panel" data-layout-allow-overflow>
%(content)s
</div>
</div>
<i id="{{ID}}-probe"></i>
<style>
#{{ID}}-box { position:absolute; left:50px; top:300px; width:%(pw)dpx; height:%(ph)dpx; transform-origin:50%% 50%%; }
#{{ID}}-shadow { position:absolute; left:0; top:0; width:%(pw)dpx; height:%(ph)dpx; border-radius:max(var(--radius), 12px);
  background:var(--c-dark); box-shadow:0 22px 48px color-mix(in srgb, var(--c-dark) 55%%, transparent),
  0 3px 10px color-mix(in srgb, var(--c-dark) 30%%, transparent); }
#{{ID}}-panel { position:absolute; left:0; top:0; width:%(pw)dpx; height:%(ph)dpx; border-radius:max(var(--radius), 12px);
  overflow:hidden; background:var(--c-dark); font-family:var(--font-text); color:var(--c-light); }
#{{ID}} .{{ID}}-head { position:absolute; left:0; top:0; width:%(pw)dpx; height:%(head)dpx; border-bottom:1px solid var(--c-hair-dark); }
#{{ID}} .{{ID}}-title { position:absolute; left:24px; top:16px; font-size:22px; line-height:1; font-weight:600;
  letter-spacing:-.01em; white-space:nowrap; }
#{{ID}}-tc { position:absolute; left:340px; width:300px; top:15px; text-align:center; font-family:var(--font-mono);
  font-size:25px; line-height:1; font-weight:500; color:var(--c-accent); letter-spacing:.02em;
  font-variant-numeric:tabular-nums; white-space:nowrap; }
#{{ID}} .{{ID}}-tools { position:absolute; left:676px; top:17px; display:flex; gap:18px; opacity:.8; color:var(--c-light); }
#{{ID}} .{{ID}}-zoom { position:absolute; left:812px; top:27px; width:140px; height:2px; }
#{{ID}} .{{ID}}-zline { position:absolute; left:0; top:0; width:140px; height:2px; border-radius:1px;
  background:color-mix(in srgb, var(--c-light) 25%%, transparent); }
#{{ID}}-zknob { position:absolute; left:13px; top:-6px; width:14px; height:14px; border-radius:7px; background:var(--c-light); }
#{{ID}} .{{ID}}-ruler { position:absolute; left:0; top:%(head)dpx; width:%(pw)dpx; height:%(ruler)dpx; }
#{{ID}} .{{ID}}-tick { position:absolute; bottom:0; width:1.5px; background:color-mix(in srgb, var(--c-light) 38%%, transparent); }
#{{ID}} .{{ID}}-tlab { position:absolute; top:6px; font-family:var(--font-mono); font-size:13px; line-height:1;
  color:var(--c-muted-dark); white-space:nowrap; }
#{{ID}} .{{ID}}-mark { position:absolute; top:0; width:0; height:0; border-left:6px solid transparent;
  border-right:6px solid transparent; border-top:9px solid var(--c-s3); }
#{{ID}} .{{ID}}-lane { position:absolute; left:0; width:%(pw)dpx; height:%(lh)dpx; transform-origin:50%% 50%%; }
#{{ID}} .{{ID}}-lh { position:absolute; left:10px; top:0; width:72px; height:%(lh)dpx; border-radius:8px;
  background:color-mix(in srgb, var(--c-light) 7%%, var(--c-dark)); }
#{{ID}} .{{ID}}-lh span { position:absolute; left:12px; top:20px; font-family:var(--font-mono); font-size:16px; line-height:1;
  font-weight:500; color:color-mix(in srgb, var(--c-light) 82%%, transparent); }
#{{ID}} .{{ID}}-lh i { position:absolute; right:11px; top:25px; width:9px; height:9px; border-radius:5px;
  background:color-mix(in srgb, var(--c-s2) 62%%, transparent); }
#{{ID}} .{{ID}}-lc { position:absolute; left:%(x0)dpx; top:0; width:%(wpx)dpx; height:%(lh)dpx; border-radius:8px;
  background:color-mix(in srgb, var(--c-light) 4%%, var(--c-dark)); overflow:hidden; }
#{{ID}} .{{ID}}-cap { position:absolute; top:16px; height:28px; border-radius:4px; background:var(--c-s3); }
#{{ID}} .{{ID}}-fx { position:absolute; top:7px; height:46px; border-radius:6px; overflow:hidden; }
#{{ID}} .{{ID}}-fx b { position:absolute; left:6px; top:6px; font-family:var(--font-mono); font-size:12px; line-height:1;
  font-weight:500; white-space:nowrap; color:var(--c-ink); }
#{{ID}} .{{ID}}-fxl { background:var(--c-light); }
#{{ID}} .{{ID}}-fxa { background:var(--c-accent); }
#{{ID}} .{{ID}}-cut { position:absolute; top:7px; height:46px; border-radius:6px;
  background:color-mix(in srgb, var(--c-light) 12%%, transparent);
  box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-light) 55%%, transparent); }
#{{ID}} .{{ID}}-clip { position:absolute; top:4px; height:52px; border-radius:6px; overflow:hidden;
  background-color:color-mix(in srgb, var(--c-s2) 18%%, var(--c-dark)); background-image:url(fx/{{ID}}/strip.jpg);
  background-repeat:no-repeat; background-size:%(sw)dpx 52px; }
#{{ID}} .{{ID}}-clip i { position:absolute; left:0; top:0; right:0; bottom:0; border-radius:6px;
  box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-s2) 85%%, transparent); }
#{{ID}} .{{ID}}-tx { position:absolute; top:10px; width:16px; height:40px; margin-left:-8px; border-radius:3px;
  background:var(--c-light); color:var(--c-ink); }
#{{ID}} .{{ID}}-tx svg { display:block; }
#{{ID}} .{{ID}}-kf { position:absolute; top:41px; width:12px; height:12px; margin-left:-6px; }
#{{ID}} .{{ID}}-kf i { position:absolute; left:0; top:0; width:12px; height:12px; background:var(--c-accent);
  transform:rotate(45deg) scale(.82); box-shadow:0 0 0 1.5px var(--c-dark); }
#{{ID}} .{{ID}}-aud { position:absolute; top:4px; height:52px; border-radius:6px; overflow:hidden; }
#{{ID}} .{{ID}}-aud svg { position:absolute; left:0; top:0; }
#{{ID}} .{{ID}}-a1 { color:var(--c-s2); background:color-mix(in srgb, var(--c-s2) 16%%, transparent);
  box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-s2) 50%%, transparent); }
#{{ID}} .{{ID}}-a2 { color:var(--c-accent); background:color-mix(in srgb, var(--c-accent) 14%%, transparent);
  box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c-accent) 45%%, transparent); }
#{{ID}} .{{ID}}-sfx { position:absolute; top:14px; width:7px; height:32px; border-radius:3px; background:var(--c-light); }
#{{ID}}-ph { position:absolute; left:%(x0)dpx; top:%(head)dpx; width:2px; height:%(phh)dpx; margin-left:-1px; background:var(--c-s3); }
#{{ID}} .{{ID}}-phh { position:absolute; left:-8px; top:0; width:18px; height:22px; background:var(--c-s3);
  clip-path:polygon(0 0, 100%% 0, 100%% 62%%, 50%% 100%%, 0 62%%); }
#{{ID}}-probe { position:absolute; left:0; top:0; width:0; height:0; }
</style>
"""

TOOLS = ('<svg width="22" height="22" viewBox="0 0 22 22"><path d="M5 3 L5 18 L9 14 L12 20 L14.5 19 L11.5 13 L17 13 Z" '
         'fill="currentColor"/></svg>'
         '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M11 2 V20" stroke="currentColor" stroke-width="2"/>'
         '<path d="M11 6 L15 10 L11 14 L7 10 Z" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>'
         '<svg width="22" height="22" viewBox="0 0 22 22"><rect x="2" y="7" width="10" height="8" rx="4" fill="none" '
         'stroke="currentColor" stroke-width="1.8"/><rect x="10" y="7" width="10" height="8" rx="4" fill="none" '
         'stroke="currentColor" stroke-width="1.8"/></svg>')


def main():
    project = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(HERE))
    TL = json.load(open(os.path.join(project, "timeline.json")))
    WORDS = json.load(open(os.path.join(project, "words.json")))
    E = load_edit(project)
    total = float(TL["total"])
    px = (X1 - X0) / total

    def lx(t):                  # lane-content px
        return t * px

    sound = getattr(E, "SOUND", {}) or {}
    FX = [F for F in getattr(E, "FX", []) if F.get("note")]
    lanes = []                  # (name, [html])

    # T1: captions, a block per caption chunk (a pause or four words)
    chunks, cur = [], []
    for w in WORDS:
        if cur and (w["start"] - cur[-1]["end"] > 0.25 or len(cur) >= 4):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    lanes.append(("T1", [f'<div class="{{{{ID}}}}-cap" style="left:{lx(c[0]["start"]):.1f}px;'
                         f'width:{max(3, (c[-1]["end"] - c[0]["start"]) * px - 1.5):.1f}px"></div>' for c in chunks]))

    def blocks(entries, cls):
        out = []
        for a, b, label in entries:
            w = max(4, (b - a) * px - 2)
            out.append(f'<div class="{{{{ID}}}}-fx {{{{ID}}}}-{cls}" style="left:{lx(a):.1f}px;width:{w:.1f}px"><b>{label}</b></div>')
        return out

    # V4: graphics inside and above the camera; V3: the cutout; V2: behind the head
    v4 = [(F["at"], t_end(F["end"], total), F["id"]) for F in FX if F.get("layer", "top") in ("cam", "top", "over")]
    v2 = [(F["at"], t_end(F["end"], total), F["id"]) for F in FX if F.get("layer") == "behind"]
    for B in getattr(E, "BEHIND", []) or []:
        a = B.get("at", min((it["at"] for it in B.get("items", [])), default=None))
        if a is not None and B.get("end") is not None:
            v2.append((a, t_end(B["end"], total), B.get("kind", "behind")))
    cuts = [(a, t_end(b, total)) for a, b in getattr(E, "CUT_WINDOWS", []) or []]
    if v4:
        lanes.append(("V4", blocks(v4, "fxl")))
    if cuts:
        lanes.append(("V3", [f'<div class="{{{{ID}}}}-cut" style="left:{lx(a):.1f}px;width:{max(4, (b - a) * px - 2):.1f}px"></div>'
                             for a, b in cuts]))
    if v2:
        lanes.append(("V2", blocks(v2, "fxa")))

    # V1: the cut, thumbnails from the picture, a transition on every picture cut, the camera's keyframes
    sw = strip(project, total, px)
    v1 = []
    for pc in TL.get("pieces", []):
        a, b = pc["out_start"], pc["out_end"]
        v1.append(f'<div class="{{{{ID}}}}-clip" style="left:{lx(a) + 1:.1f}px;width:{(b - a) * px - 2:.1f}px;'
                  f'background-position:{-lx(a) - 1:.1f}px 0"><i></i></div>')
    for t in TL.get("picture_cuts", []):
        v1.append(f'<div class="{{{{ID}}}}-tx" style="left:{lx(t):.1f}px"><svg width="16" height="40" viewBox="0 0 16 40">'
                  f'<path d="M2 38 L14 2" stroke="currentColor" stroke-width="2" fill="none"/></svg></div>')
    C = getattr(E, "CAMERA", {}) or {}
    keys = []
    for t, s in C.get("punch", []):
        keys += [t, t + 0.18]
    for a, b, s in C.get("zooms", []):
        keys += [a, t_end(b, total)]
    for a, b, s in C.get("pushes", []):
        keys += [a, t_end(b, total)]
    for t in C.get("settles", []):
        keys += [t, t + 0.32]
    v1 += [f'<div class="{{{{ID}}}}-kf" style="left:{lx(t):.1f}px"><i></i></div>' for t in sorted(set(keys))]
    lanes.append(("V1", v1))

    # A1: the voice under every kept piece (the real waveform, or the words.json stand-in when it's silent)
    voice = next((p for p in (os.path.join(project, "assets", "voice.wav"), os.path.join(project, "public", "master.wav"))
                  if os.path.exists(p)), None)
    track = pcm(voice) if voice else np.zeros(1, np.float32)
    silent = float(np.abs(track).max()) < 1e-3
    if silent:
        print("the voice track is silent: A1 is drawn from words.json timing (a stand-in); rerun after the mix")
    a1 = []
    for k in TL.get("keep", []):
        a, d = k["out"], min(k["src_out"] - k["src_in"], total - k["out"])
        w = d * px - 2
        n = max(4, int(w / 3.2))
        env = words_envelope(WORDS, n, a, d) if silent else envelope(track, n, a, d)
        a1.append(f'<div class="{{{{ID}}}}-aud {{{{ID}}}}-a1" style="left:{lx(a) + 1:.1f}px;width:{w:.1f}px">'
                  f'{wave_svg(env, w, LANE_H - 8)}</div>')
    lanes.append(("A1", a1))

    # A2: the music bed, section by section; A3: one blip per sound effect
    music = sound.get("music") or sound.get("score")
    if music and os.path.exists(os.path.join(project, music)):
        m = pcm(os.path.join(project, music))
        secs = sound.get("sections") or [dict(src=(0.0, total), at=0.0)]
        a2 = []
        for sec in secs:
            s0, s1 = sec["src"]
            a, d = sec.get("at", 0.0), min(s1 - s0, total - sec.get("at", 0.0))
            w = d * px - 2
            a2.append(f'<div class="{{{{ID}}}}-aud {{{{ID}}}}-a2" style="left:{lx(a) + 1:.1f}px;width:{w:.1f}px">'
                      f'{wave_svg(envelope(m, max(4, int(w / 3.2)), s0, d), w, LANE_H - 8)}</div>')
        lanes.append(("A2", a2))
    hits = []
    for s in sound.get("sfx", []) or []:
        hits.append(s["at"] if isinstance(s, dict) else s[0])
    if hits:
        lanes.append(("A3", [f'<div class="{{{{ID}}}}-sfx" style="left:{lx(t):.1f}px"></div>' for t in hits]))

    # ---- assemble: header, ruler, lanes, playhead
    ph = HEAD + RULER + 8 + len(lanes) * (LANE_H + LANE_GAP)
    H = ['<div class="{{ID}}-head">', '<div class="{{ID}}-title">Timeline</div>',
         '<div id="{{ID}}-tc">00:00:00:00</div>', f'<div class="{{{{ID}}}}-tools">{TOOLS}</div>',
         '<div class="{{ID}}-zoom"><div class="{{ID}}-zline"></div><div id="{{ID}}-zknob"></div></div>', '</div>']
    ticks = []
    for s in range(0, int(total) + 1):
        hgt = 14 if s % 10 == 0 else (9 if s % 5 == 0 else 5)
        ticks.append(f'<div class="{{{{ID}}}}-tick" style="left:{X0 + lx(s):.1f}px;height:{hgt}px"></div>')
        if s % 10 == 0:
            ticks.append(f'<div class="{{{{ID}}}}-tlab" style="left:{X0 + lx(s) + 5:.1f}px">{s // 60}:{s % 60:02d}</div>')
    for mk in sound.get("marks", []) or []:
        ticks.append(f'<div class="{{{{ID}}}}-mark" style="left:{X0 + lx(mk[0]) - 6:.1f}px"></div>')
    H.append(f'<div class="{{{{ID}}}}-ruler">{"".join(ticks)}</div>')
    for i, (name, items) in enumerate(lanes):
        H.append(f'<div class="{{{{ID}}}}-lane {{{{ID}}}}-l{i}" style="top:{HEAD + RULER + 8 + i * (LANE_H + LANE_GAP)}px">'
                 f'<div class="{{{{ID}}}}-lh"><span>{name}</span><i></i></div><div class="{{{{ID}}}}-lc">')
        H += items
        H.append('</div></div>')
    H.append('<div id="{{ID}}-ph"><div class="{{ID}}-phh"></div></div>')
    html = TEMPLATE % dict(content="\n".join(H), span=total, x0=X0, wpx=X1 - X0, pw=PW, ph=ph, head=HEAD, ruler=RULER,
                           lh=LANE_H, phh=ph - HEAD, sw=sw)
    open(os.path.join(HERE, "fx.html"), "w", encoding="utf-8").write(html)
    print(f"fx.html: {len(lanes)} lanes ({', '.join(n for n, _ in lanes)}), {total:.2f}s at {px:.2f} px/s, "
          f"panel {PW}x{ph}; strip.jpg {sw // THUMB_W} thumbnails")


if __name__ == "__main__":
    main()
