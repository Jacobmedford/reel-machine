/* grade-slider (layer: cam). A before/after slider that does exactly what the line says ("make it a touch
   warmer"). Beat by beat:
     A            the cut: a copy of the footage in the new look wipes in from the right behind a line tilted TILT
                  degrees and glides to a stop through the face (T.slide)
     T.labels     BEFORE / AFTER wipe open from their frame edges, one each side of the line (each is cut by the line)
     hold         the split rides through the face along FACE, drifting with it
     T.nudge      the knob takes a small press and the line steps NUDGE px further over the face ("a touch")
     T.sweep      the line sweeps the rest of the way; the new look covers the frame by the end of the word ("warmer")
     to B         the new frame holds, AFTER still up, the knob gone; B is the cut
     B            edit.GRADES switches the main picture to the same look on the cut, so the hand-off can't be seen
   Built on the kit's grade-slider. Supply a GRADES entry for the look starting at B, no fade: (B, <until>, LOOK).
   The copy in fx.html is timed by the build from the FX entry. */
// PRESET CONSTANTS START
var LOOK = "warm";                  // the new look: a named grade (the one edit.GRADES switches to at B) or a CSS filter
var LABELS = ["Before", "After"];   // left of the line (the look now), right of it (the new look)
// where the split crosses the face while it holds: [seconds after A, x, y] in px on the frame (the eyes; measure on
// stills of the shot: a face that moves gets three different points; the default is a still face, centred)
var FACE = [[0.2, 540, 700], [0.733, 540, 700], [1.295, 540, 700]];
var NUDGE = 50;                     // px the line steps on the nudge
var TILT = 8;                       // degrees, top leaning right
var HANDLE_Y = 1105;                // px: the knob's height on the line, clear of the caption box
// slide: the glide onto the face (s); labels: when they wipe open; nudge, sweep: seconds after A or spoken words
// ("touch", "warmer"); nudgeDur, sweepDur: their lengths (s)
var T = {"slide": 0.271, "labels": 0.16, "nudge": 0.74, "nudgeDur": 0.2, "sweep": 1.302, "sweepDur": 0.47};
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word: 'warmer' is the start of the first "warmer" at or
// after A, 'warmer-0.05' nudges it. preset.py checks every word against words.json when it makes the instance.
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
var FILTER = LOOK.indexOf('(') !== -1 ? LOOK : (gradeAt(B) !== (typeof COLOR === 'string' ? COLOR : 'none') ? gradeAt(B) : (LOOKS[LOOK] || 'none'));

document.getElementById('{{ID}}-tb').textContent = LABELS[0];
document.getElementById('{{ID}}-ta').textContent = LABELS[1];

// per frame, so the clip edges and the line are always the same pixel column: cx is where the line crosses y 960
var FPS = 30, TAN = Math.tan(TILT * Math.PI / 180), D = 960 * TAN;
function fq(f) { return Math.max(0, f / FPS - 0.002); }
function backo(p, c) { c = c || 1.5; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); }
function expo(p) { return p >= 1 ? 1 : 1 - Math.pow(2, -10 * p); }
function e3io(p) { return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; }
function cxThrough(x, y) { return x - (960 - y) * TAN; }        // the line through (x, y), as its crossing at y 960
var f0 = Math.round(A * FPS), f1 = Math.round(B * FPS);
var fIn = f0 + Math.round(T.slide * FPS);
var fN = Math.round((A + T.nudge) * FPS), nN = Math.round(T.nudgeDur * FPS);
var fUp = Math.round((A + T.sweep) * FPS), fDone = fUp + Math.round(T.sweepDur * FPS);
var START = 1080 + D + 24, END = -D - 24;
var P0 = cxThrough(FACE[0][1], FACE[0][2]), P1 = cxThrough(FACE[1][1], FACE[1][2]);
var P2 = cxThrough(FACE[2][1], FACE[2][2]) - NUDGE;
function cxAt(f) {
  if (f < fIn) return START + (P0 - START) * expo((f - f0 + 1) / (fIn - f0));                         // glides onto the face
  if (f < fN) return P0 + (P1 - P0) * (f - fIn) / Math.max(1, fN - fIn);                             // rides with it
  if (f < fN + nN) return P1 + (P1 - NUDGE - P1) * backo((f - fN + 1) / nN, 1.7);                     // the nudge
  if (f < fUp) return (P1 - NUDGE) + (P2 - (P1 - NUDGE)) * (f - fN - nN) / Math.max(1, fUp - fN - nN);
  return P2 + (END - P2) * e3io(Math.min(1, (f - fUp + 1) / Math.max(1, fDone - fUp)));              // the sweep
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
gsap.set('#{{ID}}-tb', { clipPath: 'inset(0% 100% 0% 0%)' });
gsap.set('#{{ID}}-ta', { clipPath: 'inset(0% 0% 0% 100%)' });
for (var f = f0; f <= Math.min(f1 - 1, fDone); f++) {
  var cx = cxAt(f);
  tl.set('#{{ID}}-v', { clipPath: poly(cx, true) }, fq(f));
  tl.set('#{{ID}}-la', { clipPath: poly(cx, true) }, fq(f));
  tl.set('#{{ID}}-lb', { clipPath: poly(cx, false) }, fq(f));
  tl.set('#{{ID}}-line', { x: cx }, fq(f));
}
// once the sweep is done the copy covers the frame and the line is off it: drop the line and BEFORE
tl.set(['#{{ID}}-line', '#{{ID}}-lb'], { opacity: 0 }, fq(fDone + 1));
// the labels wipe open from their frame edge once the split is on screen (clip-path: fromTo only); each leaves with
// its side of the line
tl.set(['#{{ID}}-lb', '#{{ID}}-la'], { opacity: 1 }, q(A + T.labels));
tl.fromTo('#{{ID}}-tb', { clipPath: 'inset(0% 100% 0% 0%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.24, ease: 'power3.out', immediateRender: false }, q(A + T.labels));
tl.fromTo('#{{ID}}-ta', { clipPath: 'inset(0% 0% 0% 100%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.24, ease: 'power3.out', immediateRender: false }, q(A + T.labels + 0.05));
// the nudge: the knob takes a small press as the line steps, like a thumb nudging it
tl.fromTo('#{{ID}}-knob', { scale: 0.84 }, { scale: 1, duration: 0.3, ease: 'back.out(2.2)', immediateRender: false }, fq(fN));
