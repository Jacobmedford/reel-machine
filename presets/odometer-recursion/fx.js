/* odometer-recursion (layer: cam). "Hours of takes became minutes: this is the video, right now": the raw
   footage's length against this video's, then the frame looking at itself.
   Beat by beat:
     T.rise          a counter plate rises over the wall beside the head, showing RAW under the kicker LABELS[0]
     T.roll          it rolls down like a mechanical counter (the seconds drum spins, tens and minutes turn on the carry,
                     each drum motion-blurred by its own speed); when the minutes pass under ten the leading drum rolls
                     to blank and drops away and the plate tightens: the number gets shorter
     T.land          it lands on FINAL, the label rolls to LABELS[1] in the accent face. The plate stays: from here on
                     it is part of the picture
     T.levels        the whole frame, counter included, shrinks into a framed inset of itself, one level per word: every
                     level is the same footage in sync with its own copy of the counter, so a new level starts
                     invisible on top of its parent
     T.dive -> B     the camera dives through one level, accelerating; on the last frame before B the picture is the
                     first level grown to full frame with the next one inset: the loop's first frame
   Built on the kit's odometer-recursion. Supply the two TRUE lengths (m:ss, under 100 minutes: ffprobe the raw
   files, timeline.json total). Every level is a synced copy of clean.mp4 (class g: the live grade). */
// PRESET CONSTANTS START
var RAW = "2:40";                          // the raw footage's true length, m:ss (all the takes, joined)
var FINAL = "0:45";                        // this video's true length, m:ss (timeline.json total)
var LABELS = ["3 raw takes", "This video"];    // the kicker over RAW, then the accent line over FINAL
// beats, seconds after A or spoken words: the plate rises, the roll starts ("hours") and lands (the end of
// "minutes"), one level per word ("this", "is", "the", "video"), the dive ("now")
var T = {"rise": 0.0, "roll": 0.166, "land": 0.665, "levels": [1.184, 1.513, 1.852, 2.062], "dive": 2.471};
var PLATE = {"left": 430, "top": 236};     // px: the counter plate (600 x 300) beside the head, above the caption band
var FOCUS = [50, 314];                     // px: the insets converge here (bare wall, clear of the face)
var S = 0.3;                               // each level is this much of its parent
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word: 'now' is the start of the first "now" at or after A,
// 'now-0.05' nudges it; in a list each word is looked for after the beat before it (and from A when it isn't spoken
// again). preset.py checks every word against words.json when it makes the instance.
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
var DH = 230, DRUM = 126;                            // a digit's slot on a drum and a drum's width with margins (fx.html)

function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function secs(s) { var p = String(s).split(':'); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }
var FPS = 30;
function fq(i) { return Math.max(0, i / FPS - 0.002); }      // frame index -> its time on the timeline
function fi(t) { return Math.round(t * FPS); }               // time -> frame index
var ID = '{{ID}}', plate = document.getElementById(ID + '-odo');
plate.style.left = PLATE.left + 'px';
plate.style.top = PLATE.top + 'px';
function P(cls) { return plate.querySelector('.' + ID + '-' + cls); }
P('k').textContent = LABELS[0];
P('s').textContent = LABELS[1];
// each level starts exactly on top of its parent, counter on counter: intentional layering for the layout audit
[].forEach.call(plate.querySelectorAll('span, .' + ID + '-colon'), function (el) {
  el.setAttribute('data-layout-allow-overlap', ''); el.setAttribute('data-layout-allow-occlusion', '');
});

// ---------------------------------------------------------------- part 1: the counter
var tRise = A + T.rise, tRoll = A + T.roll, tLand = A + T.land;
var V0 = secs(RAW), V1 = secs(FINAL);
// a mechanical counter, m m : s s. Continuous drum positions for a value in seconds: the seconds drum turns all the
// time; every other drum only turns while the one to its right carries (the last tenth of its turn)
function drums(v) {
  var sm = v % 60, u = v % 10;
  var st = Math.floor(sm / 10) + Math.max(0, u - 9);
  var M = Math.floor(v / 60) + Math.max(0, sm - 59);
  var mu = M % 10, mt = Math.floor(M / 10) + Math.max(0, mu - 9);
  return [mt, mu, st, u];
}
var STRIPS = ['dmt', 'dmu', 'dst', 'dsu'], BLUR = [0.15, 0.15, 0.15, 0.15], CAP = [40, 44, 52, 60];
var MEAN = [1 / 600, 1 / 60, 1 / 10, 1];             // each drum's average turn per second of value (for its speed)
function show(p, t) { for (var k = 0; k < 4; k++) tl.set(P(STRIPS[k]), { y: -p[k] * DH }, t); }
var p0 = drums(V0);
for (var k0 = 0; k0 < 4; k0++) gsap.set(P(STRIPS[k0]), { y: -p0[k0] * DH });
var R = tok('--radius') || '0px';
function clip(top, bottom) { return 'inset(' + top + '% 0% ' + bottom + '% 0% round ' + R + ')'; }
gsap.set(plate, { clipPath: clip(100, 0), y: 40, opacity: 0 });
tl.set(plate, { opacity: 1 }, q(tRise));
tl.fromTo(plate, { clipPath: clip(100, 0), y: 40 },
  { clipPath: clip(0, 0), y: 0, duration: 0.32, ease: 'expo.out', immediateRender: false }, q(tRise));
tl.set(plate, { clipPath: 'none' }, q(tRise + 0.34));        // unclipped from here, so its shadow falls on the wall

// the roll, frame by frame: power3.inOut on the value, each drum blurred along its travel by its own mean speed
var C0 = fi(tRoll), C1 = fi(tLand), ez = gsap.parseEase('power3.inOut'), drop = -1;
function val(i) { return V0 + (V1 - V0) * ez(Math.min(1, Math.max(0, (i - C0) / (C1 - C0)))); }
for (var s = 0; s < 4; s++) {
  tl.set(P(STRIPS[s]), { filter: 'url(#' + ID + '-mb' + s + ')' }, fq(C0));
  tl.set(P(STRIPS[s]), { filter: 'none' }, fq(C1));
}
for (var i = C0; i < C1; i++) {
  var v = val(i), dv = Math.abs(val(i + 1) - val(i - 1)) / 2;  // value change per frame around this frame
  show(drums(v), fq(i));
  for (var b = 0; b < 4; b++) {
    var sd = Math.min(CAP[b], BLUR[b] * dv * MEAN[b] * DH);
    tl.set('#' + ID + '-g' + b, { attr: { stdDeviation: '0 ' + sd.toFixed(2) } }, fq(i));
  }
  if (drop < 0 && Math.floor(v / 600) < Math.floor(V0 / 600) && drums(v)[0] < 0.02) drop = i;   // the tens of minutes went blank
}
show(drums(V1), fq(C1));
for (var g = 0; g < 4; g++) tl.set('#' + ID + '-g' + g, { attr: { stdDeviation: '0 0' } }, fq(C1));
// the leading drum rolled to blank: it drops away, the row recentres, the plate tightens around the shorter number
var dropped = Math.floor(V1 / 600) === 0 && Math.floor(V0 / 600) > 0;
if (dropped) {
  var tDrop = drop >= 0 ? fq(drop) : fq(C1), BGW = P('bg').offsetWidth;
  tl.fromTo(P('wmt'), { scaleX: 1, opacity: 1 }, { scaleX: 0, opacity: 0, duration: 0.24, ease: 'power3.inOut', immediateRender: false }, tDrop);
  tl.fromTo(P('row'), { x: 0 }, { x: -DRUM / 2, duration: 0.24, ease: 'power3.inOut', immediateRender: false }, tDrop);
  tl.fromTo(P('bg'), { scaleX: 1 }, { scaleX: (BGW - DRUM) / BGW, duration: 0.24, ease: 'power3.inOut', immediateRender: false }, tDrop);
  gsap.set(P('wmt'), { transformOrigin: '100% 50%' });
}
// it lands: the label rolls over to the accent line, the plate settles
tl.fromTo(P('lab-in'), { y: 0 }, { y: -50, duration: 0.3, ease: 'power3.out', immediateRender: false }, fq(C1));
tl.fromTo(plate, { scale: 1.035 }, { scale: 1, duration: 0.32, ease: 'back.out(1.6)', immediateRender: false }, fq(C1));

// ---------------------------------------------------------------- part 2: the recursion
// every level carries its own copy of the counter in its landed state, so the inset shows exactly this frame
function landed(el) {
  el.removeAttribute('id');
  var d = drums(V1), sel = function (cls) { return el.querySelector('.' + ID + '-' + cls); };
  for (var k = 0; k < 4; k++) gsap.set(sel(STRIPS[k]), { y: -d[k] * DH, filter: 'none' });
  gsap.set(sel('lab-in'), { y: -50 });
  gsap.set(el, { clipPath: 'none', y: 0, opacity: 1, scale: 1 });
  if (dropped) {
    gsap.set(sel('wmt'), { scaleX: 0, opacity: 0, transformOrigin: '100% 50%' });
    gsap.set(sel('row'), { x: -DRUM / 2 });
    gsap.set(sel('bg'), { scaleX: (P('bg').offsetWidth - DRUM) / P('bg').offsetWidth });
  }
  return el;
}
for (var n0 = 1; n0 <= 4; n0++) {
  var lvEl = document.getElementById(ID + '-n' + n0), fr = document.getElementById(ID + '-f' + n0);
  lvEl.insertBefore(landed(plate.cloneNode(true)), fr.nextSibling);
}

var LV = [null, { sw: 5.0, d: 0.46, ease: 'expo.out' }, { sw: 3.4, d: 0.32, ease: 'power4.out' },
  { sw: 2.4, d: 0.26, ease: 'power4.out' }, { sw: 1.7, d: 0.2, ease: 'power4.out' }];   // sw: frame line on screen, px
var ORIGIN = FOCUS[0] + 'px ' + FOCUS[1] + 'px';
var lv = T.levels.map(function (x) { return A + x; }), tDive = A + T.dive;
gsap.set('#' + ID + '-stack', { transformOrigin: ORIGIN });
gsap.set('#' + ID + '-v0', { opacity: 0 });
for (var n = 1; n <= 4; n++) {
  var L = LV[n], par = Math.pow(S, n - 1), own = Math.pow(S, n), t0 = lv[n - 1];
  gsap.set('#' + ID + '-n' + n, { opacity: 0, scale: 1, transformOrigin: ORIGIN });
  gsap.set('#' + ID + '-f' + n, { borderWidth: L.sw / par });
  tl.set('#' + ID + '-n' + n, { opacity: 1 }, q(t0));
  // it starts exactly on its parent (same footage, same frame, same counter: invisible) and shrinks into the inset
  tl.fromTo('#' + ID + '-n' + n, { scale: 1 }, { scale: S, duration: L.d, ease: L.ease, immediateRender: false }, q(t0));
  tl.fromTo('#' + ID + '-f' + n, { borderWidth: L.sw / par },
    { borderWidth: L.sw / own, duration: L.d, ease: L.ease, immediateRender: false }, q(t0));
}
// the dive: one level in (x 1/S about the focus), accelerating into B. Its own full-frame copy comes up a frame early
// so the whole picture zooms. Each frame's line weight slides to the next level's, so the last frame is the loop's first.
var Z0 = fi(tDive), Z1 = fi(B) - 1;
tl.set('#' + ID + '-v0', { opacity: 1 }, fq(Z0 - 1));
for (var j = Z0; j <= Z1; j++) {
  var pz = (j - Z0) / Math.max(1, Z1 - Z0), e2 = pz * pz, z = Math.pow(1 / S, e2);
  tl.set('#' + ID + '-stack', { scale: z }, fq(j));
  for (var m = 1; m <= 4; m++) {
    var target = m === 1 ? LV[1].sw * (1 - e2) : LV[m].sw + (LV[m - 1].sw - LV[m].sw) * e2;   // L1 thins away at the edge
    tl.set('#' + ID + '-f' + m, { borderWidth: target / (z * Math.pow(S, m)) }, fq(j));
  }
}
