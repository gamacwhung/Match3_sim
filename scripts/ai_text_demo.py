"""產生「Python 純邏輯自動測試」示意圖（給遊戲製作人報告用）。

重點訊息：伺服器端「文字版純邏輯」AI 自動測試跑超快——
不需要開遊戲、不需要影像辨識（對比 ../Match3_AI 那種 YOLO 截圖版），
直接在記憶體裡跑完整關卡，每步都有決策與計時。

輸出：ai_text_demo.png（盤面 + AI 決策日誌 + 計時秒數 + 步數 + 速度對比）
用法：python scripts/ai_text_demo.py
"""
from __future__ import annotations

import glob
import json
import pathlib
import random
import sys
import time

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / 'scripts'))

from match3_env import Match3Env          # noqa: E402
from ai_player import find_best_action     # noqa: E402
from level_generator.sim_runner import run_simulation_batch  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

LEVEL = sorted(glob.glob(str(_ROOT / 'levels' / 'level_*.json')))[0]

FONT = str(_ROOT / 'godot_demo' / 'resources' / 'fonts' / 'NotoSansTC-Regular.otf')
MONO = 'C:/Windows/Fonts/consola.ttf'

BG = (13, 17, 23)
PANEL = (22, 27, 34)
FG = (201, 209, 217)
DIM = (139, 148, 158)
GREEN = (63, 185, 80)
CYAN = (57, 197, 187)
YELLOW = (210, 153, 34)
CELL_COLORS = {
    'Red': (229, 72, 77), 'Grn': (70, 167, 88), 'Blu': (59, 130, 246),
    'Yel': (220, 180, 20), 'Pur': (139, 92, 246), 'Pnk': (236, 72, 153),
}
OBS = (120, 100, 80)


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _cell_style(tid: str):
    if not tid or tid in ('void', 'None', 'null', '.'):
        return None, ''
    key = tid[:3]
    if key in CELL_COLORS:
        return CELL_COLORS[key], tid[0]
    return OBS, tid[:2]


def run_one_game():
    """跑一場完整關卡，回傳 (初始盤面, 決策log, 總步數, 總耗時ms, 是否勝利)。"""
    env = Match3Env(level_file=LEVEL)
    env.reset()
    # 放寬步數讓 AI 跑完整關卡(和批次模擬一致)，示意圖才看得到完整一場
    env.max_steps = max(int(env.max_steps * 3), env.max_steps + 50)
    init_board = [[env.board.get_cell(r, c).get_display()
                   for c in range(env.board.cols)] for r in range(env.board.rows)]
    rng = random.Random(7)
    log = []
    t0 = time.perf_counter()
    step = 0
    while not env.done and step < 300:
        ts = time.perf_counter()
        action, score, reason = find_best_action(env, rng=rng, explain=True)
        if action is None:
            env.board.shuffle()
            action, score, reason = find_best_action(env, rng=rng, explain=True)
            if action is None:
                break
        _, _, _, info = env.step(action)
        dt_ms = (time.perf_counter() - ts) * 1000.0
        step += 1
        elim = info.get('eliminated', {})
        elim_s = ', '.join(f'{k}x{v}' for k, v in elim.items()) if elim else '—'
        if action['type'] == 'swap':
            r1, c1 = action['pos1']
            r2, c2 = action['pos2']
            desc = f'交換 ({r1},{c1})<->({r2},{c2})'
        else:
            r, c = action['pos']
            desc = f'啟動道具 ({r},{c})'
        log.append((step, desc, elim_s, dt_ms, score, reason))
    return init_board, log, step, (time.perf_counter() - t0) * 1000.0, env.win


def render(init_board, log, total_steps, single_ms, won, batch_s, win_rate):
    f_title = _font(FONT, 30)
    f_h = _font(FONT, 19)
    f_log = _font(MONO, 16)
    f_logc = _font(FONT, 16)
    f_cell = _font(FONT, 18)
    f_big = _font(MONO, 38)
    f_small = _font(FONT, 15)

    W, H = 1500, 590
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    # 盤面（圖內不放標題/說明，由簡報自行加）
    bx, by = 40, 56
    d.text((bx, by - 28), '盤面狀態 (9x9)', font=f_h, fill=CYAN)
    cs = 46
    rows, cols = len(init_board), len(init_board[0])
    for r in range(rows):
        for c in range(cols):
            col, ch = _cell_style(init_board[r][c])
            if col is None:
                continue
            x0, y0 = bx + c * cs, by + r * cs
            d.rounded_rectangle([x0 + 2, y0 + 2, x0 + cs - 4, y0 + cs - 4], radius=8, fill=col)
            if ch:
                bb = d.textbbox((0, 0), ch, font=f_cell)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                d.text((x0 + (cs - tw) / 2 - bb[0], y0 + (cs - th) / 2 - bb[1]),
                       ch, font=f_cell, fill=(255, 255, 255))

    # 決策日誌（每步：交換 ｜ 決策類別(上色) ｜ 評分 ｜ 消除來源 ｜ 耗時）
    lx = bx + cols * cs + 40
    ly = 56
    d.text((lx, ly - 28), 'AI 決策即時輸出　[ 動作 ｜ 決策類別 ｜ 評分 ｜ 消除來源 ｜ 耗時 ]',
           font=f_h, fill=CYAN)
    d.rounded_rectangle([lx - 12, ly, W - 36, ly + 300], radius=10, fill=PANEL)
    REASON_COLOR = {'道具合成': (236, 72, 153), '紙風車炸色': (139, 92, 246),
                    '戰術佈局': CYAN, '消除得分': GREEN, '啟動道具': YELLOW}
    yy = ly + 14
    for (sn, desc, elim, dt_ms, score, reason) in log[:10]:
        d.text((lx, yy), f'#{sn:>2}', font=f_log, fill=DIM)
        d.text((lx + 44, yy), desc, font=f_logc, fill=FG)
        d.text((lx + 235, yy), reason, font=f_logc, fill=REASON_COLOR.get(reason, FG))
        d.text((lx + 355, yy), f'{score:.0f} 分', font=f_logc, fill=(230, 230, 230))
        d.text((lx + 450, yy), f'來源 {elim}', font=f_logc, fill=DIM)
        d.text((W - 118, yy), f'{dt_ms:5.2f} ms', font=f_log, fill=YELLOW)
        yy += 27
    if total_steps > 10:
        d.text((lx, yy + 2), f'... 共 {total_steps} 步，{"勝利" if won else "結束"}',
               font=f_small, fill=DIM)

    # 統計（盤面下方）
    sy = 500
    d.line([36, sy - 16, W - 36, sy - 16], fill=(48, 54, 61), width=1)

    def stat(x, big, label, color=GREEN):
        d.text((x, sy), big, font=f_big, fill=color)
        d.text((x + 2, sy + 50), label, font=f_small, fill=DIM)

    stat(40, f'{total_steps}', '本場步數 (steps)')
    stat(330, f'{single_ms:.0f} ms', '本場總耗時')
    stat(640, f'{batch_s:.2f} s', '100 場批次總耗時', CYAN)
    stat(1000, f'{win_rate:.0%}', 'AI 勝率 (100 場)', GREEN)
    stat(1280, f'{batch_s / 100 * 1000:.1f} ms', '平均每場', YELLOW)

    out = _ROOT / 'ai_text_demo.png'
    img.save(out)
    return out


def main():
    init_board, log, total_steps, single_ms, won = run_one_game()

    ld = json.load(open(LEVEL, encoding='utf-8'))
    tb = time.perf_counter()
    res = run_simulation_batch(ld, n_games=100, max_workers=4)
    batch_s = time.perf_counter() - tb

    out = render(init_board, log, total_steps, single_ms, won, batch_s, res.win_rate)
    print('OK ->', out)
    print(f'單場: {total_steps} 步 / {single_ms:.0f} ms / {"勝利" if won else "結束"} ; '
          f'100 場批次: {batch_s:.2f}s ; 勝率 {res.win_rate:.0%}')


if __name__ == '__main__':
    main()
