// kinetic-hook (layer: behind, under the speaker's cutout). The hook, built on the words:
//   frame 0   line one (OPEN) in the display face is already up (the thumbnail) and settles from 1.04x
//   stamp     the creator's dark ground cuts in and line two (STAMP) stamps letter by letter from 1.38x, one letter
//             every 2 frames, the last letter on its word; the speaker's head breaks it
//   l1        line one pushes up out of its mask as L1 pushes in (expo.out, together); line two's letters drop away
//   l2        L2 rises letter by letter in its mask; a frame timecode of the video's own time runs under it
//   l3        L1 pushes out, L3 in
//   l4        L2 drops away letter by letter, L4 tracks in from wide (a horizontal scale, never letter-spacing)
//   drop      optional payoff: everything cuts away, DROP[0] slams down to size, DROP[1] lands in the accent on its
//             word and the line reflows to make room
// Pair it with kinetic-hook-front (layer top, same OPEN) for the opening frames: it carries line one over the
// speaker, split light/dark against the picture; end its window on the frame the ground cuts in (the first
// stamped letter: in the lab frame 11, 0.37s). Needs a CUT_WINDOWS entry over this effect's whole window.
// Supply: the words below and the spoken word each beat lands on. Nothing else: no assets, every colour and face
// comes from the style pack, and every line is fitted to the frame width with the pack's faces (fx.html sizes are
// maxima, so a longer word just sets smaller).
// Change only these constants:
var OPEN = 'I DIDN\u2019T';                 // line one, on screen from frame 0
var STAMP = 'EDIT';                         // line two, stamped letter by letter
var L1 = 'A SINGLE', L2 = 'SECOND', L3 = 'OF THIS', L4 = 'VIDEO.';
var DROP = ['', ''];                        // the payoff after the build, e.g. ['IT', 'DID.']; ['', ''] = none
// the spoken word each beat lands on (words.json, searched in this order from A); '' = use the fallback
var KEY = { stamp: 'edit', l1: 'a', l2: 'second', l3: 'of', l4: 'video', d1: '', d2: '' };
// fallbacks when a word isn't found, in seconds after A
var AT = { stamp: 0.51, l1: 0.77, l2: 1.28, l3: 1.53, l4: 2.04, d1: 2.10, d2: 2.30 };
// how far ahead of its word each move starts (s)
var LEAD = { stamp: 0.04, push: 0.02, rise: 0.04, l2out: 0.20, l4: 0.067 };
var FIELD = 'stamp';                        // the dark ground cuts in with the first stamped letter; a number = s after A (0 = frame 0)
var STEP = 2 / 30;                          // stamp: one letter every two frames
var PUSH = 0.3;                             // a line push through its mask

// ---- words in, fitted to the frame with the pack's faces
function $(s) { return document.querySelector(s); }
function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
function letters(host, text, cls) {
  host.textContent = '';
  Array.from(text).forEach(function (c) {
    var s = document.createElement('span');
    s.className = cls;
    s.textContent = c === ' ' ? '\u00a0' : c;
    host.appendChild(s);
  });
}
$('#{{ID}}-o1 .{{ID}}-t').textContent = OPEN;
letters($('#{{ID}}-o2 .{{ID}}-t'), STAMP, '{{ID}}-ec');
$('#{{ID}}-l1 .{{ID}}-t').textContent = L1;
letters($('#{{ID}}-l2 .{{ID}}-t'), L2, '{{ID}}-ch');
$('#{{ID}}-l3 .{{ID}}-t').textContent = L3;
$('#{{ID}}-l4 .{{ID}}-t').textContent = L4;
$('#{{ID}}-d1 .{{ID}}-dw').textContent = DROP[0];
$('#{{ID}}-d2 .{{ID}}-dw').textContent = DROP[0];
$('#{{ID}}-d2 .{{ID}}-dp').textContent = DROP[1];
// the lines cross and sit behind the head on purpose: tell the layout audit (it reads the text elements themselves)
var MARK = ' data-layout-allow-overlap data-layout-allow-occlusion';
$$('#{{ID}} *').forEach(function (e) {
  if (Array.prototype.some.call(e.childNodes, function (n) { return n.nodeType === 3 && n.nodeValue.trim(); })) {
    e.setAttribute('data-layout-allow-overlap', '');
    e.setAttribute('data-layout-allow-occlusion', '');
  }
});
$('#{{ID}}-tc').setAttribute('data-layout-allow-overlap', '');
$('#{{ID}}-tc').setAttribute('data-layout-allow-occlusion', '');

// each box keeps its fx.html size unless its text is wider than it may run: 920px for the centred display lines,
// 968px for the sans lines (56px margins)
var FIT = [['#{{ID}}-o1', '#{{ID}}-o1 .{{ID}}-t', 920], ['#{{ID}}-o2', '#{{ID}}-o2 .{{ID}}-t', 920],
  ['#{{ID}}-l1', '#{{ID}}-l1 .{{ID}}-t', 968], ['#{{ID}}-l2', '#{{ID}}-l2 .{{ID}}-t', 968], ['#{{ID}}-l3', '#{{ID}}-l3 .{{ID}}-t', 968],
  ['#{{ID}}-l4', '#{{ID}}-l4 .{{ID}}-t', 968], ['#{{ID}}-d', '#{{ID}}-d2 .{{ID}}-t', 920]];
function fit() {
  FIT.forEach(function (f) {
    var box = $(f[0]), txt = $(f[1]);
    if (!box.dataset.max) box.dataset.max = parseFloat(getComputedStyle(box).fontSize);
    var max = +box.dataset.max;
    box.style.fontSize = max + 'px';
    var w = txt.offsetWidth;
    if (w > f[2]) box.style.fontSize = (max * f[2] / w).toFixed(2) + 'px';
  });
}
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
fit();                                      // now, and again once the pack's faces have loaded (before any frame renders)
if (document.fonts && document.fonts.load) {
  var all = [OPEN, STAMP, L1, L2, L3, L4, DROP.join(' '), '0123456789:'].join(' ');
  Promise.all([tok('--display-style') + ' ' + tok('--display-weight') + ' 100px ' + tok('--font-display'),
    '800 100px ' + tok('--font-text'), '500 44px ' + tok('--font-mono')].map(function (f) {
    return document.fonts.load(f, all).catch(function () {});
  })).then(fit, fit);
  document.fonts.ready.then(fit);
}

// ---- beat times: each on its word, searched in order (a word missing from words.json falls back to AT)
var t = {}, prev = A;
['stamp', 'l1', 'l2', 'l3', 'l4', 'd1', 'd2'].forEach(function (k) {
  var w = KEY[k] ? wordAt(KEY[k], prev) : null;
  t[k] = (w === null || w >= B) ? A + AT[k] : w;
  prev = Math.max(prev, t[k]);
});
var n = Array.from(STAMP).length;
var tStamp = Math.max(A + 2 / 30, t.stamp - LEAD.stamp - (n - 1) * STEP);
var tField = FIELD === 'stamp' ? tStamp : A + FIELD;

// ---- initial states (sets at build time: a set at time 0 does not render on a seek to 0)
if (q(A) <= 0) gsap.set('#{{ID}}', { opacity: 1 });
if (q(tField) > q(A)) { gsap.set('#{{ID}}-field', { opacity: 0 }); tl.set('#{{ID}}-field', { opacity: 1 }, q(tField)); }
gsap.set(['#{{ID}}-l1 .{{ID}}-in', '#{{ID}}-l3 .{{ID}}-in'], { yPercent: 110 });
gsap.set('#{{ID}}-l2 .{{ID}}-ch', { yPercent: 110 });
gsap.set('#{{ID}}-l4 .{{ID}}-in', { opacity: 0, transformOrigin: '56px 50%' });
gsap.set('#{{ID}}-tc', { opacity: 0 });
gsap.set(['#{{ID}}-d1', '#{{ID}}-d2'], { opacity: 0 });
gsap.set('#{{ID}}-o2 .{{ID}}-ec', { opacity: 0 });

// ---- line one settles from a hair large; line two stamps in (from 1.38x, two frames a letter)
gsap.set('#{{ID}}-o1in', { transformOrigin: '50% 80%' });
tl.fromTo('#{{ID}}-o1in', { scale: 1.04 }, { scale: 1, duration: 0.4, ease: 'power2.out', immediateRender: q(A) <= 0 }, q(A));
tl.fromTo('#{{ID}}-o2 .{{ID}}-ec', { opacity: 0, scale: 1.38, yPercent: -6 },
  { opacity: 1, scale: 1, yPercent: 0, duration: 0.2, ease: 'power4.out', stagger: STEP, immediateRender: false }, q(tStamp));

// ---- L1: line one pushes up and out as L1 pushes in; line two's letters drop away behind the head
var tP1 = t.l1 - LEAD.push;
tl.fromTo('#{{ID}}-o1in', { yPercent: 0 }, { yPercent: -110, duration: PUSH, ease: 'expo.out', immediateRender: false }, q(tP1));
tl.fromTo('#{{ID}}-l1 .{{ID}}-in', { yPercent: 110 }, { yPercent: 0, duration: PUSH, ease: 'expo.out', immediateRender: false }, q(tP1));
tl.fromTo('#{{ID}}-o2 .{{ID}}-ec', { yPercent: 0, opacity: 1 },
  { yPercent: 80, opacity: 0, duration: 0.16, ease: 'power2.in', stagger: 0.02, immediateRender: false }, q(tP1 - 0.02));

// ---- L2: letters rise in their mask one after another; the timecode comes in under them
tl.fromTo('#{{ID}}-l2 .{{ID}}-ch', { yPercent: 110 },
  { yPercent: 0, duration: 0.34, ease: 'expo.out', stagger: 0.03, immediateRender: false }, q(t.l2 - LEAD.rise));
tl.fromTo('#{{ID}}-tc', { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.22, ease: 'power3.out', immediateRender: false }, q(t.l2));

// ---- L3: L1 pushes out, L3 in
var tP3 = t.l3 - LEAD.push;
tl.fromTo('#{{ID}}-l1 .{{ID}}-in', { yPercent: 0 }, { yPercent: -110, duration: PUSH, ease: 'expo.out', immediateRender: false }, q(tP3));
tl.fromTo('#{{ID}}-l3 .{{ID}}-in', { yPercent: 110 }, { yPercent: 0, duration: PUSH, ease: 'expo.out', immediateRender: false }, q(tP3));

// ---- L4: L2 drops away letter by letter, L4 tracks in from wide
tl.fromTo('#{{ID}}-l2 .{{ID}}-ch', { yPercent: 0 },
  { yPercent: -110, duration: 0.15, ease: 'power3.in', stagger: 0.012, immediateRender: false }, q(t.l4 - LEAD.l2out));
tl.fromTo('#{{ID}}-l4 .{{ID}}-in', { opacity: 0, scaleX: 1.45 },
  { opacity: 1, scaleX: 1, duration: 0.24, ease: 'expo.out', immediateRender: false }, q(t.l4 - LEAD.l4));

// ---- the timecode: the video's own time, one set per frame across the window
function pad(v) { return (v < 10 ? '0' : '') + v; }
function tc(f) {
  var s = Math.floor(f / 30);
  return '<span class="{{ID}}-tcd"' + MARK + '>00:' + pad(Math.floor(s / 60)) + ':</span>' + pad(s % 60) +
    '<span class="{{ID}}-tcd"' + MARK + '>:</span><span class="{{ID}}-tcf"' + MARK + '>' + pad(f % 30) + '</span>';
}
var f0 = Math.round(A * 30), f1 = Math.round(B * 30);
gsap.set('#{{ID}}-tc', { innerHTML: tc(f0) });
for (var f = f0 + 1; f <= f1; f++) tl.set('#{{ID}}-tc', { innerHTML: tc(f) }, q(f / 30));

// ---- the payoff: the build cuts away, word one slams down to size alone, word two lands in the accent
if (DROP[0]) {
  tl.set('#{{ID}}-txt', { opacity: 0 }, q(t.d1));
  tl.set('#{{ID}}-d1', { opacity: 1 }, q(t.d1));
  tl.fromTo('#{{ID}}-d1 .{{ID}}-dw', { scale: 1.6 }, { scale: 1, duration: 0.2, ease: 'power4.out', immediateRender: false }, q(t.d1));
  if (DROP[1]) {
    tl.set('#{{ID}}-d1', { opacity: 0 }, q(t.d2));
    tl.set('#{{ID}}-d2', { opacity: 1 }, q(t.d2));
    tl.fromTo('#{{ID}}-d2 .{{ID}}-dp', { scale: 1.5 }, { scale: 1, duration: 0.18, ease: 'power4.out', immediateRender: false }, q(t.d2));
  }
}
