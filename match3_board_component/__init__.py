"""
Match3 Board — Streamlit Custom Component

匯出：
    match3_board(env, ...)              — 高階 API，傳入 Match3Env，回傳點擊事件 dict
    serialize_env(env)                  — 把 Match3Env 序列化成 component 可吃的 board JSON
    serialize_cell(cell)                — 序列化單一 Cell

點擊回傳格式：
    { 'type': 'click', 'r': int, 'c': int, 'ts': int }   或 None
"""

import os
import streamlit.components.v1 as components

from .asset_map import resolve_image_key, ASSET_SOURCES, CSS_FALLBACK


_HERE = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_HERE, 'frontend')

_component_func = components.declare_component(
    'match3_board',
    path=_FRONTEND_DIR,
)


def _is_obstacle_id(tile_id):
    """快速判斷是否為障礙物 tile_id（用於 CSS fallback 選樣式）"""
    if tile_id is None:
        return False
    obstacle_prefixes = (
        'Crt', 'Puddle', 'Barrel', 'TrafficCone', 'SalmonCan',
        'WaterChiller', 'BeverageChiller', 'Pool', 'Stamp', 'Rope', 'Mud',
    )
    return any(tile_id.startswith(p) for p in obstacle_prefixes)


def _serialize_tile(tile):
    if tile is None:
        return None
    image_key = resolve_image_key(tile.tile_id, tile.health)
    data = {
        'id': tile.tile_id,
        'hp': tile.health,
        'image_key': image_key if image_key in ASSET_SOURCES else None,
        'css_color': CSS_FALLBACK.get(tile.tile_id),
        'css_label': tile.tile_id[:4],
        'is_obstacle': _is_obstacle_id(tile.tile_id),
    }
    # 飲料櫃 per-cell 瓶色（開門後才顯示）
    if tile.tile_id.startswith('BeverageChiller'):
        bc = getattr(tile, 'bottle_color', None)
        if bc and tile.health < 5:
            data['bottle_color'] = bc
            data['bottle_alive'] = bool(getattr(tile, 'bottle_alive', True))
    return data


def serialize_cell(cell, *, anchor=False, span=1, covered=False):
    """
    anchor=True 表示此格是多格 instance 的左上角（要畫大圖）
    covered=True 表示此格被同一 instance 的左上角的大圖蓋住（middle 不畫圖）
    span 是邊長（2 = 2x2）
    """
    middle = _serialize_tile(cell.middle)
    if middle and (anchor or covered):
        if anchor:
            middle['span'] = span
        if covered:
            middle['covered'] = True
    return {
        'middle': middle,
        'upper': _serialize_tile(cell.upper),
        'bottom': _serialize_tile(cell.bottom),
        'locked': cell.is_locked() if hasattr(cell, 'is_locked') else False,
        'mud': cell.has_mud() if hasattr(cell, 'has_mud') else False,
        'void': bool(getattr(cell, 'is_void', False)),
    }


def serialize_env(env):
    """把 Match3Env 的盤面序列化成 board 2D list（含 2x2 instance anchor 標記）"""
    rows = env.board.rows
    cols = env.board.cols

    # Pass 1: 找每個 instance_id 的左上角
    instance_anchors = {}
    instance_cells = {}
    for r in range(rows):
        for c in range(cols):
            cell = env.board.get_cell(r, c)
            if cell.middle and cell.middle.instance_id:
                iid = cell.middle.instance_id
                instance_cells.setdefault(iid, []).append((r, c))
                if iid not in instance_anchors:
                    instance_anchors[iid] = (r, c)
                else:
                    ar, ac = instance_anchors[iid]
                    if r < ar or (r == ar and c < ac):
                        instance_anchors[iid] = (r, c)

    # 推算 span 邊長（假設方形;非方形 fallback 1）
    instance_span = {}
    for iid, cells in instance_cells.items():
        rs = sorted(set(r for r, _ in cells))
        cs = sorted(set(c for _, c in cells))
        if len(rs) == 2 and len(cs) == 2 and len(cells) == 4:
            instance_span[iid] = 2
        else:
            instance_span[iid] = 1

    # Pass 2: serialize
    board = []
    for r in range(rows):
        row = []
        for c in range(cols):
            cell = env.board.get_cell(r, c)
            anchor = covered = False
            span = 1
            if cell.middle and cell.middle.instance_id:
                iid = cell.middle.instance_id
                span = instance_span.get(iid, 1)
                if span > 1:
                    if instance_anchors[iid] == (r, c):
                        anchor = True
                    else:
                        covered = True
            row.append(serialize_cell(cell, anchor=anchor, span=span, covered=covered))
        board.append(row)
    return board


def match3_board(env, *, mode='play', selected=None, cell_size=56,
                 asset_version=0, key=None):
    """
    渲染 Match3 棋盤。

    Args:
        env:           Match3Env 物件
        mode:          'play' (可點擊) | 'preview' (唯讀)
        selected:      (r, c) tuple 或 None；表示選中的格子
        cell_size:     每格像素大小
        asset_version: 圖片快取版本號;套用新美術後遞增即可強制重新載入 sprite
        key:           Streamlit component key（用於追蹤同頁多個 instance）

    Returns:
        若使用者點擊：{ 'type': 'click', 'r': int, 'c': int, 'ts': int }
        否則：None
    """
    board = serialize_env(env)
    sel = list(selected) if selected else None
    return _component_func(
        board=board,
        selected=sel,
        mode=mode,
        cell_size=int(cell_size),
        asset_version=int(asset_version),
        key=key,
        default=None,
    )
