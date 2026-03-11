"""
三消模擬器 — Streamlit 網頁版

用法（本地）:
  streamlit run streamlit_app.py

部署:
  推上 GitHub 後，在 https://share.streamlit.io/ 連結 repo 即可。
"""

import os
import streamlit as st
from match3_env import Match3Env
from basic_agent import BasicAgent
from tile_defs import is_element, is_powerup, is_obstacle, get_def

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


# ---------------------------------------------------------------------------
# 初始化 session state
# ---------------------------------------------------------------------------
def _init_state():
    if 'env' not in st.session_state:
        st.session_state.env = None
        st.session_state.agent = BasicAgent()
        st.session_state.selected = None
        st.session_state.status_msg = ''
        st.session_state.game_started = False


def _new_game(level_file=None):
    if level_file:
        st.session_state.env = Match3Env(level_file=level_file)
    else:
        st.session_state.env = Match3Env(rows=10, cols=9, num_colors=4, max_steps=30)
    st.session_state.selected = None
    st.session_state.status_msg = ''
    st.session_state.game_started = True


def _do_step(action):
    env = st.session_state.env
    _, reward, done, info = env.step(action)
    msg = info.get('msg', '')
    if info.get('shuffled'):
        msg += ' (已洗牌)'
    return msg


# ---------------------------------------------------------------------------
# 處理格子點擊
# ---------------------------------------------------------------------------
def _handle_click(r, c):
    env = st.session_state.env
    if env.done:
        return

    selected = st.session_state.selected

    if selected is None:
        st.session_state.selected = (r, c)
        st.session_state.status_msg = f'已選取 ({r}, {c})'
    else:
        sr, sc = selected
        if (sr, sc) == (r, c):
            # 點自己：道具啟動 or 取消
            tile = env.board.get_middle(sr, sc)
            if tile and is_powerup(tile.tile_id):
                cell = env.board.get_cell(sr, sc)
                if not cell.is_locked() and not cell.has_mud():
                    msg = _do_step({'type': 'activate', 'pos': (sr, sc)})
                    st.session_state.status_msg = f'啟動 ({sr},{sc})  {msg}'
            st.session_state.selected = None
        elif abs(sr - r) + abs(sc - c) == 1:
            # 相鄰 → 交換
            msg = _do_step({'type': 'swap', 'pos1': (sr, sc), 'pos2': (r, c)})
            st.session_state.status_msg = f'交換 ({sr},{sc})↔({r},{c})  {msg}'
            st.session_state.selected = None
        else:
            # 不相鄰 → 選新的
            st.session_state.selected = (r, c)
            st.session_state.status_msg = f'已選取 ({r}, {c})'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title='三消模擬器', layout='wide')
    _init_state()

    st.title('🎮 三消模擬器')

    # ---- 側邊欄 ----
    with st.sidebar:
        st.header('設定')

        # 關卡選擇
        levels_dir = os.path.join(os.path.dirname(__file__), 'levels')
        level_files = []
        if os.path.isdir(levels_dir):
            level_files = sorted(f for f in os.listdir(levels_dir) if f.endswith('.json'))

        level_options = ['(隨機)'] + level_files
        selected_level = st.selectbox('關卡', level_options)

        # 按鈕
        col1, col2 = st.columns(2)
        with col1:
            if st.button('🔄 新遊戲', use_container_width=True):
                if selected_level != '(隨機)':
                    _new_game(os.path.join(levels_dir, selected_level))
                else:
                    _new_game()
        with col2:
            if st.button('🤖 AI 一步', use_container_width=True):
                if st.session_state.env and not st.session_state.env.done:
                    action = st.session_state.agent.choose_action(st.session_state.env)
                    if action is None:
                        st.session_state.env.board.shuffle()
                        st.session_state.status_msg = '無合法步驟，已洗牌'
                    else:
                        msg = _do_step(action)
                        st.session_state.status_msg = f'AI: {_format_action(action)}  {msg}'
                    st.session_state.selected = None

        if st.button('🤖 AI 自動完成', use_container_width=True):
            if st.session_state.env and not st.session_state.env.done:
                _ai_auto_play()

        st.divider()

        # 遊戲資訊
        if st.session_state.env:
            env = st.session_state.env
            st.metric('步數', f'{env.steps_taken} / {env.max_steps}')

            if env.goals_required:
                st.subheader('目標')
                for tid, req in env.goals_required.items():
                    cur = env.goals_current.get(tid, 0)
                    progress = min(cur / req, 1.0) if req > 0 else 1.0
                    st.progress(progress, text=f'{tid}: {cur}/{req}')

            if env.done:
                if env.win:
                    st.success('🎉 勝利！')
                else:
                    st.error('💀 失敗')

        st.divider()
        st.caption('操作說明')
        st.markdown(
            '1. 點擊格子選取\n'
            '2. 點擊相鄰格子交換\n'
            '3. 點擊已選的道具啟動\n'
            '4. 點擊不相鄰格子重新選取'
        )

    # ---- 主區域：盤面 ----
    if not st.session_state.game_started:
        st.info('👈 請在左側選擇關卡，然後點擊「新遊戲」開始')
        return

    env = st.session_state.env
    if env is None:
        return

    # 狀態訊息
    if st.session_state.status_msg:
        st.info(st.session_state.status_msg)

    board = env.board
    selected = st.session_state.selected

    # 用按鈕陣列畫盤面
    for r in range(board.rows):
        cols = st.columns(board.cols, gap='small')
        for c in range(board.cols):
            with cols[c]:
                cell = board.get_cell(r, c)
                tile = cell.middle
                is_sel = (selected == (r, c))

                # 按鈕標籤
                btn_label = _make_btn_label(cell, is_sel)

                if st.button(
                    btn_label,
                    key=f'cell_{r}_{c}',
                    use_container_width=True,
                    type='primary' if is_sel else 'secondary',
                ):
                    _handle_click(r, c)
                    st.rerun()


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


def _format_action(action):
    if action['type'] == 'swap':
        r1, c1 = action['pos1']
        r2, c2 = action['pos2']
        return f'({r1},{c1})↔({r2},{c2})'
    elif action['type'] == 'activate':
        r, c = action['pos']
        return f'啟動({r},{c})'
    return str(action)


def _ai_auto_play():
    """AI 自動玩到結束"""
    env = st.session_state.env
    agent = st.session_state.agent
    max_iter = env.max_steps - env.steps_taken + 5

    for _ in range(max_iter):
        if env.done:
            break
        action = agent.choose_action(env)
        if action is None:
            env.board.shuffle()
            continue
        _do_step(action)

    st.session_state.selected = None
    st.session_state.status_msg = '🎉 勝利！' if env.win else '💀 AI 自動完成 — 失敗'


if __name__ == '__main__':
    main()
