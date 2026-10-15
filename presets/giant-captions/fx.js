// giant-captions (layer: over), built on the kit's giant-captions. "Watch the captions grow really big, then huge,
// until they take over." The caption does what the line says, on the words:
//   cap1    a normal hi-fi caption, the kit's own .cap box (CAP1; *word* = the accent)
//   cap2    the second caption (CAP2); in the silence before the next word the box crouches (T.crouch)
//   big     on T.big the box launches up into a giant slab above the head (BIG at BIG_PX), its line scaled with it
//   slam    on T.slam SLAM slams onto the chest in the display face in the accent, the slab above takes the hit
//   cover   on T.cover the box falls over the whole frame (a picture cut can happen under it)
//   words   T.w1 / T.w2 / T.w3: the cover's three words rise in it, each on its word
//   shut    on T.shut the box shrinks into the box of the NEXT caption (edit.CAPS pops it just before, under the
//           cover) and hands over by T.gone: the real caption is underneath, identical
// Hi-fi captions only (it reads the kit's .cap box: size, padding and place come from the pack).
// PRESET CONSTANTS START
var CAP1 = "Watch the *captions*";       // the first normal caption; *word* = the accent, as in edit.CAPS
var CAP2 = "grow";                       // the second, which crouches and launches
var BIG = "really big,";                 // the giant slab's line
var BIG_PX = 220;                        // its type size: the caption box grows by BIG_PX / the caption's size
var SLAB_TOP = 240;                      // px: the slab's top edge (above the head)
var SLAM = "THEN HUGE";                  // the display line that slams onto the chest
var SLAM_PX = 450;                       // its size
var SLAM_TOP = 930;                      // px: its top (across the chest, under the chin)
var COVER = ["until they", "TAKE", "OVER."];   // the small line, then the display words, each rising on its word
var COVER_PX = [110, 640];               // the small line's size, the display words' size
var COVER_TOP = 560;                     // px: the small line's top (the display words sit 20 px under its descenders)
var NEXT = "Back to normal";             // the edit.CAPS caption the cover shrinks into; "" = it folds shut instead
// beats, seconds after A or spoken words: cap1, cap2, crouch (the silence before big), big, slam, cover (the box
// falls), w1 / w2 / w3 (the cover's three words), shut (the next caption), gone (handed over)
var T = {"cap1": 0.07, "cap2": 0.87, "crouch": 1.709, "big": 1.874, "slam": 2.765, "cover": 3.748, "w1": 3.801, "w2": 4.01, "w3": 4.172, "shut": 4.435, "gone": 4.608};
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word: 'huge' is the start of the first "huge" at or
// after A, 'huge-0.05' nudges it. preset.py checks every word against words.json when it makes the instance.
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
function words(el, text) {               // *word* -> the caption's accent span
  text.split('*').forEach(function (part, k) {
    if (!part) return;
    if (k % 2) { var s = document.createElement('span'); s.className = 'em'; s.textContent = part; el.appendChild(s); }
    else el.appendChild(document.createTextNode(part));
  });
}
function lerp(a, b, p) { return a + (b - a) * p; }
// Coupled moves (the box and the line inside it) are drawn frame by frame with tl.set, from one eased progress, so
// they stay registered on every frame. Clip-paths are never tweened: GSAP reads an inset back from the browser in
// short form, pairs the numbers wrongly and the box jumps.
function frames(t0, dur, ease, fn) {
  var E = gsap.parseEase(ease), n = Math.max(1, Math.round(dur * 30));
  for (var i = 0; i <= n; i++) fn(E(i / n), q(t0 + i / 30));
}
function inset(r) {                      // r = [x, y, w, h, corner] on the 1080 x 1920 frame
  function f(v) { return (+v.toFixed(2)) + 'px'; }
  return 'inset(' + f(r[1]) + ' ' + f(1080 - r[0] - r[2]) + ' ' + f(1920 - r[1] - r[3]) + ' ' + f(r[0]) + ' round ' + f(r[4]) + ')';
}
function mix(a, b, p) { return a.map(function (v, k) { return lerp(v, b[k], p); }); }

// ---- the words and sizes in (static)
words($(P + 'c1'), CAP1);
words($(P + 'c2'), CAP2);
$(P + 't1s').textContent = BIG;
$(P + 't1').style.fontSize = BIG_PX + 'px';
$(P + 'cht').textContent = SLAM;
$(P + 'ch').style.fontSize = SLAM_PX + 'px';
$(P + 'chw').style.top = SLAM_TOP + 'px';
$(P + 'cv1').textContent = COVER[0];
$(P + 'cv2').textContent = COVER[1];
$(P + 'cv3').textContent = COVER[2];
$(P + 'mk1').style.fontSize = COVER_PX[0] + 'px';
$(P + 'mk1').style.top = COVER_TOP + 'px';
$(P + 'cvr').style.fontSize = COVER_PX[1] + 'px';
// the display words' caps start 0.0325 em into their .8 em line: set them 20 px under the small line's descenders
$(P + 'cvr').style.top = (COVER_TOP + 1.25 * COVER_PX[0] + 20 - 0.0325 * COVER_PX[1]).toFixed(1) + 'px';
// the display lines never run wider than the frame (FIT_W): a wide display face sets SLAM and the cover's words
// smaller, a condensed one keeps their sizes
var FIT_W = 1060;
function fitDisplay() {
  var ch = $(P + 'ch'), cvr = $(P + 'cvr');
  ch.style.fontSize = SLAM_PX + 'px';
  if (ch.offsetWidth > FIT_W) ch.style.fontSize = (SLAM_PX * FIT_W / ch.offsetWidth).toFixed(2) + 'px';
  cvr.style.fontSize = COVER_PX[1] + 'px';
  var w = $(P + 'mk2').offsetWidth + $(P + 'mk3').offsetWidth + 0.09 * COVER_PX[1], px = COVER_PX[1];
  if (w > FIT_W) { px = COVER_PX[1] * FIT_W / w; cvr.style.fontSize = px.toFixed(2) + 'px'; }
  cvr.style.top = (COVER_TOP + 1.25 * COVER_PX[0] + 20 - 0.0325 * px).toFixed(1) + 'px';
}
fitDisplay();
if (document.fonts && document.fonts.load) {
  document.fonts.load(tok('--display-style') + ' ' + tok('--display-weight') + ' 100px ' + tok('--font-display'),
    SLAM + ' ' + COVER.join(' ')).catch(function () {}).then(fitDisplay, fitDisplay);
  document.fonts.ready.then(fitDisplay);
}

// ---- the caption's own box, read off the kit's .cap (the pack sets its size, padding and position)
var c2 = $(P + 'c2'), cs = getComputedStyle(c2);
var CAP_PX = parseFloat(cs.fontSize) || 64, LH = parseFloat(cs.lineHeight) || CAP_PX * 1.1;
var PT = parseFloat(cs.paddingTop) || 0, PB = parseFloat(cs.paddingBottom) || 0, PX = parseFloat(cs.paddingLeft) || 0;
var CAP_TOP = parseFloat(getComputedStyle($(P + 'c2w')).top) || 1236;
var CAP_H = LH + PT + PB, K = BIG_PX / CAP_PX, RAD = parseFloat(tok('--radius')) || 0;
// the giant line is that caption blown up: its case, line height and tracking (its face: fx.html, the pack's
// caption face one weight up, as approved); the cover's small line takes the case too
var LS = cs.letterSpacing === 'normal' ? 0 : (parseFloat(cs.letterSpacing) || 0) / CAP_PX;
[P + 't1', P + 'cv1'].forEach(function (s) { $(s).style.textTransform = cs.textTransform; });
$(P + 't1').style.lineHeight = (LH / CAP_PX).toFixed(4);
$(P + 't1').style.letterSpacing = LS.toFixed(4) + 'em';
// the giant line's width: measured (the pack's faces are loaded when the timeline builds), else estimated
var faceOK = !document.fonts || document.fonts.check('800 ' + BIG_PX + 'px ' + (tok('--font-caption') || tok('--font-text')), BIG);
var TW = faceOK ? $(P + 't1s').getBoundingClientRect().width : BIG.length * 0.355 * BIG_PX;
var W0 = TW / K + 2 * PX, W1 = TW + 2 * PX * K;
if (W1 > FIT_W) {                          // a wide text face: the slab sets its line smaller, never runs off the frame
  var FS = FIT_W / W1;
  BIG_PX *= FS; K = BIG_PX / CAP_PX; TW *= FS;
  $(P + 't1').style.fontSize = BIG_PX + 'px';
  W0 = TW / K + 2 * PX; W1 = TW + 2 * PX * K;
}
var BOX0 = [540 - W0 / 2, CAP_TOP, W0, CAP_H, RAD];            // the caption box with the giant line, in the band
var BOX1 = [540 - W1 / 2, SLAB_TOP, W1, CAP_H * K, RAD];       // the same box, BIG_PX / caption size bigger
var FULL = [0, 0, 1080, 1920, 0];
$(P + 't1').style.top = (SLAB_TOP + PT * K).toFixed(2) + 'px';
var DY = (CAP_TOP + PT + LH / 2) - (SLAB_TOP + PT * K + LH * K / 2);   // the band's line centre to the slab's
// the next caption's box (edit.CAPS): the cover hands over to it
var nx = null;
if (NEXT) Array.prototype.forEach.call(document.querySelectorAll('#caps .cap'), function (c) {
  if (!nx && c.textContent.trim() === NEXT) nx = c;
});
var BOX2 = nx ? [540 - nx.offsetWidth / 2, parseFloat(getComputedStyle(nx.parentNode).top) || CAP_TOP, nx.offsetWidth, nx.offsetHeight, RAD]
              : [0, CAP_TOP + CAP_H / 2, 1080, 0, 0];   // no next caption: the box folds shut into a line in the band
var BAND = CAP_TOP + CAP_H / 2;

// ---- start states
gsap.set([P + 'c1', P + 'c2'], { opacity: 0, transformOrigin: '50% 100%' });
gsap.set(P + 'box', { opacity: 0, clipPath: inset(BOX0) });
gsap.set(P + 't1', { scale: 1 / K, y: DY, transformOrigin: '50% 50%' });
gsap.set(P + 'ch', { opacity: 0, rotation: -2, transformOrigin: '50% 50%' });
gsap.set([P + 'cv1', P + 'cv2', P + 'cv3'], { yPercent: 108 });
gsap.set(P + 'cv', { transformOrigin: '540px ' + BAND.toFixed(1) + 'px' });

// ---- 1. two normal captions (the build's pop), the second crouches before the launch
function pop(sel, t) {
  tl.set(sel, { opacity: 1 }, q(t));
  tl.fromTo(sel, { scale: 0.95 }, { scale: 1, duration: 0.16, ease: 'power3.out', immediateRender: false }, q(t));
}
pop(P + 'c1', A + T.cap1);
tl.set(P + 'c1', { opacity: 0 }, q(A + T.cap2));
pop(P + 'c2', A + T.cap2);
tl.fromTo(P + 'c2', { scaleX: 1, scaleY: 1 }, { scaleX: 1.04, scaleY: 0.86, duration: T.big - T.crouch, ease: 'power2.in',
  immediateRender: false }, q(A + T.crouch));
tl.set(P + 'c2', { opacity: 0 }, q(A + T.big));

// ---- 2. big: the box (now holding the giant line, caption-sized) launches up into the slab and swings level from
// 4 degrees about its own centre
var tB = A + T.big, SWING = gsap.parseEase('back.out(2.2)');
tl.set(P + 'box', { opacity: 1 }, q(tB));
frames(tB, 13 / 30, 'none', function (u, t) {
  var p = Math.min(1, gsap.parseEase('expo.out')(Math.min(1, u * 13 / 10))), r = mix(BOX0, BOX1, p);
  tl.set(P + 'box', { clipPath: inset(r), rotation: 4 * (1 - SWING(u)),
                      transformOrigin: (r[0] + r[2] / 2).toFixed(1) + 'px ' + (r[1] + r[3] / 2).toFixed(1) + 'px' }, t);
  tl.set(P + 't1', { scale: lerp(1 / K, 1, p), y: lerp(DY, 0, p) }, t);
});

// ...and never sits dead: the slab keeps growing a hair until the cover (eased back to 1 as the cover falls)
gsap.set(P + 'g1', { transformOrigin: '540px ' + (SLAB_TOP + CAP_H * K / 2).toFixed(1) + 'px' });
tl.fromTo(P + 'g1', { scale: 1 }, { scale: 1.025, duration: T.cover - T.big - 13 / 30, ease: 'none', immediateRender: false }, q(tB + 13 / 30));

// ---- 3. slam: the display line slams onto the chest, the slab above takes the hit
var tC = A + T.slam;
tl.set(P + 'ch', { opacity: 1 }, q(tC));
tl.fromTo(P + 'ch', { scale: 1.5, rotation: -7 }, { scale: 1, rotation: -2, duration: 0.26, ease: 'power4.out', immediateRender: false }, q(tC));
tl.fromTo(P + 'g1', { y: 0 }, { y: -12, duration: 0.067, ease: 'power2.out', immediateRender: false }, q(tC + 0.067));
tl.fromTo(P + 'g1', { y: -12 }, { y: 0, duration: 0.3, ease: 'back.out(3)', immediateRender: false }, q(tC + 0.133));
tl.fromTo(P + 'ch', { scale: 1 }, { scale: 1.03, duration: T.cover - T.slam - 0.26 + 0.2, ease: 'none', immediateRender: false }, q(tC + 0.26));

// ---- 4. cover: the box falls over the frame, the slab's line lifts out, the words rise in it
var tV = A + T.cover;
frames(tV, 6 / 30, 'power2.inOut', function (p, t) { tl.set(P + 'box', { clipPath: inset(mix(BOX1, FULL, p)) }, t); });
tl.fromTo(P + 'g1', { scale: 1.025 }, { scale: 1, duration: 6 / 30, ease: 'power2.inOut', immediateRender: false }, q(tV));
tl.fromTo(P + 't1', { y: 0, opacity: 1 }, { y: -40, opacity: 0, duration: 0.12, ease: 'power2.in', immediateRender: false }, q(tV));
tl.set(P + 'ch', { opacity: 0 }, q(tV + 7 / 30));
tl.fromTo(P + 'cv1', { yPercent: 108 }, { yPercent: 0, duration: 0.22, ease: 'power3.out', immediateRender: false }, q(A + T.w1));
tl.fromTo(P + 'cv2', { yPercent: 108 }, { yPercent: 0, duration: 0.24, ease: 'power4.out', immediateRender: false }, q(A + T.w2));
tl.fromTo(P + 'cv3', { yPercent: 108 }, { yPercent: 0, duration: 0.24, ease: 'power4.out', immediateRender: false }, q(A + T.w3));

// ---- 5. back to normal: the box shrinks into the next caption's box (its words sink into the band with it, fading,
// clipped by it), holds that box a frame and hands over to the caption under it; all of it gone before the cut at B
var tS = A + T.shut, tG = A + T.gone;
frames(tS, tG - tS - 1 / 30, 'power3.inOut', function (p, t) {
  tl.set(P + 'box', { clipPath: inset(mix(FULL, BOX2, p)) }, t);
  tl.set(P + 'cv', { scale: lerp(1, 0.3, p), opacity: Math.max(0, 1 - 1.8 * p) }, t);
});
tl.set(P + 'box', { opacity: 0 }, q(tG));
