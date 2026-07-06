"""產生「內部關卡編輯器」面板示意圖（向上報告用）。

目標：看起來像遊戲公司內部關卡設計師實際在用的工具面板——
專業深色 IDE 風、真實 sprite 畫的盤面、真實 AI 自動測試數據。
不是攤位那種給訪客的簡化介面（拿掉快捷範本/簡單選項）。

輸出：level_editor_mockup.png
用法：python scripts/level_editor_mockup.py
"""
from __future__ import annotations

import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / 'scripts'))

from match3_env import Match3Env                          # noqa: E402
from level_generator.sim_runner import run_simulation_batch  # noqa: E402
from PIL import Image, ImageDraw, ImageFont                # noqa: E402

LEVEL = _ROOT / 'levels' / 'level_03.json'
SPRITE_DIR = _ROOT / 'godot_demo' / 'resources' / 'sprite_512'
FONT = str(_ROOT / 'godot_demo' / 'resources' / 'fonts' / 'NotoSansTC-Regular.otf')
MONO = 'C:/Windows/Fonts/consola.ttf'

# 深色 IDE 配色
BG = (18, 20, 24)
PANEL = (30, 34, 41)
PANEL2 = (24, 27, 33)
LINE = (45, 50, 58)
FG = (210, 216, 224)
DIM = (138, 147, 160)
ACCENT = (88, 166, 255)
GREEN = (63, 185, 80)
ORANGE = (219, 154, 56)
RED = (229, 83, 75)
PUR = (165, 122, 245)


def F(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


_sprite_cache: dict = {}


def sprite(tile_id: str, size: int):
    key = (tile_id, size)
    if key in _sprite_cache:
        return _sprite_cache[key]
    p = SPRITE_DIR / f'{tile_id}.png'
    if not p.exists():
        _sprite_cache[key] = None
        return None
    im = Image.open(p).convert('RGBA').resize((size, size), Image.LANCZOS)
    _sprite_cache[key] = im
    return im


def main():
    data = json.loads(LEVEL.read_text(encoding='utf-8'))
    env = Match3Env(level_file=str(LEVEL))
    env.reset()
    board = env.board
    rows, cols = board.rows, board.cols

    # 真實 AI 自動測試
    res = run_simulation_batch(data, n_games=100, max_workers=4)

    W, H = 1600, 920
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    f_logo = F(FONT, 22)
    f_h = F(FONT, 18)
    f_t = F(FONT, 15)
    f_s = F(FONT, 13)
    f_mono = F(MONO, 13)
    f_big = F(MONO, 30)
    f_btn = F(FONT, 14)

    # ---- Toolbar ----
    d.rectangle([0, 0, W, 56], fill=(33, 38, 45))
    d.line([0, 56, W, 56], fill=LINE, width=1)
    d.rounded_rectangle([20, 14, 48, 42], radius=6, fill=ACCENT)
    d.text((26, 18), 'M3', font=F(FONT, 18), fill=(255, 255, 255))
    d.text((60, 16), 'Match3 關卡編輯器', font=f_logo, fill=FG)
    d.text((232, 22), 'Level Designer · 內部工具', font=f_s, fill=DIM)

    def btn(x, w, label, color, fill=False):
        if fill:
            d.rounded_rectangle([x, 12, x + w, 44], radius=6, fill=color)
            tc = (255, 255, 255)
        else:
            d.rounded_rectangle([x, 12, x + w, 44], radius=6, outline=color, width=1)
            tc = color
        bb = d.textbbox((0, 0), label, font=f_btn)
        d.text((x + (w - (bb[2] - bb[0])) / 2, 20), label, font=f_btn, fill=tc)

    btn(W - 360, 100, '＋ 新增障礙', DIM)
    btn(W - 250, 90, '✓ 驗證', GREEN)
    btn(W - 150, 130, '▶ 執行 AI 測試', ACCENT, fill=True)

    PAD = 16
    top = 56 + PAD

    # =========================================================
    # 左欄：關卡屬性 / 目標 / 圖層 / 障礙物調色盤
    # =========================================================
    lx0, lx1 = PAD, 330
    d.rounded_rectangle([lx0, top, lx1, H - PAD], radius=8, fill=PANEL)
    x = lx0 + 18
    y = top + 16
    d.text((x, y), '關卡屬性', font=f_h, fill=ACCENT)
    y += 32

    def field(label, value, vcolor=FG):
        nonlocal y
        d.text((x, y), label, font=f_s, fill=DIM)
        d.text((x + 96, y - 1), str(value), font=f_t, fill=vcolor)
        y += 26

    field('關卡 ID', f'#{data.get("level_id", 3):03d}')
    field('盤面尺寸', f'{rows} × {cols}')
    field('最大步數', data.get('max_steps', 30))
    field('顏色數', data.get('num_colors', 4))
    field('難度標籤', res.difficulty_label().split('（')[0], ORANGE)

    y += 10
    d.line([x, y, lx1 - 18, y], fill=LINE, width=1)
    y += 14
    d.text((x, y), '通關目標', font=f_h, fill=ACCENT)
    y += 30
    for tid, need in (data.get('goals') or {}).items():
        sp = sprite(tid.split('_lv')[0] if sprite(tid, 26) is None else tid, 26) or sprite(tid, 26)
        if sp:
            img.paste(sp, (x, y - 4), sp)
        d.text((x + 34, y), tid, font=f_t, fill=FG)
        d.text((lx1 - 70, y), f'× {need}', font=f_t, fill=GREEN)
        y += 34

    y += 6
    d.line([x, y, lx1 - 18, y], fill=LINE, width=1)
    y += 14
    d.text((x, y), '圖層', font=f_h, fill=ACCENT)
    y += 30
    for name, on in [('middle  中層（障礙/元素）', True),
                     ('bottom  底層（水漥）', True),
                     ('upper   上層（繩索/泥）', False)]:
        c = GREEN if on else (70, 76, 86)
        d.ellipse([x, y + 2, x + 12, y + 14], fill=c)
        d.text((x + 22, y), name, font=f_s, fill=FG if on else DIM)
        y += 26

    y += 12
    d.text((x, y), '障礙物調色盤', font=f_h, fill=ACCENT)
    y += 30
    palette = ['Crt2', 'Barrel', 'TrafficCone_lv1', 'SalmonCan', 'Puddle_lv2', 'Rope_lv1']
    px = x
    for tid in palette:
        sp = sprite(tid, 40)
        d.rounded_rectangle([px, y, px + 46, y + 46], radius=6, fill=PANEL2, outline=LINE)
        if sp:
            img.paste(sp.resize((38, 38)), (px + 4, y + 4), sp.resize((38, 38)))
        px += 50
        if px > lx1 - 50:
            px = x
            y += 52

    # =========================================================
    # 中欄：盤面編輯區（真實 sprite）
    # =========================================================
    cx0, cx1 = lx1 + PAD, 1075
    d.rounded_rectangle([cx0, top, cx1, H - PAD], radius=8, fill=PANEL2)
    d.text((cx0 + 18, top + 14), '盤面編輯區', font=f_h, fill=ACCENT)
    d.text((cx0 + 140, top + 18), f'{rows}×{cols} · 點格子放置/移除物件', font=f_s, fill=DIM)

    avail_w = (cx1 - cx0) - 40
    avail_h = (H - PAD) - (top + 50) - 20
    cell = int(min(avail_w / cols, avail_h / rows))
    bw, bh = cell * cols, cell * rows
    bx = cx0 + ((cx1 - cx0) - bw) // 2
    by = top + 50 + ((avail_h) - bh) // 2 + 10
    # 盤面底
    d.rectangle([bx - 6, by - 6, bx + bw + 6, by + bh + 6], fill=(12, 14, 18))
    for r in range(rows):
        for c in range(cols):
            x0, y0 = bx + c * cell, by + r * cell
            shade = (26, 30, 37) if (r + c) % 2 == 0 else (30, 35, 43)
            d.rectangle([x0, y0, x0 + cell, y0 + cell], fill=shade)
            cellobj = board.get_cell(r, c)
            # 底層水漥
            bt = getattr(cellobj, 'bottom', None)
            if bt is not None:
                sp = sprite(bt.tile_id, cell - 6)
                if sp:
                    img.paste(sp, (x0 + 3, y0 + 3), sp)
            mid = getattr(cellobj, 'middle', None)
            if mid is not None:
                sp = sprite(mid.tile_id, cell - 8)
                if sp:
                    img.paste(sp, (x0 + 4, y0 + 4), sp)
            d.rectangle([x0, y0, x0 + cell, y0 + cell], outline=(40, 45, 54))
    # 座標尺
    for c in range(cols):
        d.text((bx + c * cell + cell / 2 - 4, by - 22), str(c), font=f_s, fill=DIM)
    for r in range(rows):
        d.text((bx - 18, by + r * cell + cell / 2 - 8), str(r), font=f_s, fill=DIM)

    # =========================================================
    # 右欄：AI 自動測試報告 / 驗證 / JSON
    # =========================================================
    rx0, rx1 = cx1 + PAD, W - PAD
    d.rounded_rectangle([rx0, top, rx1, H - PAD], radius=8, fill=PANEL)
    x = rx0 + 18
    y = top + 16
    d.text((x, y), 'AI 自動測試報告', font=f_h, fill=ACCENT)
    d.text((x + 150, y + 3), f'{res.n_games} 場 · 純邏輯', font=f_s, fill=DIM)
    y += 36

    # 三個大數字
    def stat(sx, big, label, color):
        d.text((sx, y), big, font=f_big, fill=color)
        d.text((sx + 2, y + 38), label, font=f_s, fill=DIM)

    stat(x, f'{res.win_rate:.0%}', 'AI 勝率', GREEN)
    stat(x + 150, f'{res.avg_steps_won:.1f}', '平均步數', ACCENT)
    stat(x + 310, f'{res.difficulty_label().split("（")[0]}', '難度', ORANGE) \
        if False else None
    d.text((x + 300, y), f'{res.min_steps}-{res.max_steps_seen}', font=f_big, fill=PUR)
    d.text((x + 302, y + 38), '步數範圍', font=f_s, fill=DIM)
    y += 78

    # 步數分布直方圖
    d.text((x, y), '步數分布（100 場）', font=f_t, fill=FG)
    y += 24
    hist = res.step_histogram or {}
    if hist:
        maxc = max(hist.values())
        keys = sorted(hist.keys())
        bw_ = min(34, int((rx1 - 30 - x) / max(len(keys), 1)))
        hx = x
        base = y + 90
        for k in keys:
            h = int(70 * hist[k] / maxc)
            d.rounded_rectangle([hx, base - h, hx + bw_ - 6, base], radius=3, fill=ACCENT)
            d.text((hx, base + 4), str(k), font=f_s, fill=DIM)
            hx += bw_
        y = base + 26

    y += 8
    d.line([x, y, rx1 - 18, y], fill=LINE, width=1)
    y += 14
    # 卡關點 + 驗證
    hg = res.hardest_goal()
    if hg and len(res.goal_stats) > 1:
        tid, st = hg
        d.text((x, y), '最難達成目標', font=f_t, fill=DIM)
        d.text((x + 110, y), f'{tid}  達成率 {st["met_rate"]:.0%}', font=f_t, fill=ORANGE)
        y += 28
    d.ellipse([x, y + 2, x + 12, y + 14], fill=GREEN)
    d.text((x + 22, y), '格式驗證通過　·　關卡可正常遊玩', font=f_t, fill=GREEN)
    y += 34

    d.line([x, y, rx1 - 18, y], fill=LINE, width=1)
    y += 14
    d.text((x, y), '關卡 JSON（節錄）', font=f_h, fill=ACCENT)
    y += 26
    d.rounded_rectangle([x, y, rx1 - 18, H - PAD - 16], radius=6, fill=(14, 16, 20))
    snippet = json.dumps({
        'level_id': data.get('level_id', 3),
        'rows': rows, 'cols': cols,
        'max_steps': data.get('max_steps'),
        'num_colors': data.get('num_colors', 4),
        'goals': data.get('goals'),
    }, ensure_ascii=False, indent=2)
    jy = y + 10
    for line in snippet.splitlines()[:14]:
        d.text((x + 12, jy), line, font=f_mono, fill=(150, 200, 160))
        jy += 18

    out = _ROOT / 'level_editor_mockup.png'
    img.save(out)
    print('OK ->', out)
    print(f'level_03 | 勝率 {res.win_rate:.0%} | 平均步數 {res.avg_steps_won:.1f}')


if __name__ == '__main__':
    main()
