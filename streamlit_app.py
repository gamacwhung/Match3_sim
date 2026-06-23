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

_ROOT = pathlib.Path(__file__).parent
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

# ── 後台設定：生成用模型（改這一行即可換模型）──────────────────────
# 攤位用 Flash 求速度；要更高品質改成 'gemini-2.5-pro' 或 'gemini-3.1-pro-preview'。
BOOTH_MODEL = 'gemini-3.5-flash'
# 顯示用的漂亮名稱（單一來源：改 BOOTH_MODEL，標題/頁尾/log 全部跟著變）
BOOTH_MODEL_LABEL = BOOTH_MODEL.replace('gemini-', 'Gemini ').replace('-', ' ').title()

# (按鈕文字, 選之前就顯示的白話說明, 實際送給 AI 的 prompt)
QUICK_PROMPTS = [
    ('🎆 超爽連鎖', '一次消掉超多、超有成就感',
     '做一個中間有一大片空地、障礙物集中在四周和底部的關卡，讓我容易累積很多道具、一次消掉超多東西，超有成就感。'),
    ('🧩 步步為營', '從小空間慢慢往外清、越玩越大',
     '做一個障礙物幾乎塞滿、只在中間留一小塊空間的關卡，讓我從那一小塊慢慢往外消、把可以玩的範圍越玩越大。'),
    ('🌧️ 障礙雨', '木桶一直從上面掉下來',
     '做一個木桶會一直從上面掉下來的關卡，讓我一邊消除、一邊把掉下來的木桶清掉。'),
    ('💎 異形盤面', '形狀特別、不是普通方形',
     '做一個形狀特別的關卡，不要普通方形，可以是十字、菱形或愛心之類的有趣形狀。'
     '形狀的每段筆畫至少 2~3 格寬，不要 1 格寬的細線（否則湊不出消除、變難又怪）。'),
]

# 攤位快速體驗版：所有生成都附上這個指示（白話，不含技術術語；技術規則寫在系統 prompt 的設計指南）。
BOOTH_LEVEL_HINT = (
    '\n\n（這是攤位快速體驗版：請設計小盤面、目標單純（1~2 種），'
    '難度要「中等、有一點挑戰」——不要太簡單到隨便點就過。'
    '步數要「抓緊、剛好夠用」：先估算最佳解所需步數，max_steps 大約只給最佳解的 1.2~1.4 倍，'
    '絕對不要給一大堆步數讓人亂點也能過。'
    '障礙物不要多到把盤面塞爆（要留得下操作空間），'
    '讓人 1~2 分鐘內玩完、需要稍微動點腦、過關有成就感的短關卡，重點是好玩、有挑戰但不卡死。）'
)

# 生成後的「微調」快捷鈕（難度 + 形狀，好懂優先）。點了 → 在原需求基礎上加這句、重生一次。
ADJUST_OPTIONS = [
    ('😌 簡單一點', '（請在原本基礎上把這關做得更簡單、步數更寬鬆，讓新手更容易過關。）'),
    ('🔥 難一點', '（請在原本基礎上把這關做得更有挑戰一點，但仍要保證能過關。）'),
    ('❤️ 愛心', '（請把「可遊玩盤面範圍」做成愛心形狀：用 void 把愛心以外挖空。'
               '⚠️ 形狀的每一段筆畫務必「至少 2~3 格寬」，絕對不要出現 1 格寬的細線（1 格寬玩家湊不出相鄰消除、變成又難又怪的死關）；'
               '盤面可放大到 9×9 來容納夠粗的筆畫。內部正常放元素、只放少量障礙物，務必留足夠空地能消除。）'),
    ('🔵 Google G', '（請把「可遊玩盤面範圍」做成大寫「G」形狀：用 void 把 G 以外挖空。'
                   '⚠️ G 的每一段筆畫（含下方開口那段）務必「至少 2~3 格寬」，絕對不要 1 格寬的細線；'
                   '盤面可放大到 9×9 來容納夠粗的筆畫。筆畫內部正常放元素、只放少量障礙物，務必留足夠空地能消除。）'),
    ('🐴 Gamania g', '（請把「可遊玩盤面範圍」做成小寫「g」形狀：用 void 把 g 以外挖空。'
                    '⚠️ g 的每一段筆畫（含下方的圈與尾）務必「至少 2~3 格寬」，絕對不要 1 格寬的細線；'
                    '盤面可放大到 9×9 來容納夠粗的筆畫。筆畫內部正常放元素、只放少量障礙物，務必留足夠空地能消除。）'),
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
        'booth_ai_mode': False,     # AI 即時模式啟動旗標
        'booth_last_prompt': '',    # 上一次送出的需求(生成後仍顯示,不消失)
        'booth_input': '',          # 輸入框內容(範本會填進這裡)
        'booth_sim_pending': False, # AI 難度測試待背景執行(讓玩家先玩)
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


def _do_generate(user_msg: str, live: bool = False, status=None):
    """生成關卡 + 驗證 + 難度預估（Agent Pipeline 流程）。
    live=True 時，每一步都即時顯示在畫面上（照真實時間出現，不是最後一次跳出）。
    status：傳入 st.status 容器時，會即時更新最上方的階段標籤。"""
    def _phase(label: str):
        if status is not None:
            status.update(label=label)
    st.session_state.booth_agent_log = []
    st.session_state.booth_sim_results = None
    st.session_state.booth_env = None

    log = st.session_state.booth_agent_log

    def emit(t: str, m: str):
        log.append((t, m))
        if live:
            _render_log_line(t, m)

    # 攤位短關卡：小盤面 + easy，搭配 BOOTH_LEVEL_HINT 讓關卡短、單純、不拖
    params = {
        'rows': 8, 'cols': 8,
        'difficulty': 'medium',
        'num_colors': 4,
        'obstacle_types': [],
        'goal_types': [],
    }

    # Step 1+2: 生成 → 驗證；失敗就「帶著錯誤訊息」自動重新生成（最多 MAX_ATTEMPTS 次）
    model = BOOTH_MODEL
    MAX_ATTEMPTS = 2

    # 逐字串流：放進「固定高度可捲動容器」，思考再長也不會把下面內容往下擠
    thought_box = None
    stream_box = None
    if live:
        try:
            _zone = st.container(height=240)
        except TypeError:
            _zone = st.container()  # 舊版 Streamlit 不支援 height → 退回一般容器
        with _zone:
            thought_box = st.empty()   # 🤔 思考過程（在上）
            stream_box = st.empty()     # 📝 JSON 答案（在下）
    _thought_acc = []
    _stream_acc = []

    def _on_chunk(piece: str, is_thought: bool = False):
        if is_thought:
            # 思考過程：即時顯示「它在想什麼」，不再是空白長停頓
            _thought_acc.append(piece)
            if thought_box is not None:
                thought_box.markdown('🤔 **AI 思考中…**\n\n' + ''.join(_thought_acc)[-600:])
        else:
            # 答案（JSON）：打字機往下捲
            _stream_acc.append(piece)
            if stream_box is not None:
                stream_box.code(''.join(_stream_acc)[-350:], language='json')

    level_dict = None
    validation = None
    feedback = ''  # 重試時把上一次的錯誤回饋給模型，讓它「看著錯誤」修正
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _thought_acc.clear()
        _stream_acc.clear()
        if attempt == 1:
            _phase('🔧 生成關卡中…')
            emit('thinking', '🤔 正在理解你的需求...')
            emit('tool', '🔧 呼叫 AI 生成關卡...')
        else:
            _phase(f'🔁 自動修正重生（第 {attempt} 次）…')
            emit('tool', f'🔁 上次有問題，帶著錯誤重新生成（第 {attempt} 次）...')

        try:
            # 每次生成用「獨立的空歷史」：攤位是單次生成，不該累積對話。
            assistant_text, level_dict = generate_level(
                user_message=user_msg + BOOTH_LEVEL_HINT + feedback,
                chat_history=[],
                params=params,
                model=model,
                stream_callback=_on_chunk if live else None,
            )
        except Exception as e:
            emit('error', f'❌ 生成失敗：{e}')
            return False

        # (A) 解析失敗（沒有有效 JSON）→ 回饋並重試
        if not level_dict:
            emit('warning', f'⚠️ 第 {attempt} 次沒解析出有效 JSON。')
            if attempt < MAX_ATTEMPTS:
                feedback = ('\n\n【系統提醒】你上一次沒有輸出可解析的 JSON。請「只」輸出一個完整的 '
                            '```json ... ``` 區塊；JSON 後面不要再加任何說明或文字。')
                continue
            emit('error', '❌ 連續沒吐有效 JSON — 請再按一次「生成」或換句話描述')
            return False

        # (B) 驗證格式，把「哪裡不對」逐條印出來
        _phase('🔍 驗證格式中…')
        emit('tool', '🔍 呼叫驗證工具檢查格式...')
        validation = validate_level(level_dict)
        st.session_state.booth_validation = validation

        if validation.valid:
            emit('success', f'✅ 關卡已生成並通過驗證：{level_dict.get("rows", "?")}×{level_dict.get("cols", "?")} 盤面')
            break

        # 驗證失敗 → 印出每一條問題，並把它回饋給模型自動重生
        for err in validation.errors[:6]:
            emit('warning', f'　• {err}')
        if len(validation.errors) > 6:
            emit('warning', f'　…等共 {len(validation.errors)} 個問題')
        if attempt < MAX_ATTEMPTS:
            feedback = ('\n\n【系統提醒】你上一次產生的關卡有以下格式問題，請務必修正後重新輸出完整 JSON：\n- '
                        + '\n- '.join(validation.errors[:8]))
            continue
        # 次數用完仍有警告 → 仍讓玩家玩，只是提示可能略有瑕疵
        emit('warning', '⚠️ 自動修正後仍有格式警告，先讓你玩玩看（可能略有瑕疵）')

    st.session_state.booth_level = level_dict

    # 關卡就緒 → 先讓玩家玩；AI 難度測試移到背景（main() 結尾才跑，不擋遊玩）
    if validation.valid:
        st.session_state.booth_sim_results = None
        st.session_state.booth_sim_pending = True
        emit('success', '🎮 關卡就緒，可以開始玩了！')
        emit('tool', '🤖 AI 難度測試將在背景進行（玩你的，測它的）…')
    return True  # 有成功生成關卡（即使驗證有警告也算，關卡仍可玩）


_LOG_COLORS = {
    'thinking': ('#666', '400'),
    'tool': ('#1a73e8', '400'),
    'success': ('#0d904f', '500'),
    'warning': ('#e37400', '400'),
    'error': ('#d93025', '500'),
}


def _render_log_line(step_type: str, msg: str):
    """渲染單一行 Agent 紀錄（即時串流與事後渲染共用）"""
    color, weight = _LOG_COLORS.get(step_type, ('#333', '400'))
    st.markdown(
        f'<div style="color:{color}; padding:2px 0; font-weight:{weight};">{msg}</div>',
        unsafe_allow_html=True,
    )


def _render_agent_log():
    """渲染 Agent 思考過程（事後從 session_state 重畫）"""
    log = st.session_state.booth_agent_log
    if not log:
        return

    st.markdown('#### Agent Pipeline 執行紀錄')
    for step_type, msg in log:
        _render_log_line(step_type, msg)


def main():
    _init_state()

    # 縮小 Streamlit 預設留白 → 攤位一螢幕(16:9)塞得下、不用捲動
    st.markdown(
        '''<style>
        .block-container { padding-top: 1.2rem !important; padding-bottom: 0.8rem !important;
                           max-width: 100% !important; }
        h1 { margin-bottom: 0 !important; }
        div[data-testid="stVerticalBlock"] { gap: 0.5rem; }
        </style>''',
        unsafe_allow_html=True,
    )

    # 頂部標題
    st.markdown(
        f'''
        <div style="text-align:center; padding: 16px 0 8px 0;">
          <h1 style="margin:0; font-size: 2.2em;">
            🎮 Match3 AI Level Designer
          </h1>
          <p style="color:#666; margin: 4px 0 0 0; font-size: 1.05em;">
            用一句話設計你的遊戲關卡
          </p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # 檢查 API key / GCP credentials
    provider = get_model_provider(BOOTH_MODEL)
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
        # 清除鍵按下後 → 下一輪、在 text_area 建立「之前」把輸入框清空
        if st.session_state.pop('_booth_clear_input', False):
            st.session_state['booth_input'] = ''

        st.markdown('#### 💬 描述你想要的關卡')
        st.caption('點範本填進下面的框 → 可直接改 → 按生成')

        # 範本：2 欄排列（省高度）。點了把實際 prompt 填進輸入框，看清楚再生成
        _qp_cols = st.columns(2)
        for i, (label, _desc, prompt_text) in enumerate(QUICK_PROMPTS):
            with _qp_cols[i % 2]:
                if st.button(label, key=f'qp_{i}', use_container_width=True):
                    st.session_state['booth_input'] = prompt_text

        # 上次送出的需求 — 用小字（省高度）
        if st.session_state.get('booth_last_prompt'):
            st.caption(f'📝 上次送出：{st.session_state.booth_last_prompt}')

        # 輸入框（範本會填進這裡，可直接編輯）
        user_input = st.text_area(
            '描述（可直接編輯）',
            key='booth_input',
            placeholder='例：做一個消除起來很爽的關卡 / 給我一個愛心形狀的盤面...',
            height=80,
            label_visibility='collapsed',
        )

        # 展開看「實際送給 AI 的完整 prompt」
        with st.expander('🔍 查看實際送給 AI 的完整 prompt'):
            _params_preview = {'rows': 8, 'cols': 8, 'difficulty': 'medium',
                               'num_colors': 4, 'obstacle_types': [], 'goal_types': []}
            st.caption('① 系統提示（含完整設計規範）')
            st.code(build_system_prompt(_params_preview), language='text')
            st.caption('② 你的需求 ＋ 攤位短關卡指示')
            st.code((user_input or '（尚未輸入）') + BOOTH_LEVEL_HINT, language='text')

        # 生成 / 清除
        gen_cols = st.columns([3, 1])
        with gen_cols[0]:
            generate_clicked = st.button('✨ 用 AI 生成', use_container_width=True, type='primary')
        with gen_cols[1]:
            if st.button('🗑️', use_container_width=True, help='清除'):
                st.session_state.booth_chat_history = []
                st.session_state.booth_level = None
                st.session_state.booth_agent_log = []
                st.session_state.booth_sim_results = None
                st.session_state.booth_env = None
                st.session_state.booth_last_prompt = ''
                st.session_state['_booth_clear_input'] = True  # 下一輪清空輸入框
                st.rerun()

        # 🔧 微調這一關（生成後才出現）。放在「觸發」之前、且**不**額外 st.rerun()：
        # 點按鈕本身就會 rerun 一次，這一輪下面的觸發就會處理 → 全程只有一次 rerun，
        # Godot iframe 不會被重載而掉回預設關選單（之前兩次 rerun 才會壞）。
        if st.session_state.get('booth_level') is not None:
            st.caption('🔧 想再調整？點一下重生（會在這一關基礎上改）')
            _adj_cols = st.columns(len(ADJUST_OPTIONS))
            for _i, (_alabel, _adir) in enumerate(ADJUST_OPTIONS):
                with _adj_cols[_i]:
                    if st.button(_alabel, key=f'adj_{_i}', use_container_width=True):
                        st.session_state['_booth_regen_directive'] = _adir

        # 觸發生成 — 手動按生成，或微調按鈕觸發的重生（同一輪處理，不額外 rerun）
        _auto_directive = st.session_state.pop('_booth_regen_directive', None)
        just_generated = False
        if (generate_clicked and (user_input or '').strip()) or _auto_directive is not None:
            if _auto_directive is not None:
                # 微調：用「上一次的需求(base)」+ 微調指示；base 保持乾淨、不累積指示
                _base = (st.session_state.get('booth_last_prompt') or (user_input or '')).strip()
                _prompt = _base + _auto_directive
                st.session_state.booth_last_prompt = _base
            else:
                _prompt = user_input.strip()
                st.session_state.booth_last_prompt = _prompt
            # 用「一直可見的區塊」而非 st.status，直接攤在外面、跑完留著。
            st.markdown('##### 🤖 AI 正在即時創作這一關…')
            _ok = _do_generate(_prompt, live=True)
            if _ok:
                st.success('✅ 關卡完成，可以開始玩了！')
            else:
                st.error('❌ 這次沒生成成功（模型沒吐有效 JSON）— 再按一次「生成」試試')
            just_generated = True

        # Agent 執行紀錄（剛生成的已即時顯示過 → 避免重複；其餘靜態重畫）
        st.markdown('---')
        if not just_generated:
            _render_agent_log()

    with col_right:
        # Godot iframe — 一進頁面就載入（不用等關卡）
        st.markdown('##### 🎮 遊戲區')
        GODOT_IFRAME_KEY = 'godot_game_iframe'
        godot_url = f'{GODOT_DEMO_URL}'
        st.components.v1.iframe(godot_url, height=650, scrolling=False)

        level = st.session_state.booth_level

        # 關卡已載入時：用 postMessage 傳送到 Godot（不重新載入 iframe）
        if level and st.session_state.get('_booth_level_pushed') != id(level):
            st.session_state['_booth_level_pushed'] = id(level)
            level_json_str = json.dumps(level, ensure_ascii=False)
            # 注入 JS 發送 postMessage 給 iframe
            st.components.v1.html(
                f'''<script>
                (function() {{
                    var frames = window.parent.document.querySelectorAll('iframe');
                    for (var i = 0; i < frames.length; i++) {{
                        if (frames[i].src && frames[i].src.indexOf('gamacwhung.github.io') !== -1) {{
                            frames[i].contentWindow.postMessage({{
                                type: 'load_level',
                                level_json: JSON.stringify({json.dumps(level, ensure_ascii=False)})
                            }}, '*');
                            break;
                        }}
                    }}
                }})();
                </script>''',
                height=0,
            )

        if level is None:
            # 預設關卡（免 token）— 與左側範本同名同序，方便對照「這個範本會產出什麼」
            st.caption('載入範例關卡（不花 token，對應左邊的範本）')
            _PRESETS = {
                '🎆 超爽連鎖': 'chain_fun.json',
                '🧩 步步為營': 'rope_strategy.json',
                '🌧️ 障礙雨': 'barrel_rain.json',
                '💎 異形盤面': 'diamond_board.json',
            }
            preset_cols = st.columns(3)
            for i, (plabel, pfile) in enumerate(_PRESETS.items()):
                with preset_cols[i % 3]:
                    if st.button(plabel, key=f'preset_{i}', use_container_width=True):
                        import pathlib
                        ppath = pathlib.Path('generated_levels') / pfile
                        if ppath.exists():
                            with open(ppath, encoding='utf-8') as f:
                                st.session_state.booth_level = json.load(f)
                            st.session_state.booth_agent_log = [
                                ('success', f'✅ 已載入預設關卡：{pfile}')
                            ]
                            st.rerun()

            # 📂 載入已存範例（測試用）：列出 generated_levels/ 裡所有檔，含你存的測試關
            import pathlib as _pl
            _saved = sorted(p.name for p in _pl.Path('generated_levels').glob('*.json')) \
                if _pl.Path('generated_levels').exists() else []
            if _saved:
                with st.expander('📂 載入已存範例（測試用）'):
                    _pick = st.selectbox('選一個已存的關卡', _saved, key='load_saved_pick')
                    if st.button('載入', key='load_saved_btn'):
                        with open(_pl.Path('generated_levels') / _pick, encoding='utf-8') as f:
                            st.session_state.booth_level = json.load(f)
                        st.session_state.booth_agent_log = [('success', f'✅ 已載入：{_pick}')]
                        st.rerun()
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
                    # 顯示實際建議內容（不是只給數量）
                    st.warning(f'⚠️ 通過，可以玩，但有 {len(v.warnings)} 個建議：')
                    for w in v.warnings[:4]:
                        st.caption(f'　· {w}')
                else:
                    st.error(f'❌ {len(v.errors)} 個格式錯誤')
                    for err in v.errors[:3]:
                        st.caption(f'  · {err}')

            # 難度標籤
            sim = st.session_state.booth_sim_results
            if sim is None and st.session_state.get('booth_sim_pending'):
                st.caption('🤖 AI 正在背景測試這關的難度…（不影響你先玩）')
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

                # 📋 AI 測試報表 — 好懂的數字（平均步數、步數寬裕度、卡關點）
                with st.expander(f'📋 AI 測試報表（AI 跑了 {sim.n_games} 場）', expanded=True):
                    _ms = level.get('max_steps', None)
                    rc1, rc2, rc3 = st.columns(3)
                    rc1.metric('AI 勝率', f'{wr:.0%}')
                    rc2.metric('AI 平均步數', f'{sim.avg_steps_won:.0f}' if sim.avg_steps_won else '—',
                               help=f'只算贏的場；這關給 {_ms} 步' if _ms else '只算贏的場')
                    if sim.avg_steps_won and isinstance(_ms, int):
                        slack = _ms - sim.avg_steps_won
                        rc3.metric('步數寬裕', f'+{slack:.0f}',
                                   help='給的步數 − AI 平均用的步數；太大代表步數給太多、關卡偏鬆')
                    # 卡關點：最難達成的目標（只有 1 個目標時不顯示，沒有比較意義）
                    hg = sim.hardest_goal()
                    if hg and len(sim.goal_stats) > 1:
                        tid, sgs = hg
                        if sgs['met_rate'] >= 0.95:
                            st.success(f'🎯 最難目標：**{tid}**（需 {sgs["required"]}）'
                                       f'— 達成率 {sgs["met_rate"]:.0%}，不算卡關')
                        else:
                            st.warning(f'🎯 卡關點：**{tid}**（需 {sgs["required"]}）'
                                       f'— 只有 {sgs["met_rate"]:.0%} 場達成、平均做到 {sgs["avg_progress"]:.0%}')
                    # 各目標達成率（多目標時）
                    if len(sim.goal_stats) > 1:
                        st.caption('各目標達成率：' + '　'.join(
                            f'{t} {s["met_rate"]:.0%}' for t, s in sim.goal_stats.items()))

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
                    # 用 postMessage 通知 iframe 中的 Godot 啟動 AI（不重新載入）
                    st.components.v1.html(
                        '''<script>
                        (function() {
                            var frames = window.parent.document.querySelectorAll('iframe');
                            for (var i = 0; i < frames.length; i++) {
                                if (frames[i].src && frames[i].src.indexOf('gamacwhung.github.io') !== -1) {
                                    frames[i].contentWindow.postMessage({type: 'ai_mode_start'}, '*');
                                    break;
                                }
                            }
                        })();
                        </script>''',
                        height=0,
                    )
                    st.success('🧠 AI 已啟動！正在即時計算並操作...')
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

            # 💾 存成範例（測試用）：存到 generated_levels/，下次免 token 直接從右側清單載入
            with st.expander('💾 存成範例（測試用）'):
                import pathlib as _pl
                _name = st.text_input('檔名（不用加 .json）', value='my_test', key='save_example_name')
                if st.button('存到 generated_levels/', key='save_example_btn', use_container_width=True):
                    nm = (_name or '').strip()
                    if nm:
                        _gdir = _pl.Path('generated_levels')
                        _gdir.mkdir(exist_ok=True)
                        if not nm.endswith('.json'):
                            nm += '.json'
                        with open(_gdir / nm, 'w', encoding='utf-8') as _f:
                            json.dump(level, _f, ensure_ascii=False, indent=2)
                        st.success(f'已存：generated_levels/{nm}（右側「載入已存」可直接讀）')
                    else:
                        st.warning('請輸入檔名')

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

    # 背景 AI 難度測試 — 在兩欄都畫完(關卡已 postMessage 給 Godot、玩家可開始玩)之後才跑。
    # Streamlit 是同步的，這幾秒 Python 會 blocking，但 Godot iframe 是 client-side、照常可玩。
    if (st.session_state.get('booth_sim_pending')
            and st.session_state.get('booth_level')
            and st.session_state.get('booth_validation')
            and st.session_state.booth_validation.valid):
        st.session_state.booth_sim_pending = False
        try:
            results = run_simulation_batch(
                level_dict=st.session_state.booth_level, n_games=15,
                steps_multiplier=1.0, max_workers=4,
            )
            st.session_state.booth_sim_results = results
        except Exception:
            pass
        st.rerun()

    # 底部 footer
    st.markdown('---')
    st.markdown(
        f'<div style="text-align:center; color:#999; font-size:0.85em;">'
        f'Godot 4 Engine · Python Match3 Simulator'
        f'</div>',
        unsafe_allow_html=True,
    )


if __name__ == '__main__':
    main()
