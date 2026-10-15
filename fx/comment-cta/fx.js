// comment-cta (layer: top), the call to action, from A to the last frame. The creator's text box pops with the CTA
// and holds; under it a comment field types the keyword across the spoken keyword and posts it on the next word
// (the send presses, the comment settles, a heart appears), the speaker's reply card drops in and its words land on
// their words, the comment gets a like, then the thread folds up into the text box, which takes the hit and holds to
// the end. Optional: a profile chip rises above the captions and its Follow button presses on the word in FOLLOW_ON.
// Supply: your headshot, a square image dropped in this folder and named in HEADSHOT (until then a neutral person
// glyph), and your handle in HANDLE.
// Change: the words and the word keys below. A key finds the first matching spoken word at or after the previous
// beat (wordAt); when it is missing, the fallback in T (seconds after A, or after the previous beat) is used.

var CTA = ['Comment “EDIT” and', 'I’ll send it to you'];   // the text box, one string per line
var KEYWORD = 'EDIT';                     // typed into the comment field
var TYPE_ON = 'EDIT';                     // the keyword types across this spoken word
var POST_ON = 'and';                      // the comment posts on this word
var REPLY_ON = "I'll";                    // the reply card drops in on this word
var REPLY = [['Sending', 'send'], ['it', 'it'], ['to', 'to'], ['you.', 'you']];   // the reply, each word on its spoken word
var LIKE_ON = 'you';                      // the comment gets a like on this word
var FOLD_ON = '';                         // the thread folds into the text box on this word; '' = T.fold after the reply
var HANDLE = '@yourhandle';               // your handle, on the reply and the chip
var VIEWER = 'you', WHEN = 'now', PLACEHOLDER = 'Add a comment…';   // the commenter, the time stamp, the empty field's hint
var HEADSHOT = '';                        // e.g. 'headshot.jpg' in this folder; '' = placeholder glyph
var FOLLOW_ON = '';                       // e.g. 'follow': the chip rises and its button presses on this word; '' = no chip
var SUB = 'Daily tips';                   // the line under the handle in the chip; '' = none
var LABELS = ['Follow', 'Following'];    // the chip's button, before and after the press
var T = { field: 0.06, type: 0.40, post: 0.08, reply: 0.30, word: 0.30, fold: 0.15, follow: 0.27, sub: 0.70 };

var R = '#{{ID}} ';
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function span(w, after) {                 // [start, end] of the first spoken word w at or after `after`, in the window
  var s = w ? wordAt(w, after) : null;
  if (s === null || s >= B) return null;
  for (var i = 0; i < WORDS.length; i++) if (WORDS[i][0] === s) return [s, WORDS[i][1]];
  return [s, s + 0.3];
}
function word(w, after, fallback) { var s = span(w, after); return s ? s[0] : fallback; }
var GLYPH = '<svg viewBox="0 0 48 48"><circle class="cc-ph0" cx="24" cy="24" r="24"/><circle class="cc-gl" cx="24" cy="19" r="8"/>' +
            '<path class="cc-gl" d="M8 46 C9.5 34 16 29.5 24 29.5 C32 29.5 38.5 34 40 46 Z"/></svg>';

// build the words once, from the constants
(function () {
  var cta = document.querySelector(R + '.cc-cta');
  if (!cta || cta.childNodes.length) return;
  CTA.forEach(function (l, i) {
    var s = document.createElement('span'); s.className = 'cc-ln'; s.textContent = l; cta.appendChild(s);
    if (i < CTA.length - 1) cta.appendChild(document.createElement('br'));
  });
  var typed = document.querySelector(R + '.cc-typed');
  for (var i = 0; i < KEYWORD.length; i++) { var c = document.createElement('span'); c.textContent = KEYWORD[i]; typed.appendChild(c); }
  var rt = document.querySelector(R + '.cc-rtxt');
  REPLY.forEach(function (w, i) {
    if (i) rt.appendChild(document.createTextNode(' '));
    var s = document.createElement('span'); s.textContent = w[0]; rt.appendChild(s);
  });
  document.querySelectorAll(R + '.cc-me').forEach(function (a) { a.innerHTML = HEADSHOT ? '<img src="fx/{{ID}}/' + HEADSHOT + '" alt="">' : GLYPH; });
  document.querySelectorAll(R + '.cc-when').forEach(function (e) { e.textContent = WHEN; });
  document.querySelector(R + '.cc-viewer').textContent = VIEWER;
  document.querySelector(R + '.cc-ph').textContent = PLACEHOLDER;
  document.querySelector(R + '.cc-handle').textContent = HANDLE;
  document.querySelector(R + '.cc-chandle').textContent = HANDLE;
  document.querySelector(R + '.cc-sub').textContent = SUB;
  document.querySelector(R + '.cc-b0 span').textContent = LABELS[0];
  document.querySelector(R + '.cc-b1 span').textContent = LABELS[1];
  // the like takes the accent when it reads on the text box, else the text-box ink
  function channels(c) {
    if (c[0] === '#') {
      if (c.length === 4) c = '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
      return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
    }
    var m = c.match(/[\d.]+/g);
    return m && m.length >= 3 ? [+m[0], +m[1], +m[2]] : [0, 0, 0];
  }
  function lum(c) {
    var w = [0.2126, 0.7152, 0.0722], s = 0;
    for (var i = 0; i < 3; i++) { var v = c[i] / 255; s += w[i] * (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)); }
    return s;
  }
  var a = lum(channels(tok('--c-accent'))), b = lum(channels(tok('--c-tb-bg')));
  if ((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) < 2.2) document.querySelector(R + '.cc-heart').classList.add('cc-ink');
})();

// times
var tw = span(TYPE_ON, A), TY0 = tw ? tw[0] : A + T.type, TY1 = tw ? tw[1] : TY0 + 0.27;
var POST = word(POST_ON, TY1 - 0.02, TY1 + T.post);
var REP = word(REPLY_ON, POST + 0.05, POST + T.reply);
var WT = [], prev = REP + 0.1, last = null;
REPLY.forEach(function (w) {
  var s = span(w[1], prev);
  WT.push(s ? s[0] : prev + T.word);
  prev = WT[WT.length - 1] + 0.01;
  if (s) last = s;
});
var LAST = WT.length ? WT[WT.length - 1] : REP;
var LIKE = word(LIKE_ON, REP, LAST);
var FOLD = FOLD_ON ? word(FOLD_ON, LIKE, (last ? last[1] : LAST) + T.fold) : (last ? last[1] : LAST + 0.3) + T.fold;
FOLD = Math.min(FOLD, B - 0.35);
var RAD = parseFloat(tok('--radius')) || 0, R0 = RAD > 0 ? 52 : 0, R1 = RAD > 0 ? 26 : 0;

gsap.set([R + '.cc-fmeta', R + '.cc-reply', R + '.cc-chip', R + '.cc-b1', R + '.cc-sub', R + '.cc-heart', R + '.cc-hfill', R + '.cc-on'], { opacity: 0 });
gsap.set([R + '.cc-field', R + '.cc-anon', R + '.cc-ph', R + '.cc-send'], { opacity: 0 });
gsap.set(R + '.cc-typed span', { display: 'none' });
gsap.set(R + '.cc-caret', { opacity: 0 });
gsap.set(R + '.cc-chk', { strokeDasharray: 30, strokeDashoffset: 30 });
gsap.set(R + '.cc-rtxt span', { opacity: 0 });

// the CTA text box pops at A and holds to the end
tl.fromTo(R + '.cc-cta', { scale: 0.92 }, { scale: 1, duration: 0.18, ease: 'back.out(1.6)', immediateRender: false }, q(A));

// the comment field comes up under it, its contents settle in
var F = A + T.field;
tl.fromTo(R + '.cc-field', { opacity: 0, y: 22, scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: 0.26, ease: 'power3.out', immediateRender: false }, q(F));
tl.to([R + '.cc-anon', R + '.cc-ph', R + '.cc-send'], { opacity: 1, duration: 0.12, ease: 'power2.out' }, q(F + 0.08));
tl.fromTo(R + '.cc-ph', { x: 12 }, { x: 0, duration: 0.2, ease: 'power3.out', immediateRender: false }, q(F + 0.08));

// caret: blinks until the typing, solid while typing, blinks until the post
for (var bt = F + 0.12, bv = 1; bt < TY0 - 0.06; bt += 0.27, bv = 1 - bv) tl.set(R + '.cc-caret', { opacity: bv }, q(bt));
tl.set(R + '.cc-caret', { opacity: 1 }, q(TY0));
var ty = document.querySelectorAll(R + '.cc-typed span'), kdt = (TY1 - TY0) / Math.max(1, ty.length);
for (var bt2 = TY1 + 0.10, bv2 = 0; bt2 < POST - 0.06; bt2 += 0.27, bv2 = 1 - bv2) tl.set(R + '.cc-caret', { opacity: bv2 }, q(bt2));

// the keyword types on the word, the send button wakes up
tl.set(R + '.cc-ph', { opacity: 0 }, q(TY0));
for (var i = 0; i < ty.length; i++) tl.set(ty[i], { display: 'inline' }, q(TY0 + i * kdt));
tl.to(R + '.cc-on', { opacity: 1, duration: 0.12, ease: 'power2.out' }, q(TY0));

// post: the button presses, the arrow shoots up, the comment settles into a posted card, a heart appears
tl.to(R + '.cc-send', { scale: 0.84, duration: 0.067, ease: 'power2.in' }, q(POST));
tl.to(R + '.cc-send', { scale: 1, duration: 0.2, ease: 'back.out(1.8)' }, q(POST + 0.067));
tl.to(R + '.cc-arrow', { y: -46, duration: 0.18, ease: 'power3.in' }, q(POST + 0.067));
tl.set(R + '.cc-caret', { opacity: 0 }, q(POST + 0.067));
tl.to(R + '.cc-send', { opacity: 0, scale: 0.6, duration: 0.14, ease: 'power2.in' }, q(POST + 0.167));
tl.fromTo(R + '.cc-heart', { opacity: 0, scale: 0.5 }, { opacity: 1, scale: 1, duration: 0.24, ease: 'back.out(1.7)', immediateRender: false }, q(POST + 0.237));
tl.to(R + '.cc-txt', { y: 16, duration: 0.26, ease: 'power3.out' }, q(POST + 0.134));
tl.fromTo(R + '.cc-fmeta', { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.24, ease: 'power3.out', immediateRender: false }, q(POST + 0.134));
tl.fromTo(R + '.cc-field', { borderRadius: R0 }, { borderRadius: R1, duration: 0.26, ease: 'power3.out', immediateRender: false }, q(POST + 0.134));
tl.fromTo(R + '.cc-field', { y: 0 }, { y: -6, duration: 0.1, ease: 'power2.out', yoyo: true, repeat: 1, immediateRender: false }, q(POST + 0.134));

// the reply drops out from under the comment, its words land on the speaker's words
tl.fromTo(R + '.cc-reply', { opacity: 0, y: -40, scaleY: 0.6 }, { opacity: 1, y: 0, scaleY: 1, duration: 0.28, ease: 'back.out(1.5)', immediateRender: false }, q(REP));
document.querySelectorAll(R + '.cc-rtxt span').forEach(function (s, i) { tl.set(s, { opacity: 1 }, q(WT[i])); });

// the comment gets a like
tl.set(R + '.cc-hfill', { opacity: 1 }, q(LIKE));
tl.fromTo(R + '.cc-heart', { scale: 1.4 }, { scale: 1, duration: 0.3, ease: 'back.out(2)', immediateRender: false }, q(LIKE));

// the thread folds up into the text box, which takes the hit
tl.to([R + '.cc-reply', R + '.cc-field'], { y: -150, scale: 0.4, opacity: 0, duration: 0.24, ease: 'power3.in', stagger: 0.04 }, q(FOLD));
tl.fromTo(R + '.cc-cta', { scale: 1 }, { scale: 1.045, duration: 0.08, ease: 'power2.out', yoyo: true, repeat: 1, immediateRender: false }, q(FOLD + 0.27));

// optional: follow. The chip rises before the word, the button presses on it, the line under the handle comes in
var FOL = FOLLOW_ON ? word(FOLLOW_ON, A, null) : null;
if (FOL !== null) {
  tl.fromTo(R + '.cc-chip', { opacity: 0, y: 46, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.32, ease: 'power3.out', immediateRender: false }, q(FOL - T.follow));
  tl.to(R + '.cc-btn', { scale: 0.88, duration: 0.067, ease: 'power2.in' }, q(FOL));
  tl.to(R + '.cc-btn', { scale: 1, duration: 0.26, ease: 'back.out(1.8)' }, q(FOL + 0.067));
  tl.to(R + '.cc-b0', { yPercent: -100, opacity: 0, duration: 0.18, ease: 'power3.in' }, q(FOL + 0.067));
  tl.fromTo(R + '.cc-b1', { yPercent: 100, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.22, ease: 'power3.out', immediateRender: false }, q(FOL + 0.1));
  tl.to(R + '.cc-chk', { strokeDashoffset: 0, duration: 0.22, ease: 'power2.out' }, q(FOL + 0.2));
  if (SUB) {
    tl.to(R + '.cc-chandle', { y: -18, duration: 0.24, ease: 'power3.out' }, q(FOL + T.sub));
    tl.fromTo(R + '.cc-sub', { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.24, ease: 'power3.out', immediateRender: false }, q(FOL + T.sub));
  }
}
