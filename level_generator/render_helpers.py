"""
渲染輔助函式 — 供 streamlit_app.py 和 Level Generator 頁面共用
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
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


# ---------------------------------------------------------------------------
# 步驟記錄 — 共用邏輯（供 streamlit_app.py 和 Level Generator 共用）
# ---------------------------------------------------------------------------
ELEM_EMOJI = {
    'Red': '🔴', 'Grn': '🟢', 'Blu': '🔵',
    'Yel': '🟡', 'Pur': '🟣', 'Brn': '🟤',
}


def format_eliminated(eliminated: dict, goals_required: dict) -> str:
    """
    把 info['eliminated'] 格式化成可讀字串。

    遊戲規則：
    - 元素 / 道具：直接被 match 消除
    - 障礙物：只能被「相鄰 match」附帶消除，本身不能直接被 match

    顯示分兩組，障礙物（目標相關的加 ★）在前，元素在後。
    """
    if not eliminated:
        return '（無消除）'

    obstacle_parts = []
    element_parts = []

    for tid, cnt in sorted(eliminated.items()):
        if is_obstacle(tid):
            goal_mark = ' ★' if tid in goals_required else ''
            text = f'`{tid}`×{cnt}{goal_mark}'
            obstacle_parts.append(f'**{text}**' if tid in goals_required else text)
        else:
            emoji = ELEM_EMOJI.get(tid, '')
            element_parts.append(f'{emoji}×{cnt}')

    parts = []
    if obstacle_parts:
        parts.append('障礙消除: ' + '  '.join(obstacle_parts))
    if element_parts:
        parts.append('Match: ' + '  '.join(element_parts))
    return '  |  '.join(parts)


POWERUP_NAMES = {
    'Soda0d': '🚀↔火箭', 'Soda90': '🚀↕火箭', 'TNT': '💣炸彈',
    'TrPr': '✈️紙飛機', 'LtBl': '🌟紙風車',
}


def _format_chain(chain: dict, goals_required: dict) -> str:
    """格式化單條連鎖"""
    parts = []
    # match 摘要
    for m in chain.get('matches', []):
        emoji = ELEM_EMOJI.get(m['color'], '')
        pattern = m['pattern']
        pup = PATTERN_TO_POWERUP_NAME.get(pattern)
        match_str = f'{emoji}×{m["count"]}'
        if pup:
            match_str += f' →{pup}'
        parts.append(match_str)
    match_summary = '  '.join(parts) if parts else ''

    # 障礙消除
    elim = chain.get('eliminated', {})
    obstacle_strs = []
    for tid, cnt in sorted(elim.items()):
        if is_obstacle(tid):
            goal_mark = ' ★' if tid in goals_required else ''
            obstacle_strs.append(f'`{tid}`×{cnt}{goal_mark}')
    obs_str = ('  障礙: ' + '  '.join(obstacle_strs)) if obstacle_strs else ''

    return f'{match_summary}{obs_str}'


# Pattern → 道具名稱（用於連鎖顯示）
PATTERN_TO_POWERUP_NAME = {
    'FIVE_PLUS': '🌟紙風車',
    'L_T': '💣炸彈',
    'BLOCK_2x2': '✈️紙飛機',
    'FOUR_H': '🚀↕火箭',
    'FOUR_V': '🚀↔火箭',
}


def make_move_log_entry(action_desc: str, info: dict,
                        goals_before: dict, goals_after: dict,
                        goals_required: dict, step_num: int) -> dict:
    """產生一步的記錄 dict"""
    eliminated = info.get('eliminated', {})
    goals_delta = {
        k: goals_after.get(k, 0) - goals_before.get(k, 0)
        for k in goals_required
        if goals_after.get(k, 0) != goals_before.get(k, 0)
    }
    return {
        'step': step_num,
        'action': action_desc,
        'eliminated': eliminated,
        'chains': info.get('chains', []),
        'goals_delta': goals_delta,
        'shuffled': info.get('shuffled', False),
        'msg': info.get('msg', ''),
    }


def render_move_log(log: list, goals_required: dict):
    """在 Streamlit 裡顯示步驟記錄 expander（最新在最上）"""
    if not log:
        return
    with st.expander(f'📋 步驟記錄（共 {len(log)} 步）', expanded=False):
        for entry in log:
            chains = entry.get('chains', [])
            delta = entry.get('goals_delta', {})
            delta_str = ('  →目標 +' + '  +'.join(f'`{k}`×{v}' for k, v in delta.items())) if delta else ''

            suffix = ''
            if entry.get('shuffled'):
                suffix += '  🔀洗牌'
            msg = entry.get('msg', '')
            if msg == 'win':
                suffix += '  🎉通關'
            elif msg == 'out of steps':
                suffix += '  💀步數耗盡'

            # 標題行
            st.markdown(f'**步{entry["step"]}** {entry["action"]}{delta_str}{suffix}')

            if chains:
                for ch in chains:
                    chain_str = _format_chain(ch, goals_required)
                    st.markdown(f'&ensp; 連鎖{ch["chain"]}: {chain_str}')
            else:
                # 沒有連鎖資料時退回顯示總消除
                elim_str = format_eliminated(entry.get('eliminated', {}), goals_required)
                if elim_str != '（無消除）':
                    st.markdown(f'&ensp; {elim_str}')

            st.divider()


# ---------------------------------------------------------------------------
# 盤面 HTML 預覽
# ---------------------------------------------------------------------------
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
