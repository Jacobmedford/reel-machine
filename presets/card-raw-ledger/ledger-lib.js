/* card-raw-ledger helpers: easing curves, time labels, the waveform path and a baseline probe. Pure functions with no
   state of their own; index.html builds the card with them (the kit's dollar-split keeps its paint function the same
   way). */
window.LEDGER_LIB = (function () {
  function cl(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
  function p2o(p) { return 1 - (1 - p) * (1 - p); }
  function p3o(p) { return 1 - Math.pow(1 - p, 3); }
  function p2i(p) { return p * p; }
  function p3io(p) { return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; }
  function sio(p) { return -(Math.cos(Math.PI * p) - 1) / 2; }
  function back(p) { var c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); }
  function mmss(sec) { var r = Math.round(sec); return Math.floor(r / 60) + ':' + (r % 60 < 10 ? '0' : '') + (r % 60); }
  // a loudness envelope sampled 4 times a second, read between samples
  function ampAt(w, t) {
    var f = t * 4 - 0.5, i = Math.floor(f), r = f - i;
    var a = w[Math.max(0, Math.min(w.length - 1, i))], b = w[Math.max(0, Math.min(w.length - 1, i + 1))];
    return a + (b - a) * r;
  }
  // the envelope between t0 and t1 as a closed mirrored shape around (ox, oy), s px per second, amp px at full level
  function wave(w, t0, t1, ox, oy, minH, pad, amp, s) {
    var ts = [t0], k;
    for (k = Math.ceil(t0 * 4 - 0.5); (k + 0.5) / 4 < t1; k++) { var tc = (k + 0.5) / 4; if (tc > t0) ts.push(tc); }
    ts.push(t1);
    var top = [], bot = [];
    for (var j = 0; j < ts.length; j++) {
      var x = ox + (ts[j] - t0) * s, h = Math.max(minH, ampAt(w, ts[j]) * amp + pad);
      top.push(x.toFixed(2) + ' ' + (oy - h).toFixed(2));
      bot.push(x.toFixed(2) + ' ' + (oy + h).toFixed(2));
    }
    return 'M' + top.join(' L') + ' L' + bot.reverse().join(' L') + ' Z';
  }
  // where a line of type sits on its baseline, measured from the pack's own face
  function baseline(elm) {
    var probe = document.createElement('span'); probe.style.cssText = 'display:inline-block;width:0;height:0;';
    elm.appendChild(probe); var b = probe.offsetTop; elm.removeChild(probe); return b;
  }
  return { cl: cl, p2o: p2o, p3o: p3o, p2i: p2i, p3io: p3io, sio: sio, back: back, mmss: mmss, wave: wave, baseline: baseline };
})();
