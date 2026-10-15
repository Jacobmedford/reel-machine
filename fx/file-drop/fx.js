// file-drop (layer: top): the raw file goes in.
//   A           a dashed drop zone opens, its dashes marching while it waits
//   "drop"      the file card falls in and lands on the word; the zone takes it (the dashes go solid)
//   "in"        its thumbnail opens into a player of the raw footage; the card and the zone fall away under it
//   "in" + .14  the label lands: the file's length
//   "raw"       BAD TAKE slams onto the player, which takes the hit
//   "file"      a second BAD TAKE
//   B - out     the stack drops back and clears
//
// Supply: the real file's facts and a clip of the real filler. Run facts.py in your copy on the raw recording:
//   PY fx/<id>/facts.py <raw file>        prints FILE (name, length, size, resolution, from ffprobe) for below and
//                                          writes thumb.jpg, a frame of the file for the card
//   PY fx/<id>/facts.py <raw file> --clip <start> <seconds> [--speed 2.3]
//                                          also cuts raw.mp4, filler the edit threw out (a gap between edit.KEEP
//                                          ranges, in source seconds: dead air, a fumbled line), sped up. Then on the
//                                          <video> in fx.html set src="fx/{{ID}}/raw.mp4", data-media-start="0" and
//                                          data-playback-rate="1" (raw.mp4 is already sped up); SPEED stays its speed.
// Without a clip the player shows this video's own clean.mp4, 1 s in, at 2.3x and ungraded (raw): that's the
// <video> in fx.html. It plays from A through the whole window, so it is running whenever the player opens.
// Change the constants below, nothing else.

var FILE = { name: 'take.mov', length: '1:16', size: '412 MB', res: '1080×1920' };
var HINT = 'Drop raw footage';
var STAMP = 'Bad take';
var LABEL = [FILE.length, 'of raw footage'];                  // the number, then the words after it
var SPEED = '2.3×';                                        // the player's speed tag ('' hides it)
// each beat lands on a word (plus an offset in seconds); with no such word in the window, at A + its fallback in T
var WK = { drop: ['drop', 0], open: ['in', 0], label: ['in', 0.14], stamp1: ['raw', 0], stamp2: ['file', 0] };
var T = { drop: 0.33, open: 0.57, label: 0.71, stamp1: 1.03, stamp2: 1.27, out: 0.17 };

var ID = '{{ID}}';
function $(k) { return document.getElementById(ID + '-' + k); }
function beat(k) { var w = WK[k] ? wordAt(WK[k][0], A) : null; return (w !== null && w < B) ? w + WK[k][1] : A + T[k]; }
function fr(t) { return Math.round(t * 30) / 30; }
var ACCENT = getComputedStyle(document.documentElement).getPropertyValue('--c-accent').trim();
var g = $('g'), zone = $('zone'), rect = document.querySelector('#' + ID + '-dash rect'), card = $('card'), pl = $('pl');
var s1 = $('s1'), s2 = $('s2'), lb = $('lb');

$('ht').textContent = HINT;
$('name').textContent = FILE.name;
$('info').textContent = [FILE.length, FILE.size, FILE.res].filter(Boolean).join(' · ');
s1.textContent = STAMP;
s2.textContent = STAMP;
lb.querySelector('b').textContent = LABEL[0];
lb.querySelector('span').textContent = LABEL[1];
$('ff').querySelector('span').textContent = SPEED;
if (!SPEED) $('ff').style.display = 'none';

var tDrop = beat('drop'), tOpen = beat('open'), tLab = beat('label'), tS1 = beat('stamp1'), tS2 = beat('stamp2');
var tOut = B - T.out;

// the thumbnail's box inside the player's: the card sits at 250,474 with 16 px padding, the player at 371,230 (338x600)
var S = 56 / 338, X0 = 266 - 371, Y0 = 490 - 230;
gsap.set(zone, { scale: 0.94, opacity: 0 });
gsap.set(card, { y: -820, rotation: -9, opacity: 0 });
gsap.set(pl, { x: X0, y: Y0, scale: S, opacity: 0 });
gsap.set([$('ff'), $('bar')], { opacity: 0 });
gsap.set($('fill'), { scaleX: 0 });
gsap.set(lb, { scale: 0.94, opacity: 0 });
gsap.set(s1, { xPercent: -50, x: -14, scale: 2.2, rotation: -14, opacity: 0 });
gsap.set(s2, { xPercent: -50, x: 12, scale: 2.2, rotation: 13, opacity: 0 });

// A: the zone opens, its dashes march until the file lands
tl.to(zone, { scale: 1, opacity: 1, duration: 0.22, ease: 'power3.out' }, q(A));
tl.fromTo(rect, { strokeDashoffset: 0 }, { strokeDashoffset: -60, duration: Math.max(0.2, tDrop - A), ease: 'none', immediateRender: false }, q(A));
// "drop": the card falls (accelerating) and lands ON the word, with a small bounce
tl.set(card, { opacity: 1 }, q(tDrop - 0.2));
tl.to(card, { y: 0, rotation: 2, duration: 0.2, ease: 'power3.in' }, q(tDrop - 0.2));
tl.to(card, { keyframes: [{ y: -10, rotation: -0.6, duration: 0.07, ease: 'power2.out' }, { y: 0, rotation: 0, duration: 0.09, ease: 'power2.in' }] }, q(tDrop));
// the zone takes it: dashes go solid accent, the hint clears, a small give under the impact
tl.to($('hint'), { opacity: 0, duration: 0.08, ease: 'none' }, q(tDrop - 0.2));
tl.set(rect, { stroke: ACCENT, strokeOpacity: 1, strokeDasharray: 'none' }, q(tDrop));
tl.to(zone, { keyframes: [{ scale: 0.985, duration: 0.06, ease: 'power2.out' }, { scale: 1, duration: 0.12, ease: 'power2.out' }] }, q(tDrop));
// open: the thumbnail grows into the player; the card and the zone fall away under it
tl.set(pl, { opacity: 1 }, q(tOpen));
tl.set($('th'), { opacity: 0 }, q(tOpen));
tl.to(pl, { x: 0, y: 0, scale: 1, duration: 0.4, ease: 'expo.inOut' }, q(tOpen));
tl.to(card, { opacity: 0, duration: 0.14, ease: 'none' }, q(tOpen + 0.04));
tl.to(zone, { scale: 0.9, opacity: 0, duration: 0.26, ease: 'power2.in' }, q(tOpen + 0.06));
tl.to([$('ff'), $('bar')], { opacity: 1, duration: 0.12, ease: 'none' }, q(tOpen + 0.36));
tl.fromTo($('fill'), { scaleX: 0 }, { scaleX: 1, duration: fr(B) - fr(tOpen), ease: 'none', immediateRender: false }, q(tOpen));
// the label
tl.to(lb, { scale: 1, opacity: 1, duration: 0.16, ease: 'power3.out' }, q(tLab));
// each stamp slams down (accelerating) and lands ON its word; the player takes the hit
function stamp(el, t, rot, dx) {
  tl.set(el, { opacity: 1 }, q(t - 0.12));
  tl.to(el, { scale: 1, rotation: rot, duration: 0.12, ease: 'power4.in' }, q(t - 0.12));
  tl.to(pl, { keyframes: [{ x: dx, y: 4, duration: 0.04, ease: 'none' }, { x: -dx * 0.5, y: -2, duration: 0.05, ease: 'none' },
    { x: 0, y: 0, duration: 0.06, ease: 'power2.out' }] }, q(t));
}
stamp(s1, tS1, -8, 7);
stamp(s2, tS2, 6, -7);
// out: the whole stack drops back and clears before B
tl.to(g, { scale: 0.9, y: -30, opacity: 0, duration: T.out, ease: 'power2.in' }, q(tOut));
