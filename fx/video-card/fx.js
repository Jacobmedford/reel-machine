// video-card: "I recorded a walkthrough." A video card unfolds over the shot, play presses on the word, the chapters
// skip with a moving clip in each (the scrubber fills segment by segment, the label rolls to the chapter's name),
// then the card folds away.
//
// Use: layer top, on the line about the walkthrough. Lab: dict(id="video-card", layer="top", at=23.90, end=25.60).
// Supply: clips of your real walkthrough, its title and its chapter names. The library ships PLACEHOLDERS: the
//   <video> tags in fx.html are copies of this project's own clean.mp4 in sync with the main picture, each chapter
//   framed differently (FRAMING), tagged on the card. Replace them with clips of your walkthrough where something
//   moves (you AND the screen), never a near-still. energy.py ranks the moments by frame-difference energy (it skips
//   cuts), cuts the clips and prints the tags to paste:
//     PY fx/<id>/energy.py <walkthrough.mp4> --top 4 --cut <project>/fx/<id> --tags <at> <end> --rate 2 --play <t>
//   (--play: when the play press lands; --region x,y,w,h to make the webcam box and the screen both count).
//   Paste the printed tags over the ones in fx.html, one clip per chapter, set FRAMING to { s: 1 } for each (or a
//   punch-in where a detail matters), then set PLACEHOLDER = ''.
// Change only these constants: TITLE, KICKER, CHAPTERS, PLAY_WORD, FRAMING, PUSH, POS, SCALE, PLACEHOLDER, T.
// Times: the card unfolds at A + T.unfold, play presses on PLAY_WORD (fallback A + T.play), each chapter skips on its
//   word when it names one (else evenly from play to the fold), and the fold starts T.fold before B and lands on it.
// Media timing in fx.html is relative to the effect ({{START+0.0333}}, {{SYNC}}, {{DUR}}), so the card times itself
//   wherever it sits: every clip runs the whole window and shows only during its chapter.
// Sound: whoosh on the unfold, pop on the button, click on the press, tick on every skip, whoosh-soft on the fold.

var TITLE = 'How I make these videos';
var KICKER = { label: 'Walkthrough', count: 'chapters' };
// label; weight = its share of the scrubber; run = how far its segment fills before the next skip; word = skip on it
var CHAPTERS = [
  { label: 'The raw take', weight: 3, run: 0.55 },
  { label: 'The plan', weight: 3, run: 0.5 },
  { label: 'One note', weight: 2, run: 0.6 },
  { label: 'The finished video', weight: 2, run: 1, word: 'walkthrough' }
];
var PLAY_WORD = 'recorded';
var FRAMING = [{ s: 1 }, { s: 1.32 }, { s: 1.75, y: 14 }, { s: 1.12, y: -12 }];   // per clip: scale, offset (punch-ins)
var PUSH = 0.05;                        // each clip pushes in this much across its chapter
var POS = { x: 160, y: 470 };           // the card's top-left on the 1080x1920 frame (760 x 576 at SCALE 1): above
                                        // the head when there is room, else over the face, never cutting the head
var SCALE = 1;
var PLACEHOLDER = 'Placeholder clip';   // the tag on the clips; '' once they are your real clips
var T = {
  unfold: 0.00,   // the card unfolds from its centre (s after A)
  title: 0.08,    // the title rises through its mask
  kicker: 0.12,   // the kicker line rises
  button: 0.16,   // the play button pops in
  play: 0.45,     // the press, when PLAY_WORD is not in the line
  fold: 0.24      // the fold starts this long before B
};

// ---- the parts, built from the constants (static: before anything plays)
var ID = '{{ID}}', N = CHAPTERS.length;
function el(s) { return document.getElementById(ID + '-' + s); }
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
var card = el('card'), body = el('body'), head = el('head'), title = el('title'), tag = el('tag');
title.textContent = TITLE;
tag.textContent = PLACEHOLDER;
if (!PLACEHOLDER) tag.style.display = 'none';
var BAR_W = 720, GAP = 6, weights = 0, segX = [], segW = [], sx = 0;
CHAPTERS.forEach(function (c) { weights += c.weight || 1; });
CHAPTERS.forEach(function (c, i) {
  var w = Math.round((BAR_W - GAP * (N - 1)) * (c.weight || 1) / weights);
  var seg = document.createElement('div');
  seg.className = ID + '-seg';
  seg.style.left = sx + 'px';
  seg.style.width = w + 'px';
  var fill = document.createElement('i');
  fill.id = ID + '-f' + i;
  seg.appendChild(fill);
  el('bar').insertBefore(seg, head);
  segX.push(sx);
  segW.push(w);
  sx += w + GAP;
});
function row(i, b, text, kicker) {
  var d = document.createElement('div'), bb = document.createElement('b'), sp = document.createElement('span');
  d.id = ID + '-c' + i;
  d.className = ID + '-ch' + (kicker ? ' ' + ID + '-k' : '');
  bb.textContent = b;
  sp.textContent = text;
  d.appendChild(bb);
  d.appendChild(sp);
  el('chm').appendChild(d);
}
row(0, KICKER.label, N + ' ' + KICKER.count, true);
CHAPTERS.forEach(function (c, i) { row(i + 1, (i < 9 ? '0' : '') + (i + 1), c.label); });
// a long title shrinks to the card once its face has loaded (a static size, nothing animates it)
function fit() {
  title.style.fontSize = '';
  if (title.scrollWidth > 692) title.style.fontSize = (54 * 692 / title.scrollWidth).toFixed(1) + 'px';
}
var face = tok('--display-style') + ' ' + tok('--display-weight') + ' 54px ' + tok('--font-display');
if (document.fonts && document.fonts.load) document.fonts.load(face, TITLE).then(fit, fit); else fit();

// ---- start states
var R = tok('--radius') || '0px';
var SHUT = 'inset(42% 44% 42% 44% round ' + R + ')', OPEN = 'inset(0% 0% 0% 0% round ' + R + ')';
var clips = [];
for (var k = 0; k < N; k++) clips.push(el('v' + (k + 1)));
gsap.set(card, { x: POS.x, y: POS.y, scale: 0.94 * SCALE, transformOrigin: '50% 50%' });
gsap.set(body, { clipPath: SHUT });
gsap.set(el('shadow'), { opacity: 0 });
gsap.set(clips.filter(Boolean), { opacity: 0 });
gsap.set(title, { yPercent: 110 });
for (var r = 0; r <= N; r++) gsap.set(el('c' + r), { yPercent: 110 });
gsap.set(el('play'), { opacity: 0 });
gsap.set(head, { opacity: 0 });
for (var f = 0; f < N; f++) gsap.set(el('f' + f), { scaleX: 0 });

// ---- in: the card unfolds from its centre, the poster counter-zooms, the type rises through its masks
var tIn = A + T.unfold;
tl.fromTo(card, { scale: 0.94 * SCALE }, { scale: SCALE, duration: 0.34, ease: 'expo.out', immediateRender: false }, q(tIn));
tl.fromTo(body, { clipPath: SHUT }, { clipPath: OPEN, duration: 0.34, ease: 'expo.out', immediateRender: false }, q(tIn));
tl.fromTo(el('shadow'), { opacity: 0 }, { opacity: 1, duration: 0.2, ease: 'power2.out', immediateRender: false }, q(tIn + 0.14));
tl.fromTo(el('poster'), { scale: 1.2 }, { scale: 1, duration: 0.5, ease: 'power3.out', immediateRender: false }, q(tIn));
tl.fromTo(title, { yPercent: 110 }, { yPercent: 0, duration: 0.34, ease: 'power3.out', immediateRender: false }, q(A + T.title));
tl.fromTo(el('c0'), { yPercent: 110 }, { yPercent: 0, duration: 0.3, ease: 'power3.out', immediateRender: false }, q(A + T.kicker));
tl.fromTo(el('play'), { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.6)', immediateRender: false }, q(A + T.button));

// ---- play on the word: the button presses, then blows out as the first clip comes alive
var tPlay = wordAt(PLAY_WORD, A);
if (tPlay === null || tPlay > B - 0.8) tPlay = A + T.play;
var t0 = tPlay + 0.067, tFold = B - T.fold;
tl.fromTo(el('play'), { scale: 1 }, { scale: 0.84, duration: 0.067, ease: 'power2.in', immediateRender: false }, q(tPlay));
tl.fromTo(el('play'), { scale: 0.84, opacity: 1 }, { scale: 1.35, opacity: 0, duration: 0.2, ease: 'power2.out', immediateRender: false }, q(t0));
tl.set(head, { opacity: 1 }, q(t0));
tl.set(el('poster'), { opacity: 0 }, q(t0 + 1 / 30));

// ---- chapters: on its word, or spread evenly between the anchors around it
var at = [t0];
for (var i = 1; i < N; i++) {
  var w = CHAPTERS[i].word ? wordAt(CHAPTERS[i].word, t0) : null;
  at.push(w !== null && w > t0 + 0.12 && w < tFold - 0.12 ? w : null);
}
at.push(tFold);
for (var a = 0, b; a < N; a = b) {
  for (b = a + 1; at[b] === null; b++);
  for (var m = a + 1; m < b; m++) at[m] = at[a] + (at[b] - at[a]) * (m - a) / (b - a);
}
for (var c = 0; c < N; c++) {
  var t = at[c], len = at[c + 1] - t, run = CHAPTERS[c].run === undefined ? 0.6 : CHAPTERS[c].run;
  var d = Math.min(0.26, 0.6 * len), v = clips[c], F = FRAMING[c] || {};
  if (v) {                                                      // the thumbnail cuts to this chapter's clip
    tl.set(v, { opacity: 1 }, q(t));
    if (c + 1 < N) tl.set(v, { opacity: 0 }, q(at[c + 1]));
    tl.fromTo(v, { scale: F.s || 1, x: F.x || 0, y: F.y || 0 },
      { scale: (F.s || 1) * (1 + PUSH), duration: len, ease: 'none', immediateRender: false }, q(t));
  }
  if (c > 0) tl.set(el('f' + (c - 1)), { scaleX: 1 }, q(t));  // the skipped segment fills
  tl.fromTo(el('c' + c), { yPercent: 0 }, { yPercent: -110, duration: d * 0.8, ease: 'power3.in', immediateRender: false }, q(t - d * 0.55));
  tl.fromTo(el('c' + (c + 1)), { yPercent: 110 }, { yPercent: 0, duration: d, ease: 'power3.out', immediateRender: false }, q(t - d * 0.25));
  tl.fromTo(el('f' + c), { scaleX: 0 }, { scaleX: run, duration: len, ease: 'none', immediateRender: false }, q(t));
  tl.fromTo(head, { x: segX[c] }, { x: segX[c] + segW[c] * run, duration: len, ease: 'none', immediateRender: false }, q(t));
}

// ---- out: the unfold in reverse, accelerating into the card's centre; the last frame before B is nearly shut
var fold = Math.max(0.1, B - tFold - 1 / 30);
tl.fromTo(el('shadow'), { opacity: 1 }, { opacity: 0, duration: 0.1, ease: 'power2.in', immediateRender: false }, q(tFold));
tl.fromTo(body, { clipPath: OPEN }, { clipPath: SHUT, duration: fold, ease: 'power3.in', immediateRender: false }, q(tFold));
tl.fromTo(card, { scale: SCALE }, { scale: 0.94 * SCALE, duration: fold, ease: 'power3.in', immediateRender: false }, q(tFold));
