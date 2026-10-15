// stamp-strike (layer: behind, under the speaker's cutout). Words stamped on the wall and struck through:
//   stamp     each word stamps in letter by letter from 1.38x on its name, one letter every STEP_FRAMES frames, huge,
//             in the display face, the speaker's head breaking the foot of the line; once built it grows a hair until
//             the hard out, so it never sits still
//   strike    on the negation a stroke draws through each word in turn (power3.inOut) and the struck letters fall back
//             to the muted tokens, so the stroke carries the beat
//   split     light everywhere, ink through mask.png wherever the room behind the speaker is light; the stroke is one
//             colour; anything in front of the wall (front.png) passes in front of the type
// Built on the kit's word-stamp. Two words by default (one left, one right, both struck on the negation); a callback
// later in the video (one word, struck again) keeps SIZE, GAP, STEP_FRAMES, GROW, STROKE and DIM so it is the same
// size and the same move. Needs a CUT_WINDOWS entry over its window (never across a picture cut); out hard at the
// window end. mkmask.py writes mask.png and front.png from this shot's own footage (it reads MASK below).
// PRESET CONSTANTS START
// each word: its text, x (px on the frame) and how it hangs from x (left | right | center): where the speaker
// points as they say it
var STAMPS = [{"text": "MEETINGS", "x": 46, "align": "left"}, {"text": "EMAILS", "x": 1034, "align": "right"}];
// per word, in STAMPS order: when it stamps and when it is struck (null: never struck). Seconds after A or a spoken word
var T = {"stamp": [1.017, 0.0], "strike": [1.841, 1.941]};
var BASE = 548;                   // px: the line's baseline on the 1080x1920 frame (the head breaks its foot)
var SIZE = 432;                   // px: the type size
var MAXW = 940;                   // px: if the whole line runs wider in the pack's display face, every word sets smaller
var GAP = 0.15;                   // em: the least space between two words
var STEP_FRAMES = 2;              // the stamp: one letter every this many frames
var GROW = 0.008;                 // scale per second once a word is built (a shorter hold grows at the same speed)
// the strike: its token, thickness and height (x the cap height), overhang (px), tilt (deg), draw time (s)
var STROKE = {"color": "--c-neg", "thick": 0.11, "y": 0.5, "pad": 10, "rot": -2.5, "dur": 0.22};
var DIM = {"light": "--c-muted-dark", "ink": "--c-muted-light", "dur": 0.24, "after": 0.08};   // struck letters fall back to these
var SPLIT = true;                 // false: light type only (no wall mask needed)
// mkmask.py: luma ramp (0-255) from light to ink, blur px, frames read (0: all), the part of the window to read
// ([s, s] after A, or null), and dark things in front of the wall above y ([luma, y], or null: nothing in front)
var MASK = {"lo": 92, "hi": 124, "blur": 1.0, "samples": 0, "read": null, "front": null};
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word: 'nothing' is the start of the first "nothing" at or
// after A, 'nothing+0.1' nudges it; in a list each word is looked for after the beat before it (and from A when it
// isn't spoken again). preset.py checks every word against words.json when it makes the instance.
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
var STEP = STEP_FRAMES / 30;

function $(s) { return document.querySelector(s); }
function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
if (!SPLIT) { var dk0 = $('#{{ID}}-dk'); dk0.parentNode.removeChild(dk0); }
var copies = SPLIT ? ['#{{ID}}-lt', '#{{ID}}-dk'] : ['#{{ID}}-lt'];

// ---- the words into both copies: letters, and the stroke over them
copies.forEach(function (c) {
  var host = $(c);
  STAMPS.forEach(function (W, i) {
    var w = document.createElement('div');
    w.className = '{{ID}}-w {{ID}}-w' + i;
    var t = document.createElement('span');
    t.className = '{{ID}}-t';
    Array.from(W.text).forEach(function (ch) {
      var s = document.createElement('span');
      s.className = '{{ID}}-ch';
      s.textContent = ch === ' ' ? '\u00a0' : ch;   // a space letter must keep its width
      t.appendChild(s);
    });
    var x = document.createElement('i');
    x.className = '{{ID}}-x';
    x.style.background = 'var(' + STROKE.color + ')';
    w.appendChild(t);
    w.appendChild(x);
    host.appendChild(w);
  });
});
// the copies overlap and sit behind the head on purpose: tell the layout audit (it reads the text elements)
$$('#{{ID}} *').forEach(function (e) {
  if (Array.prototype.some.call(e.childNodes, function (n) { return n.nodeType === 3 && n.nodeValue.trim(); })) {
    e.setAttribute('data-layout-allow-overlap', '');
    e.setAttribute('data-layout-allow-occlusion', '');
  }
});

// ---- layout: SIZE unless the line runs wider than MAXW; each word stands on BASE, anchored at its x; the stroke
//      runs through its capitals
function baseline(box) {                    // the baseline's distance from the top of a line box
  var t = box.querySelector('.{{ID}}-t'), p = document.createElement('span');
  p.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline;';
  t.appendChild(p);
  var y = p.offsetTop;
  t.removeChild(p);
  return y;
}
function capHeight(px) {
  var cv = document.createElement('canvas').getContext('2d');
  cv.font = tok('--display-style') + ' ' + tok('--display-weight') + ' ' + px + 'px ' + tok('--font-display');
  var m = cv.measureText('H');
  return m.actualBoundingBoxAscent || px * 0.7;
}
function fit() {
  var size = SIZE, total = 0, gaps = 0;
  $$('#{{ID}}-lt .{{ID}}-w').forEach(function (b) { b.style.fontSize = SIZE + 'px'; total += b.querySelector('.{{ID}}-t').offsetWidth; });
  if (STAMPS.length > 1) gaps = (STAMPS.length - 1) * GAP * SIZE;        // keep at least GAP em between words
  if (total + gaps > MAXW) size = SIZE * MAXW / (total + gaps);
  var cap = capHeight(size), thick = Math.round(cap * STROKE.thick);
  copies.forEach(function (c) {
    STAMPS.forEach(function (W, i) {
      var b = $(c + ' .{{ID}}-w' + i);
      b.style.fontSize = size.toFixed(2) + 'px';
      var w = b.querySelector('.{{ID}}-t').offsetWidth, bl = baseline(b);
      var left = W.align === 'right' ? W.x - w : W.align === 'center' ? W.x - w / 2 : W.x;
      b.style.left = left.toFixed(1) + 'px';
      b.style.top = (BASE - bl).toFixed(1) + 'px';
      var x = b.querySelector('.{{ID}}-x');
      x.style.left = (-STROKE.pad) + 'px';
      x.style.width = (w + 2 * STROKE.pad) + 'px';
      x.style.height = thick + 'px';
      x.style.top = (bl - cap * STROKE.y - thick / 2).toFixed(1) + 'px';
    });
  });
}
fit();
if (document.fonts && document.fonts.load) {
  document.fonts.load(tok('--display-style') + ' ' + tok('--display-weight') + ' 100px ' + tok('--font-display'),
    STAMPS.map(function (W) { return W.text; }).join(' ')).catch(function () {}).then(fit, fit);
  document.fonts.ready.then(fit);
}

// ---- build: hidden until their beats
if (q(A) <= 0) gsap.set('#{{ID}}', { opacity: 1 });
gsap.set('#{{ID}} .{{ID}}-ch', { opacity: 0 });
gsap.set('#{{ID}} .{{ID}}-x', { scaleX: 0, rotation: STROKE.rot, transformOrigin: '0% 50%' });
gsap.set('#{{ID}} .{{ID}}-w', { transformOrigin: '50% 85%' });

STAMPS.forEach(function (W, i) {
  var tS = A + T.stamp[i], n = Array.from(W.text).length, tBuilt = tS + (n - 1) * STEP + 0.2;
  // the stamp: one tween per copy so each staggers its own letters
  copies.forEach(function (c) {
    tl.fromTo(c + ' .{{ID}}-w' + i + ' .{{ID}}-ch', { opacity: 0, scale: 1.38, yPercent: -6 },
      { opacity: 1, scale: 1, yPercent: 0, duration: 0.2, ease: 'power4.out', stagger: STEP, immediateRender: false }, q(tS));
  });
  if (B - tBuilt > 0.1) {
    tl.fromTo('#{{ID}} .{{ID}}-w' + i, { scale: 1 }, { scale: 1 + GROW * (B - tBuilt), duration: B - tBuilt, ease: 'none', immediateRender: false }, q(tBuilt));
  }
  // the strike, then the struck letters fall back to the muted tokens (opacity would let the copies show through)
  if (T.strike[i] !== undefined && T.strike[i] !== null) {
    var tX = A + T.strike[i];
    tl.fromTo('#{{ID}} .{{ID}}-w' + i + ' .{{ID}}-x', { scaleX: 0 }, { scaleX: 1, duration: STROKE.dur, ease: 'power3.inOut', immediateRender: false }, q(tX));
    tl.fromTo('#{{ID}}-lt .{{ID}}-w' + i + ' .{{ID}}-ch', { color: tok('--c-light') }, { color: tok(DIM.light), duration: DIM.dur, ease: 'power1.out', immediateRender: false }, q(tX + DIM.after));
    if (SPLIT) tl.fromTo('#{{ID}}-dk .{{ID}}-w' + i + ' .{{ID}}-ch', { color: tok('--c-ink') }, { color: tok(DIM.ink), duration: DIM.dur, ease: 'power1.out', immediateRender: false }, q(tX + DIM.after));
  }
});
