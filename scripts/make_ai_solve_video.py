"""
產生「AI 自動破關」流暢動畫（MP4 + GIF）— 給投影片自動播放 / idle 示意。

跟 make_ai_solve_gif.py 不同：這版有**中間動畫**(交換滑動、消除淡出、掉落滑動、補入)，
靠在 match_engine.resolve() 的逐階段 callback 截幀，再用內插補出流暢過場。

用法:
    python scripts/make_ai_solve_video.py [關卡json] [輸出檔名(不含副檔名)]
預設: Level 1 → ai_solve_level1.mp4 + .gif
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import match_engine  # noqa: E402
from match3_env import Match3Env  # noqa: E402
from ai_player import find_best_action  # noqa: E402

ASSETS = os.path.join(_ROOT, "match3_board_component", "frontend", "assets")
CELL = 76
PAD = 16
FPS = 30
BG = (28, 22, 44)
CELL_BG = (44, 35, 66)
GRID_LINE = (60, 50, 88)

_sprite_cache: dict = {}


def load_sprite(tile_id):
    if tile_id in _sprite_cache:
        return _sprite_cache[tile_id]
    path = os.path.join(ASSETS, f"{tile_id}.png")
    img = Image.open(path).convert("RGBA").resize((CELL, CELL), Image.LANCZOS) \
        if os.path.exists(path) else None
    _sprite_cache[tile_id] = img
    return img


def capture(board):
    """回傳 grid[r][c] = tile_id / None / '__void__'。"""
    g = []
    for r in range(board.rows):
        row = []
        for c in range(board.cols):
            cell = board.get_cell(r, c)
            if cell.is_void:
                row.append("__void__")
            elif cell.middle is not None:
                row.append(cell.middle.tile_id)
            elif cell.bottom is not None:
                row.append(cell.bottom.tile_id)
            else:
                row.append(None)
        g.append(row)
    return g


def base_image(layout, rows, cols):
    w = cols * CELL + PAD * 2
    h = rows * CELL + PAD * 2
    img = Image.new("RGBA", (w, h), BG + (255,))
    draw = ImageDraw.Draw(img)
    for r in range(rows):
        for c in range(cols):
            if layout[r][c] == "__void__":
                continue
            x0 = PAD + c * CELL
            y0 = PAD + r * CELL
            draw.rectangle([x0 + 1, y0 + 1, x0 + CELL - 2, y0 + CELL - 2],
                           fill=CELL_BG + (255,), outline=GRID_LINE + (255,))
    return img


def render(layout, placements, rows, cols):
    """placements: list of (tile_id, row_f, col_f, alpha)。回傳 RGB Image。"""
    img = base_image(layout, rows, cols)
    for tid, rf, cf, alpha in placements:
        if tid in (None, "__void__"):
            continue
        sp = load_sprite(tid)
        if sp is None:
            continue
        if alpha < 1.0:
            a = sp.split()[3].point(lambda p: int(p * alpha))
            sp = sp.copy()
            sp.putalpha(a)
        x = int(round(PAD + cf * CELL))
        y = int(round(PAD + rf * CELL))
        img.alpha_composite(sp, (x, y))
    return img.convert("RGB")


def _ease(t):
    return 1 - (1 - t) * (1 - t)   # ease-out


def static_placements(grid, rows, cols, skip=None):
    skip = skip or set()
    out = []
    for r in range(rows):
        for c in range(cols):
            tid = grid[r][c]
            if tid in (None, "__void__"):
                continue
            if (r, c) in skip:
                continue
            out.append((tid, float(r), float(c), 1.0))
    return out


def anim_swap(grid, layout, p1, p2, rows, cols, n=6):
    (r1, c1), (r2, c2) = p1, p2
    t1, t2 = grid[r1][c1], grid[r2][c2]
    frames = []
    for i in range(n):
        t = _ease((i + 1) / n)
        pl = static_placements(grid, rows, cols, skip={(r1, c1), (r2, c2)})
        pl.append((t1, r1 + (r2 - r1) * t, c1 + (c2 - c1) * t, 1.0))
        if t2 not in (None, "__void__"):
            pl.append((t2, r2 + (r1 - r2) * t, c2 + (c1 - c2) * t, 1.0))
        frames.append(render(layout, pl, rows, cols))
    return frames


def anim_clear(gridA, gridB, layout, rows, cols, n=5):
    cleared = [(r, c) for r in range(rows) for c in range(cols)
               if gridA[r][c] not in (None, "__void__") and gridB[r][c] in (None, "__void__")]
    frames = []
    for i in range(n):
        t = (i + 1) / n
        pl = static_placements(gridA, rows, cols, skip=set(cleared))
        for (r, c) in cleared:
            pl.append((gridA[r][c], float(r), float(c), max(0.0, 1.0 - t)))
        frames.append(render(layout, pl, rows, cols))
    return frames


def anim_gravity(gridA, gridB, layout, rows, cols, n=8):
    # 每欄: A 的非空(上→下) 對應 B 的非空(上→下)
    moves = []  # (tid, from_r, to_r, c)
    for c in range(cols):
        a = [(r, gridA[r][c]) for r in range(rows) if gridA[r][c] not in (None, "__void__")]
        b = [r for r in range(rows) if gridB[r][c] not in (None, "__void__")]
        for (ar, tid), br in zip(a, b):
            moves.append((tid, ar, br, c))
    frames = []
    for i in range(n):
        t = _ease((i + 1) / n)
        pl = []
        for tid, fr, to, c in moves:
            pl.append((tid, fr + (to - fr) * t, float(c), 1.0))
        frames.append(render(layout, pl, rows, cols))
    return frames


def anim_fill(gridA, gridB, layout, rows, cols, n=6):
    drops = []   # (tid, to_r, c, start_r)
    static = []
    for c in range(cols):
        new_rows = [r for r in range(rows)
                    if gridB[r][c] not in (None, "__void__") and gridA[r][c] in (None, "__void__")]
        # 由上往下排,讓它們像從盤面上方一串掉入
        for k, r in enumerate(sorted(new_rows)):
            drops.append((gridB[r][c], r, c, -(len(new_rows) - k)))
        for r in range(rows):
            if gridB[r][c] not in (None, "__void__") and gridA[r][c] not in (None, "__void__"):
                static.append((gridB[r][c], r, c))
    frames = []
    for i in range(n):
        t = _ease((i + 1) / n)
        pl = [(tid, float(r), float(c), 1.0) for tid, r, c in static]
        for tid, to, c, sr in drops:
            pl.append((tid, sr + (to - sr) * t, float(c), 1.0))
        frames.append(render(layout, pl, rows, cols))
    return frames


def main():
    level_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        _ROOT, "godot_demo", "levels", "Level_001.json")
    out_base = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_ROOT, "ai_solve_level1")

    ld = json.load(open(level_path, encoding="utf-8"))
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(ld, tf, ensure_ascii=False)
    tf.close()
    try:
        env = Match3Env(level_file=tf.name)
        env.reset()
        board = env.board
        rows, cols = board.rows, board.cols
        layout = capture(board)   # void 佈局固定

        import random
        rng = random.Random(7)

        frames = []
        grid = capture(board)
        # 開場停一下
        for _ in range(FPS // 2):
            frames.append(render(layout, static_placements(grid, rows, cols), rows, cols))

        steps = 0
        while steps < 40 and not env.done:
            action = find_best_action(env, rng=rng)
            if action is None:
                board.shuffle()
                grid = capture(board)
                continue
            if action.get("type") != "swap":
                # Level 1 無道具;保險起見其他動作直接套用引擎(無動畫過場)
                env.step(action)
                grid = capture(board)
                frames.append(render(layout, static_placements(grid, rows, cols), rows, cols))
                steps += 1
                continue

            p1, p2 = action["pos1"], action["pos2"]
            # 1) 交換動畫(視覺) + 算出交換後盤面當作後續第一段的起點
            frames += anim_swap(grid, layout, p1, p2, rows, cols)
            swapped = [row[:] for row in grid]
            swapped[p1[0]][p1[1]], swapped[p2[0]][p2[1]] = \
                swapped[p2[0]][p2[1]], swapped[p1[0]][p1[1]]

            # 2) 用 env.step 走真正的移動(正確計數+勝利)，frame_cb 截各階段盤面
            phases = []  # (phase, grid)
            env.step(action, frame_cb=lambda ph, b: phases.append((ph, capture(b))))

            # 3) 串接內插: swapped → cleared → gravity → fill → (下一波連鎖) ...
            prev = swapped
            for ph, g in phases:
                if ph == "cleared":
                    frames += anim_clear(prev, g, layout, rows, cols)
                elif ph == "gravity":
                    frames += anim_gravity(prev, g, layout, rows, cols)
                elif ph == "fill":
                    frames += anim_fill(prev, g, layout, rows, cols)
                prev = g
            grid = capture(board)
            steps += 1
            # 每步之間小停頓
            for _ in range(4):
                frames.append(render(layout, static_placements(grid, rows, cols), rows, cols))

        # 結尾停久一點
        for _ in range(FPS * 2):
            frames.append(render(layout, static_placements(grid, rows, cols), rows, cols))

        print(f"AI 解了 {steps} 步, 共 {len(frames)} 幀")
        _write_mp4(frames, out_base + ".mp4")
        _write_gif(frames, out_base + ".gif")
    finally:
        os.unlink(tf.name)


def _goals_met(env):
    for tid, need in env.goals_required.items():
        if env.goals_current.get(tid, 0) < need:
            return False
    return True


def _write_mp4(frames, path):
    import cv2
    w, h = frames[0].size
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (w, h))
    for f in frames:
        vw.write(cv2.cvtColor(np.array(f), cv2.COLOR_RGB2BGR))
    vw.release()
    print(f"已輸出 MP4: {path}  ({w}x{h}, {os.path.getsize(path)//1024} KB)")


def _write_gif(frames, path, scale=0.5, step=3):
    # GIF 縮小(預設半尺寸)+取樣(每 3 幀)壓檔,避免太大
    sub = frames[::step]
    if scale != 1.0:
        w, h = sub[0].size
        sz = (int(w * scale), int(h * scale))
        sub = [f.resize(sz, Image.LANCZOS) for f in sub]
    sub[0].save(path, save_all=True, append_images=sub[1:],
                duration=int(1000 / FPS * step), loop=0, optimize=True)
    print(f"已輸出 GIF: {path}  ({sub[0].size[0]}x{sub[0].size[1]}, {os.path.getsize(path)//1024} KB)")


if __name__ == "__main__":
    main()
