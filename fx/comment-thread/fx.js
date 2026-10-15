// comment-thread (layer: top). A storyboard beat card pops in above the head, a pin with the speaker's headshot drops
// onto a word in the beat's line, a comment opens under it and their note types in, a reply slides in from the
// editor, and an underline lands on the word the note is about. It all lifts away at B.
// Supply: your headshot, a square image dropped in this folder and named in HEADSHOT (until then a neutral person
// glyph); optionally two stills of that beat from your storyboard, named in FRAMES (until then placeholder frames).
// Change: the words and the word keys below. A key finds the first matching spoken word at or after A (wordAt); when
// it is missing, the fallback in T (seconds after A) is used. The note types in between the pin and the reply.

var NOTE = 'push this one warmer';           // the note that types in
var REPLY = 'On it.';                        // the answer
var NAME = 'You';                            // who leaves the note: your name
var AUTHOR = 'Editor';                       // who answers
var WHEN = 'now';                            // the time stamp that appears once the note is in
var BEAT = { no: '04', time: '0:05.9', kind: 'GRADE', line: 'Make it warmer.', mark: 'warmer' };   // the card (a short line); mark = the word the pin and underline land on
var HEADSHOT = '';                           // e.g. 'headshot.jpg' in this folder; '' = placeholder glyph
var FRAMES = ['', ''];                       // e.g. ['beat-a.jpg', 'beat-b.jpg'] (9:16 stills); '' = placeholder frames
var PIN_ON = 'I';                            // the pin drops on this word
var REPLY_ON = 'one';                        // the reply slides in on this word
var MARK_ON = 'note';                        // the underline lands on this word
var T = { pin: 0.10, pop: 0.12, type: 0.10, reply: 0.75, mark: 1.07, out: 0.20 };

var R = '#{{ID}} ';
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function word(w, after, fallback) { var t = w ? wordAt(w, after) : null; return t === null || t >= B ? fallback : t; }
var GLYPH = '<svg viewBox="0 0 48 48"><circle class="ct-ph" cx="24" cy="24" r="24"/><circle class="ct-gl" cx="24" cy="19" r="8"/>' +
            '<path class="ct-gl" d="M8 46 C9.5 34 16 29.5 24 29.5 C32 29.5 38.5 34 40 46 Z"/></svg>';
var STILL = ['<svg viewBox="0 0 84 150"><ellipse cx="42" cy="70" rx="13" ry="16"/><path d="M10 150 C12 118 26 104 42 104 C58 104 72 118 74 150 Z"/></svg>',
             '<svg viewBox="0 0 84 150"><ellipse cx="45" cy="62" rx="17" ry="21"/><path d="M0 150 C3 110 22 92 45 92 C68 92 86 110 90 150 Z"/></svg>'];
function head() { return HEADSHOT ? '<img src="fx/{{ID}}/' + HEADSHOT + '" alt="">' : GLYPH; }

// build the card, the pin and the comment once, from the constants
(function () {
  var line = document.querySelector(R + '.ct-line');
  if (!line || line.childNodes.length) return;
  document.querySelector(R + '.ct-no').textContent = BEAT.no;
  document.querySelector(R + '.ct-tc').textContent = BEAT.time;
  document.querySelector(R + '.ct-kind').textContent = BEAT.kind;
  document.querySelectorAll(R + '.ct-frame').forEach(function (f, i) {
    f.innerHTML = FRAMES[i] ? '<img src="fx/{{ID}}/' + FRAMES[i] + '" alt="">' : STILL[i % 2];
  });
  var L = BEAT.line, k = BEAT.mark ? L.indexOf(BEAT.mark) : -1, m = k < 0 ? '' : BEAT.mark;
  if (k < 0) k = 0;
  var mark = document.createElement('span');
  mark.className = 'ct-mark';
  mark.appendChild(document.createTextNode(m));
  mark.insertAdjacentHTML('beforeend', '<i class="ct-under"></i><b class="ct-pin"><b class="ct-av ct-me">' + head() + '</b></b>');
  line.appendChild(document.createTextNode('“' + L.slice(0, k)));
  line.appendChild(mark);
  line.appendChild(document.createTextNode(L.slice(k + m.length) + '”'));
  if (L.length > 22) line.style.fontSize = Math.max(24, Math.round(34 * 22 / L.length)) + 'px';   // long lines get smaller, never clipped
  document.querySelector(R + '.ct-msg .ct-av').innerHTML = head();
  document.querySelector(R + '.ct-myname').textContent = NAME;
  document.querySelector(R + '.ct-time').textContent = WHEN;
  document.querySelector(R + '.ct-edname').textContent = AUTHOR;
  document.querySelector(R + '.ct-rtext').textContent = REPLY;
  var note = document.querySelector(R + '.ct-note');
  for (var i = 0; i < NOTE.length; i++) { var c = document.createElement('i'); c.textContent = NOTE[i]; note.appendChild(c); }
  note.insertAdjacentHTML('beforeend', '<span class="ct-caret"></span>');
})();

// times
var PIN = word(PIN_ON, A, A + T.pin), POP = PIN + T.pop;
var REP = word(REPLY_ON, POP, A + T.reply);
var TY0 = POP + T.type, dt = Math.min(0.05, Math.max(0.012, (REP - 0.08 - TY0) / Math.max(1, NOTE.length)));
var TY1 = TY0 + NOTE.length * dt;
var OUT = B - T.out;
var MARK = Math.min(word(MARK_ON, REP + 0.05, A + T.mark), OUT - 0.2);
var reply = document.querySelector(R + '.ct-reply');
var RH = reply.offsetHeight + parseFloat(getComputedStyle(reply).marginTop), RAD = (parseFloat(tok('--radius')) || 0) * 3;
var SHUT = 'inset(0px 0px ' + RH + 'px 0px round ' + RAD + 'px)', OPEN = 'inset(0px 0px 0px 0px round ' + RAD + 'px)';

gsap.set(R + '.ct-card', { opacity: 0, scale: 0.94 });
gsap.set(R + '.ct-pin', { opacity: 0, y: -80 });
gsap.set(R + '.ct-popw', { opacity: 0, scale: 0.92 });
gsap.set(R + '.ct-pop', { clipPath: SHUT });
gsap.set(R + '.ct-time', { opacity: 0 });
gsap.set([R + '.ct-reply .ct-head', R + '.ct-rtext'], { opacity: 0, y: 10 });
gsap.set(R + '.ct-note i', { display: 'none' });
gsap.set(R + '.ct-under', { scaleX: 0 });

// the card
tl.fromTo(R + '.ct-card', { opacity: 0, scale: 0.94 }, { opacity: 1, scale: 1, duration: 0.16, ease: 'power2.out', immediateRender: false }, q(A));

// the pin drops onto the word
tl.fromTo(R + '.ct-pin', { opacity: 0, y: -80 }, { opacity: 1, y: 0, duration: 0.24, ease: 'back.out(1.7)', immediateRender: false }, q(PIN));

// the comment opens under it and the note types in
tl.fromTo(R + '.ct-popw', { opacity: 0, scale: 0.92 }, { opacity: 1, scale: 1, duration: 0.2, ease: 'power3.out', immediateRender: false }, q(POP));
var chars = document.querySelectorAll(R + '.ct-note i');
for (var i = 0; i < chars.length; i++) tl.set(chars[i], { display: 'inline' }, q(TY0 + i * dt));
tl.set(R + '.ct-caret', { display: 'none' }, q(TY1 + 0.04));
tl.set(R + '.ct-time', { opacity: 1 }, q(TY1 + 0.04));

// the reply: the comment opens downward and the answer slides in
tl.fromTo(R + '.ct-pop', { clipPath: SHUT }, { clipPath: OPEN, duration: 0.24, ease: 'power3.out', immediateRender: false }, q(REP));
tl.fromTo([R + '.ct-reply .ct-head', R + '.ct-rtext'], { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.22, ease: 'power3.out', stagger: 0.04, immediateRender: false }, q(REP + 0.04));

// the word the note is about
tl.fromTo(R + '.ct-under', { scaleX: 0 }, { scaleX: 1, duration: 0.22, ease: 'power3.out', immediateRender: false }, q(MARK));

// out
tl.to(R + '.ct-wrap', { opacity: 0, scale: 0.97, transformOrigin: '540px 420px', duration: 0.2, ease: 'power2.in' }, q(OUT));
