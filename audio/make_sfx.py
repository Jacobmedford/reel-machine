#!/usr/bin/env python3
"""reel-machine sound effects, synthesized from scratch with numpy and scipy.

No samples, no recordings, no downloads: every file in audio/sfx/ is built here from sine waves, filtered noise and
envelopes with fixed seeds, so a run always writes the same bytes. That is what lets the kit publish them as CC0.

Output: 48 kHz, 16-bit, stereo WAVs, sample peak -3 dBFS, DC-free, faded at both ends.
After rendering, every file is read back and measured, and audio/SFX.md is rewritten from those measurements:
length, and the peak offset (start of the loudest 10 ms window). The kit starts a sound at event_time - peak so its
loudest moment lands on the visual event.

Run from the repo root:
  PY audio/make_sfx.py               render everything, rewrite SFX.md
  PY audio/make_sfx.py pop ding      render only these (SFX.md still covers every file in audio/sfx)
  PY audio/make_sfx.py --review      also draw dev/out/sfx_review.png (envelope + spectrogram per file)
"""
import os
import sys
import wave

import numpy as np
from scipy.signal import butter, fftconvolve, istft, resample_poly, sosfilt, stft

SR = 48000
PEAK_DBFS = -3.0
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sfx")
KIT = os.path.dirname(HERE)
REVIEW = os.path.join(KIT, "dev", "out", "sfx_review.png")
LEAD = 0.0015          # transients start 1.5 ms in, so the 2 ms file fade-in never touches their attack


# ---------------------------------------------------------------- building blocks

def ns(sec):
    return int(round(sec * SR))


def tvec(dur):
    return np.arange(ns(dur)) / SR


def gain(db):
    return 10 ** (db / 20)


def norm(x):
    return x / (np.abs(x).max() + 1e-12)


def rise(n):
    """raised cosine 0 -> 1 over n samples, first sample exactly 0"""
    return 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / max(n, 1))


def attack(t, a):
    """raised-cosine rise over a seconds (0 at t <= 0, 1 from t >= a)"""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(t / a, 0, 1))


def release(t, at, r):
    """1 until `at`, then a raised-cosine fall to 0 over r seconds"""
    return 1 - attack(t - at, r)


def ends(t, a, r):
    """taper both ends of an envelope: raised-cosine in over a seconds, out over the last r seconds"""
    return attack(t, a) * release(t, t[-1] - r, r)


def build(u, floor_db):
    """a riser's level: climbs from floor_db to 0 dB, steady in dB at first and steepening into the top"""
    return gain(floor_db * (1 - np.clip(u, 0, 1)) ** 1.25)


def phase(f, t):
    """running phase of an instantaneous frequency f (Hz, scalar or per-sample), 0 at the first sample"""
    f = np.broadcast_to(np.asarray(f, float), t.shape)
    return 2 * np.pi * (np.cumsum(f) - f[0]) / SR


def passby(t, tp, w1, w2, p=1.0):
    """a pass-by swell: 1 at tp, Lorentzian falloff of width w1 before the peak and w2 after it"""
    w = np.where(t < tp, w1, w2)
    return (1 + ((t - tp) / w) ** 2) ** -p


def filt(x, kind, fc, order=2):
    return sosfilt(butter(order, fc, kind, fs=SR, output="sos"), x, axis=-1)


def stereo(x):
    return np.vstack([x, x])


def pan(x, p):
    """constant-power pan, p from -1 (left) to 1 (right), scalar or per-sample; centre is unity in both channels"""
    th = (np.clip(p, -1, 1) + 1) * np.pi / 4
    return np.sqrt(2) * np.vstack([x * np.cos(th), x * np.sin(th)])


def wide(c, l, r, amt):
    """blend a shared signal with independent left/right ones; amt is the independent share of the power
    (0 = mono, 1 = fully decorrelated), so L/R correlation is 1 - amt and the mono fold-down never cancels"""
    a, b = np.sqrt(1 - amt), np.sqrt(amt)
    return np.vstack([a * c + b * l, a * c + b * r])


def put(dst, src, at):
    """mix src (mono or stereo) into dst starting at time `at`"""
    if src.ndim == 1:
        src = stereo(src)
    i = ns(at)
    m = min(src.shape[1], dst.shape[1] - i)
    dst[:, i:i + m] += src[:, :m]


def _at(v, tt):
    return v(tt) if callable(v) else np.full_like(tt, float(v))


def steady(y, hold):
    """flatten slow level wobble so the caller's envelope alone sets the loudness contour"""
    n = max(ns(hold), 3)
    w = np.hanning(n + 2)[1:-1]
    e = np.convolve(y * y, w / w.sum(), mode="same")
    return y / np.sqrt(e + 1e-9 * e.max())


def band_noise(rs, dur, fc, width, nfft=1024, lo=25.0, hi=15000.0, hold=0.02):
    """noise on a log-frequency Gaussian band: centre fc Hz and width octaves, each a constant or a function of time
    (that is the filter sweep). Unit power throughout; the caller multiplies by the amplitude envelope."""
    N = ns(dur)
    pad = nfft + 2 * ns(hold)
    x = rs.standard_normal(N + 2 * pad)
    f, tt, Z = stft(x, fs=SR, nperseg=nfft, noverlap=nfft - nfft // 4)
    tt = tt - pad / SR
    F = np.maximum(f, 1.0)[:, None]
    c = _at(fc, tt)[None, :]
    w = _at(width, tt)[None, :]
    M = np.exp(-0.5 * (np.log2(F / c) / w) ** 2) / np.sqrt(1 + (lo / F) ** 4) / np.sqrt(1 + (F / hi) ** 8)
    M = M / np.sqrt((M ** 2).sum(0, keepdims=True) + 1e-20)
    _, y = istft(Z * M, fs=SR, nperseg=nfft, noverlap=nfft - nfft // 4)
    y = steady(y[:N + 2 * pad], hold)
    return y[pad:pad + N]


def modes(t, specs, rs, a=0.0004):
    """struck resonances: specs = [(Hz, decay tau s, amp)], random phases, raised-cosine attack a"""
    y = np.zeros_like(t)
    for f, tau, amp in specs:
        y += amp * np.sin(2 * np.pi * f * t + rs.uniform(0, 2 * np.pi)) * np.exp(-t / tau)
    return y * attack(t, a)


def burst(rs, t, tau, lo, hi, a=0.0003):
    """a band-passed noise tap with an exponential decay"""
    x = rs.standard_normal(len(t)) * np.exp(-t / tau) * attack(t, a)
    return filt(x, "bandpass", [lo, hi])


def saw(f0, t, cutoff, kmax=80, at=None):
    """band-limited sawtooth built from harmonics, each scaled by a smooth low-pass at `cutoff` (Hz, may move),
    and nothing above 18 kHz, so it cannot alias however the pitch moves. `at` (s): phase zero falls there, so
    detuned voices given the same `at` all line up, and their beating crests, at that moment"""
    ph = phase(f0, t)
    if at is not None:
        ph = ph - ph[min(ns(at), len(t) - 1)]
    f0 = np.broadcast_to(np.asarray(f0, float), t.shape)
    co = np.broadcast_to(np.asarray(cutoff, float), t.shape)
    y = np.zeros_like(t)
    for k in range(1, kmax + 1):
        fk = k * f0
        g = np.clip((18000 - fk) / 2000, 0, 1) / np.sqrt(1 + (fk / co) ** 4)
        if g.max() < 1e-4:
            break
        y += g * np.sin(k * ph) / k
    return y


def warm(x, drive):
    """gentle tanh saturation at 4x oversampling: adds harmonics so low hits still read on phone speakers"""
    up = resample_poly(norm(x), 4, 1)
    return resample_poly(np.tanh(drive * up) / np.tanh(drive), 1, 4)[:len(x)]


def room(x2, rs, rt, lp=5000.0, pre=0.01, mix=-14.0):
    """a small synthetic stereo room: decaying noise impulse responses, highs dying faster than lows.
    mix is the wet level in dB relative to the dry signal's RMS"""
    n = ns(rt * 1.2)
    t = np.arange(n) / SR
    wet = []
    for ch in range(2):
        a, b = rs.standard_normal(n), rs.standard_normal(n)
        ir = filt(a, "lowpass", 1500) * 10 ** (-3 * t / rt) + filt(b, "highpass", 1500) * 10 ** (-3 * t / (0.5 * rt))
        ir = filt(ir, "lowpass", lp) * attack(t, 0.004)
        ir = np.concatenate([np.zeros(ns(pre)), ir])
        wet.append(fftconvolve(x2[ch], ir)[:x2.shape[1]])
    wet = np.vstack(wet)
    return x2 + gain(mix) * wet * np.sqrt((x2 ** 2).mean() / ((wet ** 2).mean() + 1e-20))


def finish(x2, fin=0.002, fout=0.005):
    """DC-free (20 Hz high-pass), raised-cosine fades at both ends, sample peak at PEAK_DBFS"""
    x2 = filt(np.asarray(x2, float), "highpass", 20.0)
    a, b = ns(fin), ns(fout)
    x2[:, :a] *= rise(a)
    x2[:, -b:] *= rise(b)[::-1]
    return x2 * gain(PEAK_DBFS) / np.abs(x2).max()


# ---------------------------------------------------------------- the sounds

def whoosh():
    rs = np.random.default_rng(101)
    D, tp = 1.0, 0.55
    t = tvec(D)

    def env(tt):
        return passby(tt, tp, 0.13, 0.085, 1.15)

    def sweep(tt):
        k = env(tt) ** 0.7
        return np.where(tt < tp, 240 * (1100 / 240) ** k, 300 * (1100 / 300) ** k)

    A = env(t) * ends(t, 0.12, 0.2)
    p = 0.45 * np.tanh((t - tp) / 0.12)                     # passes left to right as it peaks
    body = band_noise(rs, D, 85, 0.9, nfft=4096, hold=0.08) * A ** 1.25
    air = [band_noise(rs, D, sweep, 1.15) * A for _ in range(3)]
    air = pan(air[0], p) * np.sqrt(0.75) + 0.5 * np.vstack(air[1:])
    top = band_noise(rs, D, 3000, 0.7) * A ** 2.2
    return stereo(body) + 0.17 * air + 0.035 * pan(top, 1.4 * p)


def whoosh_soft():
    rs = np.random.default_rng(102)
    D, tp = 0.8, 0.42
    t = tvec(D)

    def env(tt):
        return passby(tt, tp, 0.10, 0.08, 1.3)

    def sweep(tt):
        k = env(tt) ** 0.7
        return np.where(tt < tp, 1500 * (2800 / 1500) ** k, 1900 * (2800 / 1900) ** k)

    A = env(t) * ends(t, 0.1, 0.15)
    p = -0.4 * np.tanh((t - tp) / 0.1)                      # right to left: heading back
    body = band_noise(rs, D, 80, 0.9, nfft=4096, hold=0.08) * A ** 1.2
    air = [band_noise(rs, D, sweep, 1.1) * A ** 1.4 for _ in range(3)]
    air = pan(air[0], p) * np.sqrt(0.65) + np.sqrt(0.35) * np.vstack(air[1:])
    mid = band_noise(rs, D, 450, 0.8) * A ** 1.5
    return stereo(body) + 0.09 * air + 0.07 * stereo(mid)


def whoosh_deep():
    rs = np.random.default_rng(103)
    D, tp = 1.1, 0.45
    t = tvec(D)

    def env(tt):
        return passby(tt, tp, 0.12, 0.14, 1.1)

    def sweep(tt):
        k = env(tt) ** 0.7
        return np.where(tt < tp, 180 * (850 / 180) ** k, 230 * (850 / 230) ** k)

    A = env(t) * ends(t, 0.12, 0.25)
    ph = phase(40 + 28 * A ** 1.5, t)                        # the sub rises into the pass and sinks after it
    sub = (np.sin(ph) + 0.2 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)) * A ** 1.4
    low = band_noise(rs, D, 110, 1.0, nfft=4096, hold=0.08) * A ** 1.2
    mid = [band_noise(rs, D, sweep, 0.9) * A ** 1.3 for _ in range(3)]
    mid = pan(mid[0], 0.25 * np.tanh((t - tp) / 0.12)) * np.sqrt(0.7) + np.sqrt(0.3) * np.vstack(mid[1:])
    air = band_noise(rs, D, 2400, 0.8) * A ** 2
    return stereo(0.9 * sub + 0.7 * low + 0.02 * air) + 0.17 * mid


def whoosh_long():
    rs = np.random.default_rng(104)
    D, tp = 3.0, 2.4
    t = tvec(D)

    def env(tt):
        u = np.clip(tt / tp, 0, 1)
        pre = 0.65 * gain(-36 * (1 - u) ** 1.4) + 0.35 * passby(tt, tp, 0.06, 0.06)   # long build, sharp pass
        return np.where(tt < tp, pre, passby(tt, tp, 0.1, 0.1, 1.3))

    def sweep(tt):
        k = env(tt) ** 0.6
        return np.where(tt < tp, 220 * (2200 / 220) ** k, 500 * (2200 / 500) ** k)

    def width(tt):
        return 1.3 - 0.55 * env(tt)                          # the band narrows and focuses as it builds

    A = env(t) * ends(t, 0.1, 0.25)
    # the shared part pans across the climax; the independent parts widen the field as it builds
    c, l, r = (band_noise(rs, D, sweep, width) * A for _ in range(3))
    sh = pan(c, 0.5 * np.tanh((t - tp) / 0.15))
    amt = 0.15 + 0.4 * A ** 0.5
    main = np.sqrt(1 - amt) * sh + np.sqrt(amt) * np.vstack([l, r])
    rumble = band_noise(rs, D, 70, 0.8, nfft=4096, hold=0.1) * A ** 1.2
    ph = phase(36 + 20 * A, t)
    sub = (np.sin(ph) + 0.25 * np.sin(2 * ph)) * A ** 1.5
    air = band_noise(rs, D, 4500, 0.8) * A ** 2
    return stereo(0.7 * rumble + 0.6 * sub + 0.03 * air) + 0.17 * main


def pop():
    rs = np.random.default_rng(105)
    D = 0.22
    t = tvec(D)
    ph = phase(440 + 620 * (1 - np.exp(-t / 0.011)), t)     # a bubble: the pitch flicks up as it pops
    a = attack(t, 0.0015)
    y = a * (np.exp(-t / 0.020) * np.sin(ph) + 0.12 * np.exp(-t / 0.010) * np.sin(2 * ph))
    return room(stereo(y), rs, rt=0.15, lp=4000, pre=0.006, mix=-16)


def click():
    rs = np.random.default_rng(106)
    t = tvec(0.12)
    tt = np.maximum(t - LEAD, 0)
    snap = norm(burst(rs, tt, 0.0008, 1800, 9000))
    snap2 = norm(burst(rs, np.maximum(t - LEAD - 0.009, 0), 0.0006, 2200, 9000))
    body = norm(modes(tt, [(1750, 0.005, 0.6), (3100, 0.003, 0.35), (540, 0.005, 0.12)], rs))
    return stereo(filt(snap + 0.7 * body + 0.25 * snap2, "lowpass", 11000))


def tick():
    rs = np.random.default_rng(107)
    t = tvec(0.09)
    tt = np.maximum(t - LEAD, 0)
    body = norm(modes(tt, [(2650, 0.0025, 1.0), (4300, 0.0018, 0.5), (6400, 0.0012, 0.3), (1150, 0.003, 0.25)], rs, 0.0003))
    snap = norm(burst(rs, tt, 0.0005, 2500, 11000))
    return stereo(body + 0.8 * snap)


def clicks_run():
    rs = np.random.default_rng(108)
    D = 2.5
    x = np.zeros((2, ns(D)))
    tt = tvec(0.06)
    kinds = [[(1500, .004, 1.0), (2700, .0025, .55), (4200, .0015, .35), (650, .005, .3)],
             [(1750, .0035, 1.0), (3050, .0022, .5), (4800, .0013, .3), (720, .005, .25)]]
    at, i = LEAD, 0
    while at < D - 0.04:
        d = rs.uniform(0.96, 1.04)
        c = norm(modes(tt, [(f * d, tau, a) for f, tau, a in kinds[i % 2]], rs, 0.0003))
        c = c + 0.6 * norm(burst(rs, tt, 0.0005, 2500, 9000))
        g = 1.0 if i == 0 else gain(rs.uniform(-4.5, -2.5))  # the first clack leads, so the peak is the start
        put(x, pan(c * g, rs.uniform(-0.3, 0.3)), at)
        at += 1 / 19 + rs.uniform(-0.006, 0.006)
        i += 1
    return x


def ding():
    rs = np.random.default_rng(109)
    D, f0 = 1.4, 1760.0
    t = tvec(D)
    a = attack(t, 0.0015)
    out = []
    for side in (-1, 1):
        y = np.exp(-t / 0.26) * np.sin(2 * np.pi * f0 * t)
        y += 0.16 * np.exp(-t / 0.14) * np.sin(2 * np.pi * (2 * f0 + 0.5 * side) * t)   # a slow shimmer between sides
        y += 0.05 * np.exp(-t / 0.06) * np.sin(2 * np.pi * 2.76 * f0 * t)
        y += 0.02 * np.exp(-t / 0.025) * np.sin(2 * np.pi * 5.4 * f0 * t)
        out.append(y * a)
    strike = norm(filt(rs.standard_normal(len(t)) * np.exp(-t / 0.0012) * attack(t, 0.0003), "lowpass", 6000))
    return (np.vstack(out) + 0.06 * stereo(strike)) * release(t, D - 0.35, 0.35)


def shutter():
    rs = np.random.default_rng(110)
    D = 0.2
    x = np.zeros((2, ns(D)))
    tt = tvec(0.1)

    def clack(b):
        m = modes(tt, [(1300 * b, .005, 1), (2600 * b, .003, .6), (4400 * b, .002, .4), (240, .009, .25)], rs, 0.0003)
        return 0.8 * norm(m) + norm(burst(rs, tt, 0.0012, 1500, 8000))

    for at, g, b, p in [(LEAD, 1.0, 1.0, -0.08), (0.009, 0.3, 1.1, -0.05), (0.064, 0.72, 1.15, 0.08),
                        (0.071, 0.25, 1.2, 0.1), (0.078, 0.1, 1.25, 0.1)]:
        put(x, pan(g * clack(b), p), at)
    t = tvec(D)
    curtain = band_noise(rs, D, 4000, 0.6) * attack(t - 0.004, 0.01) * release(t, 0.06, 0.015)
    return x + 0.04 * stereo(curtain)


def stamp():
    rs = np.random.default_rng(111)
    D = 0.45
    t = tvec(D)
    tt = np.maximum(t - LEAD, 0)
    ph = phase(62 + 88 * np.exp(-tt / 0.03), t)             # 150 Hz dropping to 62 Hz
    thump = attack(tt, 0.0008) * (np.exp(-tt / 0.06) * np.sin(ph) + 0.3 * np.exp(-tt / 0.035) * np.sin(2 * ph))
    slap = norm(burst(rs, tt, 0.014, 700, 5500)) + 0.3 * norm(burst(rs, np.maximum(tt - 0.005, 0), 0.008, 900, 5000))
    knock = modes(tt, [(320, 0.025, 1.0), (610, 0.012, 0.4)], rs)
    y = norm(thump) + 0.75 * norm(slap) + 0.45 * norm(knock)
    return room(stereo(y), rs, rt=0.18, lp=3000, pre=0.004, mix=-16) * release(t, D - 0.1, 0.1)


def impact_low():
    rs = np.random.default_rng(112)
    D = 0.8
    t = tvec(D)
    tt = np.maximum(t - LEAD, 0)
    ph = phase(46 + 104 * np.exp(-tt / 0.04), t)            # 150 Hz falling to 46 Hz
    a = attack(tt, 0.001)
    sub = a * (np.exp(-tt / 0.13) * np.sin(ph) + 0.22 * np.exp(-tt / 0.07) * np.sin(2 * ph)
               + 0.08 * np.exp(-tt / 0.04) * np.sin(3 * ph))
    knock = filt(rs.standard_normal(len(t)) * np.exp(-tt / 0.005) * a, "lowpass", 1500)
    y = warm(norm(sub) + 0.18 * norm(knock), 1.6)
    return stereo(filt(y, "lowpass", 5000) * release(t, D - 0.2, 0.2))


def boom_low():
    rs = np.random.default_rng(113)
    D = 3.0
    t = tvec(D)
    tt = np.maximum(t - LEAD, 0)
    ph = phase(36 + 42 * np.exp(-tt / 0.45), t)             # 78 Hz sinking to 36 Hz
    a = attack(tt, 0.035)
    sub = a * (np.exp(-tt / 0.7) * np.sin(ph) + 0.25 * np.exp(-tt / 0.45) * np.sin(2 * ph)
               + 0.08 * np.exp(-tt / 0.3) * np.sin(3 * ph))
    bloom = attack(tt, 0.22) * np.exp(-np.maximum(tt - 0.22, 0) / 0.8)
    rum = [band_noise(rs, D, 70, 0.8, nfft=4096, hold=0.1) * bloom for _ in range(3)]
    thud = norm(filt(rs.standard_normal(len(t)) * attack(tt, 0.004) * np.exp(-tt / 0.04), "lowpass", 400))
    y = stereo(warm(sub, 1.3) + 0.15 * thud) + 0.25 * wide(*rum, 0.5)
    return y * release(t, D - 0.8, 0.8)


def riser():
    rs = np.random.default_rng(114)
    D, te = 1.0, 0.972
    t = tvec(D)
    u = np.clip(t / te, 0, 1)
    A = build(u, -40) * attack(t, 0.03) * release(t, te, 0.025)

    def sweep(tt):
        return 300 * (3500 / 300) ** (np.clip(tt / te, 0, 1) ** 1.3)

    n = [band_noise(rs, D, sweep, 0.9) * A for _ in range(3)]
    noise = wide(*n, 0.1 + 0.3 * u)
    f0 = 110 * 4 ** (u ** 1.6)
    co = 400 + 1800 * u ** 1.5
    tone = (pan(saw(f0 * 2 ** (7 / 1200), t, co, at=te) * A, -0.3)
            + pan(saw(f0 * 2 ** (-7 / 1200), t, co, at=te) * A, 0.3))
    sub = np.sin(phase(55 * 2 ** u, t)) * A
    return 0.28 * noise + 0.45 * tone / np.abs(tone).max() + 0.35 * stereo(sub)


def riser_long():
    rs = np.random.default_rng(115)
    D, te = 3.5, 3.46
    t = tvec(D)
    u = np.clip(t / te, 0, 1)
    A = build(u, -42) * attack(t, 0.25) * release(t, te, 0.03)
    depth = 0.35 * release(u, 0.85, 0.12)                    # the pulse quickens, then melts into the top
    trem = 1 - depth * (0.5 - 0.5 * np.cos(phase(3 + 10 * u ** 1.5, t)))
    f0 = 98 * 4 ** (u ** 1.8)
    co = 400 + 2400 * u ** 1.6
    tone = np.zeros((2, len(t)))
    for ratio, cents, p in [(1.0, 0, -0.15), (1.0, 9, 0.25), (1.5, -6, -0.3), (2.0, 5, 0.25)]:
        tone += pan(saw(f0 * ratio * 2 ** (cents / 1200), t, co, at=te) * A * trem, p)

    def sweep(tt):
        return 300 * (3500 / 300) ** (np.clip(tt / te, 0, 1) ** 1.3)

    n = [band_noise(rs, D, sweep, 1.0) * A for _ in range(3)]
    noise = wide(*n, 0.15 + 0.3 * u)
    sub = np.sin(phase(49 * 2 ** (0.4 * u), t)) * gain(-20 * (1 - u)) * attack(t, 0.25) * release(t, te, 0.03)
    return 0.6 * tone / np.abs(tone).max() + 0.22 * noise + 0.35 * stereo(sub)


def drum_hit():
    rs = np.random.default_rng(116)
    D = 1.45
    t = tvec(D)
    tt = np.maximum(t - LEAD, 0)
    ph = phase(88 + 50 * np.exp(-tt / 0.05), t)             # the skin's pitch bends from 138 Hz down to 88 Hz
    a = attack(tt, 0.0012)
    mem = np.zeros_like(t)
    for ratio, amp, tau in [(1.0, 1.0, 0.32), (1.59, 0.45, 0.17), (2.14, 0.32, 0.11), (2.30, 0.26, 0.09),
                            (2.65, 0.18, 0.07), (2.92, 0.12, 0.05), (3.16, 0.09, 0.045), (3.6, 0.12, 0.06),
                            (4.2, 0.09, 0.05), (5.1, 0.07, 0.04)]:
        mem += amp * np.exp(-tt / tau) * np.sin(ratio * ph + (0 if ratio == 1.0 else rs.uniform(0, 2 * np.pi)))
    shell = modes(tt, [(380, 0.06, 1.0), (610, 0.035, 0.5)], rs, 0.001)
    strike = filt(rs.standard_normal(len(t)) * np.exp(-tt / 0.005) * attack(tt, 0.0003), "lowpass", 3000)
    skin = burst(rs, tt, 0.05, 200, 1000)
    y = warm(norm(mem * a) + 0.5 * norm(strike) + 1.0 * norm(skin) + 0.3 * norm(shell), 1.5)
    return room(stereo(y), rs, rt=1.0, lp=3500, pre=0.012, mix=-12) * release(t, D - 0.3, 0.3)


def scratch():
    rs = np.random.default_rng(117)
    D = 0.42
    t = tvec(D)
    v = np.zeros_like(t)                                     # platter speed: forward, back, forward
    for t0, T, V in [(LEAD, 0.12, 2.5), (LEAD + 0.12, 0.15, -2.0), (LEAD + 0.27, 0.09, 1.4)]:
        m = (t >= t0) & (t < t0 + T)
        v[m] += V * np.sin(np.pi * (t[m] - t0) / T)
    pos = np.cumsum(v) / SR
    # the record: a sustained, slightly vocal tone, low-passed so even 2.5x speed stays under 18 kHz
    gt = tvec(1.2)
    src = saw(140 * (1 + 0.004 * np.sin(2 * np.pi * 5 * gt)), gt, 6000)
    g = sum(w * filt(src, "bandpass", [f / 1.25, f * 1.25]) for f, w in [(650, 1.0), (1100, 0.7), (2400, 0.3)])
    g = filt(g + 0.05 * rs.standard_normal(len(gt)), "lowpass", 7000, order=8)
    up = resample_poly(g, 4, 1)
    y = np.interp((0.6 + pos) * SR * 4, np.arange(len(up)), up)
    y = norm(y) * (np.abs(v) / np.abs(v).max()) ** 0.7

    def hiss_fc(tt):
        return 700 + 1800 * np.abs(np.interp(tt, t, v))

    hiss = band_noise(rs, D, hiss_fc, 0.8) * np.abs(v) / np.abs(v).max()
    return stereo(y + 0.12 * hiss)


def switch_off():
    rs = np.random.default_rng(118)
    D = 0.4
    t = tvec(D)
    tt = np.maximum(t - LEAD, 0)
    gate = np.zeros_like(t)
    f = np.full_like(t, 220.0)
    pans = np.zeros_like(t)
    for (a, b), fq, p in zip([(0.0, 0.028), (0.040, 0.062), (0.071, 0.086), (0.093, 0.103), (0.109, 0.115)],
                             [220, 233, 207, 247, 196], [0.0, -0.3, 0.3, -0.2, 0.2]):
        gate += attack(tt - a, 0.001) * release(tt, b - 0.001, 0.001)
        m = (tt >= a) & (tt < b)
        f[m], pans[m] = fq, p
    buzz = norm(saw(f, t, 4500)) * 0.6 + band_noise(rs, D, 2000, 1.0) * 0.25
    stutter = pan(buzz * gate * np.exp(-tt / 0.15), pans)
    ph = phase(30 + 1100 * np.exp(-tt / 0.05), t)           # the power-down: pitch collapses toward nothing
    fall = attack(tt, 0.003) * np.exp(-tt / 0.06) * (np.sin(ph) + 0.3 * np.sin(2 * ph))
    pop_ = burst(rs, tt, 0.02, 500, 7000)
    return (stutter + stereo(0.5 * fall + 0.4 * norm(pop_))) * release(t, D - 0.1, 0.1)


def keystroke(rs, space=False, body=0.25, release_at=None):
    """one key on a modern keyboard (mono, 0.16 s): the finger's soft tap, the bottom-out clack with a little body
    2.5 ms later, and a lighter release click as the key comes back up. space=True is the space bar: lower and
    heavier, with a short stabilizer rattle."""
    t = tvec(0.16)
    tt = np.maximum(t - LEAD, 0)
    d = rs.uniform(0.93, 1.07)                               # every key resonates a little differently
    if space:
        clack = [(1350 * d, .004, 1.0), (2300 * d, .003, .5), (5200 * d, .004, .12), (210 * d, .012, .15)]
        rel_at, rel_g = rs.uniform(0.07, 0.11), 0.4
    else:
        clack = [(2400 * d, .0035, 1.0), (3900 * d, .002, .7), (5600 * d, .0012, .3), (360 * d, .007, body)]
        rel_at, rel_g = rs.uniform(0.045, 0.085), 0.3
    hit = np.maximum(tt - 0.0025, 0)
    y = 0.35 * norm(burst(rs, tt, 0.0006, 1000, 6000)) + norm(modes(hit, clack, rs, 0.0003))
    y = y + 0.6 * norm(burst(rs, hit, 0.0007, 2000, 9000))
    if space:
        y = y + 0.3 * norm(burst(rs, np.maximum(hit - 0.004, 0), 0.001, 1500, 7000))
    rt = np.maximum(tt - (release_at or rel_at), 0)
    rel = norm(modes(rt, [(3200 * d, .0015, 1.0), (4800 * d, .001, .5)], rs, 0.0003))
    return y + rel_g * (rel + 0.6 * norm(burst(rs, rt, 0.0004, 2500, 10000)))


def key():
    rs = np.random.default_rng(119)
    return room(stereo(keystroke(rs, body=0.4, release_at=0.07)[:ns(0.12)]), rs, rt=0.15, lp=5000, pre=0.003, mix=-18)


def typing():
    rs = np.random.default_rng(120)
    D = 2.5
    x = np.zeros((2, ns(D)))
    at = LEAD
    while at < D - 0.17:
        for _ in range(rs.choice([2, 3, 3, 4, 4, 4, 5, 5, 6, 7, 8])):         # a word
            if at >= D - 0.17:
                break
            put(x, pan(gain(rs.uniform(-4, 0)) * keystroke(rs), rs.uniform(-0.3, 0.3)), at)
            fast = rs.uniform() < 0.15                                          # a quick letter pair
            at += rs.uniform(0.035, 0.055) if fast else np.clip(np.exp(rs.normal(np.log(0.085), 0.28)), 0.045, 0.16)
        if at >= D - 0.17:
            break
        at += 0.02                                                              # a beat before the space
        put(x, pan(gain(rs.uniform(0.5, 2.0)) * keystroke(rs, space=True), rs.uniform(-0.05, 0.05)), at)
        at += np.clip(np.exp(rs.normal(np.log(0.12), 0.25)), 0.08, 0.2)
        if rs.uniform() < 0.2:                                                  # now and then, a short pause
            at += rs.uniform(0.05, 0.12)
    return room(x, rs, rt=0.2, lp=5000, pre=0.003, mix=-16)                     # a desk in a room, not a vacuum


# name, generator, sounds like, an editor uses it when
SOUNDS = [
    ("whoosh", whoosh,
     "A dark air pass-by: swells, sweeps up as it passes and falls away, moving left to right",
     "a card or graphic cuts in"),
    ("whoosh-soft", whoosh_soft,
     "A lighter, airy pass-by with a soft low body, moving right to left",
     "cutting back to the speaker"),
    ("whoosh-deep", whoosh_deep,
     "A heavy whoosh: a sub that rises into the pass and sinks after it, low-mid air on top",
     "a heavy beat, a zoom, a hard cut"),
    ("whoosh-long", whoosh_long,
     "A 2.4 s build of rising, narrowing air and sub that peaks and drops away, widening as it grows",
     "building into a big transition"),
    ("pop", pop,
     "A short round bubble pop, pitch flicking up from about 440 Hz to 1 kHz, in a tiny room",
     "a chart point, tag or list item lands"),
    ("click", click,
     "A crisp, rounded UI click with a faint second tap",
     "a UI click, a text box appears"),
    ("tick", tick,
     "A light, bright tick, shorter and higher than the click",
     "one tick of a counter or clock (repeat it per tick)"),
    ("clicks-run", clicks_run,
     "A steady run of mechanical clacks, about 19 per second, first clack slightly accented",
     "a grid flipping, a counter rolling; trim it to the motion"),
    ("key", key,
     "One keystroke: a soft click with a little body, and a light release click 70 ms later",
     "a single key, an enter press"),
    ("typing", typing,
     "2.5 s of keyboard typing, about 10 keys a second in words, with a heavier space bar between them; no accent",
     "under on-screen typing: place it by its start and trim it to the text with max_len"),
    ("ding", ding,
     "A clean bell-like ding at 1.76 kHz with a soft octave shimmer and a 1 s ring",
     "a counter lands on its final value"),
    ("shutter", shutter,
     "A two-stage camera shutter: clack, then a lighter clack 60 ms later",
     "a screenshot or photo appears"),
    ("stamp", stamp,
     "A rubber stamp slam: short low thump with a paper slap on top",
     "a stamp, a verdict, an APPROVED lands"),
    ("impact-low", impact_low,
     "A short bass hit, 150 Hz dropping to 46 Hz, with a soft knock on the front",
     "a punchy accent, a word or number hits"),
    ("boom-low", boom_low,
     "A long sub boom that swells in over 0.15 s and rings down over about 2.5 s, 78 Hz sinking to 36 Hz",
     "under a big moment or reveal"),
    ("riser", riser,
     "A 1 s rising sweep (air, a two-voice tone and sub) that cuts off at its top",
     "the second before a hit or reveal"),
    ("riser-long", riser_long,
     "A 3.5 s suspense rise: a detuned chord climbing two octaves with a quickening pulse, air and sub",
     "building tension before a reveal"),
    ("drum-hit", drum_hit,
     "One big low drum (taiko-like) in a room",
     "the biggest number in the video"),
    ("scratch", scratch,
     "A short record-scratch gesture: forward, back, forward",
     "\"but here's the catch\""),
    ("switch-off", switch_off,
     "An electronic switch-off: a stuttering buzz and static that collapses into a falling tone",
     "a screen cuts out, a glitch-out"),
]


# ---------------------------------------------------------------- files, measurement, docs, review

def write_wav(path, x2):
    q = np.round(np.clip(x2, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(q.T.tobytes())


def read_wav(path):
    with wave.open(path) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), "<i2").astype(np.float64).reshape(-1, ch).T / 32768
    return x, sr


def measure(path):
    """length, sample peak, and the peak offset: start of the 10 ms window with the most energy (both channels)"""
    x, sr = read_wav(path)
    c = np.concatenate([[0.0], np.cumsum((x ** 2).sum(0))])
    k = int(0.010 * sr)
    win = c[k:] - c[:-k]
    return dict(x=x, sr=sr, length=x.shape[1] / sr, peak=int(np.argmax(win)) / sr,
                dbfs=20 * np.log10(np.abs(x).max() + 1e-12))


# starting gains (dB), from a finished hi-fi edit mixed to -14 LUFS (old levels moved by measured loudness offsets)
START_DB = {"whoosh": -14, "whoosh-soft": -19, "whoosh-deep": -16, "whoosh-long": -12, "pop": -19, "click": -16,
            "tick": -11, "clicks-run": -12, "ding": -20, "shutter": -14, "stamp": -12, "impact-low": -14,
            "boom-low": -17, "riser": -14, "riser-long": -12, "drum-hit": -12, "scratch": -8, "switch-off": -12,
            "key": -18, "typing": -11}


def write_md(rows):
    lines = [
        "# Sound effects",
        "",
        "Every file in `sfx/` was synthesized from scratch by `make_sfx.py` (numpy and scipy: sine waves, filtered noise,",
        "envelopes, fixed seeds). No samples, recordings or third-party sounds went into them.",
        "",
        "**License: CC0 1.0 Universal.** The sounds are dedicated to the public domain",
        "(https://creativecommons.org/publicdomain/zero/1.0/). Use them anywhere, commercially or not, no credit needed.",
        "",
        "Format: 48 kHz, 16-bit, stereo WAV. Every file peaks at -3 dBFS, so set the level per placement in the mix.",
        "",
        "**Peak** is the time from the start of the file to the start of its loudest 10 ms window (most energy, both",
        "channels), measured from the rendered file.",
        "`pipeline/mix.py` lines that moment up for you: give it the time of the visual event, not the file's start.",
        "",
        "**Start at** is a gain (dB) that sits the sound under a voice mixed to -14 LUFS, from a finished edit. Go",
        "quieter for a dense edit. `sound.sfx: light` in the style pack sits every effect 3 dB lower.",
        "",
        "| File | Sounds like | Use it when | Start at (dB) | Length (s) | Peak (s) |",
        "|---|---|---|---:|---:|---:|",
    ]
    for name, desc, use, m in rows:
        lines.append(f"| `{name}` | {desc} | {use} | {START_DB.get(name, -14)} | {m['length']:.2f} | {m['peak']:.3f} |")
    lines += [
        "",
        "Regenerate (writes the files and this table): `PY audio/make_sfx.py`.",
        "Add `--review` to draw `dev/out/sfx_review.png`, an envelope and spectrogram per file.",
        "",
    ]
    with open(os.path.join(HERE, "SFX.md"), "w") as fh:
        fh.write("\n".join(lines))


def review(rows, path):
    """contact sheet: per file, waveform with left/right level (dB) and a log-frequency spectrogram, peak in red"""
    from PIL import Image, ImageDraw, ImageFont

    W, H, LW, EW = 1600, 150, 200, 560
    SW = W - LW - EW - 30
    fnt = {s: ImageFont.load_default(s) for s in (11, 13, 18)}
    anchors = [(0.0, (0, 0, 4)), (0.2, (40, 11, 84)), (0.4, (101, 21, 110)), (0.6, (159, 42, 99)),
               (0.75, (212, 72, 66)), (0.88, (245, 125, 21)), (1.0, (252, 255, 164))]

    def colours(v):
        v = np.clip(v, 0, 1)
        return np.stack([np.interp(v, [a for a, _ in anchors], [c[i] for _, c in anchors]) for i in range(3)],
                        -1).astype(np.uint8)

    def spectrogram(m, sr, w, h, fmin=25, fmax=20000, rng=80):
        S = {}
        for nps in (512, 1024, 4096):
            f, tt, Z = stft(m, fs=sr, nperseg=nps, noverlap=nps - 64)
            S[nps] = (f, tt, 20 * np.log10(np.abs(Z) + 1e-12))
        top = max(v[2].max() for v in S.values())
        fr = fmin * (fmax / fmin) ** (1 - (np.arange(h) + 0.5) / h)
        tc = (np.arange(w) + 0.5) / w * len(m) / sr
        out = np.zeros((h, w))
        for row, fq in enumerate(fr):
            f, tt, Dm = S[4096 if fq < 300 else 1024 if fq < 2000 else 512]
            out[row] = Dm[min(int(round(fq / f[1])), len(f) - 1), np.clip(np.searchsorted(tt, tc), 0, len(tt) - 1)]
        return (out - (top - rng)) / rng

    def axis(d, x0, y0, w, dur):
        step = next(s for s in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0) if dur / s <= 8)
        for i in range(int(dur / step + 1e-9) + 1):
            px = x0 + i * step / dur * w
            d.line([(px, y0), (px, y0 + 4)], fill=(120, 120, 120))
            d.text((px - 8, y0 + 5), f"{i * step:g}", fill=(100, 100, 100), font=fnt[11])

    sheet = Image.new("RGB", (W, len(rows) * (H + 6)), (235, 233, 228))
    for r, (name, _, _, m) in enumerate(rows):
        x, sr = m["x"], m["sr"]
        N = x.shape[1]
        img = Image.new("RGB", (W, H), (250, 249, 246))
        d = ImageDraw.Draw(img)
        L, R = x
        corr = (L * R).sum() / np.sqrt((L * L).sum() * (R * R).sum() + 1e-20)
        d.text((10, 8), name, fill=(20, 20, 20), font=fnt[18])
        for i, (txt, col) in enumerate([(f"len  {m['length']:.3f}s", (60, 60, 60)), (f"peak {m['peak']:.3f}s", (190, 30, 30)),
                                        (f"max  {m['dbfs']:.1f} dBFS", (60, 60, 60)), (f"L/R corr {corr:.2f}", (60, 60, 60))]):
            d.text((10, 38 + 18 * i), txt, fill=col, font=fnt[13])
        ey, eh = 6, H - 26
        d.rectangle([LW, ey, LW + EW, ey + eh], fill=(255, 255, 255), outline=(200, 200, 200))
        mono = x.mean(0)
        cols = np.linspace(0, N, EW + 1).astype(int)
        mid = ey + eh / 2
        for i in range(EW):
            seg = mono[cols[i]:max(cols[i + 1], cols[i] + 1)]
            d.line([(LW + i, mid - seg.max() * eh / 2), (LW + i, mid - seg.min() * eh / 2)], fill=(200, 205, 215))
        k = int(0.010 * sr)
        top = np.convolve((x ** 2).sum(0), np.ones(k) / k, mode="same").max() / 2   # loudest 10 ms, per channel
        for ch, col in ((0, (30, 90, 200)), (1, (230, 120, 20))):
            db = 10 * np.log10(np.convolve(x[ch] ** 2, np.ones(k) / k, mode="same") / top + 1e-12)
            pts = [(LW + i, ey + np.clip(-db[min(int((i + 0.5) / EW * N), N - 1)] / 60, 0, 1) * eh) for i in range(EW)]
            d.line(pts, fill=col, width=2)
        axis(d, LW, ey + eh, EW, m["length"])
        d.line([(LW + m["peak"] / m["length"] * EW, ey), (LW + m["peak"] / m["length"] * EW, ey + eh)], fill=(200, 30, 30))
        sx = LW + EW + 20
        img.paste(Image.fromarray(colours(spectrogram(mono, sr, SW, eh))), (sx, ey))
        for fq, lab in ((100, "100"), (1000, "1k"), (10000, "10k")):
            py = ey + (1 - np.log(fq / 25) / np.log(20000 / 25)) * eh
            d.line([(sx, py), (sx + SW, py)], fill=(255, 255, 255))
            d.text((sx + 3, py - 14), lab, fill=(255, 255, 255), font=fnt[11])
        d.line([(sx + m["peak"] / m["length"] * SW, ey), (sx + m["peak"] / m["length"] * SW, ey + eh)], fill=(255, 60, 60))
        axis(d, sx, ey + eh, SW, m["length"])
        sheet.paste(img, (0, r * (H + 6)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    unknown = set(args) - {s[0] for s in SOUNDS}
    if unknown:
        sys.exit(f"unknown sound(s): {', '.join(sorted(unknown))}")
    os.makedirs(OUT, exist_ok=True)
    for name, fn, _, _ in SOUNDS:
        if not args or name in args:
            write_wav(os.path.join(OUT, f"{name}.wav"), finish(fn()))
    rows = []
    for name, _, desc, use in SOUNDS:
        p = os.path.join(OUT, f"{name}.wav")
        if os.path.exists(p):
            m = measure(p)
            rows.append((name, desc, use, m))
            print(f"{name:<12} {m['length']:5.2f} s   peak {m['peak']:.3f} s   {m['dbfs']:5.1f} dBFS")
    write_md(rows)
    if "--review" in sys.argv:
        review(rows, REVIEW)
        print(f"wrote {os.path.relpath(REVIEW, KIT)}")


if __name__ == "__main__":
    main()
