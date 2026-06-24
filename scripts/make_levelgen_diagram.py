"""
產生「AI Level Generator」流程圖(透明背景,貼白底投影片用)。

故事: 我們餵大量知識(範例/規則/好玩度/格式) → Gemini 生成關卡 JSON →
       rule-based 驗證器檢查格式 → 過關就輸出;不過就回傳錯誤訊息讓 AI 修正重生(迴圈)。

用法: python scripts/make_levelgen_diagram.py [輸出png] [--zh]
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(_ROOT, "godot_demo", "resources", "fonts", "NotoSansTC-Regular.otf")

INK = (32, 33, 36)
DIM = (110, 116, 126)
GBLUE = (66, 133, 244)
GGREEN = (52, 168, 83)
GRED = (234, 67, 53)
GYELLOW = (244, 160, 0)
LINE = (170, 176, 188)
BOXBG = (255, 255, 255, 255)

ZH = "--zh" in sys.argv


def F(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except Exception:
        return ImageFont.load_default()


def box(d, x, y, w, h, title, tcolor, lines=None, border=LINE):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=BOXBG, outline=border, width=3)
    d.text((x + 16, y + 12), title, font=F(22), fill=tcolor)
    if lines:
        ly = y + 48
        for ln in lines:
            d.ellipse([x + 18, ly + 7, x + 24, ly + 13], fill=tcolor)
            d.text((x + 32, ly), ln, font=F(18), fill=INK)
            ly += 30
    return (x, y, w, h)


def harrow(d, x1, x2, y, color=LINE, width=4):
    d.line([(x1, y), (x2 - 10, y)], fill=color, width=width)
    d.polygon([(x2 - 12, y - 8), (x2, y), (x2 - 12, y + 8)], fill=color)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.join(_ROOT, "levelgen_diagram.png")

    W, H = 1200, 470
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    CY = 165
    # 1) 知識庫
    kn_title = "我們餵的知識" if ZH else "Domain knowledge we feed"
    kn = ([" 官方關卡範例", " 設計規則(層級/障礙/可達性)", " 好玩度原則", " JSON 格式規範"] if ZH
          else [" Example levels", " Design rules", " Fun heuristics", " JSON schema"])
    kx, kw, kh = 8, 300, 196
    box(d, kx, CY - kh // 2, kw, kh, kn_title, GBLUE, kn, border=GBLUE)

    # 2) Gemini
    gx, gw, gh = 360, 168, 96
    box(d, gx, CY - gh // 2, gw, gh,
        "Gemini", GBLUE,
        ["  生成關卡" if ZH else "  generates"], border=GBLUE)

    # 3) Level JSON
    jx, jw, jh = 580, 156, 96
    box(d, jx, CY - jh // 2, jw, jh, "Level JSON", INK,
        ["  關卡資料" if ZH else "  level data"])

    # 4) 驗證器
    vx, vw, vh = 792, 210, 96
    box(d, vx, CY - vh // 2, vw, vh,
        ("規則驗證器" if ZH else "Validator"), GYELLOW,
        [("  檢查格式/結構" if ZH else "  rule-based check")], border=GYELLOW)

    # 5) 通過 → 可玩關卡
    px, pw, ph = 1040, 152, 96
    box(d, px, CY - ph // 2, pw, ph,
        ("✓ 可玩關卡" if ZH else "✓ Playable"), GGREEN,
        [("  輸出" if ZH else "  shipped")], border=GGREEN)

    # 橫向箭頭
    harrow(d, kx + kw, gx, CY)
    harrow(d, gx + gw, jx, CY)
    harrow(d, jx + jw, vx, CY)
    harrow(d, vx + vw, px, CY, color=GGREEN)

    # 迴圈：驗證失敗 → 回 Gemini 修正重生(紅色,走下方)
    ly = CY + vh // 2 + 70
    vmidx = vx + vw // 2
    gmidx = gx + gw // 2
    d.line([(vmidx, CY + vh // 2), (vmidx, ly)], fill=GRED, width=4)
    d.line([(vmidx, ly), (gmidx, ly)], fill=GRED, width=4)
    d.line([(gmidx, ly), (gmidx, CY + gh // 2 + 1)], fill=GRED, width=4)
    d.polygon([(gmidx - 8, CY + gh // 2 + 12), (gmidx, CY + gh // 2), (gmidx + 8, CY + gh // 2 + 12)], fill=GRED)
    loop_txt = ("格式不符 → 回傳錯誤訊息，AI 自動修正重生"
                if ZH else "invalid → returns error messages, AI auto-fixes & regenerates")
    bb = d.textbbox((0, 0), loop_txt, font=F(20))
    tx = (vmidx + gmidx) / 2 - (bb[2] - bb[0]) / 2
    ty = ly + 8
    # 手繪紅 X(字型沒 ✗ 符號)
    d.line([(tx - 28, ty + 5), (tx - 14, ty + 21)], fill=GRED, width=3)
    d.line([(tx - 14, ty + 5), (tx - 28, ty + 21)], fill=GRED, width=3)
    d.text((tx, ty), loop_txt, font=F(20), fill=GRED)

    img.save(out)
    print(f"已輸出: {out}  ({W}x{H}, 透明背景)")


if __name__ == "__main__":
    main()
