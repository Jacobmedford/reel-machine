// kinetic-hook-front (layer: top, above the speaker, under the captions). kinetic-hook's line one held over the
// speaker for the opening frames (the thumbnail), with the same words, size, fit and settle (1.04x to 1 over 0.4s),
// so the hand-off to kinetic-hook's copy behind the head is invisible.
// Light type everywhere; a dark copy shows through masks.png wherever the picture under the line is light, one mask
// per frame of this window, swapped on the frame. Type over moving footage splits light/dark, never an outline.
// Supply: OPEN (the same words as kinetic-hook's OPEN), then the masks for your footage:
//   PY fx/<id>/mkmask.py <project> [<id>] [--field <s>]
// It reads this effect's window from edit.py, the picture from public/clean.mp4 (and the speaker from
// public/subject.webm after --field, the time kinetic-hook's ground cuts in) and writes fx/<id>/masks.png.
// The masks.png in the library is the lab's stand-in: rerun mkmask.py whenever the window or the cut changes.
// The window: from kinetic-hook's start to the frame its ground cuts in (or until the head drops below the line,
// if later). With kinetic-hook's defaults the ground cuts in with the first stamped letter, which comes
// (letters - 1) x 2 frames + LEAD.stamp before the STAMP word is spoken (in the lab: frame 11, end = 0.37).
// Change only these constants:
var OPEN = 'I DIDN\u2019T';                 // kinetic-hook's OPEN
var SPLIT = true;                           // false: light type only (no masks.png needed)
var BAND = 232;                             // the masks' band height: matches fx.html and mkmask.py (y 212-444)

function $(s) { return document.querySelector(s); }
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
var band = $('#{{ID}}-band'), dk = $('#{{ID}}-dk0');
var N = Math.max(1, Math.round(B * 30) - Math.round(A * 30));      // one mask per frame of the window
if (!SPLIT) dk.parentNode.removeChild(dk);
for (var f = 1; SPLIT && f < N; f++) {                               // a dark copy per frame, each on its own band
  var c = dk.cloneNode(true);
  c.id = '{{ID}}-dk' + f;
  band.appendChild(c);
}
Array.prototype.slice.call(document.querySelectorAll('#{{ID}} .{{ID}}-t')).forEach(function (e) {
  e.textContent = OPEN;
  e.setAttribute('data-layout-allow-overlap', '');          // the copies (and kinetic-hook's line behind) overlap on purpose
});
Array.prototype.slice.call(document.querySelectorAll('#{{ID}} .{{ID}}-dk')).forEach(function (e, i) {
  e.style.webkitMaskPosition = '0px ' + (-i * BAND) + 'px';
  e.style.maskPosition = '0px ' + (-i * BAND) + 'px';
});

// the same fit as kinetic-hook's line one: its fx.html size, unless the line is wider than 920px
function fit() {
  Array.prototype.slice.call(document.querySelectorAll('#{{ID}} .{{ID}}-m')).forEach(function (box) {
    if (!box.dataset.max) box.dataset.max = parseFloat(getComputedStyle(box).fontSize);
    var max = +box.dataset.max;
    box.style.fontSize = max + 'px';
    var w = box.querySelector('.{{ID}}-t').offsetWidth;
    if (w > 920) box.style.fontSize = (max * 920 / w).toFixed(2) + 'px';
  });
}
fit();
if (document.fonts && document.fonts.load) {
  document.fonts.load(tok('--display-style') + ' ' + tok('--display-weight') + ' 100px ' + tok('--font-display'), OPEN)
    .catch(function () {}).then(fit, fit);
  document.fonts.ready.then(fit);
}

// on from the very first frame (a set at time 0 does not render on a seek to 0); the same settle as line one
if (q(A) <= 0) gsap.set('#{{ID}}', { opacity: 1 });
gsap.set('#{{ID}} .{{ID}}-in', { transformOrigin: '50% 80%' });
tl.fromTo('#{{ID}} .{{ID}}-in', { scale: 1.04 }, { scale: 1, duration: 0.4, ease: 'power2.out', immediateRender: q(A) <= 0 }, q(A));

// the dark copies: frame f of the window shows copy f (its own band of masks.png)
if (SPLIT) {
  gsap.set('#{{ID}} .{{ID}}-dk', { opacity: 0 });
  gsap.set('#{{ID}}-dk0', { opacity: 1 });
  for (var k = 1; k < N; k++) {
    off('#{{ID}}-dk' + (k - 1), A + k / 30);
    on('#{{ID}}-dk' + k, A + k / 30);
  }
}
