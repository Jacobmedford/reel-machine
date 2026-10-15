// wall-window (layer: behind, under the speaker's cutout; needs a CUT_WINDOWS entry over the window), built on the
// kit's video-card. "Here's the full version of this video":
//   seam   T.seam   a hairline draws on the wall beside the head, left to right
//   open   T.open   the window opens out of it: the title strip up, the picture down. The picture is a clip from
//                   MEDIA_START (default THIS video from 0:00, a copy of clean.mp4 as its own clip): the speaker walks in
//   label  T.label  LABEL types into the strip; the progress runs along the seam until the fold
//   tag    T.tag    a true tag types onto the picture, done by T.tagEnd
//   fold   T.fold   the picture rolls back up into the seam, the strip shuts, the seam retracts: gone at T.gone
// The head breaks the window's edge (CUT_WINDOWS puts the speaker in front). The clip's start in fx.html is bound to
// T.open by preset.py.
// PRESET CONSTANTS START
var LABEL = "FULL VERSION";                // the title strip, typed
var TAG = "THIS VIDEO · 0:45";        // a true tag on the picture (this video's real length: timeline.json total)
// px: the window's left, top and width (the picture is 9:16 inside), the title strip's height and the frame's width;
// beside the head, so the head breaks its left edge (measure on a still of the shot)
var WIN = {"x": 532, "y": 238, "w": 470, "strip": 56, "frame": 4};
// beats, seconds after A or spoken words: seam, open ("full"), label, tag ("this"), tagEnd, fold (after the line),
// gone (before the cut at B)
var T = {"seam": 0.637, "open": 0.738, "label": 0.839, "tag": 1.895, "tagEnd": 2.718, "fold": 3.153, "gone": 3.469};
var SRC = "clean.mp4";                     // the clip in the window: clean.mp4 (this video), or fx/{{ID}}/<file>.mp4
var MEDIA_START = 0;                       // s into the clip the window starts on (0: its first frame)
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word: 'version' is the start of the first such word at
// or after A, 'version-0.05' nudges it. preset.py checks every word against words.json when it makes the instance.
function cues(v, after) {
  if (typeof v === 'string') {
    var m = /^(.*?)([+-]\d*\.?\d+)?$/.exec(v.trim()), t = wordAt(m[1], A + (after || 0));
    if (t === null && after) t = wordAt(m[1], A);
    if (t === null) { console.error('{{ID}}: no spoken "' + m[1] + '" after ' + A); return after || 0; }
    return t - A + (m[2] ? parseFloat(m[2]) : 0);
  }
  if (Array.isArray(v)) {
    var f = after || 0;
    return v.map(function (x) { var r = cues(x, f); if (typeof r === 'number') f = r + 0.01; return r; });
  }
  if (v && typeof v === 'object') { var o = {}; for (var k in v) o[k] = cues(v[k], after); return o; }
  return v;
}
T = cues(T);

var P = '#{{ID}}-';
function $(s) { return document.querySelector(s); }
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function px(v) { return (+v.toFixed(2)) + 'px'; }
function ins(t, r, b, l, rad) { return 'inset(' + px(t) + ' ' + px(r) + ' ' + px(b) + ' ' + px(l) + ' round ' + px(rad) + ')'; }
// clip-paths are drawn per frame (tl.set from one eased progress), never tweened: GSAP reads an inset back in short
// form and the tween jumps
function frames(t0, dur, ease, fn) {
  var E = gsap.parseEase(ease), n = Math.max(1, Math.round(dur * 30));
  for (var i = 0; i <= n; i++) fn(E(i / n), q(t0 + i / 30));
}
function chars(el, text) {
  for (var i = 0; i < text.length; i++) { var s = document.createElement('span'); s.textContent = text[i]; el.appendChild(s); }
  return el.querySelectorAll('span');
}

// ---- the window, built from the constants (static)
var RAD = parseFloat(tok('--radius')) || 0;
var VW = WIN.w - 2 * WIN.frame, VH = Math.round(VW * 16 / 9), H = WIN.strip + VH + WIN.frame;
var win = $(P + 'win');
win.style.left = WIN.x + 'px'; win.style.top = WIN.y + 'px';
win.style.width = WIN.w + 'px'; win.style.height = H + 'px';
var sh = $(P + 'shadow'); sh.style.width = WIN.w + 'px'; sh.style.height = H + 'px';
var vw = $(P + 'vw');
vw.style.top = WIN.strip + 'px'; vw.style.width = WIN.w + 'px'; vw.style.height = (VH + WIN.frame) + 'px';
var v = $(P + 'v');
v.style.left = WIN.frame + 'px'; v.style.top = '0px'; v.style.width = VW + 'px'; v.style.height = VH + 'px';
var st = $(P + 'strip'); st.style.width = WIN.w + 'px'; st.style.height = WIN.strip + 'px';
var seam = $(P + 'seam'); seam.style.top = (WIN.strip - 4) + 'px'; seam.style.width = WIN.w + 'px';
var tag = $(P + 'tag'); tag.style.left = (WIN.frame + 14) + 'px'; tag.style.top = '14px';
var lab = chars($(P + 'lab'), LABEL), tg = chars($(P + 'tagt'), TAG);
var VB = VH + WIN.frame;                         // the picture's frame height

// ---- start states
gsap.set(seam, { scaleX: 0, transformOrigin: '0% 50%' });
gsap.set(P + 'fill', { scaleX: 0 });
gsap.set(st, { clipPath: ins(WIN.strip, 0, 0, 0, 0) });
gsap.set(vw, { clipPath: ins(0, 0, VB, 0, 0) });
gsap.set([sh, tag], { opacity: 0 });
gsap.set(P + 'caret', { opacity: 0 });

// ---- seam, then the window opens out of it on "walk-": the strip up, the picture down, the shadow lifts it
tl.fromTo(seam, { scaleX: 0 }, { scaleX: 1, duration: 0.16, ease: 'power3.out', immediateRender: false }, q(A + T.seam));
frames(A + T.open, 5 / 30, 'power3.out', function (p, t) {
  tl.set(st, { clipPath: ins(WIN.strip * (1 - p), 0, 0, 0, RAD * p) }, t);
});
frames(A + T.open, 11 / 30, 'expo.out', function (p, t) {
  tl.set(vw, { clipPath: ins(0, 0, VB * (1 - p), 0, RAD * p) }, t);
});
tl.fromTo(sh, { opacity: 0 }, { opacity: 1, duration: 0.24, ease: 'power2.out', immediateRender: false }, q(A + T.open + 0.1));

// ---- LABEL types into the strip; the progress runs along the seam while the picture plays
var dl = Math.min(0.03, 0.3 / LABEL.length);
for (var i = 0; i < lab.length; i++) tl.set(lab[i], { display: 'inline' }, q(A + T.label + i * dl));
tl.fromTo(P + 'fill', { scaleX: 0 }, { scaleX: 1, duration: T.fold - T.open, ease: 'none', immediateRender: false }, q(A + T.open));

// ---- the tag pops onto the picture and types, its caret solid while typing, then blinking
var t0 = A + T.tag, t1 = A + T.tagEnd, dt = (t1 - t0) / tg.length;
tl.set(tag, { opacity: 1 }, q(t0));
tl.fromTo(tag, { scale: 0.86 }, { scale: 1, duration: 0.18, ease: 'back.out(1.7)', immediateRender: false }, q(t0));
tl.set(P + 'caret', { opacity: 1 }, q(t0));
for (var j = 0; j < tg.length; j++) tl.set(tg[j], { display: 'inline' }, q(t0 + j * dt));
for (var bt = t1 + 0.2, bv = 0; bt < A + T.fold; bt += 0.27, bv = 1 - bv) tl.set(P + 'caret', { opacity: bv }, q(bt));

// ---- fold: the picture rolls back up into the seam (the tag with it), the strip shuts, the seam retracts
var tf = A + T.fold;
frames(tf, 6 / 30, 'power3.in', function (p, t) {
  tl.set(vw, { clipPath: ins(0, 0, VB * p, 0, RAD * (1 - p)) }, t);
});
tl.fromTo(sh, { opacity: 1 }, { opacity: 0, duration: 0.14, ease: 'power2.in', immediateRender: false }, q(tf));
frames(tf + 4 / 30, 4 / 30, 'power3.in', function (p, t) {
  tl.set(st, { clipPath: ins(WIN.strip * p, 0, 0, 0, RAD * (1 - p)) }, t);
});
tl.set(seam, { transformOrigin: '100% 50%' }, q(tf + 6 / 30));
tl.fromTo(seam, { scaleX: 1 }, { scaleX: 0, duration: 0.12, ease: 'power3.in', immediateRender: false }, q(tf + 6 / 30));
tl.set([win], { opacity: 0 }, q(A + T.gone));
