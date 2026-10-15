// giant-captions (layer: over, above everything). The captions get giant, on the words:
//   big       the caption box, caption-sized in the caption band, grows up into a giant slab above the head
//             (expo.out) and swings level from 4 degrees (back.out)
//   line      a display-face line in the accent wipes open from the right under it, its words rising out of the
//             slab, and the giant slab gives a small kick
//   tiles     optional: one word tile per word pops up from its base across the chest (back.out)
//   slam      optional: the last word slams in on a light slab (1.7x and 7 degrees to rest) and the whole stack takes
//             the hit
//   out       each slab folds shut, top to bottom, just before the window ends
// Reach for it on "bigger captions" or any payoff line. Give its window a KARAOKE hide (edit.py:
// KARAOKE = dict(hide=[(start, end)])) so the normal captions step aside. Nothing to supply but the words: the
// slabs take the creator's caption box, accent, ground and faces, and each slab is fitted to the frame.
// Change only these constants:
var BIG = ['BIGGER', 'bigger'];             // [text, the spoken word it lands on]: the giant slab
var LINE = ['captions.', 'captions'];       // the display-face line under it; ['', ''] = none
var TILES = [];                             // word tiles, e.g. [['THAT\u2019S', "that's"], ['JUST', 'just'], ['ONE', 'one']]
var SLAM = ['', ''];                        // the last word on a light slab, e.g. ['sentence.', 'sentence']; ['', ''] = none
var AT = { big: 0.10, line: 0.75, tiles: 1.10, slam: 1.30 };   // fallbacks (s after A) when a word isn't found
var TILE_GAP = 0.18;                        // fallback spacing between tiles (s)
var OUT = 0.26;                             // the slabs start folding this long before the window ends

function $(s) { return document.querySelector(s); }
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

// ---- the words in
$('#{{ID}}-big .{{ID}}-t').textContent = BIG[0];
$('#{{ID}}-cap .{{ID}}-t').textContent = LINE[0];
$('#{{ID}}-sen .{{ID}}-t').textContent = SLAM[0];
var tiles = $('#{{ID}}-tiles');
TILES.forEach(function (w, i) {
  var d = document.createElement('div'), s = document.createElement('span');
  d.className = '{{ID}}-tile {{ID}}-box';
  d.id = '{{ID}}-tile' + i;
  s.className = '{{ID}}-t';
  s.textContent = w[0];
  d.appendChild(s);
  tiles.appendChild(d);
});
// the slabs overlap each other on purpose: tell the layout audit (it reads the text elements themselves)
Array.prototype.slice.call(document.querySelectorAll('#{{ID}} .{{ID}}-t')).forEach(function (e) {
  e.setAttribute('data-layout-allow-overlap', '');
});

// ---- the caption box made solid: on the dark ground when its ink is light, on the light ground when it is dark
var ink = (getComputedStyle($('#{{ID}}-big .{{ID}}-t')).color.match(/[\d.]+/g) || [255, 255, 255]).map(Number);
if (0.2126 * ink[0] + 0.7152 * ink[1] + 0.0722 * ink[2] < 128) {
  Array.prototype.slice.call(document.querySelectorAll('#{{ID}} .{{ID}}-box')).forEach(function (e) {
    e.style.backgroundColor = 'var(--c-light)';
  });
}

// ---- each slab keeps its fx.html size unless it is wider than it may run: the giant slab and the line are
// staggered (left 66 / right 66), the tiles and the slam stay left of x 980
var FIT = [['#{{ID}}-big', 900], ['#{{ID}}-cap', 880], ['#{{ID}}-tiles', 928], ['#{{ID}}-sen', 934]];
function fit() {
  FIT.forEach(function (f) {
    var box = $(f[0]);
    if (!box.dataset.max) box.dataset.max = parseFloat(getComputedStyle(box).fontSize);
    var max = +box.dataset.max;
    box.style.fontSize = max + 'px';
    var w = box.scrollWidth;
    if (w > f[1]) box.style.fontSize = (max * f[1] / w).toFixed(2) + 'px';
  });
}
fit();
if (document.fonts && document.fonts.load) {
  var all = [BIG[0], LINE[0], SLAM[0]].concat(TILES.map(function (w) { return w[0]; })).join(' ');
  Promise.all(['800 100px ' + tok('--font-text'),
    tok('--display-style') + ' ' + tok('--display-weight') + ' 100px ' + tok('--font-display')].map(function (f) {
    return document.fonts.load(f, all).catch(function () {});
  })).then(fit, fit);
  document.fonts.ready.then(fit);
}

// ---- beat times, each on its word (searched in order from A; a word missing from words.json falls back to AT)
var prev = A;
function find(word, fallback) {
  var w = word ? wordAt(word, prev) : null;
  var t = (w === null || w >= B) ? A + fallback : w;
  prev = Math.max(prev, t);
  return t;
}
var tBig = find(BIG[1], AT.big);
var tLine = LINE[0] ? find(LINE[1], AT.line) : null;
var tTiles = TILES.map(function (w, i) { return find(w[1], AT.tiles + i * TILE_GAP); });
var tSlam = SLAM[0] ? find(SLAM[1], AT.slam) : null;
var tOut = B - OUT;

// ---- where the captions sit (the pack sets them), so the giant slab starts as one
var kc = $('#caps .kc:not(.huge)'), kw = $('#caps .kw');
var capSize = kc ? parseFloat(getComputedStyle(kc).fontSize) : 66;
var capTop = kw ? parseFloat(getComputedStyle(kw).top) : 1318;
var capH = capSize * 1.08 + 13;                       // the caption box: its line plus its padding
var bigMax = +$('#{{ID}}-big').dataset.max;              // the fx.html size (fit() read it before any font loaded)
var s0 = capH / (0.907 * bigMax), dy = capTop + capH / 2 - (232 + 214 / 2);   // from the caption's centre to row one's (fx.html)

// ---- build
if (q(A) <= 0) gsap.set('#{{ID}}', { opacity: 1 });
gsap.set('#{{ID}} .{{ID}}-b', { opacity: 0 });
if (TILES.length) gsap.set('#{{ID}} .{{ID}}-tile', { opacity: 0, transformOrigin: '50% 100%' });
gsap.set('#{{ID}}-big', { transformOrigin: '474px 50%' });            // shrinks toward the frame's centre line
gsap.set('#{{ID}}-cap .{{ID}}-t', { yPercent: 100 });
gsap.set('#{{ID}}-sen', { rotation: -2, transformOrigin: '30% 60%' });

// big: a caption-sized box in the caption band grows up into the giant slab
tl.set('#{{ID}}-big', { opacity: 1 }, q(tBig));
tl.fromTo('#{{ID}}-big', { scale: s0, y: dy }, { scale: 1, y: 0, duration: 0.3, ease: 'expo.out', immediateRender: false }, q(tBig));
tl.fromTo('#{{ID}}-big', { rotation: 4 }, { rotation: 0, duration: 0.42, ease: 'back.out(2.2)', immediateRender: false }, q(tBig));

// line: the slab wipes open from the right edge, the words rise out of it, the giant slab kicks
if (tLine !== null) {
  tl.set('#{{ID}}-cap', { opacity: 1 }, q(tLine));
  tl.fromTo('#{{ID}}-cap', { clipPath: 'inset(0% 0% 0% 100%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.26, ease: 'expo.out', immediateRender: false }, q(tLine));
  tl.fromTo('#{{ID}}-cap .{{ID}}-t', { yPercent: 100 }, { yPercent: 0, duration: 0.34, ease: 'power4.out', immediateRender: false }, q(tLine + 0.03));
  if (tLine - tBig > 0.32) {                          // only once the giant slab has landed
    tl.fromTo('#{{ID}}-big', { y: 0 }, { y: -8, duration: 0.08, ease: 'power2.out', yoyo: true, repeat: 1, immediateRender: false }, q(tLine + 0.04));
  }
}

// tiles: one per word, popped up from its base
tTiles.forEach(function (t, i) {
  tl.set('#{{ID}}-tile' + i, { opacity: 1 }, q(t));
  tl.fromTo('#{{ID}}-tile' + i, { scaleY: 0.2, scaleX: 0.85, y: 24 }, { scaleY: 1, scaleX: 1, y: 0, duration: 0.24, ease: 'back.out(1.8)', immediateRender: false }, q(t));
});

// slam: the light slab slams in, the whole stack takes the hit
if (tSlam !== null) {
  tl.set('#{{ID}}-sen', { opacity: 1 }, q(tSlam));
  tl.fromTo('#{{ID}}-sen', { scale: 1.7, rotation: -7 }, { scale: 1, rotation: -2, duration: 0.26, ease: 'power4.out', immediateRender: false }, q(tSlam));
  tl.fromTo('#{{ID}}-all', { y: 0 }, { y: 14, duration: 0.05, ease: 'power2.out', immediateRender: false }, q(tSlam + 0.07));
  tl.to('#{{ID}}-all', { y: 0, duration: 0.3, ease: 'back.out(3)' }, q(tSlam + 0.12));
}

// out: each slab folds shut, top to bottom, gone just before the window ends
['#{{ID}}-big', '#{{ID}}-cap', '#{{ID}} .{{ID}}-tile', '#{{ID}}-sen'].forEach(function (s, i) {
  if (document.querySelector(s)) {
    tl.fromTo(s, { scaleY: 1 }, { scaleY: 0, duration: 0.14, ease: 'power3.in', immediateRender: false }, q(tOut + i * 0.035));
  }
});
