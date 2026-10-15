// nle-timeline (layer: top): an editing timeline of THIS video piles up on the words, a playhead tears across it,
// then it folds to a line and is gone by B.
//   A           a thin line unfolds into the panel: header, ruler, lane headers
//   "know"      the cut lands clip by clip on V1, the voice draws on A1
//   "nothing"   the graphics pile onto V4 and V2, the music onto A2
//   "about"     every caption on T1, every sound effect on A3, the ruler marks
//   "editing"   (a beat before it) the cutout windows (V3), transitions and camera keyframes pop in, the zoom
//               slider pulls out
//   B - fold    lanes close from the edges in, the panel pinches to a line, the line to nothing
// The playhead runs from the cut landing to the fold, its timecode reading where it is, frame by frame.
//
// Supply: nothing by hand. fx.html and strip.jpg are generated from the project's own edit.py, timeline.json,
// words.json, audio and picture: run gen.py in your copy (PY fx/<id>/gen.py) after the cut, again after the mix (the
// real voice waveform) and whenever the FX list changes. Here you change the title, where the panel sits and the
// words each beat lands on; nothing else.

var TITLE = 'Timeline';
var PANEL = { left: 50, top: 236 };                    // frame px; the panel is 980 wide, its height comes from gen.py
// each beat lands on a word (plus an offset in seconds); with no such word in the window, at A + its fallback in T
var WK = { clips: ['know', 0], blocks: ['nothing', 0], captions: ['about', 0], keys: ['editing', -0.1] };
var T = { clips: 0.30, blocks: 0.60, captions: 0.90, keys: 1.10, fold: 0.32 };   // fold: how long before B it folds

var ID = '{{ID}}', box = document.getElementById(ID + '-box');
function c(s) { return s.split(',').map(function (p) { return '#' + ID + ' .' + ID + '-' + p.trim(); }).join(', '); }
function has(sel) { return !!document.querySelector(sel); }
function beat(k) { var w = WK[k] ? wordAt(WK[k][0], A) : null; return (w !== null && w < B) ? w + WK[k][1] : A + T[k]; }
var SPAN = +box.getAttribute('data-span'), WPX = +box.getAttribute('data-wpx');
var LIGHT = getComputedStyle(document.documentElement).getPropertyValue('--c-light').trim();
box.style.left = PANEL.left + 'px';
box.style.top = PANEL.top + 'px';
box.querySelector('.' + ID + '-title').textContent = TITLE;

// labels on the accent blocks: ink or light, whichever reads better on the pack's accent
var probe = document.getElementById(ID + '-probe');
function lum(token) {
  probe.style.color = 'var(' + token + ')';
  var v = (getComputedStyle(probe).color.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(function (x) {
    x = x / 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
function contrast(a, b) { return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); }
var la = lum('--c-accent'), onAccent = contrast(la, lum('--c-ink')) >= contrast(la, lum('--c-light')) ? 'var(--c-ink)' : 'var(--c-light)';
[].forEach.call(document.querySelectorAll(c('fxa') + ' b'), function (b) { b.style.color = onAccent; });

var tClips = beat('clips'), tBlocks = beat('blocks'), tCaps = beat('captions'), tKeys = beat('keys');
var F0 = B - T.fold, f = T.fold / 0.32;                 // the fold's own beats scale with T.fold

gsap.set(box, { opacity: 0 });
gsap.set(c('head') + ' > *, ' + c('lh'), { opacity: 0 });
gsap.set(c('ruler'), { clipPath: 'inset(0% 100% 0% 0%)' });
gsap.set(c('lc'), { opacity: 0 });
if (has(c('clip'))) gsap.set(c('clip'), { scaleX: 0, transformOrigin: '0% 50%' });
if (has(c('aud'))) gsap.set(c('aud'), { clipPath: 'inset(0% 100% 0% 0%)' });
['fx', 'cap', 'sfx', 'cut'].forEach(function (k) {
  if (has(c(k))) gsap.set(c(k), { scaleY: 0, opacity: 0, transformOrigin: '50% 50%' });
});
['kf', 'mark', 'tx'].forEach(function (k) { if (has(c(k))) gsap.set(c(k), { opacity: 0, y: -10 }); });
gsap.set('#' + ID + '-ph', { opacity: 0, x: 0 });
function add(k, vars, t) { if (has(c(k))) tl.to(c(k), vars, q(t)); }
function wipe(k, vars, t) {                     // clip-path reveals: fromTo only (a .to reads the value back short)
  if (!has(c(k))) return;
  vars.clipPath = 'inset(0% 0% 0% 0%)'; vars.immediateRender = false;
  tl.fromTo(c(k), { clipPath: 'inset(0% 100% 0% 0%)' }, vars, q(t));
}

// open: a thin line that unfolds into the panel
tl.set(box, { opacity: 1 }, q(A));
tl.fromTo(box, { scaleY: 0.008, scaleX: 0.9 }, { scaleY: 1, scaleX: 1, duration: 0.24, ease: 'expo.out', immediateRender: false }, q(A));
tl.to(c('head') + ' > *', { opacity: 1, duration: 0.14, stagger: 0.02, ease: 'power2.out' }, q(A + 0.03));
wipe('ruler', { duration: 0.3, ease: 'power3.out' }, A + 0.03);
tl.to(c('lh'), { opacity: 1, duration: 0.12, stagger: 0.02, ease: 'power2.out' }, q(A + 0.04));
tl.to(c('lc'), { opacity: 1, duration: 0.12, stagger: 0.02, ease: 'power2.out' }, q(A + 0.04));
// the cut lands clip by clip, the voice under it
add('clip', { scaleX: 1, duration: 0.16, stagger: 0.028, ease: 'power3.out' }, tClips);
wipe('a1', { duration: 0.14, stagger: 0.028, ease: 'power2.out' }, tClips + 0.06);
// the graphics and the music
add('fx', { scaleY: 1, opacity: 1, duration: 0.2, stagger: 0.022, ease: 'back.out(1.6)' }, tBlocks);
wipe('a2', { duration: 0.4, stagger: 0.12, ease: 'power2.inOut' }, tBlocks + 0.04);
// every caption, every sound effect, the marks
add('cap', { scaleY: 1, opacity: 1, duration: 0.12, stagger: 0.0035, ease: 'power3.out' }, tCaps);
add('sfx', { scaleY: 1, opacity: 0.85, duration: 0.12, stagger: 0.006, ease: 'power3.out' }, tCaps + 0.06);
add('mark', { opacity: 1, y: 0, duration: 0.16, stagger: 0.03, ease: 'back.out(2)' }, tCaps + 0.04);
// the cutout, the transitions, the keyframes; the zoom slider pulls out
add('cut', { scaleY: 1, opacity: 1, duration: 0.2, stagger: 0.03, ease: 'back.out(1.6)' }, tKeys);
add('tx', { opacity: 1, y: 0, duration: 0.14, stagger: 0.04, ease: 'back.out(2)' }, tKeys + 0.04);
add('kf', { opacity: 1, y: 0, duration: 0.14, stagger: 0.008, ease: 'back.out(2)' }, tKeys + 0.08);
tl.to('#' + ID + '-zknob', { x: 96, duration: 0.3, ease: 'power3.inOut' }, q(tKeys + 0.04));

// the playhead tears across the whole video; the timecode reads where it is, frame by frame
var ph0 = tClips + 0.06, ph1 = F0, eph = gsap.parseEase('power2.inOut');
tl.set('#' + ID + '-ph', { opacity: 1 }, q(ph0));
tl.fromTo('#' + ID + '-ph', { x: 0 }, { x: WPX, duration: ph1 - ph0, ease: 'power2.inOut', immediateRender: false }, q(ph0));
function tc(s) {
  var fr = Math.floor(s * 30 + 1e-6), ff = fr % 30, ss = Math.floor(fr / 30) % 60, mm = Math.floor(fr / 1800);
  function p(n) { return (n < 10 ? '0' : '') + n; }
  return '00:' + p(mm) + ':' + p(ss) + ':' + p(ff);
}
for (var k = 0; ; k++) {
  var t = ph0 + k / 30;
  if (t > ph1 + 0.001) break;
  tl.set('#' + ID + '-tc', { textContent: tc(eph(Math.min(1, (t - ph0) / (ph1 - ph0))) * SPAN) }, q(t));
}

// fold: lanes close from the outside in, the panel pinches to a light line, the line to nothing
tl.set('#' + ID + '-ph', { opacity: 0 }, q(F0));
tl.to(c('lane'), { scaleY: 0, duration: 0.13 * f, stagger: { each: 0.025 * f, from: 'edges' }, ease: 'power3.in' }, q(F0));
tl.to(c('head') + ' > *, ' + c('ruler'), { opacity: 0, duration: 0.1 * f, ease: 'power2.in' }, q(F0 + 0.04 * f));
tl.to(box, { scaleY: 0.006, duration: 0.16 * f, ease: 'power3.in' }, q(F0 + 0.06 * f));
tl.set(['#' + ID + '-panel', '#' + ID + '-shadow'], { backgroundColor: LIGHT }, q(F0 + 0.22 * f));
tl.to(box, { scaleX: 0, duration: 0.1 * f, ease: 'power3.in' }, q(F0 + 0.22 * f));
tl.set(box, { opacity: 0 }, q(F0 + 0.32 * f));
