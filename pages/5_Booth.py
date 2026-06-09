"""
🎪 攤位模式 — Google Cloud Day 展示專用

設計原則：
- 零門檻：第一次看到的人 5 秒內知道怎麼操作
- 左右分欄：左邊輸入 / 右邊即時結果
- 快捷按鈕：不知道打什麼就按一個
- Agent 思考過程可視化：讓觀眾看到 AI 在做什麼
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

import streamlit as st

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from level_generator.ai_generator import (
    generate_level, build_system_prompt, build_zero_input_message,
    extract_json_from_response, get_model_provider, _get_key,
    DEFAULT_MODEL,
)
from level_generator.validator import validate_level
from level_generator.sim_runner import run_simulation_batch
from match3_board_component import match3_board
from match3_env import Match3Env

sys.path.insert(0, str(_ROOT / 'scripts'))
from ai_player import find_best_action

st.set_page_config(
    page_title='Match3 AI Level Designer — Google Cloud Day',
    layout='wide',
    page_icon='🎪',
    initial_sidebar_state='collapsed',
)

GODOT_DEMO_URL = 'https://gamacwhung.github.io/Match3_sim/'

QUICK_PROMPTS = [
    ('🎆 超爽連鎖', '請設計一個大面積紙箱填滿底部的關卡，步數充裕，讓玩家容易觸發道具連鎖反應，獲得爽快的消除體驗。'),
    ('🧩 步步為營', '請設計一個有繩索封住上方、底部放高血量紙箱的關卡，玩家需要策略性地先解鎖繩索再攻擊障礙物。'),
    ('🌧️ 障礙雨', '請設計一個有 spawner 的關卡，木桶會持續從頂部落下，玩家要一邊消除一邊應對不斷出現的新障礙。'),
    ('💎 異形盤面', '請設計一個非矩形的特殊盤面（用 void 挖出十字形或菱形），讓關卡看起來與眾不同，增加空間挑戰。'),
    ('🎯 混搭挑戰', '請設計一個中高難度的綜合關卡，混合 2-3 種不同障礙物（如罐頭+水漥+紙箱），目標多元但步數緊張。'),
]


def _init_state():
    defaults = {
        'booth_level': None,
        'booth_chat_history': [],
        'booth_validation': None,
        'booth_sim_results': None,
        'booth_env': None,
        'booth_selected': None,
        'booth_generating': False,
        'booth_agent_log': [],
        'booth_replay': None,       # AI 解關回放記錄
        'booth_replay_step': 0,     # 當前回放步驟
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _load_env_from_dict(level_dict: dict) -> Match3Env:
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


def _run_ai_replay(level_dict: dict, max_steps: int = 200) -> list[dict]:
    """跑一場 AI 解關，記錄每步的動作和盤面狀態供回放用"""
    import random
    import copy

    env = _load_env_from_dict(level_dict)
    rng = random.Random(42)
    replay = []

    # 記錄初始盤面
    replay.append({
        'step': 0,
        'action': None,
        'action_desc': '🎬 初始盤面',
        'goals_current': dict(env.goals_current),
        'goals_required': dict(env.goals_required),
        'steps_left': env.max_steps - env.steps_taken,
        'won': False,
    })

    step = 0
    while not env.done and step < max_steps:
        action = find_best_action(env, rng=rng)
        if action is None:
            env.board.shuffle()
            action = find_best_action(env, rng=rng)
            if action is None:
                break

        # 描述動作
        if action['type'] == 'swap':
            r1, c1 = action['pos1']
            r2, c2 = action['pos2']
            desc = f'🔄 交換 ({r1},{c1}) ↔ ({r2},{c2})'
        else:
            r, c = action['pos']
            desc = f'💥 啟動道具 ({r},{c})'

        obs, reward, done, info = env.step(action)
        step += 1
        eliminated = info.get('eliminated', {})
        elim_str = ', '.join(f'{k}×{v}' for k, v in eliminated.items()) if eliminated else '—'

        replay.append({
            'step': step,
            'action': action,
            'action_desc': f'{desc}　→　消除: {elim_str}',
            'goals_current': dict(env.goals_current),
            'goals_required': dict(env.goals_required),
            'steps_left': env.max_steps - env.steps_taken,
            'won': env.win,
        })

    return replay


def _do_generate(user_msg: str):
    """生成關卡 + 驗證 + 難度預估（Agent Pipeline 流程）"""
    st.session_state.booth_agent_log = []
    st.session_state.booth_sim_results = None
    st.session_state.booth_env = None

    params = {
        'rows': 10, 'cols': 9,
        'difficulty': 'medium',
        'num_colors': 4,
        'obstacle_types': [],
        'goal_types': [],
    }

    log = st.session_state.booth_agent_log

    # Step 1: 生成
    log.append(('thinking', '🤔 正在理解你的需求...'))
    log.append(('tool', '🔧 呼叫 Gemini 2.5 Pro 生成關卡...'))

    try:
        assistant_text, level_dict = generate_level(
            user_message=user_msg,
            chat_history=st.session_state.booth_chat_history,
            params=params,
            model=DEFAULT_MODEL,
        )
    except Exception as e:
        log.append(('error', f'❌ 生成失敗：{e}'))
        return

    if not level_dict:
        log.append(('error', '❌ AI 沒有回傳有效的 JSON'))
        return

    log.append(('success', f'✅ 關卡已生成：{level_dict.get("rows", "?")}×{level_dict.get("cols", "?")} 盤面'))

    # Step 2: 驗證
    log.append(('tool', '🔍 呼叫驗證工具檢查格式...'))
    validation = validate_level(level_dict)
    st.session_state.booth_validation = validation

    if validation.valid:
        log.append(('success', '✅ 格式驗證通過'))
    else:
        error_summary = '、'.join(validation.errors[:3])
        log.append(('warning', f'⚠️ 有 {len(validation.errors)} 個格式問題：{error_summary}'))

    st.session_state.booth_level = level_dict

    # Step 3: 難度預估（快速跑 15 場）
    if validation.valid:
        log.append(('tool', '🤖 呼叫模擬器預估難度（15 場快速測試）...'))
        try:
            results = run_simulation_batch(
                level_dict=level_dict, n_games=15,
                steps_multiplier=1.0, max_workers=4,
            )
            st.session_state.booth_sim_results = results
            log.append(('success', f'📊 模擬完成：AI 勝率 {results.win_rate:.0%} → {results.difficulty_label()}'))
        except Exception as e:
            log.append(('warning', f'⚠️ 模擬失敗（不影響關卡）：{e}'))


def _render_agent_log():
    """渲染 Agent 思考過程"""
    log = st.session_state.booth_agent_log
    if not log:
        return

    st.markdown('#### Agent Pipeline 執行紀錄')
    for step_type, msg in log:
        if step_type == 'thinking':
            st.markdown(f'<div style="color:#666; padding:2px 0;">{msg}</div>', unsafe_allow_html=True)
        elif step_type == 'tool':
            st.markdown(f'<div style="color:#1a73e8; padding:2px 0;">{msg}</div>', unsafe_allow_html=True)
        elif step_type == 'success':
            st.markdown(f'<div style="color:#0d904f; padding:2px 0; font-weight:500;">{msg}</div>', unsafe_allow_html=True)
        elif step_type == 'warning':
            st.markdown(f'<div style="color:#e37400; padding:2px 0;">{msg}</div>', unsafe_allow_html=True)
        elif step_type == 'error':
            st.markdown(f'<div style="color:#d93025; padding:2px 0; font-weight:500;">{msg}</div>', unsafe_allow_html=True)


def main():
    _init_state()

    # 頂部標題
    st.markdown(
        '''
        <div style="text-align:center; padding: 16px 0 8px 0;">
          <h1 style="margin:0; font-size: 2.2em;">
            🎮 Match3 AI Level Designer
          </h1>
          <p style="color:#666; margin: 4px 0 0 0; font-size: 1.05em;">
            用一句話設計你的遊戲關卡 — Powered by <b>Gemini 2.5 Pro</b>
          </p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # 檢查 API key / GCP credentials
    provider = get_model_provider(DEFAULT_MODEL)
    has_key = _get_key(provider) or _get_key('gcp_project')
    if not has_key:
        st.warning(
            '⚠️ 尚未設定 GOOGLE_API_KEY。'
            '請在 config.py 或環境變數中設定，或在下方輸入：'
        )
        key_input = st.text_input('GOOGLE_API_KEY', type='password', placeholder='AIza...')
        if key_input:
            st.session_state['ui_GOOGLE_API_KEY'] = key_input
            st.rerun()
        return

    st.markdown('---')

    # ============================
    # 左右分欄
    # ============================
    col_left, col_right = st.columns([2, 3])

    with col_left:
        st.markdown('#### 💬 描述你想要的關卡')
        st.caption('點一個快捷按鈕，或自己輸入任何想法')

        # 快捷按鈕
        prompt_cols = st.columns(3)
        clicked_prompt = None
        for i, (label, prompt_text) in enumerate(QUICK_PROMPTS):
            col_idx = i % 3
            with prompt_cols[col_idx]:
                if st.button(label, key=f'qp_{i}', use_container_width=True):
                    clicked_prompt = prompt_text

        # 顯示選中的 prompt 文字（讓觀眾看到）
        if clicked_prompt:
            st.info(f'📝 Prompt：「{clicked_prompt}」')

        # 自由輸入
        user_input = st.text_area(
            '自由輸入',
            placeholder='例：做一個消除起來很爽的關卡 / 給我一個需要動腦的策略關 / 做一個愛心形狀的盤面...',
            height=80,
            label_visibility='collapsed',
        )

        # 生成按鈕
        gen_cols = st.columns([3, 1])
        with gen_cols[0]:
            generate_clicked = st.button(
                '✨ 用 Gemini 生成',
                use_container_width=True,
                type='primary',
            )
        with gen_cols[1]:
            if st.button('🗑️', use_container_width=True, help='清除對話'):
                st.session_state.booth_chat_history = []
                st.session_state.booth_level = None
                st.session_state.booth_agent_log = []
                st.session_state.booth_sim_results = None
                st.session_state.booth_env = None
                st.rerun()

        # 觸發生成
        final_prompt = clicked_prompt or (user_input if generate_clicked else None)
        if final_prompt:
            with st.spinner('Agent 執行中...'):
                _do_generate(final_prompt)
            st.rerun()

        # Agent 執行紀錄
        st.markdown('---')
        _render_agent_log()

    with col_right:
        level = st.session_state.booth_level
        if level is None:
            st.markdown(
                '''
                <div style="text-align:center; padding: 80px 20px; color:#999;">
                  <div style="font-size: 3em;">🎲</div>
                  <p style="margin-top: 16px; font-size: 1.1em;">
                    點左邊的按鈕或輸入描述<br>AI 會在幾秒內生成一個可玩的關卡
                  </p>
                </div>
                ''',
                unsafe_allow_html=True,
            )
        else:
            # 關卡資訊卡
            info_cols = st.columns(4)
            with info_cols[0]:
                st.metric('盤面', f"{level.get('rows', '?')}×{level.get('cols', '?')}")
            with info_cols[1]:
                st.metric('步數', level.get('max_steps', '?'))
            with info_cols[2]:
                st.metric('目標數', len(level.get('goals', {})))
            with info_cols[3]:
                sim = st.session_state.booth_sim_results
                if sim:
                    st.metric('AI 勝率', f'{sim.win_rate:.0%}')
                else:
                    st.metric('AI 勝率', '—')

            # 目標
            goals = level.get('goals', {})
            if goals:
                st.markdown('**目標：** ' + '　'.join(f'`{k}` ×{v}' for k, v in goals.items()))

            # 驗證狀態
            v = st.session_state.booth_validation
            if v:
                if v.valid and not v.warnings:
                    st.success('✅ 格式驗證通過，可以遊玩')
                elif v.valid:
                    st.warning(f'⚠️ 通過但有 {len(v.warnings)} 個建議')
                else:
                    st.error(f'❌ {len(v.errors)} 個格式錯誤')
                    for err in v.errors[:3]:
                        st.caption(f'  · {err}')

            # 難度標籤
            sim = st.session_state.booth_sim_results
            if sim:
                wr = sim.win_rate
                if wr >= 0.8:
                    st.info(f'📊 難度評估：🟢 輕鬆（AI 勝率 {wr:.0%}）— 大多數人可輕鬆過關')
                elif wr >= 0.5:
                    st.info(f'📊 難度評估：🟡 適中（AI 勝率 {wr:.0%}）— 需要一些策略')
                elif wr >= 0.25:
                    st.warning(f'📊 難度評估：🟠 有挑戰（AI 勝率 {wr:.0%}）— 可能要試幾次')
                else:
                    st.error(f'📊 難度評估：🔴 極難（AI 勝率 {wr:.0%}）— 需要運氣+策略')

            # Godot 嵌入式試玩
            st.markdown('---')
            if v and v.valid:
                import base64
                level_json_str = json.dumps(level, ensure_ascii=False)
                level_b64 = base64.b64encode(level_json_str.encode('utf-8')).decode('ascii')

                # 如果有 autoplay 動作，加入 URL 參數
                autoplay_param = ''
                if st.session_state.get('booth_autoplay_moves'):
                    moves_json = json.dumps(st.session_state['booth_autoplay_moves'], ensure_ascii=False)
                    moves_b64 = base64.b64encode(moves_json.encode('utf-8')).decode('ascii')
                    autoplay_param = f'&autoplay={moves_b64}'
                    st.session_state['booth_autoplay_moves'] = None

                godot_url = f'{GODOT_DEMO_URL}?level_lz={level_b64}{autoplay_param}'

                st.markdown('##### 🎮 直接試玩')
                st.components.v1.iframe(godot_url, height=700, scrolling=False)

                # 重製關卡按鈕
                regen_cols = st.columns([3, 1])
                with regen_cols[1]:
                    if st.button('🔄 重製', use_container_width=True, help='重新生成關卡'):
                        last_prompt = st.session_state.booth_chat_history[-1]['content'] if st.session_state.booth_chat_history else None
                        if last_prompt:
                            with st.spinner('重新生成中...'):
                                _do_generate(last_prompt)
                            st.rerun()

            # 行動按鈕
            st.markdown('---')
            action_cols = st.columns([2, 2, 1])
            with action_cols[0]:
                if st.button('🤖 詳細模擬（30 場）', use_container_width=True):
                    with st.spinner('模擬中...'):
                        try:
                            results = run_simulation_batch(
                                level_dict=level, n_games=30,
                                steps_multiplier=1.0, max_workers=4,
                            )
                            st.session_state.booth_sim_results = results
                            st.rerun()
                        except Exception as e:
                            st.error(f'模擬失敗：{e}')
            with action_cols[1]:
                if st.button('🧠 觀看 AI 解關', use_container_width=True):
                    with st.spinner('AI 正在計算解法...'):
                        replay = _run_ai_replay(level)
                        st.session_state.booth_replay = replay
                        st.session_state.booth_replay_step = len(replay) - 1
                        # 提取動作序列給 Godot autoplay
                        moves = [f['action'] for f in replay if f['action'] is not None]
                        moves_for_godot = []
                        for m in moves:
                            if m['type'] == 'swap':
                                moves_for_godot.append({
                                    'type': 'swap',
                                    'pos1': list(m['pos1']),
                                    'pos2': list(m['pos2']),
                                })
                            elif m['type'] == 'activate':
                                moves_for_godot.append({
                                    'type': 'activate',
                                    'pos': list(m['pos']),
                                })
                        st.session_state['booth_autoplay_moves'] = moves_for_godot
                        st.rerun()
            with action_cols[2]:
                if level:
                    st.download_button(
                        '⬇️',
                        data=json.dumps(level, indent=2, ensure_ascii=False),
                        file_name='ai_generated_level.json',
                        mime='application/json',
                        use_container_width=True,
                        help='下載關卡 JSON',
                    )

            # AI 解關回放
            replay = st.session_state.booth_replay
            if replay:
                st.markdown('---')
                st.markdown('#### 🧠 AI 解關紀錄')

                last = replay[-1]
                if last['won']:
                    st.success(f"✅ AI 在 {last['step']} 步內通關！")
                else:
                    st.warning(f"❌ AI 用了 {last['step']} 步但未通關")

                # 進度顯示
                total_steps = len(replay) - 1
                if total_steps > 0:
                    step_idx = st.slider(
                        '回放步驟', 0, total_steps, total_steps,
                        key='replay_slider',
                    )
                    frame = replay[step_idx]
                    st.markdown(f"**第 {frame['step']} 步** — {frame['action_desc']}")

                    # 目標進度
                    goals_str_parts = []
                    for gid, req in frame['goals_required'].items():
                        cur = frame['goals_current'].get(gid, 0)
                        pct = min(cur / req, 1.0) if req > 0 else 1.0
                        bar = '█' * int(pct * 10) + '░' * (10 - int(pct * 10))
                        goals_str_parts.append(f'`{gid}` {bar} {cur}/{req}')
                    if goals_str_parts:
                        st.markdown('　'.join(goals_str_parts))
                    st.caption(f"剩餘步數：{frame['steps_left']}")

    # 底部 footer
    st.markdown('---')
    st.markdown(
        '<div style="text-align:center; color:#999; font-size:0.85em;">'
        'Built with <b>Gemini 2.5 Pro</b> · Google Gen AI SDK · '
        'Godot 4 Engine · Python Match3 Simulator'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == '__main__':
    main()
