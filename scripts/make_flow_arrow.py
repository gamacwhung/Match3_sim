"""
產生「GIF → 報告」流程箭頭(透明背景,貼白底投影片用)。

箭頭上放最殺的速度數字「100 games · < 2s」,直接連起左邊 GIF(AI 玩)和右邊報告。
用法: python scripts/make_flow_arrow.py [輸出png] [--zh]
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(_ROOT, "godot_demo", "resources", "fonts", "NotoSansTC-Regular.otf")
MONO = "C:/Windows/Fonts/consolab.ttf"

INK = (32, 33, 36)
DIM = (120, 124, 130)
GBLUE = (66, 133, 244)
WHITE = (255, 255, 255)

ZH = "--zh" in sys.argv


def _font(p, s):
    try:
        return ImageFont.truetype(p, s)
    except Exception:
        return ImageFont.load_default()


def _ctext(d, cx, y, text, font, fill):
    bb = d.textbbox((0, 0), text, font=font)
    d.text((cx - (bb[2] - bb[0]) / 2, y), text, font=font, fill=fill)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.join(_ROOT, "flow_arrow.png")

    W, H = 400, 170
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    f_top = _font(FONT_PATH, 24)
    f_big = _font(MONO, 30)
    f_bot = _font(FONT_PATH, 19)

    # 上方標籤：AI 自動試玩
    _ctext(d, W / 2, 4, "AI 自動試玩" if ZH else "AI auto-plays", f_top, INK)

    # 箭頭(藍,圓角身體 + 三角頭)
    cy = 92
    bh = 58
    head_w = 52
    body_r = bh // 2
    d.rounded_rectangle([6, cy - bh // 2, W - head_w, cy + bh // 2], radius=body_r, fill=GBLUE)
    d.polygon([(W - head_w - 2, cy - bh // 2 - 12), (W - 6, cy), (W - head_w - 2, cy + bh // 2 + 12)],
              fill=GBLUE)

    # 箭頭上：最殺速度數字
    _ctext(d, (W - head_w) / 2 + 3, cy - 18, "100 場 · < 2 秒" if ZH else "100 games · < 2s", f_big, WHITE)

    # 下方標籤：即時產出報告
    _ctext(d, W / 2, cy + bh // 2 + 16, "即時產出平衡報告" if ZH else "instant balance report", f_bot, DIM)

    img.save(out)
    print(f"已輸出: {out}  ({W}x{H}, 透明背景)")


if __name__ == "__main__":
    main()
