// camera-transitions: a different camera move on every picture cut: whip (with motion blur), zoom-through, spin,
// push, drop, reveal. Keyed frame by frame on #foot, the wrapper around the camera, so the footage is never re-timed
// and the CAMERA zooms on #cam keep working inside it. Every keyed frame is overscaled enough that the moved frame
// still covers the whole canvas (no black corners), and the frame after a move's last key is a clean identity (no
// transform, no filter).
//
// Use: one entry for the whole video, dict(id="camera-transitions", layer="over", at=0.0, end="end").
// Supply: nothing. The cuts come from CUTS (this edit's picture cuts), so a re-cut moves the transitions with it.
// Change only these constants:
//   MOVES     which moves, in order. They cycle over the cuts that get one (a skipped cut does not use one up).
//   SKIP      cuts a full-frame graphic already covers (a card, a grid, a cover): no move there. Seconds on the
//             output timeline, matched within 0.1 s.
//   STRENGTH  per move: 1 is the reference look, 0.5 half the travel, turn, zoom and blur, 0 switches it off.
//   MOVE      the moves themselves: frames out (before the cut) and in (after it), 4 to 8 a side, and their peaks.
// Sound, one per move on the cut: whoosh (whip), whoosh-deep (zoom, drop), whoosh-soft (spin, push, reveal),
// 14 to 18 dB under the voice.

var MOVES = ['whip', 'zoom', 'spin', 'push', 'drop', 'reveal'];
var SKIP = [];
var STRENGTH = { whip: 1, zoom: 1, spin: 1, push: 1, drop: 1, reveal: 1 };

// out / inn: frames before / after the cut. peakOut: where the outgoing shot is on the last frame before the cut
// (it accelerates there from rest). peakIn: where the incoming shot is on the cut frame (it brakes back to rest).
// s scale, x / y px, r degrees clockwise, bx / by motion blur in px (horizontal / vertical).
var MOVE = {
  // pans left under a horizontal blur; the new shot arrives from the right and brakes
  whip:   { out: 4, inn: 6, peakOut: { s: 1.36, x: -170, bx: 46 }, peakIn: { s: 1.36, x: 170, bx: 46 } },
  // rushes at the lens; the new shot lands out of it
  zoom:   { out: 4, inn: 6, peakOut: { s: 1.6, bx: 14, by: 14 }, peakIn: { s: 1.5, bx: 12, by: 12 } },
  // turns clockwise through the cut
  spin:   { out: 4, inn: 6, peakOut: { s: 1.42, r: 9, bx: 9, by: 9 }, peakIn: { s: 1.42, r: -9, bx: 9, by: 9 } },
  // a small push in on the new shot, nothing on the way out
  push:   { out: 0, inn: 5, peakIn: { s: 1.07 } },
  // falls out the bottom; the new shot drops in from above
  drop:   { out: 4, inn: 5, peakOut: { s: 1.24, y: 150, by: 40 }, peakIn: { s: 1.24, y: -170, by: 40 } },
  // the new shot pulls back with a slight counter-turn
  reveal: { out: 0, inn: 7, peakIn: { s: 1.24, r: -1.6, bx: 5, by: 5 } }
};

var FPS = 30;
var REST = { s: 1, x: 0, y: 0, r: 0, bx: 0, by: 0 };
var foot = document.getElementById('foot');
var W = foot.offsetWidth || 1080, H = foot.offsetHeight || 1920;
var org = (getComputedStyle(document.getElementById('cam')).transformOrigin || '').split(' ');
var OX = parseFloat(org[0]), OY = parseFloat(org[1]);          // the camera's own origin (CAM_ORIGIN)
if (!isFinite(OX) || !isFinite(OY)) { OX = W / 2; OY = H * 0.4; }
gsap.set('#foot', { transformOrigin: OX + 'px ' + OY + 'px' });

function ein(p) { return p * p; }                               // outgoing: accelerates into the cut
function eout(p) { return 1 - Math.pow(1 - p, 3); }             // incoming: brakes out of it
function peak(p, k) {                                           // a peak at strength k
  p = p || {};
  return { s: 1 + ((p.s || 1) - 1) * k, x: (p.x || 0) * k, y: (p.y || 0) * k, r: (p.r || 0) * k,
           bx: (p.bx || 0) * k, by: (p.by || 0) * k };
}
function mix(a, b, p) {
  var o = {};
  for (var n in REST) o[n] = a[n] + (b[n] - a[n]) * p;
  return o;
}
// the smallest scale at which the moved frame still covers the canvas (half a pixel of bleed on every side)
function cover(k) {
  if (Math.abs(k.x) < 0.01 && Math.abs(k.y) < 0.01 && Math.abs(k.r) < 0.001) return 1;
  var a = k.r * Math.PI / 180, c = Math.cos(a), n = Math.sin(a), need = 1;
  [[-0.5, -0.5], [W + 0.5, -0.5], [-0.5, H + 0.5], [W + 0.5, H + 0.5]].forEach(function (p) {
    var dx = p[0] - OX - k.x, dy = p[1] - OY - k.y;
    var u = c * dx + n * dy, v = -n * dx + c * dy;               // the canvas corner, turned back into the frame
    need = Math.max(need, u > 0 ? u / (W - OX) : -u / OX, v > 0 ? v / (H - OY) : -v / OY);
  });
  return need;
}
function key(f, k) {
  var t = q(f / FPS), blur = k.bx > 0.3 || k.by > 0.3;
  if (k === REST) {
    tl.set('#foot', { scale: 1, x: 0, y: 0, rotation: 0, filter: 'none' }, t);
    return;
  }
  tl.set('#foot', { scale: Math.max(k.s, cover(k)), x: k.x, y: k.y, rotation: k.r,
                    filter: blur ? 'url(#{{ID}}-mb)' : 'none' }, t);
  if (blur) tl.set('#{{ID}}-mb-g', { attr: { stdDeviation: k.bx.toFixed(1) + ' ' + k.by.toFixed(1) } }, t);
}

var last = -1, used = 0;
CUTS.forEach(function (cut) {
  if (cut <= A || cut >= B || !MOVES.length) return;
  if (SKIP.some(function (t) { return Math.abs(t - cut) < 0.1; })) return;
  if (FXS.some(function (f) { return f.id !== '{{ID}}' && (f.layer === 'cam' || f.layer === 'over') &&
                                     Math.abs(f.at - cut) < 0.1; })) return;   // a full-frame effect starts on this cut: it is the transition
  var c = Math.round(cut * FPS);
  if (c <= last) return;                                        // too close to the last move to get its own
  var name = MOVES[used % MOVES.length], m = MOVE[name];
  var k = STRENGTH[name] === undefined ? 1 : STRENGTH[name];
  used++;
  if (!m || !(k > 0)) return;
  var po = peak(m.peakOut, k), pi = peak(m.peakIn, k);
  for (var i = 0; i < m.out; i++) {
    if (c - m.out + i > last) key(c - m.out + i, mix(REST, po, ein((i + 1) / m.out)));
  }
  for (var j = 0; j < m.inn; j++) key(c + j, mix(pi, REST, eout(j / m.inn)));
  key(c + m.inn, REST);
  last = c + m.inn;
});
