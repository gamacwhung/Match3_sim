"""
簡易 GUI 互動模式 — 使用 tkinter

用法:
  python gui_play.py
  python gui_play.py --level levels/level_01.json
"""

import argparse
import os
import tkinter as tk
from tkinter import ttk, messagebox

from match3_env import Match3Env
from basic_agent import BasicAgent
from tile_defs import is_element, is_powerup, is_obstacle, get_def

# ---------------------------------------------------------------------------
# 顏色映射
# ---------------------------------------------------------------------------
COLOR_MAP = {
    # 元素
    'Red': '#FF4444',
    'Grn': '#44BB44',
    'Blu': '#4488FF',
    'Yel': '#FFCC00',
    'Pur': '#AA44CC',
    'Brn': '#886644',
    # 道具
    'Soda0d': '#00CCCC',
    'Soda90': '#00AACC',
    'TNT': '#FF6600',
    'TrPr': '#FF88CC',
    'LtBl': '#FFFFFF',
}

OBSTACLE_COLOR = '#CD853F'  # 障礙物通用色
POWERUP_OUTLINE = '#FFD700'  # 道具外框色
EMPTY_COLOR = '#333333'
SELECT_COLOR = '#FFFF00'  # 選取高亮色

CELL_SIZE = 56
PADDING = 4


class Match3GUI:
    def __init__(self, root, level_file=None):
        self.root = root
        self.root.title('三消模擬器')

        self.env = Match3Env(
            rows=10, cols=9, num_colors=4, max_steps=30,
            level_file=level_file,
        )
        self.agent = BasicAgent()
        self.selected = None  # (r, c) or None

        self._build_ui()
        self._draw_board()

    def _build_ui(self):
        # 頂部控制列
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # 關卡選擇
        tk.Label(top_frame, text='關卡:').pack(side=tk.LEFT)
        self.level_var = tk.StringVar()
        levels_dir = os.path.join(os.path.dirname(__file__), 'levels')
        level_files = []
        if os.path.isdir(levels_dir):
            level_files = sorted(
                f for f in os.listdir(levels_dir) if f.endswith('.json')
            )
        self.level_combo = ttk.Combobox(
            top_frame, textvariable=self.level_var,
            values=['(隨機)'] + level_files, width=20, state='readonly',
        )
        if self.env.level_file:
            basename = os.path.basename(self.env.level_file)
            if basename in level_files:
                self.level_combo.set(basename)
            else:
                self.level_combo.set('(隨機)')
        else:
            self.level_combo.set('(隨機)')
        self.level_combo.pack(side=tk.LEFT, padx=5)

        tk.Button(top_frame, text='重置', command=self._reset).pack(side=tk.LEFT, padx=2)
        tk.Button(top_frame, text='AI 一步', command=self._ai_step).pack(side=tk.LEFT, padx=2)
        tk.Button(top_frame, text='AI 自動', command=self._ai_auto).pack(side=tk.LEFT, padx=2)

        # 狀態列
        self.status_var = tk.StringVar(value='')
        tk.Label(top_frame, textvariable=self.status_var, fg='blue').pack(side=tk.RIGHT, padx=5)

        # 目標+步數
        info_frame = tk.Frame(self.root)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=5)
        self.info_var = tk.StringVar(value='')
        tk.Label(info_frame, textvariable=self.info_var, justify=tk.LEFT,
                 font=('Consolas', 10)).pack(side=tk.LEFT)

        # 盤面 Canvas
        canvas_w = self.env.board.cols * CELL_SIZE + PADDING * 2
        canvas_h = self.env.board.rows * CELL_SIZE + PADDING * 2
        self.canvas = tk.Canvas(
            self.root, width=canvas_w, height=canvas_h, bg='#222222',
        )
        self.canvas.pack(padx=5, pady=5)
        self.canvas.bind('<Button-1>', self._on_click)

    def _reset(self):
        sel = self.level_var.get()
        if sel and sel != '(隨機)':
            level_path = os.path.join(os.path.dirname(__file__), 'levels', sel)
            self.env = Match3Env(level_file=level_path)
        else:
            self.env = Match3Env(rows=10, cols=9, num_colors=4, max_steps=30)
        self.selected = None
        self.status_var.set('')

        # 更新 canvas 大小
        canvas_w = self.env.board.cols * CELL_SIZE + PADDING * 2
        canvas_h = self.env.board.rows * CELL_SIZE + PADDING * 2
        self.canvas.config(width=canvas_w, height=canvas_h)

        self._draw_board()

    def _ai_step(self):
        if self.env.done:
            return
        action = self.agent.choose_action(self.env)
        if action is None:
            self.env.board.shuffle()
            self.status_var.set('無合法步驟，已洗牌')
        else:
            _, reward, done, info = self.env.step(action)
            msg = info.get('msg', '')
            if info.get('shuffled'):
                msg += ' (已洗牌)'
            self.status_var.set(f'AI: {_format_action_short(action)}  {msg}')
        self.selected = None
        self._draw_board()

    def _ai_auto(self):
        if self.env.done:
            return
        # 每步呼叫一次，用 after 讓 UI 可以更新
        action = self.agent.choose_action(self.env)
        if action is None:
            self.env.board.shuffle()
            self.status_var.set('無合法步驟，已洗牌')
            self._draw_board()
            if not self.env.done:
                self.root.after(100, self._ai_auto)
            return

        _, reward, done, info = self.env.step(action)
        msg = info.get('msg', '')
        self.status_var.set(f'AI: {_format_action_short(action)}  {msg}')
        self._draw_board()

        if not self.env.done:
            self.root.after(200, self._ai_auto)

    def _on_click(self, event):
        if self.env.done:
            return

        c = (event.x - PADDING) // CELL_SIZE
        r = (event.y - PADDING) // CELL_SIZE
        if not self.env.board.in_bounds(r, c):
            return

        tile = self.env.board.get_middle(r, c)

        if self.selected is None:
            # 第一次點擊：選取
            self.selected = (r, c)
            self._draw_board()
        else:
            sr, sc = self.selected

            if (sr, sc) == (r, c):
                # 點擊已選取的自己
                # 如果是道具 → 直接啟動
                sel_tile = self.env.board.get_middle(sr, sc)
                if sel_tile and is_powerup(sel_tile.tile_id):
                    cell = self.env.board.get_cell(sr, sc)
                    if not cell.is_locked() and not cell.has_mud():
                        _, reward, done, info = self.env.step({
                            'type': 'activate', 'pos': (sr, sc),
                        })
                        msg = info.get('msg', '')
                        self.status_var.set(f'啟動 ({sr},{sc})  {msg}')
                # 不是道具 → 取消選取
                self.selected = None
                self._draw_board()
                return

            # 嘗試交換
            if abs(sr - r) + abs(sc - c) == 1:
                _, reward, done, info = self.env.step({
                    'type': 'swap', 'pos1': (sr, sc), 'pos2': (r, c),
                })
                msg = info.get('msg', '')
                if info.get('shuffled'):
                    msg += ' (已洗牌)'
                self.status_var.set(f'交換 ({sr},{sc})<->({r},{c})  {msg}')
                self.selected = None
            else:
                # 不相鄰 → 改為選取新的格子
                self.selected = (r, c)
                self.status_var.set('')

            self._draw_board()

    def _draw_board(self):
        self.canvas.delete('all')
        board = self.env.board

        for r in range(board.rows):
            for c in range(board.cols):
                x = PADDING + c * CELL_SIZE
                y = PADDING + r * CELL_SIZE

                cell = board.get_cell(r, c)
                tile = cell.middle

                # 底色（下層水漥）
                bg = EMPTY_COLOR
                if cell.bottom:
                    bg = '#6688AA'  # 水漥底色

                self.canvas.create_rectangle(
                    x + 1, y + 1, x + CELL_SIZE - 1, y + CELL_SIZE - 1,
                    fill=bg, outline='#444444',
                )

                if tile:
                    fill = _get_tile_color(tile.tile_id)
                    outline = '#666666'
                    if is_powerup(tile.tile_id):
                        outline = POWERUP_OUTLINE

                    # 繪製方塊
                    pad = 3
                    self.canvas.create_rectangle(
                        x + pad, y + pad,
                        x + CELL_SIZE - pad, y + CELL_SIZE - pad,
                        fill=fill, outline=outline, width=2,
                    )

                    # 文字標籤
                    label = tile.tile_id
                    if len(label) > 6:
                        label = label[:6]
                    # 血量 > 1 時顯示
                    if tile.health > 1:
                        label += f'\n{tile.health}'

                    text_color = '#000000' if _is_light_color(fill) else '#FFFFFF'
                    self.canvas.create_text(
                        x + CELL_SIZE // 2, y + CELL_SIZE // 2,
                        text=label, fill=text_color,
                        font=('Consolas', 8), justify=tk.CENTER,
                    )

                # 上層覆蓋（Rope/Mud）
                if cell.upper:
                    upper_label = cell.upper.tile_id
                    # 半透明覆蓋效果
                    if cell.upper.tile_id == 'Mud':
                        overlay_color = '#8B6914'
                    else:
                        overlay_color = '#AA4444'
                    self.canvas.create_rectangle(
                        x + 1, y + 1, x + CELL_SIZE - 1, y + 12,
                        fill=overlay_color, outline='',
                    )
                    self.canvas.create_text(
                        x + CELL_SIZE // 2, y + 6,
                        text=upper_label, fill='white',
                        font=('Consolas', 7),
                    )

                # 下層水漥標籤
                if cell.bottom:
                    self.canvas.create_text(
                        x + CELL_SIZE // 2, y + CELL_SIZE - 6,
                        text=f'~{cell.bottom.health}', fill='#AADDFF',
                        font=('Consolas', 7),
                    )

                # 選取高亮
                if self.selected == (r, c):
                    self.canvas.create_rectangle(
                        x, y, x + CELL_SIZE, y + CELL_SIZE,
                        outline=SELECT_COLOR, width=3,
                    )

        # 更新資訊
        self._update_info()

    def _update_info(self):
        lines = [f'步數: {self.env.steps_taken}/{self.env.max_steps}']
        if self.env.goals_required:
            lines.append('目標:')
            for tid, req in self.env.goals_required.items():
                cur = self.env.goals_current.get(tid, 0)
                status = '完成' if cur >= req else f'{cur}/{req}'
                lines.append(f'  {tid}: {status}')
        if self.env.done:
            result = '勝利！' if self.env.win else '失敗'
            lines.append(f'結果: {result}')
        self.info_var.set('\n'.join(lines))


def _get_tile_color(tile_id):
    """取得 tile 的顯示顏色"""
    if tile_id in COLOR_MAP:
        return COLOR_MAP[tile_id]
    if is_obstacle(tile_id):
        return OBSTACLE_COLOR
    defn = get_def(tile_id)
    if defn and defn.get('color'):
        return COLOR_MAP.get(defn['color'], '#888888')
    return '#888888'


def _is_light_color(hex_color):
    """判斷顏色是否偏亮（決定文字顏色）"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (r * 0.299 + g * 0.587 + b * 0.114) > 150


def _format_action_short(action):
    """格式化動作為簡短字串"""
    if action['type'] == 'swap':
        r1, c1 = action['pos1']
        r2, c2 = action['pos2']
        return f'({r1},{c1})<->({r2},{c2})'
    elif action['type'] == 'activate':
        r, c = action['pos']
        return f'啟動({r},{c})'
    return str(action)


def main():
    parser = argparse.ArgumentParser(description='三消模擬器 GUI')
    parser.add_argument('--level', type=str, default=None,
                        help='關卡 JSON 檔案路徑')
    args = parser.parse_args()

    root = tk.Tk()
    root.resizable(False, False)
    app = Match3GUI(root, level_file=args.level)
    root.mainloop()


if __name__ == '__main__':
    main()
