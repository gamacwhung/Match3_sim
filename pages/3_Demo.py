"""
🎬 Demo 頁 — 為 Google Marketing Day 3-5 分鐘演示而生

核心理念:零雜訊、零參數,一打開直接玩。

主流程(流 A:無限關卡循環)
    開場 → 大按鈕「開始試玩」 → 載入第一個 demo 關卡 →
    通關後 → 「下一關」按鈕 → 載入下一個 → 循環

進階區(預設折疊)
    - 客製化生成(流 C):輸入需求 → AI 生成 → 試玩
    - 切換到 Godot 美術版盤面(等 Godot web export 完成後啟用)
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import sys
import tempfile

import streamlit as st

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from match3_env import Match3Env
from tile_defs import is_powerup
from level_generator.official_format import official_to_ours
from level_generator.render_helpers import (
    format_eliminated, make_move_log_entry, render_move_log,
)
from match3_board_component import match3_board

# ---------------------------------------------------------------------------
# 頁面設定 — 不要 sidebar(本頁邏輯不依賴 sidebar)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title='Match3 Demo',
    layout='wide',
    page_icon='🎬',
    initial_sidebar_state='collapsed',
)

# ---------------------------------------------------------------------------
# Demo 關卡曲目單(從 100 個官方關卡精選)
#
# 挑選原則:由淺入深、視覺差異大、能 show 不同障礙物 / 道具
# 每個關卡可在跑 demo 時即時改 — 但用 list 控制順序保證順暢
# ---------------------------------------------------------------------------
DEMO_PLAYLIST = [
    # (官方編號, demo 標籤, 一句話介紹)
    (1,  '🟫 紙箱關', '消除整片紙箱'),
    (3,  '🟧 交通錐關', '清掉所有交通錐'),
    (12, '💧 水漥關', '把地面水漥踩乾'),
    (25, '🥫 罐頭關', '打開罐頭釋放魚'),
    (33, '🧊 飲料櫃關', '2×2 大冰箱共享血量'),
    (50, '🏊 充氣泳池關', '多層障礙連鎖'),
    (73, '🎁 綜合關', '混合障礙與道具'),
    (91, '🔥 高難度關', 'AI 模擬通過率 < 30%'),
]
OFFICIAL_DIR = _ROOT / '關卡格式資料'


def _load_official_level(num: int):
    """把官方關卡轉成我們的格式 dict"""
    path = OFFICIAL_DIR / f'Level_{num}.json'
    if not path.exists():
        return None, f'找不到 Level_{num}.json'
    try:
        official = json.loads(path.read_text(encoding='utf-8'))
        ours, _warnings = official_to_ours(official)
        return ours, None
    except Exception as e:
        return None, f'轉換失敗:{e}'


def _make_env(level_dict: dict) -> Match3Env:
    """從 dict 建一個 Env(用 NamedTemporaryFile + delete=False;Windows 友善)"""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            tmp_path = f.name
            json.dump(level_dict, f, ensure_ascii=False)
        return Match3Env(level_file=tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        'demo_started': False,
        'demo_idx': 0,
        'demo_level_dict': None,
        'demo_env': None,
        'demo_selected': None,
        'demo_status': '',
        'demo_move_log': [],
        'demo_streak': 0,
        'demo_show_advanced': False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _start_demo_level(idx: int):
    """載入 playlist 中第 idx 個關卡,wrap around"""
    idx = idx % len(DEMO_PLAYLIST)
    num, _label, _desc = DEMO_PLAYLIST[idx]
    lvl, err = _load_official_level(num)
    if err:
        st.error(err)
        return False
    try:
        env = _make_env(lvl)
    except Exception as e:
        st.error(f'載入引擎失敗:{e}')
        return False
    st.session_state.demo_idx = idx
    st.session_state.demo_level_dict = lvl
    st.session_state.demo_env = env
    st.session_state.demo_selected = None
    st.session_state.demo_status = ''
    st.session_state.demo_move_log = []
    st.session_state.demo_started = True
    return True


def _handle_click(r: int, c: int):
    env: Match3Env = st.session_state.demo_env
    if env is None or env.done:
        return
    selected = st.session_state.demo_selected

    if selected is None:
        st.session_state.demo_selected = (r, c)
        st.session_state.demo_status = f'已選取 ({r},{c})'
        return

    sr, sc = selected
    if (sr, sc) == (r, c):
        # 同格 → 道具啟動 / 取消
        tile = env.board.get_middle(sr, sc)
        if tile and is_powerup(tile.tile_id):
            cell = env.board.get_cell(sr, sc)
            if not cell.is_locked() and not cell.has_mud():
                goals_before = dict(env.goals_current)
                _, _, _, info = env.step({'type': 'activate', 'pos': (sr, sc)})
                st.session_state.demo_move_log.insert(0, make_move_log_entry(
                    f'啟動 ({sr},{sc})', info, goals_before,
                    env.goals_current, env.goals_required, env.steps_taken))
                st.session_state.demo_status = f'啟動 ({sr},{sc})  {info.get("msg","")}'
        st.session_state.demo_selected = None
    elif abs(sr - r) + abs(sc - c) == 1:
        # 鄰格 → 交換
        goals_before = dict(env.goals_current)
        _, _, _, info = env.step({'type': 'swap', 'pos1': (sr, sc), 'pos2': (r, c)})
        st.session_state.demo_move_log.insert(0, make_move_log_entry(
            f'交換 ({sr},{sc})↔({r},{c})', info, goals_before,
            env.goals_current, env.goals_required, env.steps_taken))
        st.session_state.demo_status = f'交換 ({sr},{sc})↔({r},{c})  {info.get("msg","")}'
        st.session_state.demo_selected = None
    else:
        st.session_state.demo_selected = (r, c)
        st.session_state.demo_status = f'已選取 ({r},{c})'


# ---------------------------------------------------------------------------
# 各區段 UI
# ---------------------------------------------------------------------------
def _render_intro():
    """開場 — 還沒按過開始"""
    st.markdown(
        """
        <div style="text-align:center; padding: 40px 20px;">
          <h1 style="font-size: 3em; margin: 0;">🎬 Match3 模擬器</h1>
          <p style="font-size: 1.2em; color:#666; margin-top: 8px;">
            AI 關卡生成 × 即時試玩 × 難度模擬 — 三合一
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns([1, 2, 1])
    with cols[1]:
        if st.button('▶  開始試玩', use_container_width=True, type='primary',
                     key='btn_start_demo'):
            if _start_demo_level(0):
                st.rerun()

        st.markdown(
            """
            <div style="text-align:center; color:#888; margin-top: 16px;">
              共 8 個精選關卡,通關後一鍵下一關
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 三大亮點區塊
    st.markdown('---')
    feat_cols = st.columns(3)
    with feat_cols[0]:
        st.markdown(
            """
            ### 🤖 AI 一鍵生成
            支援 GPT-4o / Claude
            可從圖片、文字描述、官方 JSON 生成關卡
            """
        )
    with feat_cols[1]:
        st.markdown(
            """
            ### 🎮 即時試玩
            基本元素 / 道具 / 障礙物
            完整支援 2×2 大物件、層狀盤面
            """
        )
    with feat_cols[2]:
        st.markdown(
            """
            ### 📊 難度模擬
            BasicAgent 暴力搜索
            一鍵跑 100 場估算成功率
            """
        )


def _render_play():
    """主遊玩畫面"""
    env: Match3Env = st.session_state.demo_env
    idx = st.session_state.demo_idx
    num, label, desc = DEMO_PLAYLIST[idx]

    # 頂部關卡資訊列
    head_cols = st.columns([2, 3, 2])
    with head_cols[0]:
        st.markdown(f'### {label}')
        st.caption(f'官方關卡 #{num}  ·  {desc}')
    with head_cols[1]:
        # 目標進度 — 用 progress bar 比文字直觀
        if env.goals_required:
            for tid, req in env.goals_required.items():
                cur = env.goals_current.get(tid, 0)
                pct = min(cur / req, 1.0) if req > 0 else 1.0
                st.progress(pct, text=f'{tid}: {cur} / {req}')
    with head_cols[2]:
        sub_cols = st.columns(2)
        with sub_cols[0]:
            steps_left = env.max_steps - env.steps_taken
            st.metric('剩餘步數', steps_left)
        with sub_cols[1]:
            st.metric('連勝', st.session_state.demo_streak)

    # 上一步消除摘要
    log = st.session_state.demo_move_log
    if log:
        last = log[0]
        last_msg = format_eliminated(last['eliminated'], env.goals_required)
        if last.get('shuffled'):
            last_msg += '  🔀 已自動洗牌'
        if last_msg:
            st.caption(last_msg)

    # ================ 通關 / 失敗 處理 ================
    if env.done:
        if getattr(env, 'win', False):
            # 通關 — streak 只在第一次進入這個分支時 +1
            streak_flag = f'_streak_counted_{idx}'
            if not st.session_state.get(streak_flag):
                st.session_state.demo_streak += 1
                st.session_state[streak_flag] = True
            st.success(f'🎉 通關!連勝 {st.session_state.demo_streak} 關')
            ctrl = st.columns([1, 2, 1])
            with ctrl[1]:
                if st.button('▶  下一關 →', use_container_width=True, type='primary',
                             key=f'btn_next_{idx}'):
                    # 清掉本關的 streak counted flag
                    st.session_state.pop(f'_streak_counted_{idx}', None)
                    _start_demo_level(idx + 1)
                    st.rerun()
            small = st.columns([1, 1, 1])
            with small[1]:
                if st.button('🔁 再玩一次', use_container_width=True, key=f'btn_replay_{idx}'):
                    st.session_state.pop(f'_streak_counted_{idx}', None)
                    st.session_state.demo_streak = max(0, st.session_state.demo_streak - 1)
                    _start_demo_level(idx)
                    st.rerun()
        else:
            st.session_state.demo_streak = 0
            st.error('💀 步數用完')
            ctrl = st.columns([1, 1, 1])
            with ctrl[0]:
                if st.button('🔁 重新挑戰', use_container_width=True,
                             key=f'btn_retry_{idx}'):
                    _start_demo_level(idx)
                    st.rerun()
            with ctrl[1]:
                if st.button('⏭ 跳過此關', use_container_width=True,
                             key=f'btn_skip_{idx}'):
                    _start_demo_level(idx + 1)
                    st.rerun()

        # 結束畫面也要顯示盤面當作復盤
        st.divider()
        match3_board(env, mode='preview', cell_size=52, key=f'demo_done_{idx}')
        return

    # ================ 進行中 ================
    selected = st.session_state.demo_selected
    click = match3_board(
        env,
        mode='play',
        selected=selected,
        cell_size=58,  # 比 Level_Generator(56)略大,demo 觀感
        key=f'demo_play_{idx}',
    )
    if click and click.get('type') == 'click':
        last_ts = st.session_state.get('demo_last_ts')
        if click.get('ts') != last_ts:
            st.session_state.demo_last_ts = click.get('ts')
            _handle_click(int(click['r']), int(click['c']))
            st.rerun()

    # 底部小工具列(放重置 / 跳關 / 進階)
    foot = st.columns([1, 1, 1, 4])
    with foot[0]:
        if st.button('🔁 重置本關', key=f'btn_reset_{idx}'):
            _start_demo_level(idx)
            st.rerun()
    with foot[1]:
        if st.button('⏭ 跳到下一關', key=f'btn_skipnow_{idx}'):
            _start_demo_level(idx + 1)
            st.rerun()
    with foot[2]:
        if st.button('🏁 退出 demo', key=f'btn_quit_{idx}'):
            st.session_state.demo_started = False
            st.session_state.demo_streak = 0
            st.rerun()


def _render_advanced():
    """進階區 — 預設折疊。展開後可切到 Level_Generator / 開啟 Godot 美術版。"""
    with st.expander('⚙️ 進階模式', expanded=False):
        st.markdown('### 🎲 完整工具')
        st.markdown(
            '想試試 **AI 客製化生成**、**JSON 編輯**、**BasicAgent 模擬難度**?'
            '完整工具在 → **Level Generator** 頁(左側選單)'
        )
        st.caption(
            'Demo 主流程刻意精簡。所有開發者選項都收在 Level Generator,'
            '免得不小心點到打斷 demo 節奏。'
        )

        st.divider()
        st.markdown('### 🎨 Godot 美術版盤面')
        st.markdown(
            '相比 Streamlit Component,Godot 是真正的遊戲引擎,'
            '可以做粒子、shader、tween 等真實遊戲特效。'
        )

        # 兩種模式:iframe 內嵌(預設) / 新分頁打開(備案)
        # Godot 4 single-thread export(thread_support=false)不需要
        # SharedArrayBuffer,所以 iframe 嵌入是可行的。
        # 若 audio 卡住或畫面異常,切回新分頁打開即可。
        godot_url = st.text_input(
            'Godot web build URL',
            value='http://localhost:8765/',
            help=(
                '需要在另一個終端執行 (或用根目錄 `.\\start_demo.ps1` 一鍵起):\n\n'
                '`cd godot_demo/web; python -m http.server 8765`'
            ),
        )

        embed_mode = st.radio(
            '嵌入方式',
            ['🪟 直接嵌在頁內(iframe)', '🔗 在新分頁打開'],
            horizontal=True,
            help='iframe 模式體驗最連貫,但若 audio 卡住或 wasm 載入失敗,切「新分頁」即可',
        )

        if embed_mode.startswith('🪟'):
            # iframe 內嵌
            iframe_height = st.slider('盤面高度 (px)', 480, 1200, 800, 40)
            try:
                import streamlit.components.v1 as components
                components.iframe(godot_url, height=iframe_height, scrolling=False)
            except Exception as e:
                st.error(f'iframe 載入失敗:{e}。請改用新分頁打開。')
            st.caption(
                '若看到「Failed to fetch」: Godot HTTP server 沒起,'
                '到根目錄跑 `.\\start_demo.ps1` 或 `cd godot_demo/web; python -m http.server 8765`。'
            )
        else:
            st.link_button(
                '🎬 在新分頁打開 Godot 美術版',
                url=godot_url,
                use_container_width=True,
            )
            st.caption(
                '新分頁打開最穩,iframe 若有 cross-origin / audio worklet 問題就用這個。'
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    _init_state()

    if not st.session_state.demo_started:
        _render_intro()
    else:
        _render_play()

    _render_advanced()


if __name__ == '__main__':
    main()
