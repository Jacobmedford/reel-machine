/* Shared "dollar" layout for the dollar-split pair: index.html (the split) and index-followup.html (the split shifts).
   One layout, one paint function: both cards build the same SVG and differ only in the state they feed paint(), so
   the last frame of index.html and the first frame of index-followup.html match pixel for pixel. Keep it that way:
   anything visual that both cards show belongs in this file.

   The 100-cent bar is a real one-dollar bill (bill.jpg, a public-domain scan). Each share tints the bill at render
   time: an SVG colour-matrix filter multiplies the scan by the share's token colour, so the engraving reads through
   the ink. Tints are revealed cent by cent through stair-shaped clips. The bill can be cut at the boundary B: two
   pieces, each moved half the gap g outward, carrying their tag, number and label.

   Shares: left = the ink share (--c-ink on a light ground, --c-light on a dark one), right = the accent share
   (--c-accent), cents the left share loses = --c-neg. Every colour and font comes from brand.css + card.css. */
(function () {
  var NS = 'http://www.w3.org/2000/svg';
  var root = document.getElementById('root');
  function tok(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  // the example's words (both cards show them)
  var WORDS = { left: 'to you', right: 'to costs', whole: '$1.00' };

  // layout (px, 1080x1920 canvas)
  var L = {
    x0: 90, cw: 9, n: 100,            // 100 cents, 9px pitch -> x 90..990 (the bill)
    top: 584, h: 386,                 // bill y 584..970 (1780x764 scan, aspect kept)
    base: 540,                        // shared baseline of the two big numbers
    lSize: 230, rSize: 150,           // left / right number sizes (fit() shrinks them for wide display faces)
    tagW: 3, pad: 18,                 // the 3px tag and the text indent after it
    labBase: 1030, labSize: 40,       // the two share labels under the bill
    brY: 1096, brTick: 18, brSize: 34,// the $1.00 dimension bracket
    gap: 14,                          // the cut opens to 14px
    lowB: 45, highB: 60,              // the boundary range the pair shows: the numbers are sized to fit at both ends
    right: 1010                       // right edge of the content area
  };
  L.x1 = L.x0 + L.cw * L.n;
  L.bot = L.top + L.h;
  L.r = parseFloat(tok('--radius')) || 0;

  // token names for this card's ground
  var DARK = root.classList.contains('ground-dark');
  var K = {
    ink: DARK ? '--c-light' : '--c-ink',                 // the ink share: its tint, tag, number and label
    acc: '--c-accent',                                   // the accent share's tint
    accT: DARK ? '--c-accent' : '--c-accent-light',      // the accent share's tag, number and label
    neg: '--c-neg',                                      // the lost cents' tint
    muted: DARK ? '--c-muted-dark' : '--c-muted-light',
    hair: DARK ? '--c-hair-dark' : '--c-hair-light',
    ground: DARK ? '--c-dark' : '--c-light'
  };
  function v(name) { return 'var(' + name + ')'; }

  // a colour token as [r, g, b] in 0..1, flattened onto the ground (so translucent tokens work too)
  var px = document.createElement('canvas'); px.width = px.height = 1;
  var g2 = px.getContext('2d', { willReadFrequently: true });
  function channels(name) {
    g2.clearRect(0, 0, 1, 1);
    g2.fillStyle = tok(K.ground); g2.fillRect(0, 0, 1, 1);
    g2.fillStyle = tok(name); g2.fillRect(0, 0, 1, 1);
    var d = g2.getImageData(0, 0, 1, 1).data;
    return [d[0] / 255, d[1] / 255, d[2] / 255];
  }
  function lum(c) { return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }
  function lin(x) { return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }
  function contrast(a, b) {
    var A = 0.2126 * lin(a[0]) + 0.7152 * lin(a[1]) + 0.0722 * lin(a[2]), B = 0.2126 * lin(b[0]) + 0.7152 * lin(b[1]) + 0.0722 * lin(b[2]);
    return (Math.max(A, B) + 0.05) / (Math.min(A, B) + 0.05);
  }
  // a colour token used for type on this ground: mixed toward the ink only as far as large type needs (WCAG 3:1),
  // so a pack whose accent is too light for its own ground still reads; packs that pass keep their colour exactly
  function legible(name) {
    var g = channels(K.ground), c = channels(name), t = channels(K.ink);
    for (var p = 0; p <= 100; p += 2) {
      var m = [c[0] + (t[0] - c[0]) * p / 100, c[1] + (t[1] - c[1]) * p / 100, c[2] + (t[2] - c[2]) * p / 100];
      if (contrast(m, g) >= 3.3) return p ? 'color-mix(in srgb, var(' + name + ') ' + (100 - p) + '%, var(' + K.ink + '))' : v(name);
    }
    return v(K.ink);
  }

  // the tint: bill luminance x share colour, normalised so the paper takes the colour exactly and the engraving
  // goes darker in the same hue. A colour too dark to show any engraving is lifted toward --c-light first.
  var PAPER = 0.84, MINL = 0.18;
  function tint(defs, id, name) {
    var c = channels(name), l = lum(c);
    if (l < MINL) {
      var w = channels('--c-light'), k = clamp((MINL - l) / Math.max(0.001, lum(w) - l));
      c = [c[0] + (w[0] - c[0]) * k, c[1] + (w[1] - c[1]) * k, c[2] + (w[2] - c[2]) * k];
    }
    var row = function (ch) {
      var s = ch / PAPER;
      return [0.2126 * s, 0.7152 * s, 0.0722 * s, 0, 0].map(function (n) { return n.toFixed(5); }).join(' ');
    };
    var f = el('filter', { id: id, x: 0, y: 0, width: 1, height: 1, 'color-interpolation-filters': 'sRGB' }, defs);
    el('feColorMatrix', { type: 'matrix', values: row(c[0]) + ' ' + row(c[1]) + ' ' + row(c[2]) + ' 0 0 0 1 0' }, f);
  }

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function clamp(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
  function cx(c) { return L.x0 + L.cw * c; }           // x of cent position c (fractional ok)

  var R = {};   // element refs

  // wait for the pack's fonts, then build: the number sizes are measured (hyperframes: build in the callback,
  // register the timeline at its end)
  function ready(cb) {
    var done = false, go = function () { if (!done) { done = true; cb(); } };
    if (!document.fonts || !document.fonts.load) return go();
    var faces = [
      tok('--display-style') + ' ' + tok('--display-weight') + ' ' + L.lSize + 'px ' + tok('--font-display'),
      '600 ' + L.labSize + 'px ' + tok('--font-text'),
      '500 ' + L.brSize + 'px ' + tok('--font-mono')
    ];
    Promise.all(faces.map(function (f) { return document.fonts.load(f, '0123456789$.¢ abcdefghijklmnopqrstuvwxyz'); }))
      .then(function () { return document.fonts.ready; }).then(go, go);
  }

  function build(svg) {
    var accType = legible(K.accT);               // the accent share's tag, number and label
    var defs = el('defs', {}, svg);
    tint(defs, 'tintInk', K.ink); tint(defs, 'tintNeg', K.neg); tint(defs, 'tintAcc', K.acc);
    el('rect', { x: L.x0, y: L.top, width: L.x1 - L.x0, height: L.h, rx: L.r }, el('clipPath', { id: 'cRound' }, defs));
    R.cL = el('rect', { x: L.x0 - 6, y: L.top - 6, width: 0, height: L.h + 12 }, el('clipPath', { id: 'cL' }, defs));
    R.cR = el('rect', { x: L.x0, y: L.top - 6, width: 0, height: L.h + 12 }, el('clipPath', { id: 'cR' }, defs));
    var tI = el('clipPath', { id: 'tI' }, defs), tN = el('clipPath', { id: 'tN' }, defs), tA = el('clipPath', { id: 'tA' }, defs);
    R.tI = el('path', { d: 'M0 0Z' }, tI);
    R.tN = el('path', { d: 'M0 0Z' }, tN);
    R.tNs = el('rect', { x: 0, y: L.top - 2, width: 0, height: L.h + 4 }, tN);
    R.tA = el('path', { d: 'M0 0Z' }, tA);

    // two pieces of one bill: identical stacks, each clipped to its side of the cut and moved by half the gap
    R.piece = {}; R.edge = {};
    ['L', 'R'].forEach(function (side) {
      var g = el('g', {}, svg);
      R.edge[side] = el('path', { d: '', fill: 'none', 'stroke-width': 1.5, style: 'stroke:' + v(K.hair) }, g);
      var inner = el('g', { 'clip-path': 'url(#cRound)' }, el('g', { 'clip-path': 'url(#c' + side + ')' }, g));
      var img = function (filter, clip) {
        var a = { href: 'bill.jpg', x: L.x0, y: L.top, width: L.x1 - L.x0, height: L.h, preserveAspectRatio: 'none' };
        if (filter) a.filter = 'url(#' + filter + ')';
        if (clip) a['clip-path'] = 'url(#' + clip + ')';
        return el('image', a, inner);
      };
      img(); img('tintInk', 'tI'); img('tintNeg', 'tN'); img('tintAcc', 'tA');
      R.piece[side] = g;
    });

    // 99 cent dividers: ink hairlines drawn down over the bare bill, ground-coloured rules rising with the tint
    var dg = el('g', {}, svg), rg = el('g', {}, svg);
    R.div = []; R.rule = [];
    for (var k = 1; k < L.n; k++) {
      var d10 = k % 10 === 0, w = d10 ? 1.5 : 1;
      R.div.push(el('rect', { x: cx(k) - w / 2, y: L.top, width: w, height: 0, 'fill-opacity': d10 ? 0.40 : 0.20, style: 'fill:' + v(K.ink) }, dg));
      R.rule.push(el('rect', { x: cx(k) - w / 2, y: L.bot, width: w, height: 0, 'fill-opacity': d10 ? 0.30 : 0.14, style: 'fill:' + v(K.ground) }, rg));
    }

    // the cut: a ground-coloured incision down the boundary, before the pieces part
    R.cut = el('rect', { x: 0, y: L.top, width: 2, height: 0, style: 'fill:' + v(K.ground) }, svg);

    // tags (3px coloured left border device), grow up from the bill
    R.lTag = el('rect', { x: L.x0 - 0.75, y: L.top, width: L.tagW, height: 0, style: 'fill:' + v(K.ink) }, svg);
    R.rTag = el('rect', { x: 0, y: L.top, width: L.tagW, height: 0, style: 'fill:' + accType }, svg);

    // big numbers in the display face, lining tabular figures
    var numStyle = function (size, col) { return 'font-size:' + size + 'px;fill:' + col + ';font-feature-settings:"lnum" 1,"tnum" 1;'; };
    R.lNumG = el('g', {}, svg);
    R.lNum = el('text', { x: 0, y: L.base, 'class': 'display', style: numStyle(L.lSize, v(K.ink)) }, R.lNumG);
    R.rNumG = el('g', {}, svg);
    R.rNum = el('text', { x: 0, y: L.base, 'class': 'display', style: numStyle(L.rSize, accType) }, R.rNumG);

    // labels under the bill
    var labStyle = function (col) { return 'font-size:' + L.labSize + 'px;font-weight:600;letter-spacing:-0.01em;fill:' + col + ';'; };
    R.lLab = el('text', { x: 0, y: L.labBase, 'class': 'text', style: labStyle(v(K.ink)) }, svg);
    R.lLab.textContent = WORDS.left;
    R.rLab = el('text', { x: 0, y: L.labBase, 'class': 'text', style: labStyle(accType) }, svg);
    R.rLab.textContent = WORDS.right;

    // $1.00 dimension bracket under everything: hairline, end ticks up, label in a gap
    var mid = (L.x0 + L.x1) / 2;
    var ln = function () { return el('line', { x1: 0, y1: 0, x2: 0, y2: 0, 'stroke-width': 1.5, style: 'stroke:' + v(K.muted) }, svg); };
    R.brL = ln(); R.brR = ln(); R.brTL = ln(); R.brTR = ln();
    R.brLab = el('text', { x: mid, y: L.brY + 12, 'text-anchor': 'middle', 'class': 'mono', style: 'font-size:' + L.brSize + 'px;font-weight:500;letter-spacing:0.02em;fill:' + v(K.ink) + ';' }, svg);
    R.brLab.textContent = WORDS.whole;
    R.mid = mid;

    fit();
  }

  // size the numbers to the pack's display face: the left one must clear the right tag when the cut sits at its
  // lowest boundary, the right one the content edge at its highest; the 230:150 hierarchy is kept
  function fit() {
    var w = function (t, size) { t.textContent = '00¢'; return t.getComputedTextLength() / size; };
    var lw = w(R.lNum, L.lSize), rw = w(R.rNum, L.rSize), open = L.gap / 2;
    var lRoom = (cx(L.lowB) + open - 24) - (L.x0 - 0.75 - open + L.tagW + L.pad);
    var rRoom = L.right - (cx(L.highB) + open + L.tagW + L.pad);
    var ratio = L.rSize / L.lSize;
    if (lw > 0) L.lSize = Math.min(L.lSize, Math.floor(lRoom / lw));
    if (rw > 0) L.rSize = Math.min(L.rSize, Math.floor(rRoom / rw));
    L.rSize = Math.min(L.rSize, Math.round(L.lSize * ratio));
    R.lNum.style.fontSize = L.lSize + 'px';
    R.rNum.style.fontSize = L.rSize + 'px';
    R.lNum.textContent = ''; R.rNum.textContent = '';
  }

  function num(x, pad) {
    var n = Math.round(x);
    return (pad && n < 10 ? ' ' : '') + n + '¢';
  }

  // one closed stair polygon for the cents rising under f(i) (no inner edges, so no seams)
  function stair(f) {
    if (!f) return 'M0 0Z';
    var e = 2, H = L.h + 2 * e, yb = L.bot + e, d = 'M' + (L.x0 - e) + ' ' + yb, any = false;
    for (var i = 0; i < L.n; i++) {
      var y0 = clamp(f(i)); if (y0 < 0.0005) y0 = 0; else any = true;
      var y = (yb - H * y0).toFixed(2);
      d += 'L' + (i === 0 ? L.x0 - e : cx(i)) + ' ' + y + 'L' + (i === L.n - 1 ? L.x1 + e : cx(i + 1)) + ' ' + y;
    }
    return any ? d + 'L' + (L.x1 + e) + ' ' + yb + 'Z' : 'M0 0Z';
  }
  function edgePath(side, xc) {
    var r = L.r, t = L.top, b = L.bot;
    return side === 'L'
      ? 'M' + xc + ' ' + t + 'H' + (L.x0 + r) + 'A' + r + ' ' + r + ' 0 0 0 ' + L.x0 + ' ' + (t + r) + 'V' + (b - r) + 'A' + r + ' ' + r + ' 0 0 0 ' + (L.x0 + r) + ' ' + b + 'H' + xc
      : 'M' + xc + ' ' + t + 'H' + (L.x1 - r) + 'A' + r + ' ' + r + ' 0 0 1 ' + L.x1 + ' ' + (t + r) + 'V' + (b - r) + 'A' + r + ' ' + r + ' 0 0 1 ' + (L.x1 - r) + ' ' + b + 'H' + xc;
  }

  /* s = {
       div(k) -> 0..1 ink divider k (1..99) drawn down from the bill top,
       ink(i), acc(i), neg(i) -> 0..1 tint of cent i rising from the bill bottom (null = none),
       negSpan: [c0, c1] full-height negative span in cents (the follow-up: the lost cents), or null,
       B: boundary in cents (right tag, cut), cut: 0..1 incision drawn down, g: gap in px (0..L.gap),
       lNum, rNum: values shown, lA, lY, rA, rY: number opacity / y offset, lTag, rTag: tag growth 0..1,
       lLabA, lLabY, rLabA, rLabY: label opacity / y offset, br: bracket draw 0..1, brA: bracket label opacity } */
  function paint(s) {
    var i, k, g = s.g || 0, half = g / 2, xb = cx(s.B);

    // pieces: clip each stack to its side of the cut, then move it half the gap outward
    R.cL.setAttribute('width', (xb - (L.x0 - 6)).toFixed(3));
    R.cR.setAttribute('x', xb.toFixed(3)); R.cR.setAttribute('width', (L.x1 + 6 - xb).toFixed(3));
    R.piece.L.setAttribute('transform', 'translate(' + (-half).toFixed(3) + ',0)');
    R.piece.R.setAttribute('transform', 'translate(' + half.toFixed(3) + ',0)');
    R.edge.L.setAttribute('d', edgePath('L', xb.toFixed(3)));
    R.edge.R.setAttribute('d', edgePath('R', xb.toFixed(3)));

    // tints
    R.tI.setAttribute('d', stair(s.ink));
    R.tN.setAttribute('d', stair(s.neg));
    R.tA.setAttribute('d', stair(s.acc));
    if (s.negSpan && s.negSpan[1] - s.negSpan[0] > 0.0005) {
      R.tNs.setAttribute('x', (cx(s.negSpan[0]) - (s.negSpan[0] <= 0 ? 2 : 0)).toFixed(3));
      R.tNs.setAttribute('width', (L.cw * (s.negSpan[1] - s.negSpan[0])).toFixed(3));
    } else R.tNs.setAttribute('width', 0);

    // how far each cent is tinted (for the rules)
    var T = [];
    for (i = 0; i < L.n; i++) {
      var tv = Math.max(s.ink ? s.ink(i) : 0, s.acc ? s.acc(i) : 0, s.neg ? s.neg(i) : 0);
      if (s.negSpan && i + 1 > s.negSpan[0] && i < s.negSpan[1]) tv = 1;
      T[i] = clamp(tv);
    }
    for (k = 1; k < L.n; k++) {
      var dv = R.div[k - 1], ru = R.rule[k - 1];
      var side = k < s.B - 0.001 ? -half : (k > s.B + 0.001 ? half : 0);
      var onCut = g > 0.01 && Math.abs(k - s.B) * L.cw < 1.5;   // a rule on the cut sits in the gap: drop it
      var w = k % 10 === 0 ? 1.5 : 1, x = (cx(k) - w / 2 + side).toFixed(3);
      var hr = onCut ? 0 : L.h * Math.min(T[k - 1], T[k]);
      var hd = onCut ? 0 : Math.max(0, Math.min(L.h * clamp(s.div(k)), L.h - hr));
      dv.setAttribute('x', x); dv.setAttribute('height', hd.toFixed(3));
      ru.setAttribute('x', x); ru.setAttribute('y', (L.bot - hr).toFixed(3)); ru.setAttribute('height', hr.toFixed(3));
    }

    // the incision: drawn down the boundary, gone once the gap is open
    var ch = L.h * clamp(s.cut || 0);
    R.cut.setAttribute('x', (xb - 1).toFixed(3));
    R.cut.setAttribute('height', ch.toFixed(3));
    R.cut.setAttribute('opacity', clamp(1 - g / 3).toFixed(3));

    // tags: rise from the bill top to just above the cap height of each number; ride their pieces
    var kk = clamp(g / L.gap);
    var lx = L.x0 - 0.75 - half, rx = xb - L.tagW / 2 + kk * (L.gap / 2 + L.tagW / 2);
    var lTop = L.base - 0.65 * L.lSize - 10, rTop = L.base - 0.65 * L.rSize - 10;
    var lh = (L.top - lTop) * s.lTag, rh = (L.top - rTop) * s.rTag;
    R.lTag.setAttribute('x', lx.toFixed(3)); R.lTag.setAttribute('y', L.top - lh); R.lTag.setAttribute('height', lh);
    R.rTag.setAttribute('x', rx.toFixed(3)); R.rTag.setAttribute('y', L.top - rh); R.rTag.setAttribute('height', rh);
    var lText = lx + L.tagW + L.pad, rText = rx + L.tagW + L.pad;

    R.lNum.textContent = num(s.lNum, true);
    R.lNum.setAttribute('x', lText.toFixed(3));
    R.lNumG.setAttribute('opacity', s.lA);
    R.lNumG.setAttribute('transform', 'translate(0,' + s.lY.toFixed(3) + ')');
    R.rNum.textContent = num(s.rNum, true);
    R.rNum.setAttribute('x', rText.toFixed(3));
    R.rNumG.setAttribute('opacity', s.rA);
    R.rNumG.setAttribute('transform', 'translate(0,' + s.rY.toFixed(3) + ')');

    R.lLab.setAttribute('x', lText.toFixed(3));
    R.lLab.setAttribute('opacity', s.lLabA);
    R.lLab.setAttribute('transform', 'translate(0,' + s.lLabY.toFixed(3) + ')');
    R.rLab.setAttribute('x', rText.toFixed(3));
    R.rLab.setAttribute('opacity', s.rLabA);
    R.rLab.setAttribute('transform', 'translate(0,' + s.rLabY.toFixed(3) + ')');

    // bracket draws outward from the label gap to the outer edges of the (cut) bill, then the end ticks rise
    var mid = R.mid, gp = 74, xl = L.x0 - half, xr = L.x1 + half, run = (mid - gp) - xl;
    var pl = clamp(s.br / 0.8), pt = clamp((s.br - 0.7) / 0.3), vis = s.br > 0.001 ? 1 : 0;
    var set = function (e, x1, y1, x2, y2, o) { e.setAttribute('x1', x1); e.setAttribute('y1', y1); e.setAttribute('x2', x2); e.setAttribute('y2', y2); e.setAttribute('opacity', o); };
    set(R.brL, mid - gp, L.brY, (mid - gp - run * pl).toFixed(3), L.brY, vis);
    set(R.brR, mid + gp, L.brY, (mid + gp + run * pl).toFixed(3), L.brY, vis);
    set(R.brTL, xl.toFixed(3), L.brY + 0.75, xl.toFixed(3), (L.brY + 0.75 - (L.brTick + 0.75) * pt).toFixed(3), pt > 0 ? 1 : 0);
    set(R.brTR, xr.toFixed(3), L.brY + 0.75, xr.toFixed(3), (L.brY + 0.75 - (L.brTick + 0.75) * pt).toFixed(3), pt > 0 ? 1 : 0);
    R.brLab.setAttribute('opacity', s.brA);
  }

  window.Dollar = { L: L, ready: ready, build: build, paint: paint, clamp: clamp };
})();
