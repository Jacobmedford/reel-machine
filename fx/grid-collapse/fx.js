/* grid-collapse (layer: cam). "Lots of people do this": you are one of many, then back to you.
   Beat by beat:
     A          (on a picture cut, or anywhere) the full frame shrinks into the centre tile of a 3x3 grid; it starts
                as the picture itself, so the first frame shows no change
     POP word   the eight tiles around it pop in from the centre out: the four sides, then the corners
     CUE word   the centre snaps back to full frame while the eight let go and fall away, each with its own tilt
     -> B       the full-frame centre is the picture again (a synced copy), so the hand-off at B can't be seen
   Supply: eight real screenshots of other people doing what you describe (9:16 crops, headlines readable), as
   img tags in fx.html (see its header). The library ships token-built PLACEHOLDER cards in their place.
   Change: POP, CUE, T, LABEL. The centre copy is timed by the build from the FX entry.
   If A sits on a picture cut, give that cut no camera transition (the grid already moves on it).
   Sound: a soft whoosh as the frame shrinks (A), a pop per tile (eight, staggered), a whoosh on the scatter (CUE). */
var POP = 'of';                     // the tiles pop in on this word, while the frame is still shrinking (fallback: A + T.pop)
var CUE = 'this';                   // they fall away and you snap back on this word (fallback: A + T.scatter)
var T = { shrink: 0.30, pop: 0.08, corners: 0.13, stagger: 0.033, scatter: 0.92, snap: 0.18 };   // seconds
var LABEL = 'Screenshot';           // the placeholder cards' label (numbered); gone once real screenshots are in

function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function rnd(i) { var x = Math.sin(i * 12.9898) * 43758.5453; return x - Math.floor(x); }
var G = 14, W = (1080 - 4 * G) / 3, K = W / 1080, H = 1920 * K, Y0 = (1920 - (3 * H + 2 * G)) / 2;
function tx(c) { return G + c * (W + G); }
function ty(r) { return Y0 + r * (H + G); }
var RING = [[0, 1], [1, 0], [1, 2], [2, 1]], CORNERS = [[0, 0], [0, 2], [2, 2], [2, 0]], OUTER = RING.concat(CORNERS);
var R = tok('--radius') || '0px', C = '#{{ID}}-t11';
var tPop = wordAt(POP, A); if (tPop === null || tPop >= B) tPop = A + T.pop;
var tCue = wordAt(CUE, tPop); if (tCue === null || tCue >= B - 0.2) tCue = A + T.scatter;
document.querySelectorAll('#{{ID}} .{{ID}}-n').forEach(function (el, i) { el.textContent = LABEL + ' ' + (i + 1); });

OUTER.forEach(function (rc) { gsap.set('#{{ID}}-t' + rc[0] + rc[1], { opacity: 0, transformOrigin: '50% 50%' }); });
// A: the full frame shrinks into the centre tile (it starts as the picture itself, so the cut stays clean). The
// backdrop comes up a frame later: on the first frame the scaled tile's anti-aliased edge would show it as a line.
gsap.set('#{{ID}}-bg', { opacity: 0 });
tl.set('#{{ID}}-bg', { opacity: 1 }, q(A + 1 / 30));
gsap.set(C, { transformOrigin: '0 0', x: -tx(1), y: -ty(1), scale: 1 / K, borderRadius: 0 });
tl.fromTo(C, { x: -tx(1), y: -ty(1), scale: 1 / K, borderRadius: 0 },
  { x: 0, y: 0, scale: 1, borderRadius: R, duration: T.shrink, ease: 'power3.inOut', immediateRender: false }, q(A));
// POP: the others, the four sides then the corners, popping outwards from the centre
OUTER.forEach(function (rc, i) {
  var s = '#{{ID}}-t' + rc[0] + rc[1], t = tPop + (i < 4 ? i * T.stagger : T.corners + (i - 4) * T.stagger);
  tl.set(s, { opacity: 1 }, q(t));
  tl.fromTo(s, { scale: 0.45 }, { scale: 1, duration: 0.3, ease: 'back.out(1.6)', immediateRender: false }, q(t));
});
// CUE: the centre snaps back to full frame; the other eight let go at once (shrink, fast out) and drop (gravity,
// slow in), outwards and down, each with its own tilt
tl.fromTo(C, { x: 0, y: 0, scale: 1, borderRadius: R },
  { x: -tx(1), y: -ty(1), scale: 1 / K, borderRadius: 0, duration: T.snap, ease: 'power2.inOut', immediateRender: false }, q(tCue));
OUTER.forEach(function (rc, i) {
  var s = '#{{ID}}-t' + rc[0] + rc[1], dc = rc[1] - 1, dr = rc[0] - 1, t = q(tCue + rnd(i + 5) * 0.03);
  tl.fromTo(s, { scale: 1 }, { scale: 0.62, duration: 0.22, ease: 'power3.out', immediateRender: false }, t);
  tl.fromTo(s, { x: 0, y: 0, rotation: 0 },
    { x: dc * 200, y: dr * 220 + 900 + rnd(i + 3) * 260, rotation: (dc || (rnd(i) - 0.5) * 2) * (8 + rnd(i + 9) * 8),
      duration: 0.4, ease: 'power2.in', immediateRender: false }, t);
});
// once the centre covers the frame again, the rest goes
off('#{{ID}}-bg', tCue + T.snap - 0.01);
OUTER.forEach(function (rc) { off('#{{ID}}-t' + rc[0] + rc[1], tCue + T.snap - 0.01); });
