/* mood-curtain (layer: cam). "...and [a held pause] it goes dark." The new look falls like a curtain on the cue word.
   Beat by beat:
     A          the cut: a copy of the footage in the look that was on screen just before A covers the frame, so nothing
                changes yet. A pause before the cue is left alone on purpose: the held, untouched frame is the suspense
     T.cue      the copy lifts away top-down in T.fall seconds (fast out of the gate, the face is dark by the second
                frame), a light hem riding its edge: the new look drops over the frame
     landed     the vignette closes in from VIG x wider (the room dims around the speaker), grain moves every frame
     hold       grain and vignette hold over the new picture until B
   Built on the kit's mood-curtain. edit.py needs a GRADES entry for the new look that starts at or before the
   curtain's first frame and runs to B or later. grain.png is self-made
   (make_grain.py, seeded noise); the footage copy is timed by the build from the FX entry. */
// PRESET CONSTANTS START
var FROM = null;                    // the look it lifts away: null = whatever was on screen the frame before A, or a CSS filter
// cue: when the curtain falls (seconds after A or a spoken word, "dark"); fall: how long it takes; close: the vignette
// closing in after it lands (s)
var T = {"cue": 0.355, "fall": 0.3, "close": 0.7};
var GRAIN = 0.18;                   // grain strength (opacity of the overlay)
var VIG = 1.22;                     // the vignette starts this much wider and closes to 1 once the curtain is down
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word: 'dark' is the start of the first "dark" at or after A,
// 'dark-0.05' nudges it. preset.py checks every word against words.json when it makes the instance.
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

// the live grade at time t, read off the timeline: edit.GRADES, BW and the house grade all set the filter on '.g'
function gradeAt(t) {
  var v = document.getElementById('v'), f = typeof COLOR === 'string' ? COLOR : 'none', at = -1;
  tl.getChildren(false, true, false).forEach(function (tw) {
    var s = tw.startTime();
    if (tw.vars && tw.vars.filter !== undefined && s <= t + 0.0005 && s >= at && tw.targets().indexOf(v) !== -1) { at = s; f = tw.vars.filter; }
  });
  return f;
}
var FPS = 30;
function fq(f) { return Math.max(0, f / FPS - 0.002); }
function e3o(p) { return 1 - Math.pow(1 - p, 3); }            // power3.out: the edge is already moving on the word
var tFall = A + T.cue; if (tFall >= B - T.fall) tFall = A;
var f0 = Math.round(tFall * FPS), N = Math.max(2, Math.round(T.fall * FPS)), f1 = Math.round(B * FPS);

gsap.set('#{{ID}}-v', { filter: FROM || gradeAt(A - 1 / FPS) });
gsap.set('#{{ID}}-grain', { opacity: GRAIN });
gsap.set('#{{ID}}-vig', { scale: VIG });
// the curtain: per frame so the hem and the clip edge are always the same pixel row
for (var i = 0; i <= N; i++) {
  var y = 1926 * e3o(Math.min(1, (i + 1) / (N + 1)));
  tl.set('#{{ID}}-v', { clipPath: 'inset(' + y.toFixed(1) + 'px 0px 0px 0px)' }, fq(f0 + i));
  tl.set('#{{ID}}-hem', { y: y }, fq(f0 + i));
}
gsap.set('#{{ID}}-hem', { opacity: 0 });
tl.set('#{{ID}}-hem', { opacity: 1 }, fq(f0));
tl.set(['#{{ID}}-v', '#{{ID}}-hem'], { opacity: 0 }, fq(f0 + N + 1));
// once it has landed, the vignette closes in
tl.fromTo('#{{ID}}-vig', { scale: VIG }, { scale: 1, duration: T.close, ease: 'power2.out', immediateRender: false }, fq(f0 + N));
// grain: one seeded tile, a new offset every frame (deterministic), from the fall to B
function rnd(i) { var x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); }
for (var f = f0; f < f1; f++) {
  tl.set('#{{ID}}-gt', { x: -Math.floor(rnd(f) * 512), y: -Math.floor(rnd(f + 977) * 512) }, fq(f));
}
