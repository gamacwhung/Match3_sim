"""
渲染輔助函式 — 供 streamlit_app.py 和 Level Generator 頁面共用

從 streamlit_app.py 提取，邏輯完全相同。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tile_defs import is_obstacle, is_powerup, get_def

# ---------------------------------------------------------------------------
# 顏色映射
# ---------------------------------------------------------------------------
COLOR_MAP = {
    'Red': '#FF4444', 'Grn': '#44BB44', 'Blu': '#4488FF',
    'Yel': '#FFCC00', 'Pur': '#AA44CC', 'Brn': '#886644',
    'Soda0d': '#00CCCC', 'Soda90': '#00AACC',
    'TNT': '#FF6600', 'TrPr': '#FF88CC', 'LtBl': '#FFFFFF',
}
OBSTACLE_COLOR = '#CD853F'
EMPTY_COLOR = '#333333'
PUDDLE_COLOR = '#6688AA'
ROPE_COLOR = '#AA4444'
MUD_COLOR = '#8B6914'

# 道具 emoji / 符號
POWERUP_SYMBOL = {
    'Soda0d': '🚀↔', 'Soda90': '🚀↕', 'TNT': '💣',
    'TrPr': '✈️', 'LtBl': '🌟',
}


def _get_tile_color(tile_id):
    if tile_id in COLOR_MAP:
        return COLOR_MAP[tile_id]
    if is_obstacle(tile_id):
        return OBSTACLE_COLOR
    defn = get_def(tile_id)
    if defn and defn.get('color'):
        return COLOR_MAP.get(defn['color'], '#888888')
    return '#888888'


def _is_light(hex_color):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r * 0.299 + g * 0.587 + b * 0.114) > 150


def _cell_html(cell, r, c, selected):
    """產生單一格子的 HTML"""
    tile = cell.middle
    is_sel = (selected == (r, c))

    # 外框
    border = '3px solid #FFFF00' if is_sel else '1px solid #555'

    # 底色（水漥）
    bg = EMPTY_COLOR
    if cell.bottom:
        bg = PUDDLE_COLOR

    if tile is None:
        return (
            f'<div style="width:52px;height:52px;background:{bg};'
            f'border:{border};border-radius:4px;display:flex;'
            f'align-items:center;justify-content:center;font-size:10px;'
            f'color:#666;margin:1px;">&nbsp;</div>'
        )

    fill = _get_tile_color(tile.tile_id)
    text_color = '#000' if _is_light(fill) else '#FFF'

    # 標籤
    label = tile.tile_id
    if tile.tile_id in POWERUP_SYMBOL:
        label = POWERUP_SYMBOL[tile.tile_id]
    elif len(label) > 6:
        label = label[:6]

    hp_text = f'<br><small>{tile.health}</small>' if tile.health > 1 else ''

    # 上層覆蓋
    upper_html = ''
    if cell.upper:
        u_color = MUD_COLOR if cell.upper.tile_id == 'Mud' else ROPE_COLOR
        u_label = cell.upper.tile_id
        upper_html = (
            f'<div style="position:absolute;top:0;left:0;right:0;'
            f'background:{u_color};color:#FFF;font-size:8px;'
            f'text-align:center;border-radius:3px 3px 0 0;'
            f'padding:0 2px;opacity:0.85;">{u_label}</div>'
        )

    # 水漥標籤
    bottom_html = ''
    if cell.bottom:
        bottom_html = (
            f'<div style="position:absolute;bottom:0;left:0;right:0;'
            f'color:#AADDFF;font-size:8px;text-align:center;">~{cell.bottom.health}</div>'
        )

    # 道具外框
    powerup_border = 'border:2px solid #FFD700;' if is_powerup(tile.tile_id) else ''

    return (
        f'<div style="position:relative;width:52px;height:52px;'
        f'background:{fill};{powerup_border}'
        f'border:{border};border-radius:6px;display:flex;'
        f'align-items:center;justify-content:center;'
        f'color:{text_color};font-size:11px;font-weight:bold;'
        f'font-family:Consolas,monospace;margin:1px;cursor:pointer;'
        f'text-align:center;">'
        f'{upper_html}{label}{hp_text}{bottom_html}</div>'
    )


def _make_btn_label(cell, is_sel):
    """產生按鈕文字標籤"""
    tile = cell.middle
    parts = []

    # 上層
    if cell.upper:
        uid = cell.upper.tile_id
        if uid == 'Mud':
            parts.append('🟤')
        elif uid.startswith('Rope'):
            parts.append(f'🪢{cell.upper.health}')

    # 中層
    if tile is None:
        parts.append('·')
    elif tile.tile_id in POWERUP_SYMBOL:
        parts.append(POWERUP_SYMBOL[tile.tile_id])
    else:
        tid = tile.tile_id
        symbol_map = {
            'Red': '🔴', 'Grn': '🟢', 'Blu': '🔵',
            'Yel': '🟡', 'Pur': '🟣', 'Brn': '🟤',
        }
        if tid in symbol_map:
            parts.append(symbol_map[tid])
        else:
            # 障礙物
            short = tid[:5] if len(tid) > 5 else tid
            parts.append(short)
            if tile.health > 1:
                parts.append(f'×{tile.health}')

    # 下層
    if cell.bottom:
        parts.append(f'💧{cell.bottom.health}')

    return ''.join(parts)


def render_board_preview_html(env) -> str:
    """
    產生只讀盤面 HTML（無按鈕，用於預覽）。
    env: Match3Env 物件
    """
    rows_html = []
    for r in range(env.board.rows):
        cells_html = [
            _cell_html(env.board.get_cell(r, c), r, c, None)
            for c in range(env.board.cols)
        ]
        rows_html.append(
            '<div style="display:flex;gap:2px;">' + ''.join(cells_html) + '</div>'
        )
    return (
        '<div style="display:inline-block;padding:8px;'
        'background:#222;border-radius:8px;">'
        + ''.join(rows_html)
        + '</div>'
    )
