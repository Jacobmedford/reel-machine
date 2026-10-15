/* grade-slider (layer: cam). A before/after slider for a look change: "make it warmer", "it warms up".
   Beat by beat:
     A           a copy of the footage in the new look slides in from the right behind a line tilted TILT degrees
                 and lands on the face with a small overshoot
     A + labels  BEFORE / AFTER arrive, one on each side of the line (each is cut by the line as it passes)
     hold        the split holds through the face, drifting a few pixels
     CUE word    the line sweeps left; the new look covers the whole frame by the last frame before B
     B           edit.GRADES switches the main picture to the same look, so the hand-off can't be seen
   Supply: nothing but the look. Add a GRADES entry to edit.py that starts at B, no fade: (B, <until>, "warm").
   Change: LOOK, CUE, LABELS, FACE (where the split holds, on your face in this shot), HANDLE_Y, T. The copy in
   fx.html is timed by the build from the FX entry, so it works wherever the effect sits.
   Sound: a soft whoosh as the slider lands (A + 0.1), a whoosh on the sweep (the CUE word). */
var LOOK = 'warm';                  // the new look: a named grade (the one edit.GRADES switches to at B) or a CSS filter
var CUE = 'warmer';                 // the sweep starts on this word (fallback: A + T.sweep)
var LABELS = ['Before', 'After'];   // left of the line (the look now), right of it (the new look)
var FACE = [540, 770];              // the split holds through this point: the middle of the face (px on 1080x1920)
var TILT = 8;                       // degrees, top leaning right
var HANDLE_Y = 1250;                // the handle's height on the line (px): just above the captions
var T = { slide: 0.20, labels: 0.13, sweep: 0.66, drift: 14, out: 0.12 };   // s after A; drift: px the hold creeps
                                                                            // left; out: s before B the handle goes

// the look's filter. A CSS filter is used as written; a named grade is read off the timeline at B, where
// edit.GRADES switches to it, so the sweep always lands on exactly the grade that holds after it.
function gradeAt(t) {
  var v = document.getElementById('v'), f = typeof COLOR === 'string' ? COLOR : 'none', at = -1;
  tl.getChildren(false, true, false).forEach(function (tw) {
    var s = tw.startTime();
    if (tw.vars && tw.vars.filter !== undefined && s <= t + 0.0005 && s >= at && tw.targets().indexOf(v) !== -1) { at = s; f = tw.vars.filter; }
  });
  return f;
}
var FILTER = LOOK.indexOf('(') !== -1 ? LOOK : gradeAt(B);

document.getElementById('{{ID}}-tb').textContent = LABELS[0];
document.getElementById('{{ID}}-ta').textContent = LABELS[1];

// per frame, so the clip edges and the line are always the same pixel column: cx is where the line crosses y 960
var FPS = 30, D = 960 * Math.tan(TILT * Math.PI / 180);
function fq(f) { return Math.max(0, f / FPS - 0.002); }
function backo(p) { var c = 1.5; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); }
function e3io(p) { return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; }
var tCue = wordAt(CUE, A); if (tCue === null || tCue >= B) tCue = A + T.sweep;
var f0 = Math.round(A * FPS), fUp = Math.round(tCue * FPS), f1 = Math.round(B * FPS), nIn = Math.round(T.slide * FPS);
var START = 1080 + D + 24, MID = FACE[0] - (960 - FACE[1]) * Math.tan(TILT * Math.PI / 180), END = -D - 24;
function cxAt(f) {
  if (f < f0 + nIn) return START + (MID - START) * backo((f - f0 + 1) / nIn);
  if (f < fUp) return MID - T.drift * (f - f0 - nIn) / Math.max(1, fUp - f0 - nIn);
  return (MID - T.drift) + (END - (MID - T.drift)) * e3io(Math.min(1, (f - fUp + 1) / Math.max(1, f1 - fUp - 1)));
}
function poly(cx, right) {
  var a = (cx + D).toFixed(1), b = (cx - D).toFixed(1);
  return right ? 'polygon(' + a + 'px 0px, 1300px 0px, 1300px 1920px, ' + b + 'px 1920px)'
               : 'polygon(-220px 0px, ' + a + 'px 0px, ' + b + 'px 1920px, -220px 1920px)';
}
gsap.set('#{{ID}}-v', { filter: FILTER, clipPath: poly(START, true) });
gsap.set('#{{ID}}-line', { x: START, rotation: TILT });
gsap.set('#{{ID}}-knob', { y: (HANDLE_Y - 960) / Math.cos(TILT * Math.PI / 180), rotation: -TILT });   // along the tilted line
gsap.set(['#{{ID}}-la', '#{{ID}}-lb'], { opacity: 0 });
for (var f = f0; f < f1; f++) {
  var cx = cxAt(f);
  tl.set('#{{ID}}-v', { clipPath: poly(cx, true) }, fq(f));
  tl.set('#{{ID}}-la', { clipPath: poly(cx, true) }, fq(f));
  tl.set('#{{ID}}-lb', { clipPath: poly(cx, false) }, fq(f));
  tl.set('#{{ID}}-line', { x: cx }, fq(f));
}
// the labels arrive once the split is on screen; each leaves with its side of the line
tl.fromTo(['#{{ID}}-lb', '#{{ID}}-la'], { opacity: 0, y: 10 },
  { opacity: 1, y: 0, duration: 0.15, ease: 'power3.out', stagger: 0.04, immediateRender: false }, q(A + T.labels));
// the handle shrinks away as the sweep leaves the frame; AFTER has nothing left to compare against
tl.to('#{{ID}}-knob', { scale: 0.4, opacity: 0, duration: T.out, ease: 'power2.in' }, q(B - T.out));
tl.to('#{{ID}}-la', { opacity: 0, duration: T.out - 0.02, ease: 'power1.in' }, q(B - T.out + 0.02));
