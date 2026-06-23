#!/usr/bin/env python3
"""Arrange all sprites in a directory into a single labeled contact sheet."""
import os
from PIL import Image, ImageDraw, ImageFont

SRC = "/Users/tkwang/Match3_sim/godot_demo/resources/sprites"
OUT = "/Users/tkwang/Match3_sim/godot_demo/resources/sprites_contact_sheet.png"

CELL = 200          # thumbnail box size (px)
PAD = 12            # padding around each thumb
LABEL_H = 22        # label strip height
COLS = 8            # number of columns
BG = (32, 34, 40)   # dark background
FG = (235, 235, 235)

def load_font(size):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()

font = load_font(13)

files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".png"))
n = len(files)
rows = (n + COLS - 1) // COLS

cell_w = CELL + PAD * 2
cell_h = CELL + LABEL_H + PAD * 2

sheet_w = COLS * cell_w
sheet_h = rows * cell_h

sheet = Image.new("RGBA", (sheet_w, sheet_h), BG + (255,))
draw = ImageDraw.Draw(sheet)

for i, fname in enumerate(files):
    r, c = divmod(i, COLS)
    x0 = c * cell_w
    y0 = r * cell_h

    path = os.path.join(SRC, fname)
    try:
        img = Image.open(path).convert("RGBA")
    except Exception as e:
        print(f"skip {fname}: {e}")
        continue

    img.thumbnail((CELL, CELL), Image.LANCZOS)
    ix = x0 + PAD + (CELL - img.width) // 2
    iy = y0 + PAD + (CELL - img.height) // 2
    sheet.alpha_composite(img, (ix, iy))

    name = os.path.splitext(fname)[0]
    # truncate label if too wide
    label = name
    while draw.textlength(label, font=font) > CELL and len(label) > 3:
        label = label[:-2]
    if label != name:
        label = label[:-1] + "\u2026"
    tw = draw.textlength(label, font=font)
    tx = x0 + (cell_w - tw) // 2
    ty = y0 + PAD + CELL + 3
    draw.text((tx, ty), label, fill=FG, font=font)

sheet.convert("RGB").save(OUT)
print(f"wrote {OUT} ({sheet_w}x{sheet_h}), {n} sprites in {rows}x{COLS} grid")
