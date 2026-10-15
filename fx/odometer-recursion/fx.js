/* odometer-recursion (layer: cam). "A few minutes later, this is the video": how long the raw take was against the
   finished video, then the video looking at itself.
   Beat by beat:
     A               a counter plate rises in showing the raw take's length (RAW) under LABELS[0]
     CUES.roll       it rolls down like a mechanical counter (the units drum turns, tens and minutes only turn on a
                     carry) and lands on the final length (FINAL) on CUES.land; the label rolls to LABELS[1]
     out             the plate wipes away upward just before the first level
     CUES.levels     the frame shrinks into a framed inset of itself, one level per word, four deep (each level is
                     the same footage in sync, so a new level starts invisible on top of its parent)
     CUES.dive -> B  the camera dives through one level, accelerating; on the last frame before B the picture is
                     the first level grown to full frame, the next one inset: the loop's first frame
   Supply: the two true lengths (m:ss, under 10 minutes). Nothing else: every level is a synced copy of clean.mp4 and
   follows the live grade (class g).
   Change: RAW, FINAL, LABELS, CUES, PLATE, FOCUS (where the insets converge: empty space beside the head), S,
   T (fallbacks when a cue word isn't found). The five footage copies in fx.html are timed by the build from
   the FX entry, a frame apart.
   Sound: a soft whoosh as the plate rises (A), a clacking run under the roll (roll -> land), a ding on the landing,
   a pop per level, a deep whoosh on the dive. */
var RAW = '1:16', FINAL = '0:29';                    // the raw take's length -> the finished video's (m:ss)
var LABELS = ['Raw take', 'This video'];             // over the counter before and after it lands
var CUES = { roll: 'a', land: 'later', levels: ['this', 'is', 'the', null], dive: 'video' };   // null: right after the last
var PLATE = [540, 240];                              // the counter's top centre (px on 1080x1920): clear of the face
var FOCUS = [1030, 330];                             // the insets converge on this point (px on 1080x1920)
var S = 0.3;                                         // each level is this much of its parent
var T = { roll: 0.10, land: 0.81, levels: [1.05, 1.29, 1.53, 1.65], dive: 1.76,   // fallbacks, seconds after A
          out: 0.12, gap: 0.12 };   // the plate leaves this long before the first level; a level without a word follows after gap

function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function cue(w, fb, after) { var t = w ? wordAt(w, after) : null; return (t === null || t >= B) ? A + fb : t; }
function secs(s) { var p = String(s).split(':'); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }
var FPS = 30;
function fq(i) { return Math.max(0, i / FPS - 0.002); }      // frame index -> its time on the timeline
function fi(t) { return Math.round(t * FPS); }               // time -> frame index
var odo = document.getElementById('{{ID}}-odo');
odo.style.left = (PLATE[0] - odo.offsetWidth / 2) + 'px'; odo.style.top = PLATE[1] + 'px';
document.getElementById('{{ID}}-l0').textContent = LABELS[0];
document.getElementById('{{ID}}-l1').textContent = LABELS[1];

// ---------------------------------------------------------------- part 1: the counter
var tRoll = cue(CUES.roll, T.roll, A), tLand = cue(CUES.land, T.land, tRoll);
var lv = [], prev = tLand;                                   // the level times, each after the one before
for (var k = 0; k < 4; k++) { lv[k] = CUES.levels[k] ? cue(CUES.levels[k], T.levels[k], prev + 0.01) : prev + T.gap; prev = lv[k]; }
var tDive = cue(CUES.dive, T.dive, prev + 0.01), tOut = Math.max(tLand + 0.1, lv[0] - T.out);
var R = tok('--radius') || '0px', DH = 270;                  // DH: one digit on a drum (the span height in fx.html)
function clip(top, bottom) { return 'inset(' + top + '% 0% ' + bottom + '% 0% round ' + R + ')'; }
// a mechanical counter: the units drum turns continuously, tens and minutes only turn while the drum below carries
function drums(v) {
  var sm = v % 60, u = v % 10;
  return { u: u, t: Math.floor(sm / 10) + Math.max(0, u - 9), m: Math.floor(v / 60) + Math.max(0, sm - 59) };
}
function show(d, t) {
  tl.set('#{{ID}}-du', { y: -d.u * DH }, t); tl.set('#{{ID}}-dt', { y: -d.t * DH }, t); tl.set('#{{ID}}-dm', { y: -d.m * DH }, t);
}
var V0 = secs(RAW), V1 = secs(FINAL), d0 = drums(V0);
gsap.set('#{{ID}}-odo', { clipPath: clip(100, 0), y: 40 });
gsap.set('#{{ID}}-du', { y: -d0.u * DH }); gsap.set('#{{ID}}-dt', { y: -d0.t * DH }); gsap.set('#{{ID}}-dm', { y: -d0.m * DH });
tl.fromTo('#{{ID}}-odo', { clipPath: clip(100, 0), y: 40 },
  { clipPath: clip(0, 0), y: 0, duration: 0.32, ease: 'expo.out', immediateRender: false }, q(A));
var C0 = fi(tRoll), C1 = fi(tLand);
for (var i = C0; i < C1; i++) {
  var p = (i - C0) / (C1 - C0), e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;   // power3.inOut
  show(drums(V0 + (V1 - V0) * e), fq(i));
}
show({ u: V1 % 10, t: Math.floor((V1 % 60) / 10), m: Math.floor(V1 / 60) }, fq(C1));
// it lands: the label rolls over, the plate settles
tl.fromTo('#{{ID}}-lab-in', { y: 0 }, { y: -36, duration: 0.28, ease: 'power3.out', immediateRender: false }, fq(C1));
tl.fromTo('#{{ID}}-odo', { scale: 1.04 }, { scale: 1, duration: 0.3, ease: 'back.out(1.6)', immediateRender: false }, fq(C1));
// out, upward, as the frame starts to shrink
tl.fromTo('#{{ID}}-odo', { clipPath: clip(0, 0), y: 0 },
  { clipPath: clip(0, 100), y: -40, duration: 0.18, ease: 'power2.in', immediateRender: false }, q(tOut));

// ---------------------------------------------------------------- part 2: the recursion
var LV = [null, { sw: 5.0, d: 0.46, ease: 'expo.out' }, { sw: 3.4, d: 0.32, ease: 'power4.out' },
  { sw: 2.4, d: 0.28, ease: 'power4.out' }, { sw: 1.7, d: 0.20, ease: 'power4.out' }];   // sw: frame line on screen, px
var ORIGIN = FOCUS[0] + 'px ' + FOCUS[1] + 'px';
gsap.set('#{{ID}}-stack', { transformOrigin: ORIGIN });
gsap.set('#{{ID}}-v0', { opacity: 0 });
for (var n = 1; n <= 4; n++) {
  var L = LV[n], par = Math.pow(S, n - 1), own = Math.pow(S, n), t0 = lv[n - 1];
  gsap.set('#{{ID}}-n' + n, { opacity: 0, scale: 1, transformOrigin: ORIGIN });
  gsap.set('#{{ID}}-f' + n, { borderWidth: L.sw / par });
  tl.set('#{{ID}}-n' + n, { opacity: 1 }, q(t0));
  // it starts exactly on its parent (same footage, same frame: invisible) and shrinks into the inset
  tl.fromTo('#{{ID}}-n' + n, { scale: 1 }, { scale: S, duration: L.d, ease: L.ease, immediateRender: false }, q(t0));
  tl.fromTo('#{{ID}}-f' + n, { borderWidth: L.sw / par },
    { borderWidth: L.sw / own, duration: L.d, ease: L.ease, immediateRender: false }, q(t0));
}
// the dive: one level in (x 1/S about the focus), accelerating into B. Its own full-frame copy comes up a frame early
// so the whole picture zooms. Each frame's line weight slides to the next level's, so the last frame is the loop's first.
var Z0 = fi(tDive), Z1 = fi(B) - 1;
tl.set('#{{ID}}-v0', { opacity: 1 }, fq(Z0 - 1));
for (var j = Z0; j <= Z1; j++) {
  var pz = (j - Z0) / Math.max(1, Z1 - Z0), ez = pz * pz, z = Math.pow(1 / S, ez);
  tl.set('#{{ID}}-stack', { scale: z }, fq(j));
  for (var m = 1; m <= 4; m++) {
    var target = m === 1 ? LV[1].sw * (1 - ez) : LV[m].sw + (LV[m - 1].sw - LV[m].sw) * ez;   // L1 thins away at the edge
    tl.set('#{{ID}}-f' + m, { borderWidth: target / (z * Math.pow(S, m)) }, fq(j));
  }
}
