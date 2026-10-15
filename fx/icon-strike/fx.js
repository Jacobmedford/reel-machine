// icon-strike (layer: top), for "no X, no Y, nothing". App icons pop in above the head on their names, a hand-drawn
// stroke strikes through each one (it flinches and greys out), and on the last word they hop and drop out of frame
// with gravity while one word rises where they were.
// Supply: nothing for the placeholders: generic tiles drawn from tokens (glyph 'timeline', 'presets' or 'grid').
// When the speaker names real apps, fetch their icons into this folder with icons.py
// (PY icons.py <this folder> "App One" "App Two") and set img on each icon. Fetched icons belong to their owners:
// they live in your project's copy of this effect, never in the library.
// Change: ICONS, FALL_ON, WORD and INK below. A key finds the first matching spoken word at or after the previous
// beat (wordAt); when it is missing, the fallback in T (seconds after A) is used.

var ICONS = [                                   // up to three: the word it pops on, its name, a glyph or an image
  { on: 'timeline', label: 'timeline', glyph: 'timeline', img: '' },
  { on: 'presets', label: 'presets', glyph: 'presets', img: '' }
];
var FALL_ON = 'nothing';                        // the icons drop on this word
var WORD = 'nothing.';                          // the word that rises where they were; '' = none
var INK = 'dark';                               // the names and the word: 'light' over dark footage, 'dark' over bright
var T = { pop: 0.40, gap: 0.70, strike: 0.20, fall: 1.46, rise: 0.18, out: 0.08 };

var R = '#{{ID}} ';
function word(w, after, fallback) { var t = w ? wordAt(w, after) : null; return t === null || t >= B ? fallback : t; }
var GLYPHS = {
  timeline: '<svg viewBox="0 0 220 220"><rect class="k1" x="40" y="64" width="72" height="24" rx="6"/><rect class="k2" x="120" y="64" width="60" height="24" rx="6"/>' +
            '<rect class="k2" x="40" y="98" width="38" height="24" rx="6"/><rect class="k1" x="86" y="98" width="94" height="24" rx="6"/>' +
            '<rect class="k1" x="40" y="132" width="108" height="24" rx="6"/><rect class="k2" x="156" y="132" width="24" height="24" rx="6"/>' +
            '<path class="ph" d="M132 54 V172"/><path class="phh" d="M121 44 H143 L132 58 Z"/></svg>',
  presets: '<svg viewBox="0 0 220 220"><path class="tr" d="M68 56 V164 M110 56 V164 M152 56 V164"/>' +
           '<path class="fl" d="M68 126 V164 M110 84 V164 M152 112 V164"/>' +
           '<circle class="kn" cx="68" cy="126" r="16"/><circle class="kn ka" cx="110" cy="84" r="16"/><circle class="kn" cx="152" cy="112" r="16"/></svg>',
  grid: '<svg viewBox="0 0 220 220"><rect class="k1" x="50" y="50" width="54" height="54" rx="12"/><rect class="k2" x="116" y="50" width="54" height="54" rx="12"/>' +
        '<rect class="k2" x="50" y="116" width="54" height="54" rx="12"/><rect class="k1" x="116" y="116" width="54" height="54" rx="12"/></svg>'
};
// two hand-drawn strokes, one falling and one rising, alternated
var STROKES = ['M -6 58 C 40 72, 92 98, 132 124 S 200 166, 228 170', 'M -8 162 C 44 140, 86 118, 120 96 S 190 52, 228 44'];
var LEN = 420;

// build the icons once, centred above the head
(function () {
  var box = document.querySelector(R + '.is-apps');
  if (!box || box.childNodes.length) return;
  var n = ICONS.length, x0 = 540 - (n * 220 + (n - 1) * 48) / 2;
  ICONS.forEach(function (ic, i) {
    var g = GLYPHS[ic.glyph] ? ic.glyph : 'grid', d = STROKES[i % 2];
    var a = document.createElement('div');
    a.className = 'is-app';
    a.setAttribute('data-layout-allow-overlap', '');          // they fall through the captions on purpose
    a.style.left = (x0 + i * 268) + 'px';
    a.innerHTML = '<div class="is-tile ' + (ic.img ? '' : 'is-g-' + g) + '">' +
      (ic.img ? '<img src="fx/{{ID}}/' + ic.img + '" alt="">' : GLYPHS[g]) + '</div>' +
      '<svg class="is-strike" viewBox="0 0 220 220"><path class="is-under" d="' + d + '"/><path class="is-ink-stroke" d="' + d + '"/></svg>' +
      '<div class="is-name" data-layout-allow-overlap></div>';
    a.querySelector('.is-name').textContent = ic.label;
    box.appendChild(a);
  });
  document.querySelector(R + '.is-word span').textContent = WORD;
  box.classList.add(INK === 'light' ? 'is-light' : 'is-dark');
  document.querySelector(R + '.is-word').classList.add(INK === 'light' ? 'is-light' : 'is-dark');
})();

var apps = document.querySelectorAll(R + '.is-app');
gsap.set(apps, { opacity: 0 });
gsap.set(R + '.is-strike path', { strokeDasharray: LEN + ' ' + (LEN + 40), strokeDashoffset: LEN, opacity: 0 });
gsap.set(R + '.is-word span', { yPercent: 105 });

// times: each icon pops on its word, the drop comes on FALL_ON, and every strike lands before the drop
var POPS = [], prev = A;
ICONS.forEach(function (ic, i) { var t = word(ic.on, prev, A + T.pop + i * T.gap); POPS.push(t); prev = t + 0.01; });
var FALL = word(FALL_ON, prev, A + T.fall), RISE = FALL + T.rise;

// pop on the name: up from below with a little turn, the name after it
function pop(el, t, r0) {
  tl.fromTo(el, { opacity: 0, scale: 0.45, y: 34, rotation: r0 },
    { opacity: 1, scale: 1, y: 0, rotation: 0, duration: 0.34, ease: 'back.out(1.7)', immediateRender: false }, q(t));
  tl.fromTo(el.querySelector('.is-name'), { opacity: 0, y: 8 },
    { opacity: 1, y: 0, duration: 0.2, ease: 'power3.out', immediateRender: false }, q(t + 0.1));
}
// strike: the stroke draws through in 0.2s, the icon flinches as it is hit and loses its colour
function strike(el, t) {
  var under = el.querySelector('.is-under'), ink = el.querySelector('.is-ink-stroke'), tile = el.querySelector('.is-tile');
  tl.set([under, ink], { opacity: 1 }, q(t));
  tl.to(under, { strokeDashoffset: 0, duration: 0.2, ease: 'power2.inOut' }, q(t));
  tl.to(ink, { strokeDashoffset: 0, duration: 0.2, ease: 'power2.inOut' }, q(t + 0.02));
  tl.to(tile, { scale: 0.94, duration: 0.08, ease: 'power2.out' }, q(t + 0.08));
  tl.to(tile, { scale: 1, duration: 0.22, ease: 'back.out(2)' }, q(t + 0.16));
  tl.fromTo(tile, { filter: 'saturate(1) brightness(1)' }, { filter: 'saturate(0.3) brightness(0.86)', duration: 0.2, ease: 'power2.out', immediateRender: false }, q(t + 0.1));
}
// the drop: a little hop, then gravity (power2.in), each with its own spin
function fall(el, t, rot, dx) {
  tl.to(el, { y: -26, duration: 0.08, ease: 'power2.out' }, q(t));
  tl.to(el, { y: 1760, x: dx, rotation: rot, duration: 0.38, ease: 'power2.in' }, q(t + 0.08));
}
for (var i = 0; i < apps.length; i++) {
  pop(apps[i], POPS[i], i % 2 ? 8 : -8);
  strike(apps[i], Math.max(POPS[i] + 0.06, Math.min(POPS[i] + T.strike, FALL - 0.2)));
  fall(apps[i], FALL + i * 0.04, [-24, 19, -14][i % 3], [-40, 30, -20][i % 3]);
}

// the word rises where they were, and is gone at B
if (WORD) {
  tl.to(R + '.is-word span', { yPercent: 0, duration: 0.24, ease: 'power3.out' }, q(RISE));
  tl.to(R + '.is-word span', { opacity: 0, duration: T.out, ease: 'none' }, q(B - T.out));
}
