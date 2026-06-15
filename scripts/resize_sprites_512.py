#!/usr/bin/env python3
"""Resize all PNGs in sprites/ to 512x512 (aspect-preserving, transparent pad) into sprite_512/."""
import os
from PIL import Image

SRC = "/Users/tkwang/Match3_sim/godot_demo/resources/sprites"
DST = "/Users/tkwang/Match3_sim/godot_demo/resources/sprite_512"
SIZE = 512

os.makedirs(DST, exist_ok=True)

files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".png"))
for fname in files:
    img = Image.open(os.path.join(SRC, fname)).convert("RGBA")
    img.thumbnail((SIZE, SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ox = (SIZE - img.width) // 2
    oy = (SIZE - img.height) // 2
    canvas.alpha_composite(img, (ox, oy))
    canvas.save(os.path.join(DST, fname))
    print(f"{fname}: -> 512x512")

print(f"\ndone: {len(files)} files written to {DST}")
