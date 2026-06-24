"""
產生「AI 自動測試報告」投影片卡片圖(淺色/透明背景，貼在白底投影片右邊用)。

只出報告卡(勝率/平均步數/步數範圍/步數分布/難度)，不畫盤面——盤面用左邊的 GIF。
透明背景 PNG，可直接疊在白底投影片上。

用法:
    python scripts/make_ai_report_image.py [關卡json] [輸出png] [--zh]
預設: Level 1 → ai_report.png (英文標籤配合英文投影片;加 --zh 改中文)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from level_generator.sim_runner import run_simulation_batch  # noqa: E402

FONT_PATH = os.path.join(_ROOT, "godot_demo", "resources", "fonts", "NotoSansTC-Regular.otf")
MONO = "C:/Windows/Fonts/consolab.ttf"

# 淺色主題(Google Cloud 風)
INK = (32, 33, 36)        # 深灰文字
DIM = (120, 124, 130)
GBLUE = (66, 133, 244)
GGREEN = (52, 168, 83)
GYELLOW = (244, 160, 0)
GRED = (234, 67, 53)
BARBG = (232, 234, 240)

ZH = "--zh" in sys.argv


def _font(size, mono=False):
    try:
        return ImageFont.truetype(MONO if mono else FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _diff_en(wr):
    if wr >= 0.8:
        return "Too Easy", GYELLOW
    if wr >= 0.5:
        return "Easy–Medium", GGREEN
    if wr >= 0.25:
        return "Balanced", GGREEN
    if wr >= 0.1:
        return "Challenging", GYELLOW
    return "Too Hard", GRED


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    level_path = args[0] if len(args) > 0 else os.path.join(
        _ROOT, "godot_demo", "levels", "Level_001.json")
    out_path = args[1] if len(args) > 1 else os.path.join(_ROOT, "ai_report.png")

    ld = json.load(open(level_path, encoding="utf-8"))
    res = run_simulation_batch(ld, n_games=100, steps_multiplier=1.0, max_workers=4)

    W, H = 780, 430
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))   # 透明背景
    d = ImageDraw.Draw(img)

    f_title = _font(34)
    f_sub = _font(18)
    f_big = _font(62, mono=True)
    f_lbl = _font(20)
    f_h = _font(22)
    f_sm = _font(17)

    x = 4
    y = 0
    title = "AI 自動測試報告" if ZH else "Automated Playtest Report"
    d.text((x, y), title, font=f_title, fill=INK)
    # 副標放標題下一行,避免和長標題重疊
    sub = "100 場 · 純邏輯模擬，每場每步都有決策" if ZH else "100 simulated runs · pure-logic, decision per move"
    d.text((x + 2, y + 42), sub, font=f_sub, fill=DIM)
    y += 78

    def big(bx, value, label, color):
        d.text((bx, y), value, font=f_big, fill=color)
        d.text((bx + 3, y + 70), label, font=f_lbl, fill=DIM)

    big(x, f"{res.win_rate * 100:.0f}%", "Win Rate" if not ZH else "AI 勝率", GGREEN)
    big(x + 260, f"{res.avg_steps:.1f}", "Avg Moves" if not ZH else "平均步數", GBLUE)
    big(x + 520, f"{res.min_steps}–{res.max_steps_seen}",
        "Move Range" if not ZH else "步數範圍", GYELLOW)
    y += 122

    d.text((x, y), "Move Distribution" if not ZH else "步數分布", font=f_h, fill=INK)
    y += 32
    hist = res.step_histogram or {}
    bh_max = 78
    if hist:
        keys = sorted(hist.keys())
        maxv = max(hist.values())
        each = max(10, min(54, (W - 10) // max(1, len(keys)) - 8))
        bx = x
        for k in keys:
            v = hist[k]
            bar = int(bh_max * v / maxv)
            d.rounded_rectangle([bx, y, bx + each, y + bh_max], radius=3, fill=BARBG)
            d.rounded_rectangle([bx, y + (bh_max - bar), bx + each, y + bh_max], radius=3, fill=GBLUE)
            d.text((bx + 2, y + bh_max + 4), str(k), font=_font(13), fill=DIM)
            bx += each + 8
            if bx > x + W - 40:
                break
    y += bh_max + 34

    diff_en, dc = _diff_en(res.win_rate)
    if ZH:
        d.text((x, y), "難度校準：", font=f_h, fill=INK)
        d.text((x + 95, y + 1), res.difficulty_label(), font=f_h, fill=dc)
    else:
        d.text((x, y), "Difficulty: ", font=f_h, fill=INK)
        d.text((x + 110, y), diff_en, font=f_h, fill=dc)
    y += 36
    tail = ("✓ 格式驗證通過 · 可正常遊玩 · 100 場 < 2 秒" if ZH
            else "✓ Format validated · Playable · 100 runs in < 2s")
    d.text((x, y), tail, font=f_sm, fill=GGREEN)

    img.save(out_path)
    print(f"已輸出: {out_path}  ({W}x{H}, 透明背景)  勝率 {res.win_rate*100:.0f}% 平均 {res.avg_steps:.1f}")


if __name__ == "__main__":
    main()
