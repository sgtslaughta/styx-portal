"""Shrink big PNGs in docs/assets/screens (palette quantise only when over the size budget)."""
import os, sys
from PIL import Image

d = sys.argv[1]
for f in sorted(os.listdir(d)):
    p = os.path.join(d, f)
    if f.endswith(".png") and os.path.getsize(p) > 1_200_000:
        Image.open(p).convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(p, optimize=True)
        print("optimised", f, os.path.getsize(p) // 1024, "KB")
