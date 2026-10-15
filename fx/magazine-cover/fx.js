// magazine-cover (layer: behind): a full magazine cover set behind the speaker, built on the words.
//   A            the frame draws from two corners, the masthead drops in letter by letter (the head breaks it)
//   A + date     the dateline wipes on
//   "like"       the barcode prints, left to right; a beat later the left coverlines rise out of their line masks
//   "magazine"   the right coverlines rise
//   "cover"      the sticker slaps on
//   B - out      everything clears (set T.out to 0 to hold it to B, when B is a picture cut with a transition)
// The cover's type is built twice, a light copy and an ink copy, each masked to its part of the picture (mask-light.png,
// mask-ink.png from mask.py), so every letter, line and rule splits light/dark against the footage it crosses.
//
// Supply: MAST, DATELINE, LINES, BARCODE and STICKER (true words: the video's own claims), then LAYOUT, measured on a
// still of the shot (ffmpeg -ss <t> -i public/clean.mp4 -frames:v 1 still.jpg): set mastBase about 60 px below the
// top of the head so the head breaks the masthead, and keep the coverline blocks beside the head. Run mask.py in
// your copy (PY fx/<id>/mask.py) to rebuild the masks from THIS shot, or set INK to false (light type only). The
// window needs a CUT_WINDOWS entry (layer behind). Change the constants below, nothing else.

var MAST = 'THE EDIT';                                         // the masthead, fitted to LAYOUT.mastWidth
var DATELINE = 'No. 01 · October 2026 · One sentence, one edit';
var LINES = [['One sentence', 'Whole video,', 'edited.'],      // left block: kicker, then its lines
             ['Zero editing', 'No timeline.', 'No presets.']];  // right block
var BARCODE = ['No. 01', 'Oct 2026'];
var STICKER = ['100%', 'AI', 'edited'];                        // small, big (display face), small
var INK = true;                                                // false: light type only, no masks needed
var LAYOUT = {
  frame: [40, 236, 1040, 1284],                // the frame rules: left, top, right, bottom
  mastBase: 560, mastWidth: 920, mastMax: 240, // masthead baseline (y), the width it fits to, its largest size
  date: 340,                                   // dateline top
  left: [72, 640], right: [1008, 640],         // coverline blocks: left block's left edge / right block's right edge, top
  barcode: [64, 1010], sticker: [862, 980]     // left, top
};
// each beat lands on a word (plus an offset in seconds); with no such word in the window, at A + its fallback in T
var WK = { barcode: ['like', 0], left: ['like', 0.26], right: ['magazine', 0], sticker: ['cover', 0] };
var T = { step: 0.05, date: 0.20, barcode: 0.47, left: 0.73, right: 0.99, sticker: 1.24, out: 0.18 };

var ID = '{{ID}}', root = document.getElementById(ID);
function sel(s) { return s.split(',').map(function (p) { return '#' + ID + ' ' + p.trim().replace(/\$/g, ID); }).join(', '); }
function beat(k) { var w = WK[k] ? wordAt(WK[k][0], A) : null; return (w !== null && w < B) ? w + WK[k][1] : A + T[k]; }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// ---- build the cover's type (one copy), then the ink copy
var F = LAYOUT.frame, h = '', nl = 0, OK = ' data-layout-allow-overlap data-layout-allow-occlusion';   // two copies by design
h += '<i class="$-rule $-rt" style="left:' + F[0] + 'px;top:' + F[1] + 'px;width:' + (F[2] - F[0]) + 'px;height:3px"></i>';
h += '<i class="$-rule $-rb" style="left:' + F[0] + 'px;top:' + (F[3] - 3) + 'px;width:' + (F[2] - F[0]) + 'px;height:3px"></i>';
h += '<i class="$-rule $-rl" style="left:' + F[0] + 'px;top:' + F[1] + 'px;width:3px;height:' + (F[3] - F[1]) + 'px"></i>';
h += '<i class="$-rule $-rr" style="left:' + (F[2] - 3) + 'px;top:' + F[1] + 'px;width:3px;height:' + (F[3] - F[1]) + 'px"></i>';
h += '<div class="$-dl"' + OK + ' style="top:' + LAYOUT.date + 'px"><span class="$-dlt"' + OK + '>' + esc(DATELINE) + '</span></div>';
h += '<div class="$-mh"' + OK + '><span class="$-mhi"' + OK + '>';
for (var i = 0; i < MAST.length; i++) {
  if (MAST[i] === ' ') { h += '<span class="$-sp">&nbsp;</span>'; continue; }
  h += '<span class="$-c $-c' + nl + '"' + OK + '>' + esc(MAST[i]) + '</span>';
  nl++;
}
h += '<i class="$-bl"></i></span></div>';
LINES.forEach(function (ls, b) {
  var x = b === 0 ? LAYOUT.left[0] : LAYOUT.right[0] - 300, y = b === 0 ? LAYOUT.left[1] : LAYOUT.right[1];
  h += '<div class="$-sky $-l' + b + (b ? ' $-r' : '') + '"' + OK + ' style="left:' + x + 'px;top:' + y + 'px">';
  ls.forEach(function (s, j) {
    h += '<div class="$-m $-m' + j + '"' + OK + ' data-layout-allow-overflow><span class="' + (j ? '$-t' : '$-k') + '"' + OK +
      '>' + esc(s) + '</span></div>';
  });
  h += '</div>';
});
h = h.replace(/\$/g, ID);
document.getElementById(ID + '-lt').innerHTML = h;
var ink = document.getElementById(ID + '-ik');
if (INK) ink.innerHTML = h;
else { ink.parentNode.removeChild(ink); document.getElementById(ID + '-lt').classList.remove(ID + '-split'); }

// ---- barcode (seeded bars, guard bars at both ends) and sticker
var bc = document.getElementById(ID + '-bc'), st = document.getElementById(ID + '-st');
function rnd(k) { var x = Math.sin(k * 12.9898) * 43758.5453; return x - Math.floor(x); }
var bars = '', bw, gw, w = 0;
for (i = 0; w < 136; i++) {
  bw = (i < 2 || w > 128) ? 2 : 1 + Math.floor(rnd(i + 3) * 4); gw = 1 + Math.floor(rnd(i + 41) * 3);
  bars += '<i style="width:' + bw + 'px;margin-right:' + gw + 'px"></i>'; w += bw + gw;
}
document.getElementById(ID + '-bars').innerHTML = bars;
var bn = document.querySelectorAll('#' + ID + '-bcn span');
bn[0].textContent = BARCODE[0]; bn[1].textContent = BARCODE[1];
bc.style.left = LAYOUT.barcode[0] + 'px'; bc.style.top = LAYOUT.barcode[1] + 'px';
st.style.left = LAYOUT.sticker[0] + 'px'; st.style.top = LAYOUT.sticker[1] + 'px';
var sw = document.querySelectorAll('#' + ID + '-sti > *');
for (i = 0; i < 3; i++) sw[i].textContent = STICKER[i] || '';
// sticker type: ink or light, whichever reads better on the accent
var probe = document.getElementById(ID + '-probe');
function lum(token) {
  probe.style.color = 'var(' + token + ')';
  var v = (getComputedStyle(probe).color.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(function (c) {
    c = c / 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
function contrast(a, b) { return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); }
var la = lum('--c-accent');
document.getElementById(ID + '-sti').style.color =
  contrast(la, lum('--c-ink')) >= contrast(la, lum('--c-light')) ? 'var(--c-ink)' : 'var(--c-light)';

// ---- masthead: fit it to mastWidth, then sit its baseline on mastBase (again once the display face has loaded)
function fit() {
  var mhs = root.querySelectorAll('.' + ID + '-mh'), m = mhs[0];
  var f0 = parseFloat(getComputedStyle(m).fontSize), w0 = m.querySelector('.' + ID + '-mhi').offsetWidth;
  var f = Math.min(LAYOUT.mastMax, f0 * LAYOUT.mastWidth / Math.max(1, w0)), k;
  for (k = 0; k < mhs.length; k++) mhs[k].style.fontSize = f.toFixed(2) + 'px';
  var top = LAYOUT.mastBase - m.querySelector('.' + ID + '-bl').offsetTop;
  for (k = 0; k < mhs.length; k++) mhs[k].style.top = top.toFixed(1) + 'px';
}
fit();
var mcs = getComputedStyle(root.querySelector('.' + ID + '-mh'));
document.fonts.load(mcs.fontStyle + ' ' + mcs.fontWeight + ' 100px ' + mcs.fontFamily).then(fit);

// ---- the beats
var tBar = beat('barcode'), tL = beat('left'), tR = beat('right'), tSt = beat('sticker'), tOut = B - T.out;
gsap.set(sel('.$-rt, .$-rb'), { scaleX: 0 });
gsap.set(sel('.$-rl, .$-rr'), { scaleY: 0 });
gsap.set(sel('.$-c'), { yPercent: -70, opacity: 0 });
gsap.set(sel('.$-dlt'), { clipPath: 'inset(0% 100% 0% 0%)' });
gsap.set(sel('.$-sky span'), { yPercent: 110 });
gsap.set(bc, { clipPath: 'inset(0% 100% 0% 0%)' });
gsap.set(st, { scale: 1.7, rotation: 24, opacity: 0 });

// the frame: top and left from the top-left corner, bottom and right from the bottom-right
tl.to(sel('.$-rt, .$-rb'), { scaleX: 1, duration: 0.5, ease: 'expo.out' }, q(A));
tl.to(sel('.$-rl, .$-rr'), { scaleY: 1, duration: 0.5, ease: 'expo.out' }, q(A));
// the masthead: each letter drops from above, both copies together
for (i = 0; i < nl; i++) {
  tl.to(sel('.$-c' + i), { yPercent: 0, duration: 0.36, ease: 'back.out(1.6)' }, q(A + T.step * i));
  tl.to(sel('.$-c' + i), { opacity: 1, duration: 0.1, ease: 'none' }, q(A + T.step * i));
}
var SHUT = 'inset(0% 100% 0% 0%)', OPEN = 'inset(0% 0% 0% 0%)', GONE = 'inset(0% 0% 0% 100%)';   // clip-path: fromTo only
tl.fromTo(sel('.$-dlt'), { clipPath: SHUT }, { clipPath: OPEN, duration: 0.4, ease: 'power3.out', immediateRender: false }, q(A + T.date));
tl.fromTo(bc, { clipPath: SHUT }, { clipPath: OPEN, duration: 0.24, ease: 'power2.out', immediateRender: false }, q(tBar));
// coverlines rise out of their line masks, one block per word
[tL, tR].forEach(function (t, b) {
  for (var j = 0; j < (LINES[b] || []).length; j++) {
    tl.to(sel('.$-l' + b + ' .$-m' + j + ' span'), { yPercent: 0, duration: 0.34, ease: 'power3.out' }, q(t + 0.06 * j));
  }
});
// the sticker slaps on
tl.to(st, { scale: 1, rotation: 0, duration: 0.26, ease: 'back.out(1.7)' }, q(tSt));
tl.to(st, { opacity: 1, duration: 0.06, ease: 'none' }, q(tSt));

// out: letters fall away behind the head, lines rise out through their masks, the rest clears
if (T.out > 0) {
  var d = Math.min(0.14, T.out * 0.75), gap = nl > 1 ? (T.out - d) / (nl - 1) : 0;    // the last letter is gone at B
  for (i = 0; i < nl; i++) {
    tl.to(sel('.$-c' + i), { yPercent: 45, opacity: 0, duration: d, ease: 'power2.in' }, q(tOut + gap * i));
  }
  tl.to(sel('.$-sky span'), { yPercent: -110, duration: d, ease: 'power2.in' }, q(tOut));
  tl.to(sel('.$-rt, .$-rb'), { scaleX: 0, duration: d, ease: 'power2.in' }, q(tOut));
  tl.to(sel('.$-rl, .$-rr'), { scaleY: 0, duration: d, ease: 'power2.in' }, q(tOut));
  tl.fromTo(sel('.$-dlt'), { clipPath: OPEN }, { clipPath: GONE, duration: d, ease: 'power2.in', immediateRender: false }, q(tOut));
  tl.fromTo(bc, { clipPath: OPEN }, { clipPath: GONE, duration: d, ease: 'power2.in', immediateRender: false }, q(tOut));
  tl.to(st, { scale: 0.6, opacity: 0, duration: d, ease: 'power2.in' }, q(tOut));
}
