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
from level_generator.render_helpers import (
    COLOR_MAP, OBSTACLE_COLOR, EMPTY_COLOR, PUDDLE_COLOR, ROPE_COLOR, MUD_COLOR,
    POWERUP_SYMBOL, _get_tile_color, _is_light, _cell_html,
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
# set_page_config 必須在 module 最頂層呼叫（multi-page 模式相容）
# ---------------------------------------------------------------------------
st.set_page_config(page_title='三消模擬器', layout='wide', page_icon='🎮')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
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
                st.rerun()
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
                    st.rerun()

        if st.button('🤖 AI 自動完成', use_container_width=True):
            if st.session_state.env and not st.session_state.env.done:
                _ai_auto_play()
                st.rerun()

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
