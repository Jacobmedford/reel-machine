// word-stamp (layer: behind, under the speaker's cutout). One emphatic word gets the stamp:
//   word      WORD stamps in letter by letter from 1.38x, one letter every 2 frames, the first letter on its word,
//             huge, in the display face, the speaker's head breaking it; once built it keeps growing a hair
//             (1 to 1.035) until the hard out, so it never sits still
//   split     light type, turning to ink wherever it crosses a light part of the picture (mask.png)
//   line      optional: SMALL sets above it word group by word group on its words, then a stroke in the negative
//             colour strikes it through and the line dims
// Reach for it on never, huge, always, zero. Needs a CUT_WINDOWS entry over its window; out hard at the window end.
// Supply: the word, its line, the spoken words they land on, and the light/dark mask for your shot:
//   PY fx/<id>/mkmask.py <project> [<id>]
// It reads this effect's window from edit.py, the room behind the speaker from public/clean.mp4 (the speaker is
// left out with public/subject.webm) and writes fx/<id>/mask.png. The mask.png in the library is the lab's
// stand-in: rerun mkmask.py on your footage, or set SPLIT = false to keep the word light everywhere.
// Change only these constants:
var WORD = 'NEVER';                         // the stamped word
var SMALL = [['open an', 'open'], ['editing', 'editing'], ['app', 'app']];   // [text, the word it lands on]; [] = no line
var KEY = 'never';                          // the spoken word the stamp lands on
var AT = { word: 0.22, small: [0.50, 1.00, 1.25] };   // fallbacks (s after A) when a word isn't found
var LEAD = 0.03;                            // the stamp starts this far ahead of its word
var STRIKE = 0.06;                          // the stroke starts this long after the last small word
var CENTER_X = 540;                         // the speaker's head on the 1080 frame: the word centres on it
var Y = 0;                                  // px: move the word down (+) or up (-) so the head breaks only its foot
var SPLIT = true;                           // false: light type only (no mask.png needed)
var STEP = 2 / 30;                          // one letter every two frames
var GROW = 1.035;                           // the slow grow once the word is built

function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
if (!SPLIT) { var dk = document.getElementById('{{ID}}-dk'); dk.parentNode.removeChild(dk); }
var copies = SPLIT ? ['#{{ID}}-lt', '#{{ID}}-dk'] : ['#{{ID}}-lt'];

// ---- the words into both copies
$$('#{{ID}} .{{ID}}-t').forEach(function (host) {
  host.textContent = '';
  Array.from(WORD).forEach(function (c) {
    var s = document.createElement('span');
    s.className = '{{ID}}-ch';
    s.textContent = c === ' ' ? '\u00a0' : c;
    host.appendChild(s);
  });
});
$$('#{{ID}} .{{ID}}-sw').forEach(function (host) {
  host.textContent = '';
  SMALL.forEach(function (g, i) {
    if (i) host.appendChild(document.createTextNode(' '));
    var s = document.createElement('span');
    s.className = '{{ID}}-g {{ID}}-g' + i;
    s.textContent = g[0];
    host.appendChild(s);
  });
});
if (!SMALL.length) $$('#{{ID}} .{{ID}}-srow').forEach(function (e) { e.style.display = 'none'; });
// the two copies overlap and sit behind the head on purpose: tell the layout audit (it reads the text elements)
$$('#{{ID}} *').forEach(function (e) {
  if (Array.prototype.some.call(e.childNodes, function (n) { return n.nodeType === 3 && n.nodeValue.trim(); })) {
    e.setAttribute('data-layout-allow-overlap', '');
    e.setAttribute('data-layout-allow-occlusion', '');
  }
});

// ---- the word keeps its fx.html size unless it is wider than 960px with the pack's display face (1000px grown)
function fit() {
  $$('#{{ID}} .{{ID}}-w').forEach(function (box) {
    if (!box.dataset.max) box.dataset.max = parseFloat(getComputedStyle(box).fontSize);
    var max = +box.dataset.max;
    box.style.fontSize = max + 'px';
    var w = box.querySelector('.{{ID}}-t').offsetWidth;
    if (w > 960) box.style.fontSize = (max * 960 / w).toFixed(2) + 'px';
  });
}
fit();
if (document.fonts && document.fonts.load) {
  Promise.all([tok('--display-style') + ' ' + tok('--display-weight') + ' 100px ' + tok('--font-display'),
    tok('--text-weight') + ' 46px ' + tok('--font-text')].map(function (f) {
    return document.fonts.load(f, WORD + ' ' + SMALL.map(function (g) { return g[0]; }).join(' ')).catch(function () {});
  })).then(fit, fit);
  document.fonts.ready.then(fit);
}

// ---- beat times, each on its word (searched in order from A; a word missing from words.json falls back to AT)
function find(word, after, fallback) {
  var w = word ? wordAt(word, after) : null;
  return (w === null || w >= B) ? A + fallback : w;
}
var tWord = find(KEY, A, AT.word);
var tStamp = Math.max(A, tWord - LEAD);
var tSmall = [], prev = tWord;
SMALL.forEach(function (g, i) {
  prev = find(g[1], prev, AT.small[i] !== undefined ? AT.small[i] : AT.word + 0.3 * (i + 1));
  tSmall.push(prev);
});
var tBuilt = tStamp + (Array.from(WORD).length - 1) * STEP + 0.2;

// ---- build: hidden until their beats; centred on the head
if (q(A) <= 0) gsap.set('#{{ID}}', { opacity: 1 });
gsap.set('#{{ID}} .{{ID}}-stack', { x: CENTER_X - 540, y: Y });
gsap.set('#{{ID}} .{{ID}}-ch', { opacity: 0 });
gsap.set('#{{ID}} .{{ID}}-g', { opacity: 0 });
gsap.set('#{{ID}} .{{ID}}-x', { scaleX: 0 });
gsap.set('#{{ID}} .{{ID}}-w', { transformOrigin: '50% 85%' });

// the stamp: both colour copies together, one tween per copy so each staggers its own letters
copies.forEach(function (c) {
  tl.fromTo(c + ' .{{ID}}-ch', { opacity: 0, scale: 1.38, yPercent: -6 },
    { opacity: 1, scale: 1, yPercent: 0, duration: 0.2, ease: 'power4.out', stagger: STEP, immediateRender: false }, q(tStamp));
});
// once built it keeps growing a hair until the hard out
if (B - tBuilt > 0.1) {
  tl.fromTo('#{{ID}} .{{ID}}-w', { scale: 1 }, { scale: GROW, duration: B - tBuilt, ease: 'none', immediateRender: false }, q(tBuilt));
}

// the small line: each group rises in on its word, then the stroke strikes it through and the line dims
SMALL.forEach(function (g, i) {
  tl.fromTo('#{{ID}} .{{ID}}-g' + i, { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.16, ease: 'power3.out', immediateRender: false }, q(tSmall[i]));
});
if (SMALL.length) {
  var tStrike = tSmall[tSmall.length - 1] + STRIKE;
  tl.fromTo('#{{ID}} .{{ID}}-x', { scaleX: 0 }, { scaleX: 1, duration: 0.22, ease: 'power3.inOut', immediateRender: false }, q(tStrike));
  tl.fromTo('#{{ID}} .{{ID}}-sw', { opacity: 1 }, { opacity: 0.6, duration: 0.2, ease: 'none', immediateRender: false }, q(tStrike + 0.1));
}
