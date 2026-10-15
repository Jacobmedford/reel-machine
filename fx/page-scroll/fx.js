// page-scroll (layer: top): a window card slides up with a page, two scroll flicks like a screen recording, then one
// push into a single section, its rows lighting up on the words.
//   A             the card slides up from below
//   A + flicks    two flicks down the page (fast off the finger, settling), the scrollbar riding along
//   "plan" - .2   back up to the focus beat and in, one move that lands on the word
//   LITE words    the rest of the page dims, the lit rows underline one by one
//   B - out       the card drops away
//
// Supply: the real page. Real artifacts beat the placeholder: capture.py screenshots a page (the project's own
// storyboard, any local HTML file or URL) and cuts it into tiles here:
//   PY fx/<id>/capture.py <project>/storyboard/index.html      (or https://...)
// It prints TILES for below and writes page-full.png; measure the rows to light on it (page px) into LIT and the
// push follows them. With TILES null, the page is a placeholder built from this video's own lines (words.json, one
// beat per sentence, real times) and PLAN, in the creator's tokens. Change the constants below, nothing else.

var BAR = ['my-video / plan', ''];               // the window's title bar; '' on the right counts the beats
var PAGE = { kicker: 'Edit plan', title: 'The edit, beat by beat',
             intro: 'One move per line, each on its word. Leave a note on any beat; nothing renders until the notes are in.' };
var PLAN = [                                    // per line of the script, in order: [move, sound]
  ['Kinetic type behind the head, readable on frame 0', 'a tick per stamped letter'],
  ['Icons pop on their names, get struck, fall', 'pops, two strikes'],
  ['The prompt bar types the line and sends', 'typing, one click'],
  ['A before/after slider sweeps the warm grade in', 'a soft whoosh'],
  ['A magazine cover builds behind the head', 'a shutter, pops, a stamp'],
  ['This video\'s own timeline piles up and folds', 'ticks, a deep whoosh'],
  ['The raw file drops in, BAD TAKE stamps', 'a click, two stamps'],
  ['A counter rolls down, the frame recurses', 'clicks, a ding'],
  ['The moody grade falls like a curtain', 'a low hit'],
  ['A grid of others, the speaker in the middle', 'pops'],
  ['This page, scrolled, then one beat up close', 'a whoosh, clicks'],
  ['A pin drops, the note types in, a reply', 'a pop, typing'],
  ['NEVER stamps behind the head', 'ticks, a drum hit'],
  ['The captions go giant', 'an impact'],
  ['A video card plays its chapters', 'a whoosh, ticks'],
  ['The comment types and posts', 'typing, a ding']
];
var FOCUS = 1;                                   // the beat the push lands on (1 = the first line)
var TILES = null;                               // from capture.py, e.g. { n: 4, h: 1300, height: 4987 }
var LIT = null;                                 // with TILES: the rows to light, [[x, y, w, h], ...] in page px
var FLICKS = [0.3, 0.72];                       // where the two flicks land, as a share of the page's scroll
var T = { flick1: 0.16, flick2: 0.40, zoom: 0.55, out: 0.2 };    // after A (out: before B)
var WK = { zoom: ['plan', -0.2] };              // the push starts on a word (plus an offset); else at A + T.zoom
var LITE = [['plan', 0.22], ['it', 0.06], ['made', 0]];          // one per lit row: [word, offset]

var ID = '{{ID}}', card = document.getElementById(ID + '-card'), page = document.getElementById(ID + '-page');
var thumb = document.getElementById(ID + '-thumb');
var K = 960 / 1080, VIEW = 1000 / K;            // page px -> card px at rest; the viewport's height in page px
var G = { head: 352, beatH: 236, gap: 16 };     // the placeholder's geometry, page px
var OK = ' data-layout-allow-overlap data-layout-allow-occlusion';
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function d2(n) { return (n < 10 ? '0' : '') + n; }
function tc(t) { var m = Math.floor(t / 60), s = t - m * 60; return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1); }
function rnd(k) { var x = Math.sin(k * 12.9898) * 43758.5453; return x - Math.floor(x); }
function at(w, fb) { var t = w && w[0] ? wordAt(w[0], A) : null; return (t !== null && t < B) ? t + w[1] : A + fb; }

// ---- the page: tiles of a real capture, or the placeholder plan
var H, lit = [], n = 0;                          // page height; lit items: { box: [x, y, w, h], us: [underlines] }
if (TILES) {
  H = TILES.height;
  var tiles = '';
  for (var i = 0; i < TILES.n; i++) {
    tiles += '<img src="fx/' + ID + '/page' + i + '.jpg" alt="" style="top:' + i * TILES.h + 'px;height:' +
      Math.min(TILES.h, H - i * TILES.h) + 'px">';
  }
  page.innerHTML = tiles;
  (LIT || []).forEach(function (b) { lit.push({ box: b, us: [] }); });
} else {
  var lines = [], cur = [];
  WORDS.forEach(function (w) { cur.push(w); if (/[.!?]["'”)]*$/.test(w[2])) { lines.push(cur); cur = []; } });
  if (cur.length) lines.push(cur);
  n = lines.length;
  var dur = n ? lines[n - 1][lines[n - 1].length - 1][1] : 0;
  H = G.head + n * (G.beatH + G.gap) - G.gap + 48;
  var h = '<div class="$-pg" style="height:' + H + 'px">';
  h += '<div class="$-eb"' + OK + '>' + esc(PAGE.kicker) + ' · ' + n + ' beats · ' + tc(dur) + '</div>';
  h += '<div class="$-h1"' + OK + '>' + esc(PAGE.title) + '</div><div class="$-how"' + OK + '>' + esc(PAGE.intro) + '</div>';
  h += '<div class="$-strip">';
  lines.forEach(function (ln, k) {
    h += '<i style="flex:' + (ln[ln.length - 1][1] - ln[0][0]).toFixed(2) + ' 1 0"' + (k === FOCUS - 1 ? ' class="$-on"' : '') + '></i>';
  });
  h += '</div><div class="$-scale"' + OK + '><span>0:00</span><span>' + tc(dur) + '</span></div>';
  lines.forEach(function (ln, k) {
    var a = ln[0][0], b = ln[ln.length - 1][1], p = PLAN[k] || [], top = G.head + k * (G.beatH + G.gap);
    h += '<div class="$-bt" style="top:' + top + 'px">';
    for (var f = 0; f < 2; f++) {                // two placeholder frames per beat (a figure, a caption bar)
      h += '<div class="$-fr" style="left:' + (22 + f * 118) + 'px"><i class="$-hd"></i><i class="$-sh"></i>' +
        '<i class="$-cb" style="width:' + Math.round(40 + 44 * rnd(k * 2 + f + 1)) + 'px"></i></div>';
    }
    h += '<div class="$-meta"' + OK + '><b>' + d2(k + 1) + '</b>' + tc(a) + '-' + tc(b) + '<span>' + (b - a).toFixed(1) + 's</span></div>';
    h += '<div class="$-ln"' + OK + '><span class="$-lt">“' + esc(ln.map(function (w) { return w[2]; }).join(' ')) + '”</span></div>';
    if (p[0]) h += '<div class="$-row $-r1"' + OK + '><span class="$-dt">Move</span><span class="$-dd">' + esc(p[0]) + '</span></div>';
    if (p[1]) h += '<div class="$-row $-r2"' + OK + '><span class="$-dt">Sound</span><span class="$-dd">' + esc(p[1]) + '</span></div>';
    h += '<div class="$-nb"' + OK + '>Leave a note</div></div>';
  });
  page.innerHTML = (h + '</div>').replace(/\$/g, ID);
  // the focus beat's line and its two rows are the lit items; their boxes come from the fixed geometry
  var fb = Math.max(0, Math.min(n - 1, FOCUS - 1)), ftop = G.head + fb * (G.beatH + G.gap), beatEl = page.querySelectorAll('.' + ID + '-bt')[fb];
  if (beatEl) {
    lit.push({ box: [318, ftop + 48, 560, 70], el: beatEl.querySelector('.' + ID + '-lt'), us: [] });
    if (beatEl.querySelector('.' + ID + '-r1')) lit.push({ box: [318, ftop + 132, 560, 26], el: beatEl.querySelector('.' + ID + '-r1 .' + ID + '-dd'), us: [] });
    if (beatEl.querySelector('.' + ID + '-r2')) lit.push({ box: [318, ftop + 166, 560, 26], el: beatEl.querySelector('.' + ID + '-r2 .' + ID + '-dd'), us: [] });
  }
}
var bd = document.getElementById(ID + '-bd');
document.getElementById(ID + '-bt').textContent = BAR[0];
bd.textContent = BAR[1] || (n ? 'v1 · ' + n + ' beats' : '');

// ---- the veil (the page dims around the lit rows) and the underlines
var veil = document.createElement('i');
veil.className = ID + '-veil';
veil.style.height = H + 'px';
var holes = [];                                  // a hole per lit row; rows that sit close together share one
lit.map(function (it) { var b = it.box; return [b[0] - 12, b[1] - 8, b[2] + 24, b[3] + 16]; })
  .sort(function (a, b) { return a[1] - b[1]; }).forEach(function (o) {
    var p = holes[holes.length - 1];
    if (p && o[1] <= p[1] + p[3] + 24) {
      var x0 = Math.min(p[0], o[0]), x1 = Math.max(p[0] + p[2], o[0] + o[2]);
      p[3] = Math.max(p[1] + p[3], o[1] + o[3]) - p[1]; p[0] = x0; p[2] = x1 - x0;
    } else holes.push(o);
  });
veil.style.clipPath = "path(evenodd, 'M0 0H1080V" + H + "H0Z" + holes.map(function (o) {
  return ' M' + o[0] + ' ' + o[1] + 'H' + (o[0] + o[2]) + 'V' + (o[1] + o[3]) + 'H' + o[0] + 'Z';
}).join('') + "')";
page.appendChild(veil);
lit.forEach(function (it) {                       // two underlines per item (a line can wrap), placed once fonts are in
  for (var k = 0; k < 2; k++) {
    var u = document.createElement('i');
    u.className = ID + '-u';
    u.style.left = it.box[0] + 'px'; u.style.top = (it.box[1] + it.box[3] + 2) + 'px';
    u.style.width = (k || it.el ? 0 : it.box[2]) + 'px';
    page.appendChild(u);
    it.us.push(u);
  }
});
function measure() {                              // underline each rendered line of text at its own width
  var pr = page.getBoundingClientRect(), s = pr.width / 1080 || 1;
  lit.forEach(function (it) {
    if (!it.el) return;
    var rs = it.el.getClientRects();
    it.us.forEach(function (u, k) {
      var r = rs[k];
      if (!r) { u.style.width = '0px'; return; }
      u.style.left = ((r.left - pr.left) / s).toFixed(1) + 'px';
      u.style.top = ((r.bottom - pr.top) / s + 1).toFixed(1) + 'px';
      u.style.width = (r.width / s).toFixed(1) + 'px';
    });
  });
}
if (!TILES) {
  measure();
  var fs = ['400 27px ', '400 18px '].map(function (w, k) {
    var cs = getComputedStyle(page.querySelector('.' + ID + (k ? '-dd' : '-ln')) || page);
    return cs.fontStyle + ' ' + w + cs.fontFamily;
  });
  Promise.all(fs.map(function (f) { return document.fonts.load(f); })).then(measure, measure);
}

// ---- the moves
var S1 = FLICKS[0] * Math.max(0, H - VIEW), S2 = FLICKS[1] * Math.max(0, H - VIEW);
function thumbY(s) { return 4 + s / Math.max(1, H - VIEW) * (1000 - 126 - 8); }
var bx0 = 1e9, by0 = 1e9, bx1 = -1e9, by1 = -1e9;
holes.forEach(function (o) { bx0 = Math.min(bx0, o[0]); by0 = Math.min(by0, o[1]); bx1 = Math.max(bx1, o[0] + o[2]); by1 = Math.max(by1, o[1] + o[3]); });
if (!holes.length) { bx0 = 60; by0 = 0; bx1 = 1020; by1 = 600; }
var Z = Math.min(2.2, 900 / (bx1 - bx0), 860 / (by1 - by0)), cx = (bx0 + bx1) / 2, cy = (by0 + by1) / 2;
var zx = Math.min(0, Math.max(960 - Z * 1080, 480 - Z * cx)), zy = Math.min(0, Math.max(1000 - Z * H, 500 - Z * cy));   // the page always fills the view
var tF1 = A + T.flick1, tF2 = A + T.flick2, tZ = at(WK.zoom, T.zoom), tOut = B - T.out;

gsap.set(card, { y: 1700 });
gsap.set(page, { x: 0, y: 0, scale: K });
gsap.set(thumb, { y: thumbY(0) });
gsap.set(veil, { opacity: 0 });
lit.forEach(function (it) { gsap.set(it.us, { scaleX: 0 }); });

// in
tl.fromTo(card, { y: 1700 }, { y: 0, duration: 0.4, ease: 'expo.out', immediateRender: false }, q(A));
// two flicks (power3.out: fast off the finger, settling), the scrollbar riding along
tl.fromTo(page, { y: 0 }, { y: -S1 * K, duration: 0.32, ease: 'power3.out', immediateRender: false }, q(tF1));
tl.fromTo(thumb, { y: thumbY(0) }, { y: thumbY(S1), duration: 0.32, ease: 'power3.out', immediateRender: false }, q(tF1));
tl.fromTo(page, { y: -S1 * K }, { y: -S2 * K, duration: 0.34, ease: 'power3.out', immediateRender: false }, q(tF2));
tl.fromTo(thumb, { y: thumbY(S1) }, { y: thumbY(S2), duration: 0.34, ease: 'power3.out', immediateRender: false }, q(tF2));
// the push: back to the focus beat and in, one move
tl.to(thumb, { opacity: 0, duration: 0.15, ease: 'power1.out' }, q(tZ));
tl.fromTo(page, { x: 0, y: -S2 * K, scale: K }, { x: zx, y: zy, scale: Z, duration: 0.44,
  ease: 'expo.inOut', immediateRender: false }, q(tZ));
// the rows light: the page dims around them, then an underline per row on its word
var tL = lit.map(function (it, k) { return at(LITE[k], T.zoom + 0.34 + 0.12 * k); });
if (lit.length) tl.fromTo(veil, { opacity: 0 }, { opacity: 1, duration: 0.2, ease: 'power2.out', immediateRender: false }, q(Math.min(tL[0], tZ + 0.4) - 0.06));
lit.forEach(function (it, k) {
  it.us.forEach(function (u, j) {
    tl.fromTo(u, { scaleX: 0 }, { scaleX: 1, duration: 0.22, ease: 'power3.out', immediateRender: false }, q(tL[k] + 0.06 * j));
  });
});
// out
tl.to(card, { y: 1700, duration: T.out, ease: 'power3.in' }, q(tOut));
