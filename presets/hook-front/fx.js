// hook-front (layer: top, above the speaker, under the captions). A proof line over the hook, and line one on frame 0:
//   proof     LINE is up in mono above the hook: what the video was made from, all true. Each frame's copy is knocked
//             out wherever the speaker is (knock.png), so as they move up into it the line is eaten by the head, as if
//             it hung on the wall behind them
//   ignite    on T.ignite the line's last word turns the accent, a beat before the cut
//   split     light everywhere, an ink copy through masks.png wherever the picture under the line is light
//   frame 0   when the window starts the video, OPEN stands big behind the head on frame 0 only (OPEN_UNTIL_FRAMES):
//             the thumbnail. Scaled like the camera's opening settle, split by wall.png and knocked out by the frame-0
//             cutout (knock0.png), since a cutout window can't start on frame 0. OPEN_UNTIL_FRAMES 0 drops it
// Built on the kit's kinetic-hook-front. mkmask.py writes the masks from this project's own footage.
// PRESET CONSTANTS START
// [plain, the word that lights], set in caps by the CSS; [] = no proof line (only the frame-0 line). Only true facts:
// count the raw files and ffprobe their joined length
var LINE = ["3 takes · 2:40 · edited by ", "Claude"];
var T = {"ignite": 2.333};                    // seconds after A, or a spoken word: the hook line's last word
var BAND = {"top": 222, "height": 44};        // px: the proof line's band on the frame (the line stands 33 px into it)
// null: line one is OPEN, set from the four constants below. Or the id of a behind-the-head hook effect whose line one
// sits at #<id>-lt .<id>-l0: frame 0 then copies its words, size and place, and mkmask.py its wall mask
var OPEN_FROM = null;
var OPEN = "WATCH THIS";                      // line one on frame 0 (the thumbnail), in the display face
var OPEN_SIZE = 470;                          // px: its size (a wider display face sets it smaller, to OPEN_MAXW)
var OPEN_BASE = 622;                          // px: its baseline (the head should break its foot)
var OPEN_MAXW = 940;                          // px: the widest it may run
var OPEN_UNTIL_FRAMES = 1;                    // frames line one holds from frame 0 (0 = none)
var CAM_OPEN = 1.04;                          // the camera's scale on frame 0: edit.CAMERA["open"][0] (kit default 1.04)
var MASK = {"lo": 92, "hi": 124, "blur": 1.0};   // mkmask.py: the light/ink ramp under the lines (luma 0-255)
// PRESET CONSTANTS END

// ---- beats: a time in T is seconds after A, or a spoken word ('reel', 'reel+0.02'), read off words.json once here
function cues(v, after) {
  if (typeof v === 'string') {
    var m = /^(.*?)([+-]\d*\.?\d+)?$/.exec(v.trim()), t = wordAt(m[1], A + (after || 0));
    if (t === null && after) t = wordAt(m[1], A);
    if (t === null) { console.error('{{ID}}: no spoken "' + m[1] + '" after ' + A); return after || 0; }
    return t - A + (m[2] ? parseFloat(m[2]) : 0);
  }
  if (Array.isArray(v)) {
    var f = after || 0;
    return v.map(function (x) { var r = cues(x, f); if (typeof r === 'number') f = r + 0.01; return r; });
  }
  if (v && typeof v === 'object') { var o = {}; for (var k in v) o[k] = cues(v[k], after); return o; }
  return v;
}
T = cues(T);
var OPEN_UNTIL = OPEN_UNTIL_FRAMES / 30;

function $(s) { return document.querySelector(s); }
function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

// ---- line one, frame 0 only
var carry = q(A) <= 0 && OPEN_UNTIL > 0;
if (!carry) { var big0 = $('#{{ID}}-big'); big0.parentNode.removeChild(big0); }
function hookLine() { return OPEN_FROM ? document.querySelector('#' + OPEN_FROM + '-lt .' + OPEN_FROM + '-l0') : null; }
function baseline(box) {                    // the baseline's distance from the top of a line box
  var t = box.querySelector('.{{ID}}-bt'), p = document.createElement('span');
  p.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline;';
  t.appendChild(p);
  var y = p.offsetTop;
  t.removeChild(p);
  return y;
}
function fitBig() {
  var h = hookLine();
  $$('#{{ID}} .{{ID}}-bln').forEach(function (box) {
    if (h && h.style.fontSize) {            // the hook effect's own fitted line: inside its slot, so add the slot's top
      box.querySelector('.{{ID}}-bt').textContent = h.querySelector('.' + OPEN_FROM + '-t').textContent;
      box.style.fontSize = h.style.fontSize;
      box.style.top = ((parseFloat(h.parentNode.style.top) || 0) + (parseFloat(h.style.top) || 0)).toFixed(1) + 'px';
      return;
    }
    box.querySelector('.{{ID}}-bt').textContent = OPEN;
    box.style.fontSize = OPEN_SIZE + 'px';
    var w = box.querySelector('.{{ID}}-bt').offsetWidth;
    if (w > OPEN_MAXW) box.style.fontSize = (OPEN_SIZE * OPEN_MAXW / w).toFixed(2) + 'px';
    box.style.top = (OPEN_BASE - baseline(box)).toFixed(1) + 'px';
  });
}
if (carry) {
  fitBig();
  if (document.fonts && document.fonts.load) {               // one step after a hook effect's own refit, whatever the order
    document.fonts.load(tok('--display-style') + ' ' + tok('--display-weight') + ' 100px ' + tok('--font-display'), OPEN)
      .catch(function () {}).then(function () {}).then(fitBig, fitBig);
    document.fonts.ready.then(function () {}).then(fitBig);
  }
  var cam = document.getElementById('cam');                       // scaled like the camera on frame 0, about its origin
  gsap.set('#{{ID}}-big', { scale: CAM_OPEN, transformOrigin: cam ? getComputedStyle(cam).transformOrigin : '540px 760px' });
  tl.set('#{{ID}}-big', { opacity: 0 }, q(A + OPEN_UNTIL));
}

// ---- the proof line
var band = $('#{{ID}}-band'), f0 = $('#{{ID}}-f0');
if (!LINE || !LINE.length) {
  band.parentNode.removeChild(band);
} else {
  band.style.top = BAND.top + 'px';
  band.style.height = BAND.height + 'px';
  $$('#{{ID}} .{{ID}}-cp').forEach(function (e) { e.style.height = BAND.height + 'px'; });
  var N = Math.max(1, Math.round(B * 30) - Math.round(A * 30));      // one copy (and one band of each sheet) per frame
  $$('#{{ID}} .{{ID}}-a').forEach(function (e) { e.textContent = LINE[0]; });
  $$('#{{ID}} .{{ID}}-c').forEach(function (e) { e.textContent = LINE[1] || ''; });
  for (var f = 1; f < N; f++) {
    var c = f0.cloneNode(true);
    c.id = '{{ID}}-f' + f;
    band.appendChild(c);
  }
  $$('#{{ID}} .{{ID}}-fr').forEach(function (fr, i) {                // frame i: band i of both sheets
    [fr, fr.querySelector('.{{ID}}-dk')].forEach(function (e) {
      e.style.webkitMaskPosition = '0px ' + (-i * BAND.height) + 'px';
      e.style.maskPosition = '0px ' + (-i * BAND.height) + 'px';
    });
  });
}
$$('#{{ID}} .{{ID}}-a, #{{ID}} .{{ID}}-c, #{{ID}} .{{ID}}-ln, #{{ID}} .{{ID}}-bt').forEach(function (e) {
  e.setAttribute('data-layout-allow-overlap', '');                  // the copies overlap and sit over the speaker on purpose
  e.setAttribute('data-layout-allow-occlusion', '');
});

// on from the very first frame (a set at time 0 does not render on a seek to 0); frame k shows copy k
if (q(A) <= 0) gsap.set('#{{ID}}', { opacity: 1 });
if (LINE && LINE.length) {
  gsap.set('#{{ID}} .{{ID}}-fr', { opacity: 0 });
  gsap.set('#{{ID}}-f0', { opacity: 1 });
  for (var k = 1; k < N; k++) {
    off('#{{ID}}-f' + (k - 1), A + k / 30);
    on('#{{ID}}-f' + k, A + k / 30);
  }
  // the last word lights up in the accent (the accent on light in the ink copies)
  var tIg = A + T.ignite;
  tl.fromTo('#{{ID}} .{{ID}}-lt .{{ID}}-c', { color: tok('--c-light') }, { color: tok('--c-accent'), duration: 0.12, ease: 'none', immediateRender: false }, q(tIg));
  tl.fromTo('#{{ID}} .{{ID}}-dk .{{ID}}-c', { color: tok('--c-ink') }, { color: tok('--c-accent-light'), duration: 0.12, ease: 'none', immediateRender: false }, q(tIg));
}
