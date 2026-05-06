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
    return {
        'id': tile.tile_id,
        'hp': tile.health,
        'image_key': image_key if image_key in ASSET_SOURCES else None,
        'css_color': CSS_FALLBACK.get(tile.tile_id),
        'css_label': tile.tile_id[:4],
        'is_obstacle': _is_obstacle_id(tile.tile_id),
    }


def serialize_cell(cell):
    return {
        'middle': _serialize_tile(cell.middle),
        'upper': _serialize_tile(cell.upper),
        'bottom': _serialize_tile(cell.bottom),
        'locked': cell.is_locked() if hasattr(cell, 'is_locked') else False,
        'mud': cell.has_mud() if hasattr(cell, 'has_mud') else False,
    }


def serialize_env(env):
    """把 Match3Env 的盤面序列化成 board 2D list"""
    return [
        [serialize_cell(env.board.get_cell(r, c)) for c in range(env.board.cols)]
        for r in range(env.board.rows)
    ]


def match3_board(env, *, mode='play', selected=None, cell_size=56, key=None):
    """
    渲染 Match3 棋盤。

    Args:
        env:        Match3Env 物件
        mode:       'play' (可點擊) | 'preview' (唯讀)
        selected:   (r, c) tuple 或 None；表示選中的格子
        cell_size:  每格像素大小
        key:        Streamlit component key（用於追蹤同頁多個 instance）

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
        key=key,
        default=None,
    )
