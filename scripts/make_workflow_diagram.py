"""
產生「整體 workflow」流程圖(透明背景,貼白底投影片)。

故事: 傳統遊戲生產線(設計→美術→關卡→驗證→測試→調整→上線),
       我們用 AI 把中間最重的幾段自動化(對應 3 個 feature)。

用法: python scripts/make_workflow_diagram.py [輸出png] [--zh]
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(_ROOT, "godot_demo", "resources", "fonts", "NotoSansTC-Regular.otf")

INK = (32, 33, 36)
DIM = (120, 124, 130)
GBLUE = (66, 133, 244)
GGREEN = (52, 168, 83)
GRED = (234, 67, 53)
GYELLOW = (244, 160, 0)
GREY = (150, 156, 166)
LINE = (175, 181, 192)
WHITE = (255, 255, 255, 255)

ZH = "--zh" in sys.argv


def F(sz):
    try:
        return ImageFont.truetype(FONT, sz)
    except Exception:
        return ImageFont.load_default()


def _ctext(d, cx, y, text, font, fill):
    bb = d.textbbox((0, 0), text, font=font)
    d.text((cx - (bb[2] - bb[0]) / 2, y), text, font=font, fill=fill)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.join(_ROOT, "workflow_diagram.png")

    W, H = 1300, 470
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 6 段生產線:(標題, 副標, 邊框色, feature 標籤 or None)
    if ZH:
        stages = [
            ("遊戲設計", "人主導", GREY, None),
            ("美術", "IP/主題換皮", GBLUE, "Feature 1"),
            ("關卡", "一句話生成", GBLUE, "Feature 2"),
            ("驗證", "規則檢查", GBLUE, "Feature 2"),
            ("自動測試", "100場·<2秒", GGREEN, "Feature 3"),
            ("調整→上線", "人依數據平衡", GREY, None),
        ]
        bracket = "AI 自動化最重的幾段"
    else:
        stages = [
            ("Game Design", "human-led", GREY, None),
            ("Art", "theme re-skin", GBLUE, "Feature 1"),
            ("Levels", "1 sentence → level", GBLUE, "Feature 2"),
            ("Validate", "rule-based check", GBLUE, "Feature 2"),
            ("Auto-test", "100 runs · <2s", GGREEN, "Feature 3"),
            ("Tune → Ship", "human-led", GREY, None),
        ]
        bracket = "AI automates the heavy lifting"

    n = len(stages)
    bw, bh, gap = 178, 104, 26
    total = n * bw + (n - 1) * gap
    x0 = (W - total) // 2
    cy = 250

    # 上方括號:只蓋 AI 自動化的段(Art~Auto-test = idx 1~4),不含人工的 Tune&Ship
    bx1 = x0 + (bw + gap) - 8
    bx2 = x0 + 4 * (bw + gap) + bw
    byb = cy - bh // 2 - 40
    d.line([(bx1, byb + 14), (bx1, byb), (bx2, byb), (bx2, byb + 14)], fill=GBLUE, width=3)
    _ctext(d, (bx1 + bx2) / 2, byb - 30, bracket, F(24), GBLUE)

    # 畫各段
    for i, (title, sub, color, tag) in enumerate(stages):
        x = x0 + i * (bw + gap)
        y = cy - bh // 2
        d.rounded_rectangle([x, y, x + bw, y + bh], radius=14, fill=WHITE, outline=color, width=3)
        _ctext(d, x + bw / 2, y + 20, title, F(24), color if color != GREY else INK)
        _ctext(d, x + bw / 2, y + 56, sub, F(17), DIM)
        if tag:
            # feature 標籤(實心膠囊)
            tb = d.textbbox((0, 0), tag, font=F(15))
            tw = tb[2] - tb[0] + 20
            tcx = x + bw / 2
            d.rounded_rectangle([tcx - tw / 2, y - 16, tcx + tw / 2, y + 8], radius=12, fill=color)
            _ctext(d, tcx, y - 14, tag, F(15), (255, 255, 255))
        # 箭頭
        if i < n - 1:
            ax = x + bw
            d.line([(ax + 4, cy), (ax + gap - 8, cy)], fill=LINE, width=4)
            d.polygon([(ax + gap - 10, cy - 7), (ax + gap, cy), (ax + gap - 10, cy + 7)], fill=LINE)

    bot = cy + bh // 2
    lvx = x0 + 2 * (bw + gap) + bw // 2     # Levels 中心
    vx = x0 + 3 * (bw + gap) + bw // 2      # Validate 中心
    tsx = x0 + 5 * (bw + gap) + bw // 2     # Tune&Ship 中心

    # 迴圈 1(自動,F2 內部):驗證不過 → 叫 generator 重生
    ly1 = bot + 40
    ax1 = lvx + 26                          # 進 Levels 底部偏右
    d.line([(vx, bot), (vx, ly1)], fill=GBLUE, width=3)
    d.line([(vx, ly1), (ax1, ly1)], fill=GBLUE, width=3)
    d.line([(ax1, ly1), (ax1, bot + 1)], fill=GBLUE, width=3)
    d.polygon([(ax1 - 7, bot + 11), (ax1, bot), (ax1 + 7, bot + 11)], fill=GBLUE)
    _ctext(d, (vx + lvx) / 2 + 10, ly1 - 2,
           "驗證不過→自動重生" if ZH else "invalid → auto-regenerate", F(15), GBLUE)

    # 迴圈 2(人工):Tune&Ship 看數據 → 回頭調關卡重生
    ly2 = bot + 94
    ax2 = lvx - 26                          # 進 Levels 底部偏左
    d.line([(tsx, bot), (tsx, ly2)], fill=GREY, width=3)
    d.line([(tsx, ly2), (ax2, ly2)], fill=GREY, width=3)
    d.line([(ax2, ly2), (ax2, bot + 1)], fill=GREY, width=3)
    d.polygon([(ax2 - 7, bot + 11), (ax2, bot), (ax2 + 7, bot + 11)], fill=GREY)
    _ctext(d, (tsx + lvx) / 2, ly2 + 6,
           "人依數據判斷 → 調整 / 重生關卡" if ZH else "human reviews data → adjust & regenerate",
           F(17), INK)

    img.save(out)
    print(f"已輸出: {out}  ({W}x{H}, 透明背景)")


if __name__ == "__main__":
    main()
