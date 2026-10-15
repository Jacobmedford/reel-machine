// nle-timeline (layer: top), built on the kit's nle-timeline. "You'd think this took hours in an editor": THIS video's
// real editing timeline sits over the shot, above the eyes, and answers the line.
//   A (the cut)      a line opens into the panel at the playhead: header, ruler, lane headers, and every lane EMPTY.
//                    The playhead stands on the frame being watched and its timecode runs with the video, frame by
//                    frame, for the whole beat (it is never a fake)
//   T.captions       the captions flood onto T1 outward from the playhead (thesis lines in the accent)
//   T.video          the video tracks flood in: graphics and cards (V4), the cutout (V3), behind the head (V2), the
//                    cut itself (V1: every clip with its own graded thumbnails)
//   T.audio          the voice (A1: the kept lines, the real waveform, the J-cuts), the camera keyframes; this
//                    graphic's own block on V4 gets selected
//   B - T.fold       lanes close from the edges in, the panel pinches to a line in the playhead's colour and retracts
//                    into it, gone on B
// Supply nothing by hand: fx.html and strip.jpg come from gen.py (rerun it after pasting the FX entry, after the mix,
// and after any change to the cut, the captions or the FX list).
// PRESET CONSTANTS START
var TITLE = "";                                 // the sequence name in the tab; "" = the project's folder name
var PANEL = {"left": 35, "top": 220};           // px on the frame: the panel (1010 wide) sits above the eyes in every shot
// beats, seconds after A or spoken words: the lanes flood in on captions, video, audio; fold: how long before B the
// fold starts (s)
var T = {"open": 0.0, "captions": 0.787, "video": 1.107, "audio": 1.327, "fold": 0.33};
// which beat of T each lane floods in on, plus a small stagger (s) so the lanes cascade top to bottom
var LANE_AT = {"T1": ["captions", 0], "V4": ["video", 0], "V3": ["video", 0.035], "V2": ["video", 0.07], "V1": ["video", 0.1], "A1": ["audio", 0], "KF": ["audio", 0.1], "A2": ["audio", 0.05]};
var SELECT = ["audio", 0.24];                 // this graphic's own V4 block gets selected (a beat of T + s)
var RIPPLE = 0.42;                              // s: the flood reaches both ends of a lane this long after it starts
var SHAPE = 0.72;                               // how the flood spreads along a lane (1 = even, lower = faster near)
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word: 'editor' is the start of the first "editor" at or
// after A, 'editor-0.05' nudges it. preset.py checks every word against words.json when it makes the instance.
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

var ID = '{{ID}}', box = document.getElementById(ID + '-box');
function c(s) { return s.split(',').map(function (p) { return '#' + ID + ' .' + ID + '-' + p.trim(); }).join(', '); }
function has(sel) { return !!document.querySelector(sel); }
function at(k) { return A + T[k[0]] + k[1]; }
var SPAN = +box.getAttribute('data-span'), X0 = +box.getAttribute('data-x0'), WPX = +box.getAttribute('data-wpx');
function phx(t) { return t * WPX / SPAN; }             // a time on the timeline -> lane px
box.style.left = PANEL.left + 'px';
box.style.top = PANEL.top + 'px';
document.getElementById(ID + '-title').textContent = TITLE || box.getAttribute('data-title') || 'sequence';

var F0 = B - T.fold, f = T.fold / 0.33;                // the fold's own beats scale with T.fold

// ---- build-time state: the panel and everything in it hidden
gsap.set(box, { opacity: 0, transformOrigin: (X0 + phx(A)) + 'px 50%' });
gsap.set(c('head') + ' > *, ' + c('lane'), { opacity: 0 });
gsap.set(c('ruler'), { clipPath: 'inset(0% 100% 0% 0%)' });
gsap.set('#' + ID + '-ph', { opacity: 0, x: phx(A) });
if (has(c('sel'))) gsap.set(c('sel'), { opacity: 0, scale: 1.12 });

// ---- open on the cut: a line at the playhead opens into the panel; every lane empty
tl.set(box, { opacity: 1 }, q(A));
tl.fromTo(box, { scaleY: 0.008, scaleX: 0.9 }, { scaleY: 1, scaleX: 1, duration: 0.26, ease: 'expo.out', immediateRender: false }, q(A));
tl.to(c('head') + ' > *', { opacity: 1, duration: 0.14, stagger: 0.025, ease: 'power2.out' }, q(A + 0.05));
var rl = (X0 + phx(A)) / box.offsetWidth * 100;        // the ruler wipes open from the playhead outward
tl.fromTo(c('ruler'), { clipPath: 'inset(0% ' + (100 - rl).toFixed(2) + '% 0% ' + rl.toFixed(2) + '%)' },
  { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.34, ease: 'power3.out', immediateRender: false }, q(A + 0.05));
tl.to(c('lane'), { opacity: 1, duration: 0.12, stagger: 0.018, ease: 'power2.out' }, q(A + 0.05));   // built before "nothing"

// ---- the playhead is real time: it sits on the frame being watched; the timecode reads that frame
tl.set('#' + ID + '-ph', { opacity: 1 }, q(A + 0.06));
tl.fromTo('#' + ID + '-ph', { x: phx(A) }, { x: phx(B), duration: B - A, ease: 'none', immediateRender: false }, q(A));
function tc(fr) {
  var ff = fr % 30, ss = Math.floor(fr / 30) % 60, mm = Math.floor(fr / 1800);
  function p(n) { return (n < 10 ? '0' : '') + n; }
  return '00:' + p(mm) + ':' + p(ss) + ':' + p(ff);
}
for (var fr = Math.round(A * 30); fr <= Math.round((F0 + 0.2 * f) * 30); fr++) {
  tl.set('#' + ID + '-tc', { textContent: tc(fr) }, Math.max(0, fr / 30 - 0.002));
}

// ---- the flood: each lane fills outward from the playhead on its word, nearest blocks first
[].forEach.call(box.querySelectorAll('.' + ID + '-b'), function (el) {
  var cue = LANE_AT[el.getAttribute('data-lane')] || LANE_AT.T1, t0 = at(cue);
  var a = +el.getAttribute('data-a'), b = +el.getAttribute('data-b'), now = t0;   // the playhead's time then
  var d = now < a ? a - now : (now > b ? now - b : 0), dmax = Math.max(now, SPAN - now);
  var t = t0 + RIPPLE * Math.pow(d / dmax, SHAPE), k = el.getAttribute('data-k');
  if (k === 'clip') {                                   // clips are laid in growing away from the playhead
    gsap.set(el, { scaleX: 0, transformOrigin: (b <= now ? '100%' : '0%') + ' 50%' });
    tl.fromTo(el, { scaleX: 0 }, { scaleX: 1, duration: 0.2, ease: 'power3.out', immediateRender: false }, q(t));
  } else if (k === 'aud') {                             // the waveform wipes on away from the playhead
    var from = b <= now ? 'inset(0% 0% 0% 100%)' : 'inset(0% 100% 0% 0%)';
    gsap.set(el, { clipPath: from });
    tl.fromTo(el, { clipPath: from }, { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.22, ease: 'power2.out', immediateRender: false }, q(t));
  } else if (el.className.indexOf(ID + '-kf') >= 0) {
    gsap.set(el, { opacity: 0, y: -8 });
    tl.fromTo(el, { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.16, ease: 'back.out(2)', immediateRender: false }, q(t));
  } else {
    gsap.set(el, { scaleY: 0, opacity: 0 });
    tl.fromTo(el, { scaleY: 0, opacity: 0 }, { scaleY: 1, opacity: 1, duration: 0.17, ease: 'back.out(1.7)', immediateRender: false }, q(t));
  }
});
// this graphic's own block on V4: selected, the way an editor marks the clip under the playhead
if (has(c('sel'))) tl.fromTo(c('sel'), { opacity: 0, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.2, ease: 'power3.out', immediateRender: false }, q(at(SELECT)));

// ---- fold: lanes close from the edges in, the panel pinches to a line, the line retracts into the playhead
tl.set(box, { transformOrigin: (X0 + phx(F0)) + 'px 50%' }, q(F0));
tl.to(c('lane'), { scaleY: 0, duration: 0.13 * f, stagger: { each: 0.022 * f, from: 'edges' }, ease: 'power3.in' }, q(F0));
tl.to(c('head') + ' > *, ' + c('ruler'), { opacity: 0, duration: 0.1 * f, ease: 'power2.in' }, q(F0 + 0.04 * f));
tl.to(box, { scaleY: 0.007, duration: 0.16 * f, ease: 'power3.in' }, q(F0 + 0.06 * f));
var ACC = getComputedStyle(document.documentElement).getPropertyValue('--c-accent').trim();
tl.set(['#' + ID + '-panel', '#' + ID + '-shadow'], { backgroundColor: ACC }, q(F0 + 0.22 * f));   // the line is the playhead's colour
tl.to(box, { scaleX: 0, duration: 0.1 * f, ease: 'power3.in' }, q(F0 + 0.22 * f));
tl.set(box, { opacity: 0 }, q(B));
