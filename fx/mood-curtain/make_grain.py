#!/usr/bin/env python3
"""Make grain.png, the film-grain tile mood-curtain lays over the moody look. Self-made and reproducible: seeded
noise from Python's own random module, written as a PNG with zlib, nothing else (no samples, no third-party
images, no dependencies). The same seed always gives the same file.

    python fx/<id>/make_grain.py [size] [seed]       default 512 px, seed 1729 -> fx/<id>/grain.png

The tile is grey (128 = no change under mix-blend-mode: overlay) with gaussian noise, softened by a small blur so it
reads as film grain rather than digital noise. fx.html repeats it over the frame and fx.js moves it every frame.
"""
import hashlib
import os
import random
import struct
import sys
import zlib


def grain(size, seed):
    rnd = random.Random(seed)
    px = [rnd.gauss(0.0, 1.0) for _ in range(size * size)]
    soft = []                                   # 3x3 blur, centre-weighted, wrapping so the tile repeats seamlessly
    for y in range(size):
        up, dn = ((y - 1) % size) * size, ((y + 1) % size) * size
        row = y * size
        for x in range(size):
            l, r = (x - 1) % size, (x + 1) % size
            soft.append((4 * px[row + x] + 2 * (px[row + l] + px[row + r] + px[up + x] + px[dn + x])
                         + px[up + l] + px[up + r] + px[dn + l] + px[dn + r]) / 16.0)
    sd = (sum(v * v for v in soft) / len(soft)) ** 0.5
    return bytes(max(0, min(255, int(round(128 + 42 * v / sd)))) for v in soft)


def png(path, size, grey):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + grey[y * size:(y + 1) * size] for y in range(size))
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 512
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1729
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grain.png")
    png(out, size, grain(size, seed))
    print(f"{out}: {size}x{size}, seed {seed}, sha256 {hashlib.sha256(open(out, 'rb').read()).hexdigest()[:16]}")


if __name__ == "__main__":
    main()
