"""
AI 關卡生成器 — Streamlit 頁面
"""

import sys
import os
import json
import random
import tempfile
import pathlib

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

import streamlit as st
from match3_env import Match3Env
from tile_defs import is_powerup
from level_generator.ai_generator import (
    generate_level, build_zero_input_message, build_system_prompt,
    extract_json_from_response, get_available_models,
    get_model_provider, model_id_from_display, _get_key,
    DEFAULT_MODEL,
)
from level_generator.validator import validate_level
from level_generator.sim_runner import run_simulation_batch
from level_generator.render_helpers import (
    render_board_preview_html, _make_btn_label, _cell_html,
)

st.set_page_config(
    page_title='AI 關卡生成器',
    layout='wide',
    page_icon='🎲',
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
ALL_OBSTACLES = [
    'Crt1', 'Crt2', 'Crt3', 'Crt4',
    'Barrel', 'TrafficCone_lv1', 'TrafficCone_lv2',
    'SalmonCan', 'WaterChiller_closed', 'BeverageChiller_closed',
    'Pool_lv1', 'Pool_lv2', 'Pool_lv3', 'Stamp',
]
ALL_GOAL_TYPES = [
    'Crt（紙箱）', 'Puddle（水漥）', 'TrafficCone（交通錐）',
    'SalmonCan（罐頭）', 'Pool（游泳池）', 'Stamp（印章）',
    'Barrel（木桶）',
]
GOAL_HINT_MAP = {
    'Crt（紙箱）': 'Crt1', 'Puddle（水漥）': 'Puddle',
    'TrafficCone（交通錐）': 'TrafficCone', 'SalmonCan（罐頭）': 'SalmonCan',
    'Pool（游泳池）': 'Pool', 'Stamp（印章）': 'Stamp', 'Barrel（木桶）': 'Barrel',
}
ALL_GOAL_KEYS = list(GOAL_HINT_MAP.values())

# 支援視覺輸入的模型
VISION_MODELS = {
    'gpt-4o', 'gpt-4o-mini',
    'gpt-5.4-2026-03-05', 'gpt-5.3-chat-latest',
    'claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5-20251001',
}

# ---------------------------------------------------------------------------
# Session state 初始化
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        'gen_level_json': None,
        'gen_chat_history': [],
        'gen_sim_results': None,
        'gen_validation': None,
        'gen_last_image_bytes': None,
        'gen_last_image_type': 'image/png',
        'gen_json_version': 0,    # 每次 level 更新時遞增，強制 text_area 刷新
        'gen_play_env': None,
        'gen_play_selected': None,
        'gen_play_status': '',
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _set_level(level_dict: dict):
    """統一更新 gen_level_json，並讓 textarea 刷新"""
    st.session_state.gen_level_json = level_dict
    st.session_state.gen_validation = validate_level(level_dict)
    st.session_state.gen_sim_results = None
    st.session_state.gen_play_env = None
    st.session_state.gen_play_selected = None
    st.session_state.gen_play_status = ''
    st.session_state.gen_json_version += 1


def _clear_conversation():
    st.session_state.gen_chat_history = []
    st.session_state.gen_level_json = None
    st.session_state.gen_sim_results = None
    st.session_state.gen_validation = None
    st.session_state.gen_play_env = None
    st.session_state.gen_json_version += 1


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


def _do_generate(user_msg: str, params: dict,
                 image_bytes=None, image_type='image/png', model=DEFAULT_MODEL):
    try:
        with st.spinner('AI 正在生成關卡...'):
            assistant_text, level_dict = generate_level(
                user_message=user_msg,
                chat_history=st.session_state.gen_chat_history,
                params=params,
                image_bytes=image_bytes,
                image_media_type=image_type,
                model=model,
            )
        if level_dict:
            _set_level(level_dict)
        else:
            st.warning('AI 沒有回傳有效的 JSON，請嘗試重新描述需求。')
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f'生成失敗：{e}')


# ---------------------------------------------------------------------------
# 互動遊玩
# ---------------------------------------------------------------------------
def _handle_play_click(r: int, c: int):
    env = st.session_state.gen_play_env
    if env is None or env.done:
        return
    selected = st.session_state.gen_play_selected

    if selected is None:
        st.session_state.gen_play_selected = (r, c)
        st.session_state.gen_play_status = f'已選取 ({r},{c})'
    else:
        sr, sc = selected
        if (sr, sc) == (r, c):
            tile = env.board.get_middle(sr, sc)
            if tile and is_powerup(tile.tile_id):
                cell = env.board.get_cell(sr, sc)
                if not cell.is_locked() and not cell.has_mud():
                    _, _, _, info = env.step({'type': 'activate', 'pos': (sr, sc)})
                    st.session_state.gen_play_status = f'啟動  {info.get("msg","")}'
            st.session_state.gen_play_selected = None
        elif abs(sr - r) + abs(sc - c) == 1:
            _, _, _, info = env.step({'type': 'swap', 'pos1': (sr, sc), 'pos2': (r, c)})
            st.session_state.gen_play_status = f'交換 ({sr},{sc})↔({r},{c})  {info.get("msg","")}'
            st.session_state.gen_play_selected = None
        else:
            st.session_state.gen_play_selected = (r, c)
            st.session_state.gen_play_status = f'已選取 ({r},{c})'


def _render_play_ui(env: Match3Env):
    """互動盤面（按鈕版）"""
    selected = st.session_state.gen_play_selected

    # 目標進度
    goals = env.goals_required
    progress = getattr(env, 'goals_progress', {})
    if goals:
        parts = []
        for tid, req in goals.items():
            done_cnt = progress.get(tid, 0)
            remaining = max(0, req - done_cnt)
            parts.append(f'`{tid}` {remaining}/{req}')
        st.markdown('**目標剩餘：** ' + '  '.join(parts))

    # 狀態列
    steps_left = env.max_steps - env.steps_taken
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.metric('剩餘步數', steps_left)
    with col_s2:
        if env.done:
            win = getattr(env, 'win', None)
            if win:
                st.success('🎉 通關！')
            else:
                st.error('💀 失敗')
    with col_s3:
        if st.session_state.gen_play_status:
            st.caption(st.session_state.gen_play_status)

    if env.done:
        return

    # 棋盤按鈕
    for r in range(env.board.rows):
        cols = st.columns(env.board.cols)
        for c in range(env.board.cols):
            cell = env.board.get_cell(r, c)
            is_sel = selected == (r, c)
            label = _make_btn_label(cell, is_sel)
            if is_sel:
                label = f'[{label}]'
            with cols[c]:
                if st.button(label, key=f'gen_play_{r}_{c}', use_container_width=True):
                    _handle_play_click(r, c)
                    st.rerun()


def _render_validation(v):
    if not v:
        return
    if v.valid and not v.warnings:
        st.success('✅ 格式驗證通過')
    elif v.valid:
        st.warning(f'⚠️ {len(v.warnings)} 個警告')
        with st.expander('查看警告'):
            for w in v.warnings:
                st.markdown(f'- 🟡 {w}')
    else:
        st.error(f'❌ {len(v.errors)} 個錯誤')
        with st.expander('查看錯誤'):
            for err in v.errors:
                st.markdown(f'- 🔴 {err}')
        if v.warnings:
            with st.expander(f'另有 {len(v.warnings)} 個警告'):
                for w in v.warnings:
                    st.markdown(f'- 🟡 {w}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    _init_state()
    st.title('🎲 AI 關卡生成器')

    # ============================================================
    # 側欄
    # ============================================================
    with st.sidebar:
        st.header('關卡參數')
        st.caption('勾選 ☑ = 生成時此參數隨機化（預設全勾）')

        # 行數
        c_cb, c_ctrl = st.columns([1, 5])
        with c_cb:
            rand_rows = st.checkbox('', value=True, key='cb_rand_rows', label_visibility='collapsed')
        with c_ctrl:
            rows_val = st.slider('行數 (rows)', 5, 12, 10, disabled=rand_rows)

        # 列數
        c_cb, c_ctrl = st.columns([1, 5])
        with c_cb:
            rand_cols = st.checkbox('', value=True, key='cb_rand_cols', label_visibility='collapsed')
        with c_ctrl:
            cols_val = st.slider('列數 (cols)', 5, 10, 9, disabled=rand_cols)

        # 難度
        c_cb, c_ctrl = st.columns([1, 5])
        with c_cb:
            rand_diff = st.checkbox('', value=True, key='cb_rand_diff', label_visibility='collapsed')
        with c_ctrl:
            diff_val = st.selectbox('難度', ['easy', 'medium', 'hard'], index=1, disabled=rand_diff)

        # 顏色數
        c_cb, c_ctrl = st.columns([1, 5])
        with c_cb:
            rand_colors = st.checkbox('', value=True, key='cb_rand_colors', label_visibility='collapsed')
        with c_ctrl:
            colors_val = st.slider('顏色數', 3, 6, 4, disabled=rand_colors)

        # 障礙物類型
        c_cb, c_ctrl = st.columns([1, 5])
        with c_cb:
            rand_obs = st.checkbox('', value=True, key='cb_rand_obs', label_visibility='collapsed')
        with c_ctrl:
            st.markdown('**障礙物類型**（可多選）')
        obs_val = st.multiselect('障礙物', ALL_OBSTACLES, label_visibility='collapsed', disabled=rand_obs)

        # 目標類型
        c_cb, c_ctrl = st.columns([1, 5])
        with c_cb:
            rand_goals = st.checkbox('', value=True, key='cb_rand_goals', label_visibility='collapsed')
        with c_ctrl:
            st.markdown('**目標類型**（可多選）')
        goals_display_val = st.multiselect('目標', ALL_GOAL_TYPES, label_visibility='collapsed', disabled=rand_goals)

        # 計算兩組 params：生成用（帶隨機化）和 Chat 用（純 sidebar 值）
        params_for_generate = {
            'rows': random.randint(7, 12) if rand_rows else rows_val,
            'cols': random.randint(7, 10) if rand_cols else cols_val,
            'difficulty': random.choice(['easy', 'medium', 'hard']) if rand_diff else diff_val,
            'num_colors': random.randint(3, 6) if rand_colors else colors_val,
            'obstacle_types': (random.sample(ALL_OBSTACLES, k=random.randint(0, 3)) if rand_obs else obs_val),
            'goal_types': (random.sample(ALL_GOAL_KEYS, k=random.randint(1, 2)) if rand_goals
                           else [GOAL_HINT_MAP.get(g, g) for g in goals_display_val]),
        }
        params_for_chat = {
            'rows': rows_val, 'cols': cols_val, 'difficulty': diff_val,
            'num_colors': colors_val, 'obstacle_types': obs_val,
            'goal_types': [GOAL_HINT_MAP.get(g, g) for g in goals_display_val],
        }

        st.divider()

        model_display = st.selectbox('AI 模型', get_available_models(), index=0)
        model = model_id_from_display(model_display)
        provider = get_model_provider(model)
        key_label = 'OPENAI_API_KEY' if provider == 'openai' else 'ANTHROPIC_API_KEY'
        ss_key = f'ui_{key_label}'

        config_has_key = _get_key(provider) is not None and not st.session_state.get(ss_key)
        if config_has_key:
            st.caption(f'✅ {key_label} 已設定（config.py）')
        else:
            entered = st.text_input(
                key_label, value=st.session_state.get(ss_key, ''),
                type='password', placeholder='sk-...',
                help='填入後僅存在此瀏覽器 session，不會被儲存',
            )
            if entered != st.session_state.get(ss_key, ''):
                st.session_state[ss_key] = entered
                st.rerun()
            if entered:
                st.caption('✅ API key 已填入')
            else:
                st.warning(f'⚠️ 請填入 {key_label}')

        if model not in VISION_MODELS:
            st.caption(f'ℹ️ {model_display} 不確定是否支援圖片輸入')

        st.divider()

        if st.button('🎲 立即生成', use_container_width=True, type='primary'):
            params = params_for_generate
            user_msg = build_zero_input_message(params)
            _do_generate(user_msg, params, model=model)
            st.rerun()

        if st.button('🗑️ 清除對話', use_container_width=True):
            _clear_conversation()
            st.rerun()

        if st.session_state.gen_level_json:
            st.divider()
            lvl = st.session_state.gen_level_json
            st.caption(f"當前：{lvl.get('name', '未命名')}")
            st.caption(f"{lvl.get('rows')}×{lvl.get('cols')} | {lvl.get('max_steps')} 步")
            v = st.session_state.gen_validation
            if v:
                if v.valid:
                    st.success('✅ 格式驗證通過')
                else:
                    st.error(f'❌ 有 {len(v.errors)} 個錯誤')

        st.divider()
        st.subheader('載入現有關卡')
        levels_dir = _ROOT / 'levels'
        level_files = sorted(
            f for f in os.listdir(levels_dir) if f.endswith('.json')
        ) if levels_dir.is_dir() else []
        if level_files:
            selected_lvl = st.selectbox('選擇關卡', [''] + level_files)
            if selected_lvl and st.button('載入', use_container_width=True):
                try:
                    with open(levels_dir / selected_lvl, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    _set_level(loaded)
                    st.rerun()
                except Exception as e:
                    st.error(f'載入失敗：{e}')

    # ============================================================
    # 主區域：3 個 Tab
    # ============================================================
    tab_chat, tab_edit, tab_sim = st.tabs([
        '💬 Chat & 生成', '📝 JSON + 預覽 & 遊玩', '🤖 模擬測試'
    ])

    # ----------------------------------------------------------
    # Tab 1: Chat & Generate
    # ----------------------------------------------------------
    with tab_chat:
        st.markdown('輸入需求讓 AI 生成關卡，也可以對結果提出修改意見。')

        uploaded = st.file_uploader(
            '📷 參考圖片（可選）',
            type=['png', 'jpg', 'jpeg', 'webp'],
            help='需選支援 vision 的模型（GPT-4o、GPT-5.x、Claude 系列）。Streamlit 不支援直接在對話框貼圖，請用此上傳。',
        )
        if uploaded:
            st.image(uploaded, caption='參考圖片', width=300)
            st.session_state.gen_last_image_bytes = uploaded.read()
            mime = (
                'image/webp' if uploaded.type == 'image/webp' else
                'image/jpeg' if uploaded.type in ('image/jpeg', 'image/jpg') else 'image/png'
            )
            st.session_state.gen_last_image_type = mime
            if model not in VISION_MODELS:
                st.warning(f'⚠️ {model_display} 不確定支援圖片，圖片可能不會被傳入 AI。')

        for msg in st.session_state.gen_chat_history:
            content = msg['content']
            display_text = (
                next((c['text'] for c in content if isinstance(c, dict) and c.get('type') == 'text'), '（含圖片）')
                if isinstance(content, list) else content
            )
            with st.chat_message(msg['role']):
                st.markdown(display_text[:2000] + ('...' if len(display_text) > 2000 else ''))

        user_input = st.chat_input('描述你想要的關卡（例如：生成一個有水漥的困難關卡）...')
        if user_input:
            params = params_for_chat
            image_bytes = st.session_state.gen_last_image_bytes if uploaded else None
            _do_generate(user_input, params,
                         image_bytes=image_bytes,
                         image_type=st.session_state.gen_last_image_type,
                         model=model)
            st.rerun()

        st.divider()
        with st.expander('🔍 查看 AI System Prompt（完整）'):
            params = params_for_chat
            prompt_text = build_system_prompt(params)
            st.text_area('System Prompt', value=prompt_text, height=400,
                         disabled=True, label_visibility='collapsed')
            st.caption(f'共 {len(prompt_text)} 字元，包含 level_design_guide.md 全文 + 當前參數。')

    # ----------------------------------------------------------
    # Tab 2: JSON 編輯 + 預覽 & 遊玩
    # ----------------------------------------------------------
    with tab_edit:
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown('#### JSON 編輯')

            json_file = st.file_uploader(
                '📂 匯入 JSON 檔案',
                type=['json'],
                key='json_import',
                help='上傳任意關卡 JSON 檔案，載入後可直接在下方編輯',
            )
            if json_file:
                try:
                    imported = json.load(json_file)
                    _set_level(imported)
                    st.success(f'已匯入：{json_file.name}')
                    st.rerun()
                except Exception as e:
                    st.error(f'匯入失敗：{e}')

            # 用版本號當 key，確保 level 更新時 textarea 也刷新
            ver = st.session_state.gen_json_version
            current_json_str = (
                json.dumps(st.session_state.gen_level_json, indent=2, ensure_ascii=False)
                if st.session_state.gen_level_json else ''
            )
            edited = st.text_area(
                'Level JSON',
                value=current_json_str,
                height=480,
                key=f'gen_json_editor_{ver}',
                placeholder='{"rows": 10, "cols": 9, "max_steps": 30, "goals": {"Crt1": 20}, "board": null}',
            )

            btn_a, btn_b, btn_c = st.columns(3)
            with btn_a:
                if st.button('✅ 套用', use_container_width=True, type='primary'):
                    try:
                        parsed = json.loads(edited)
                        _set_level(parsed)
                        st.success('已套用')
                        st.rerun()
                    except json.JSONDecodeError as e:
                        st.error(f'JSON 格式錯誤：{e}')

            with btn_b:
                if st.session_state.gen_level_json:
                    lvl = st.session_state.gen_level_json
                    fname = lvl.get('name', 'level').replace(' ', '_') + '.json'
                    st.download_button(
                        '⬇️ 下載',
                        data=json.dumps(lvl, indent=2, ensure_ascii=False),
                        file_name=fname, mime='application/json',
                        use_container_width=True,
                    )

            with btn_c:
                if st.session_state.gen_level_json:
                    lvl = st.session_state.gen_level_json
                    save_name = lvl.get('name', 'new_level').replace(' ', '_')
                    if st.button('💾 存到 levels/', use_container_width=True):
                        try:
                            save_path = _ROOT / 'levels' / f'{save_name}.json'
                            with open(save_path, 'w', encoding='utf-8') as f:
                                json.dump(lvl, f, indent=2, ensure_ascii=False)
                            st.success(f'已儲存 levels/{save_name}.json')
                        except Exception as e:
                            st.error(f'儲存失敗：{e}')

        with col_right:
            st.markdown('#### 驗證 & 關卡資訊')

            if not st.session_state.gen_level_json:
                st.info('尚無關卡。請先在 Chat 生成，或從左側匯入 / 貼上 JSON 後點「套用」。')
            else:
                lvl = st.session_state.gen_level_json
                _render_validation(st.session_state.gen_validation)

                st.divider()
                info_cols = st.columns(4)
                with info_cols[0]:
                    st.metric('盤面', f"{lvl.get('rows')}×{lvl.get('cols')}")
                with info_cols[1]:
                    st.metric('最大步數', lvl.get('max_steps', '?'))
                with info_cols[2]:
                    st.metric('顏色數', lvl.get('num_colors', 4))
                with info_cols[3]:
                    st.metric('目標數', len(lvl.get('goals', {})))

                goals = lvl.get('goals', {})
                if goals:
                    st.markdown('**目標：** ' + '  '.join(f'`{k}` ×{v}' for k, v in goals.items()))

                if lvl.get('description'):
                    st.caption(lvl['description'])

        # 盤面區：全寬，分靜態預覽和互動遊玩
        if st.session_state.gen_level_json:
            st.divider()
            lvl = st.session_state.gen_level_json
            play_env = st.session_state.gen_play_env

            play_ctrl_cols = st.columns([1, 1, 6])
            with play_ctrl_cols[0]:
                if st.button('🎮 開始遊玩', use_container_width=True):
                    try:
                        st.session_state.gen_play_env = _load_env_from_dict(lvl)
                        st.session_state.gen_play_selected = None
                        st.session_state.gen_play_status = '遊戲開始！'
                        st.rerun()
                    except Exception as e:
                        st.error(f'載入遊戲失敗：{e}')
            with play_ctrl_cols[1]:
                if play_env is not None:
                    if st.button('🔄 重置', use_container_width=True):
                        try:
                            st.session_state.gen_play_env = _load_env_from_dict(lvl)
                            st.session_state.gen_play_selected = None
                            st.session_state.gen_play_status = '已重置'
                            st.rerun()
                        except Exception as e:
                            st.error(f'重置失敗：{e}')

            if play_env is None:
                # 靜態預覽
                try:
                    env = _load_env_from_dict(lvl)
                    html = render_board_preview_html(env)
                    st.components.v1.html(
                        f'<div style="overflow-x:auto;">{html}</div>',
                        height=env.board.rows * 58 + 30, scrolling=True,
                    )
                except Exception as e:
                    st.error(f'盤面預覽失敗：{e}')
            else:
                # 互動遊玩
                _render_play_ui(play_env)

    # ----------------------------------------------------------
    # Tab 3: Simulation Test
    # ----------------------------------------------------------
    with tab_sim:
        if not st.session_state.gen_level_json:
            st.info('請先生成或載入關卡再執行模擬測試。')
        else:
            lvl = st.session_state.gen_level_json
            default_steps = lvl.get('max_steps', 30)

            st.markdown(
                'BasicAgent 是**暴力搜索 Agent**：每步列舉所有合法動作，各做一次盤面深拷貝模擬，選最高分的動作。\n\n'
                '建議先跑 30 場快速確認，確定方向後再跑 100 場精確統計。'
            )

            sim_col1, sim_col2, sim_col3 = st.columns(3)
            with sim_col1:
                n_games = st.number_input('模擬場數', min_value=10, max_value=500, value=30, step=10)
            with sim_col2:
                elevated_mult = st.number_input(
                    'max_steps 倍率', min_value=1.0, max_value=10.0, value=3.0, step=0.5,
                    help='模擬時將 max_steps 放大，讓 AI 有機會完成（分析難度用）',
                )
            with sim_col3:
                st.metric('模擬步數上限', int(default_steps * elevated_mult))

            if st.button(f'🤖 跑 {n_games} 場模擬', use_container_width=True, type='primary'):
                progress_bar = st.progress(0, text='準備中...')
                status_text = st.empty()

                def on_progress(current, total):
                    progress_bar.progress(current / total, text=f'模擬中... {current}/{total}')
                    status_text.text(f'已完成 {current}/{total} 場')

                try:
                    results = run_simulation_batch(
                        level_dict=lvl, n_games=int(n_games),
                        steps_multiplier=float(elevated_mult),
                        max_workers=4, progress_callback=on_progress,
                    )
                    st.session_state.gen_sim_results = results
                    progress_bar.progress(1.0, text='完成！')
                    status_text.empty()
                    st.rerun()
                except Exception as e:
                    st.error(f'模擬失敗：{e}')

            results = st.session_state.gen_sim_results
            if results:
                st.divider()
                st.subheader('模擬結果')

                metric_cols = st.columns(4)
                with metric_cols[0]:
                    st.metric('勝率', f'{results.win_rate:.1%}',
                              delta=f'{results.wins}/{results.n_games} 場勝利')
                with metric_cols[1]:
                    st.metric('平均步數', f'{results.avg_steps:.1f}')
                with metric_cols[2]:
                    st.metric('最少步數', results.min_steps)
                with metric_cols[3]:
                    st.metric('最多步數', results.max_steps_seen)

                label = results.difficulty_label()
                if results.win_rate >= 0.8:
                    st.warning(f'📊 **{label}**')
                elif results.win_rate >= 0.25:
                    st.success(f'📊 **{label}**')
                else:
                    st.error(f'📊 **{label}**')

                if results.step_histogram:
                    st.markdown('**步數分布**')
                    st.bar_chart({
                        f'{k}-{k+4}步': v
                        for k, v in sorted(results.step_histogram.items())
                    })

                st.markdown('**調整建議**')
                if results.win_rate > 0.85:
                    st.markdown('- 關卡可能太簡單。考慮：減少 `max_steps`、增加障礙物數量或 HP、新增更難的目標。')
                elif results.win_rate < 0.1:
                    st.markdown('- 關卡可能太難。考慮：增加 `max_steps`、減少障礙物數量或 HP、降低目標數。')
                else:
                    st.markdown(
                        f'- 難度適中（AI 勝率 {results.win_rate:.0%}）。'
                        f'人類玩家通常比 BasicAgent 更強，實際難度對玩家可能更低。'
                    )


if __name__ == '__main__':
    main()
