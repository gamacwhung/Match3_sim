"""產生「AI 關卡生成工具」面板示意圖（向上報告用）。

展示本專案的差異化：一句話設計需求 → AI 生成管線（理解→生成→驗證→AI自動試玩）
→ 產出已驗證、可遊玩的關卡。做成專業內部工具樣子（非攤位簡化版）。

盤面用真實 sprite、AI 測試用真實 100 場模擬數據。

輸出：generator_mockup.png
用法：python scripts/generator_mockup.py
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
SPRITE_DIR = _ROOT / 'match3_board_component' / 'frontend' / 'assets'  # 現在的 candy_cartoon 美術
FONT = str(_ROOT / 'godot_demo' / 'resources' / 'fonts' / 'NotoSansTC-Regular.otf')
MONO = 'C:/Windows/Fonts/consola.ttf'

BG = (18, 20, 24)
PANEL = (30, 34, 41)
PANEL2 = (24, 27, 33)
LINE = (45, 50, 58)
FG = (210, 216, 224)
DIM = (138, 147, 160)
ACCENT = (88, 166, 255)
GREEN = (63, 185, 80)
ORANGE = (219, 154, 56)
PUR = (165, 122, 245)


def F(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


_cache: dict = {}


def sprite(tid: str, size: int):
    key = (tid, size)
    if key in _cache:
        return _cache[key]
    p = SPRITE_DIR / f'{tid}.png'
    if not p.exists():
        _cache[key] = None
        return None
    im = Image.open(p).convert('RGBA').resize((size, size), Image.LANCZOS)
    _cache[key] = im
    return im


def main():
    data = json.loads(LEVEL.read_text(encoding='utf-8'))
    env = Match3Env(level_file=str(LEVEL))
    env.reset()
    board = env.board
    rows, cols = board.rows, board.cols
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
    f_btn = F(FONT, 15)

    # ---- Toolbar ----
    d.rectangle([0, 0, W, 56], fill=(33, 38, 45))
    d.line([0, 56, W, 56], fill=LINE, width=1)
    d.rounded_rectangle([20, 14, 48, 42], radius=6, fill=ACCENT)
    d.text((25, 18), 'M3', font=F(FONT, 18), fill=(255, 255, 255))
    d.text((60, 16), 'Match3 AI 關卡生成器', font=f_logo, fill=FG)
    d.text((268, 22), 'AI Level Generator · 內部工具', font=f_s, fill=DIM)
    d.ellipse([W - 150, 24, W - 138, 36], fill=GREEN)
    d.text((W - 128, 20), '模型已連線', font=f_s, fill=DIM)

    PAD = 16
    top = 56 + PAD

    # =========================================================
    # 左欄：設計需求 + 參數 + 生成按鈕 + Agent Pipeline
    # =========================================================
    lx0, lx1 = PAD, 560
    d.rounded_rectangle([lx0, top, lx1, H - PAD], radius=8, fill=PANEL)
    x = lx0 + 18
    y = top + 16
    d.text((x, y), '設計需求（自然語言規格）', font=f_h, fill=ACCENT)
    y += 30
    d.rounded_rectangle([x, y, lx1 - 18, y + 96], radius=6, fill=(14, 16, 20))
    spec = ['中難度關卡，木箱與鮪魚罐為主要障礙，2 種通關目標。',
            '鮪魚罐只能用道具清除，盤面需留出合成道具的空間。',
            '步數抓緊（最佳解的 1.3 倍），目標可達成、有挑戰但不卡死。']
    yy = y + 12
    for ln in spec:
        d.text((x + 12, yy), ln, font=f_t, fill=FG)
        yy += 26
    y += 112

    d.text((x, y), '生成參數', font=f_h, fill=ACCENT)
    y += 30
    params = [('盤面尺寸', f'{rows} × {cols}'), ('難度', 'medium'),
              ('顏色數', data.get('num_colors', 4)),
              ('障礙物', 'Crt2 · SalmonCan'), ('目標數', len(data.get('goals') or {}))]
    px = x
    for i, (k, v) in enumerate(params):
        col = i % 2
        cx = x + col * 260
        if col == 0 and i > 0:
            y += 30
        d.text((cx, y), k, font=f_s, fill=DIM)
        d.text((cx + 70, y - 1), str(v), font=f_t, fill=FG)
    y += 42

    d.rounded_rectangle([x, y, lx1 - 18, y + 40], radius=8, fill=ACCENT)
    d.text((x + 180, y + 9), '✨ 生成關卡', font=f_btn, fill=(255, 255, 255))
    y += 60

    d.line([x, y, lx1 - 18, y], fill=LINE, width=1)
    y += 14
    d.text((x, y), 'Agent Pipeline 執行紀錄', font=f_h, fill=ACCENT)
    d.text((x + 220, y + 3), '本次生成 · 端到端', font=f_s, fill=DIM)
    y += 32

    steps = [
        ('解析設計需求', '中難度 · 木箱+鮪魚罐 · 2 目標', '0.18s'),
        ('呼叫生成模型（Gemini）', '產出 8×8 盤面、目標與障礙佈局', '3.42s'),
        ('格式驗證（規則引擎）', '0 errors · 2 warnings · 通過', '0.04s'),
        (f'AI 自動試玩測試（{res.n_games} 場純邏輯）',
         f'勝率 {res.win_rate:.0%} · 平均 {res.avg_steps_won:.0f} 步', '1.51s'),
        ('關卡就緒', '已驗證、可遊玩', '總計 5.15s'),
    ]
    for i, (title, sub, t) in enumerate(steps):
        d.ellipse([x, y + 3, x + 16, y + 19], fill=GREEN)
        d.text((x + 5, y + 3), '✓', font=F(FONT, 12), fill=(255, 255, 255))
        d.text((x + 26, y), title, font=f_t, fill=FG)
        d.text((lx1 - 88, y + 1), t, font=f_mono, fill=ORANGE)
        d.text((x + 26, y + 20), sub, font=f_s, fill=DIM)
        if i < len(steps) - 1:
            d.line([x + 8, y + 22, x + 8, y + 44], fill=(60, 66, 76), width=2)
        y += 48

    # =========================================================
    # 中欄：生成結果盤面（真實 sprite）
    # =========================================================
    cx0, cx1 = lx1 + PAD, 1110
    d.rounded_rectangle([cx0, top, cx1, H - PAD], radius=8, fill=PANEL2)
    d.text((cx0 + 18, top + 14), '生成結果 · 盤面預覽', font=f_h, fill=ACCENT)
    d.ellipse([cx1 - 150, top + 17, cx1 - 138, top + 29], fill=GREEN)
    d.text((cx1 - 128, top + 14), '已驗證', font=f_s, fill=GREEN)

    avail_w = (cx1 - cx0) - 50
    avail_h = (H - PAD) - (top + 56) - 80
    cell = int(min(avail_w / cols, avail_h / rows))
    bw, bh = cell * cols, cell * rows
    bx = cx0 + ((cx1 - cx0) - bw) // 2
    by = top + 56 + 14
    d.rectangle([bx - 6, by - 6, bx + bw + 6, by + bh + 6], fill=(12, 14, 18))
    for r in range(rows):
        for c in range(cols):
            x0, y0 = bx + c * cell, by + r * cell
            shade = (26, 30, 37) if (r + c) % 2 == 0 else (30, 35, 43)
            d.rectangle([x0, y0, x0 + cell, y0 + cell], fill=shade)
            co = board.get_cell(r, c)
            bt = getattr(co, 'bottom', None)
            if bt is not None:
                sp = sprite(bt.tile_id, cell - 6)
                if sp:
                    img.paste(sp, (x0 + 3, y0 + 3), sp)
            mid = getattr(co, 'middle', None)
            if mid is not None:
                sp = sprite(mid.tile_id, cell - 8)
                if sp:
                    img.paste(sp, (x0 + 4, y0 + 4), sp)
            d.rectangle([x0, y0, x0 + cell, y0 + cell], outline=(40, 45, 54))

    # 目標列（盤面下方）
    gy = by + bh + 22
    d.text((cx0 + 18, gy), '通關目標', font=f_t, fill=DIM)
    gx = cx0 + 110
    for tid, need in (data.get('goals') or {}).items():
        sp = sprite(tid, 30)
        if sp:
            img.paste(sp, (gx, gy - 6), sp)
        d.text((gx + 36, gy), f'{tid} ×{need}', font=f_t, fill=FG)
        gx += 200

    # =========================================================
    # 右欄：AI 自動測試報告 + JSON
    # =========================================================
    rx0, rx1 = cx1 + PAD, W - PAD
    d.rounded_rectangle([rx0, top, rx1, H - PAD], radius=8, fill=PANEL)
    x = rx0 + 18
    y = top + 16
    d.text((x, y), 'AI 自動測試報告', font=f_h, fill=ACCENT)
    d.text((x + 150, y + 3), f'{res.n_games} 場 · 純邏輯文字版', font=f_s, fill=DIM)
    y += 36

    def stat(sx, big, label, color):
        d.text((sx, y), big, font=f_big, fill=color)
        d.text((sx + 2, y + 38), label, font=f_s, fill=DIM)

    stat(x, f'{res.win_rate:.0%}', 'AI 勝率', GREEN)
    stat(x + 150, f'{res.avg_steps_won:.1f}', '平均步數', ACCENT)
    d.text((x + 300, y), f'{res.min_steps}-{res.max_steps_seen}', font=f_big, fill=PUR)
    d.text((x + 302, y + 38), '步數範圍', font=f_s, fill=DIM)
    y += 78

    d.text((x, y), '步數分布（100 場）', font=f_t, fill=FG)
    y += 22
    hist = res.step_histogram or {}
    if hist:
        maxc = max(hist.values())
        keys = sorted(hist.keys())
        bwid = min(34, int((rx1 - 30 - x) / max(len(keys), 1)))
        hx, base = x, y + 84
        for k in keys:
            h = int(64 * hist[k] / maxc)
            d.rounded_rectangle([hx, base - h, hx + bwid - 6, base], radius=3, fill=ACCENT)
            d.text((hx, base + 4), str(k), font=f_s, fill=DIM)
            hx += bwid
        y = base + 28

    d.line([x, y, rx1 - 18, y], fill=LINE, width=1)
    y += 14
    d.text((x, y), '難度校準', font=f_t, fill=DIM)
    _diff = res.difficulty_label().split('（')[0]
    d.text((x + 90, y), f'{_diff}（勝率 {res.win_rate:.0%}）— AI 建議再加難',
           font=f_t, fill=ORANGE)
    y += 30
    d.ellipse([x, y + 2, x + 12, y + 14], fill=GREEN)
    d.text((x + 22, y), '格式驗證通過 · 關卡可正常遊玩', font=f_t, fill=GREEN)
    y += 34

    d.line([x, y, rx1 - 18, y], fill=LINE, width=1)
    y += 14
    d.text((x, y), '生成的關卡 JSON（節錄）', font=f_h, fill=ACCENT)
    y += 26
    d.rounded_rectangle([x, y, rx1 - 18, H - PAD - 16], radius=6, fill=(14, 16, 20))
    snippet = json.dumps({
        'level_id': data.get('level_id', 3), 'rows': rows, 'cols': cols,
        'max_steps': data.get('max_steps'), 'num_colors': data.get('num_colors', 4),
        'goals': data.get('goals'),
    }, ensure_ascii=False, indent=2)
    jy = y + 10
    for ln in snippet.splitlines()[:13]:
        d.text((x + 12, jy), ln, font=f_mono, fill=(150, 200, 160))
        jy += 18

    out = _ROOT / 'generator_mockup.png'
    img.save(out)
    print('OK ->', out)
    print(f'勝率 {res.win_rate:.0%} | 平均步數 {res.avg_steps_won:.1f} | 難度 {res.difficulty_label()}')


if __name__ == '__main__':
    main()
