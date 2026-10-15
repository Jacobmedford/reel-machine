/* mood-curtain (layer: cam). The dark look falls from the top like a curtain: "make it moody", "the colors go dark".
   Beat by beat:
     A         a copy of the footage in the look that was on screen just before A covers the frame (no visible change),
               so edit.GRADES can switch the main picture to the moody look anywhere from A to the cue unseen
     CUE word  the copy lifts away top-down in T.fall seconds (power3.out, the edge already moving on the word), a
               light hem riding its edge: the moody look falls over the frame
     hold      film grain (grain.png, moved every frame) and a vignette hold over the moody picture until B
   Supply: nothing. grain.png is self-made: make_grain.py writes it from seeded noise (rerun it to rebuild the file).
   edit.py needs a GRADES entry for the new look that starts between A and the cue word (any fade done by the cue)
   and runs to B or later: (A, B, "moody").
   Change: CUE, FROM, T, GRAIN. The footage copy is timed by the build from the FX entry.
   Sound: a deep whoosh as the curtain falls (the CUE word), a low boom under the moody hold. */
var CUE = 'moody';                  // the curtain falls on this word (fallback: A)
var FROM = null;                    // the look it lifts away: null = whatever was on screen the frame before A, or a CSS filter
var T = { fall: 0.33 };             // seconds for the curtain to clear the frame (10 frames)
var GRAIN = 0.22;                   // grain strength (opacity of the overlay)

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
var tFall = wordAt(CUE, A); if (tFall === null || tFall >= B - T.fall) tFall = A;
var f0 = Math.round(tFall * FPS), N = Math.max(2, Math.round(T.fall * FPS)), f1 = Math.round(B * FPS);

gsap.set('#{{ID}}-v', { filter: FROM || gradeAt(A - 1 / FPS) });
gsap.set('#{{ID}}-grain', { opacity: GRAIN });
// the curtain: per frame so the hem and the clip edge are always the same pixel row
for (var i = 0; i <= N; i++) {
  var y = 1926 * e3o(Math.min(1, (i + 1) / (N + 1)));
  tl.set('#{{ID}}-v', { clipPath: 'inset(' + y.toFixed(1) + 'px 0px 0px 0px)' }, fq(f0 + i));
  tl.set('#{{ID}}-hem', { y: y }, fq(f0 + i));
}
gsap.set('#{{ID}}-hem', { opacity: 0 });
tl.set('#{{ID}}-hem', { opacity: 1 }, fq(f0));
tl.set(['#{{ID}}-v', '#{{ID}}-hem'], { opacity: 0 }, fq(f0 + N + 1));
// grain: one seeded tile, a new offset every frame (deterministic), for the whole hold
function rnd(i) { var x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); }
for (var f = f0; f < f1; f++) {
  tl.set('#{{ID}}-gt', { x: -Math.floor(rnd(f) * 512), y: -Math.floor(rnd(f + 977) * 512) }, fq(f));
}
