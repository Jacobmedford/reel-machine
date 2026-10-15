// prompt-bar, the motif (layer: top). A bar opens out of a pill at the top of the frame, types the instruction on the
// speaker's words, sends it (the button presses, the arrow leaves, a ring turns, the label flips to SENT), a line
// runs along its base, the result rolls in (DONE, the ring becomes a check) and the bar closes back to the pill and
// lifts away, gone at B.
// Supply: nothing, it is all type and tokens. The motif comes back 3 or 4 times in a video (every time the speaker
// says what they told the AI to do): gen.py writes one fx/<id>/ folder per appearance from a single BEATS table,
// so every appearance is the same component with the same in and out move.
// Change: the constants below. Word keys find the first matching spoken word at or after A (wordAt); when one is
// missing, the fallback in T (seconds after A) is used. The bar always starts closing T.out before B.

// ---- constants: gen.py rewrites the lines between these two markers ----
var TEXT = "cut the pauses and add captions";   // the instruction the bar types
var TYPE = ["I", "typed"];   // typing runs from the start of the first word to the end of the second
var SEND_ON = "one";   // the send button presses on this word
var DONE_TEXT = "cut and captioned";   // the result that rolls in; empty = the bar sends and leaves
var DONE_ON = "sentence";   // the word the result lands on; empty = T.run after the send
var LABELS = ["PROMPT", "SENT", "DONE"];   // the small label over the field: waiting, sent, done
var T = { type0: 0.05, type1: 0.60, send: 0.68, run: 0.50, out: 0.26 };   // fallbacks, seconds after A; out: the bar starts closing this long before B
// ---- end of constants ----

var R = '#{{ID}} ', P = R + '.pb', C = R + '.pb-card';
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function span(w, after) {                     // [start, end] of the first spoken word w at or after `after`, in the window
  var s = w ? wordAt(w, after) : null;
  if (s === null || s >= B) return null;
  for (var i = 0; i < WORDS.length; i++) if (WORDS[i][0] === s) return [s, WORDS[i][1]];
  return [s, s + 0.3];
}

// the words go in once, one span per character (typed by showing each on its frame)
(function () {
  var box = document.querySelector(R + '.pb-text');
  if (box && !box.childNodes.length) {
    for (var i = 0; i < TEXT.length; i++) { var s = document.createElement('span'); s.textContent = TEXT[i]; box.appendChild(s); }
  }
  var labs = document.querySelectorAll(R + '.pb-lab');
  labs[0].textContent = LABELS[0];
  labs[1].querySelector('b').textContent = LABELS[1];
  labs[2].querySelector('b').textContent = LABELS[2];
  document.querySelector(R + '.pb-done').textContent = DONE_TEXT;
})();

// times
var s0 = span(TYPE[0], A), s1 = s0 ? span(TYPE[1] || TYPE[0], s0[0]) : null;
var TYPE0 = s0 ? s0[0] : A + T.type0, TYPE1 = s1 ? s1[1] : A + T.type1;
var SEND = SEND_ON ? span(SEND_ON, TYPE1 - 0.05) : null;
SEND = SEND ? SEND[0] : (s1 ? TYPE1 + 0.08 : A + T.send);
var OUT = B - T.out, DONE = 0;
if (DONE_TEXT) {
  DONE = DONE_ON ? span(DONE_ON, SEND + 0.05) : null;
  DONE = DONE ? DONE[0] : SEND + T.run;
  if (DONE > OUT - 0.12) DONE = 0;              // no room for the result: the bar sends and leaves
}
var RAD = (parseFloat(tok('--radius')) || 0) * 3;
var PILL = 'inset(0px 812px 0px 0px round ' + (RAD > 0 ? 74 : 0) + 'px)', FULL = 'inset(0px 0px 0px 0px round ' + RAD + 'px)';

gsap.set(P, { opacity: 0 });
gsap.set(C, { clipPath: PILL });
gsap.set(R + '.pb-text span', { display: 'none' });
gsap.set(R + '.pb-caret', { opacity: 1 });
gsap.set([R + '.pb-lab1', R + '.pb-lab2'], { y: 28 });
gsap.set(R + '.pb-done', { y: 74 });
gsap.set(R + '.pb-line', { scaleX: 0 });
gsap.set([R + '.pb-ring', R + '.pb-check'], { opacity: 0 });

// in: a pill appears at the left and opens to the full bar (the send button is revealed last)
tl.fromTo(P, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.12, ease: 'power2.out', immediateRender: false }, q(A));
tl.fromTo(C, { clipPath: PILL }, { clipPath: FULL, duration: 0.36, ease: 'expo.out', immediateRender: false }, q(A));

// typing: one character per step, evenly across the spoken words
var chars = document.querySelectorAll(R + '.pb-text span'), dt = (TYPE1 - TYPE0) / Math.max(1, chars.length);
for (var i = 0; i < chars.length; i++) tl.set(chars[i], { display: 'inline' }, q(TYPE0 + i * dt));

// caret: solid while typing, blinks while it waits for the send, gone on send
for (var bt = TYPE1 + 0.30, bv = 0; bt < SEND - 0.12; bt += 0.27, bv = 1 - bv) tl.set(R + '.pb-caret', { opacity: bv }, q(bt));
tl.set(R + '.pb-caret', { opacity: 0 }, q(SEND));

// send: the button presses, the arrow leaves upward, a ring starts turning, the label flips to SENT
var END = DONE || OUT + 0.24;
tl.to(R + '.pb-send', { scale: 0.84, duration: 0.07, ease: 'power2.in' }, q(SEND));
tl.to(R + '.pb-send', { scale: 1, duration: 0.32, ease: 'back.out(1.8)' }, q(SEND + 0.07));
tl.to(R + '.pb-arrow', { y: -70, duration: 0.14, ease: 'power2.in' }, q(SEND + 0.02));
tl.fromTo(R + '.pb-ring', { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.2, ease: 'back.out(1.6)', immediateRender: false }, q(SEND + 0.16));
tl.fromTo(R + '.pb-ring', { rotation: 0 }, { rotation: 360 * Math.ceil((END - SEND) / 0.6), duration: Math.max(0.1, END - SEND - 0.16), ease: 'none', immediateRender: false, transformOrigin: '50% 50%' }, q(SEND + 0.16));
tl.to(R + '.pb-lab0', { y: -28, duration: 0.2, ease: 'power3.out' }, q(SEND));
tl.to(R + '.pb-lab1', { y: 0, duration: 0.2, ease: 'power3.out' }, q(SEND));
tl.to(R + '.pb-field', { opacity: 0.5, duration: 0.2, ease: 'power2.out' }, q(SEND + 0.06));

// the line runs along the base of the bar until the result lands (or the bar leaves)
tl.fromTo(R + '.pb-line', { scaleX: 0 }, { scaleX: 1, duration: Math.max(0.1, (DONE || OUT) - SEND - 0.1), ease: 'power1.inOut', immediateRender: false }, q(SEND + 0.1));

if (DONE) {
  // done: the instruction rolls up and out as the result rolls in under it (one strip, so they never overlap), the
  // ring becomes a check, the label reads DONE
  tl.to(R + '.pb-field', { y: -74, duration: 0.26, ease: 'power3.inOut' }, q(DONE - 0.04));
  tl.to(R + '.pb-done', { y: 0, duration: 0.26, ease: 'power3.inOut' }, q(DONE - 0.04));
  tl.to(R + '.pb-lab1', { y: -28, duration: 0.22, ease: 'power3.inOut' }, q(DONE - 0.04));
  tl.to(R + '.pb-lab2', { y: 0, duration: 0.22, ease: 'power3.inOut' }, q(DONE - 0.04));
  tl.to(R + '.pb-ring', { opacity: 0, scale: 0.5, duration: 0.1, ease: 'power2.in' }, q(DONE - 0.04));
  tl.fromTo(R + '.pb-check', { opacity: 0, scale: 0.3 }, { opacity: 1, scale: 1, duration: 0.24, ease: 'back.out(1.8)', immediateRender: false, transformOrigin: '50% 50%' }, q(DONE));
}

// out: the bar closes back to the pill and lifts away (0.24s), gone before B. Always fromTo for the clip: the
// browser reports a full inset in short form, which would not tween number for number into the pill.
tl.fromTo(C, { clipPath: FULL }, { clipPath: PILL, duration: 0.2, ease: 'expo.in', immediateRender: false }, q(OUT));
tl.to(P, { opacity: 0, y: -14, duration: 0.08, ease: 'power2.in' }, q(OUT + 0.16));
