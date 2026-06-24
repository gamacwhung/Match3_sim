"""
產生動機頁「Watch → Play」對比圖(透明背景,貼白底投影片)。

左: 靜態內容(漫畫頁,muted) → 中: AI 箭頭 → 右: 可玩遊戲(真實糖果盤面)。
呼應「把 IP 從『看』變成『玩』」。

用法: python scripts/make_watchplay_image.py [輸出png] [--zh]
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(_ROOT, "godot_demo", "resources", "fonts", "NotoSansTC-Regular.otf")
ASSETS = os.path.join(_ROOT, "match3_board_component", "frontend", "assets")

INK = (32, 33, 36)
DIM = (130, 136, 146)
GBLUE = (66, 133, 244)
WHITE = (255, 255, 255, 255)
PAGE = (244, 245, 248, 255)
PANEL = (214, 219, 228, 255)     # muted 漫畫格
PANEL2 = (224, 228, 236, 255)
BOARDBG = (40, 33, 60, 255)
CELLBG = (54, 46, 78, 255)

ZH = "--zh" in sys.argv
_cache = {}


def F(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except Exception:
        return ImageFont.load_default()


def _ctext(d, cx, y, t, f, fill):
    bb = d.textbbox((0, 0), t, font=f)
    d.text((cx - (bb[2] - bb[0]) / 2, y), t, font=f, fill=fill)


def sprite(tid, cell):
    k = (tid, cell)
    if k in _cache:
        return _cache[k]
    p = os.path.join(ASSETS, f"{tid}.png")
    im = Image.open(p).convert("RGBA").resize((cell, cell), Image.LANCZOS) if os.path.exists(p) else None
    _cache[k] = im
    return im


def draw_comic(d, img, x, y, w, h):
    # 漫畫頁(靜態,muted):一個 page + 幾格 panel + 抽象人物(圈+身體)
    d.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=PAGE, outline=PANEL, width=2)
    m = 18
    gx, gy, gw, gh = x + m, y + m, w - 2 * m, h - 2 * m
    # 上排一大格、下排兩格
    d.rounded_rectangle([gx, gy, gx + gw, gy + gh * 0.46], radius=8, fill=PANEL2, outline=PANEL, width=2)
    d.rounded_rectangle([gx, gy + gh * 0.52, gx + gw * 0.48, gy + gh], radius=8, fill=PANEL2, outline=PANEL, width=2)
    d.rounded_rectangle([gx + gw * 0.54, gy + gh * 0.52, gx + gw, gy + gh], radius=8, fill=PANEL2, outline=PANEL, width=2)
    # 抽象人物(頭+身) 放上排,暗示角色
    hx, hy = gx + gw * 0.5, gy + gh * 0.12
    d.ellipse([hx - 16, hy, hx + 16, hy + 32], fill=(150, 158, 170, 255))
    d.rounded_rectangle([hx - 26, hy + 36, hx + 26, hy + gh * 0.30], radius=10, fill=(160, 168, 180, 255))


def draw_board(d, img, x, y, cell=52, pad=10):
    # 5x5 真實糖果盤面(可玩遊戲)
    pat = [
        ["Red", "Grn", "Blu", "Yel", "Red"],
        ["Yel", "Blu", "Red", "Grn", "Pur"],
        ["Grn", "Red", "Yel", "Blu", "Grn"],
        ["Blu", "Pur", "Grn", "Red", "Yel"],
        ["Red", "Yel", "Blu", "Grn", "Blu"],
    ]
    n = len(pat)
    bw = n * cell + pad * 2
    d.rounded_rectangle([x, y, x + bw, y + bw], radius=16, fill=BOARDBG, outline=(70, 60, 96, 255), width=2)
    for r in range(n):
        for c in range(n):
            cx0, cy0 = x + pad + c * cell, y + pad + r * cell
            d.rounded_rectangle([cx0 + 2, cy0 + 2, cx0 + cell - 2, cy0 + cell - 2], radius=6, fill=CELLBG)
            sp = sprite(pat[r][c], cell - 2)
            if sp:
                img.alpha_composite(sp, (int(cx0), int(cy0)))
    return bw


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.join(_ROOT, "watchplay.png")

    W, H = 1160, 430
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    f_lbl = F(40)
    f_sub = F(20)
    f_ai = F(22)

    # 左:WATCH
    lx, ly, lw, lh = 30, 90, 360, 290
    draw_comic(d, img, lx, ly, lw, lh)
    _ctext(d, lx + lw / 2, ly - 56, "WATCH", f_lbl, DIM)
    _ctext(d, lx + lw / 2, ly + lh + 12,
           "漫畫 · 角色 · 美術（看）" if ZH else "comics · characters · art  (passive)", f_sub, DIM)

    # 右:PLAY (真實盤面)
    bw = 5 * 52 + 2 * 10            # 盤面尺寸(n*cell + pad*2),直接算不畫
    rx = W - 30 - bw
    ry = ly + (lh - bw) // 2
    img2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img2)
    draw_board(d2, img2, rx, ry)
    img.alpha_composite(img2)
    _ctext(d, rx + bw / 2, ly - 56, "PLAY", f_lbl, GBLUE)
    _ctext(d, rx + bw / 2, ry + bw + 12,
           "可玩的互動小遊戲（玩）" if ZH else "interactive mini-game  (play)", f_sub, GBLUE)

    # 中:AI 箭頭
    ax1 = lx + lw + 24
    ax2 = rx - 24
    cy = ly + lh // 2
    d.line([(ax1, cy), (ax2 - 14, cy)], fill=GBLUE, width=6)
    d.polygon([(ax2 - 18, cy - 12), (ax2, cy), (ax2 - 18, cy + 12)], fill=GBLUE)
    # AI 膠囊
    pill_w = 64
    pcx = (ax1 + ax2) / 2
    d.rounded_rectangle([pcx - pill_w / 2, cy - 22, pcx + pill_w / 2, cy + 22], radius=22, fill=GBLUE)
    _ctext(d, pcx, cy - 15, "AI", f_ai, (255, 255, 255))

    img.save(out)
    print(f"已輸出: {out}  ({W}x{H}, 透明背景)")


if __name__ == "__main__":
    main()
