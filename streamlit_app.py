"""
攤位模式 — Google Cloud Day 展示專用

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
    page_icon='',
    initial_sidebar_state='collapsed',
)

# 遊戲 iframe 來源：
#   預設 = GitHub Pages(公開站，同事 main 版)。
#   本機測試「整個網站 pipeline + 自己分支的 Godot」時，設環境變數 BOOTH_GODOT_LOCAL=1
#   並另開 `python serve_godot_local.py`(localhost:8765 服務本機 godot_demo/web/)。
GODOT_PAGES_URL = 'https://gamacwhung.github.io/Match3_sim/'
# 遊戲伺服器位址：別台(攤位筆電)要連得到「這台」，就把 BOOTH_GODOT_HOST 設成這台的
# 區網 IP:8765（例：172.23.19.106:8765）；自己這台玩就用預設 localhost:8765。
_GODOT_HOST = os.environ.get('BOOTH_GODOT_HOST', 'localhost:8765')
GODOT_LOCAL_URL = f'http://{_GODOT_HOST}/'
_USE_LOCAL_GODOT = os.environ.get('BOOTH_GODOT_LOCAL', '0') == '1'
GODOT_DEMO_URL = GODOT_LOCAL_URL if _USE_LOCAL_GODOT else GODOT_PAGES_URL
# 找 Godot iframe 用的 host 標記（本機/Pages 都通）：localhost:8765 或 gamacwhung.github.io
GODOT_HOST_MARKER = GODOT_DEMO_URL.split('//')[-1].split('/')[0]

# ── 後台設定：生成用模型（改這一行即可換模型）──────────────────────
# 攤位用 Flash 求速度；要更高品質改成 'gemini-2.5-pro' 或 'gemini-3.1-pro-preview'。
BOOTH_MODEL = 'gemini-3.5-flash'
# 顯示用的漂亮名稱（單一來源：改 BOOTH_MODEL，標題/頁尾/log 全部跟著變）
BOOTH_MODEL_LABEL = BOOTH_MODEL.replace('gemini-', 'Gemini ').replace('-', ' ').title()

# Demo 安全模式：只生「不會卡死」的簡單關（無木桶雨、無異形 void）。
# 木桶/異形那條路目前會觸發遊戲端死鎖，修好後把這個改 False 即可恢復全功能。
SAFE_MODE = True

# (按鈕文字, 選之前就顯示的白話說明, 實際送給 AI 的 prompt)
QUICK_PROMPTS = [
    ('💥 超爽連鎖', '一次消掉超多、超有成就感',
     '做一個中間有一大片空地、障礙物集中在四周和底部的關卡，讓我容易累積很多道具、一次消掉超多東西，超有成就感。'),
    ('🧩 步步為營', '從小空間慢慢往外清、越玩越大',
     '做一個障礙物幾乎塞滿、只在中間留一小塊空間的關卡，讓我從那一小塊慢慢往外消、把可以玩的範圍越玩越大。'),
]
if not SAFE_MODE:
    QUICK_PROMPTS.append(
        ('🛢️ 障礙雨', '木桶一直從上面掉下來',
         '做一個木桶會一直從上面掉下來的關卡，讓我一邊消除、一邊把掉下來的木桶清掉。'))

# 攤位快速體驗版：所有生成都附上這個指示（白話，不含技術術語；技術規則寫在系統 prompt 的設計指南）。
BOOTH_LEVEL_HINT = (
    '\n\n（這是攤位快速體驗版：請設計小盤面、目標單純（1~2 種），'
    '難度要「中等、有一點挑戰」——不要太簡單到隨便點就過。'
    '步數要「抓緊、剛好夠用」：先估算最佳解所需步數，max_steps 大約只給最佳解的 1.2~1.4 倍，'
    '絕對不要給一大堆步數讓人亂點也能過。'
    '障礙物不要多到把盤面塞爆（要留得下操作空間），'
    '讓人 1~2 分鐘內玩完、需要稍微動點腦、過關有成就感的短關卡，重點是好玩、有挑戰但不卡死。）'
)
if SAFE_MODE:
    # 安全模式：明確禁止會觸發遊戲端死鎖的設計（木桶/連續掉落 + 異形 void）
    BOOTH_LEVEL_HINT += (
        '\n\n（重要安全限制：請用「普通方形盤面」，'
        '絕對不要使用 void、不要做特殊形狀（不要愛心/G/十字/菱形等）；'
        '絕對不要放木桶(Barrel)、也不要任何會從上方持續掉落或不斷生成的障礙（不要 spawner/障礙雨）；'
        '障礙物只用少量「固定箱子 Crt」，其餘留空地給元素，確保盤面好操作、不會卡死。）'
    )

# 形狀關專用指示：盤面要大才畫得出形狀，所以不講「小盤面」，其餘要求一樣（單純、不卡死）。
BOOTH_LEVEL_HINT_SHAPE = (
    '\n\n（這是攤位快速體驗版的「形狀關」：盤面可以大一點（把指定形狀做粗、做明顯），'
    '但目標仍要單純（1~2 種）、難度中等有點挑戰、步數抓緊（max_steps 約最佳解的 1.2~1.4 倍），'
    '形狀筆畫至少 2~3 格寬、每個障礙物旁邊都要有空地能湊出三消，務必留足夠操作空間、不要卡死。）'
)

# 通用「形狀」指示：把可遊玩範圍挖成某形狀（筆畫要夠粗，否則湊不出消除）。
def _shape_directive(name: str) -> str:
    return (f'（請把「可遊玩盤面範圍」做成「{name}」形狀：用 void 把該形狀以外挖空。'
            '形狀的每一段筆畫務必「至少 2~3 格寬」，絕對不要出現 1 格寬的細線'
            '（1 格寬玩家湊不出相鄰消除、變成又難又怪的死關）；'
            '盤面放大到約 12×12（最大就是 12×12）來容納夠粗的筆畫，形狀做大一點比較好認。'
            '內部正常放元素、只放少量障礙物，務必留足夠空地能消除。）')


# 生成後的「微調 — 形狀」快捷鈕。點了在原需求基礎上加這句、重生一次。
SHAPE_OPTIONS = [
    ('矩形', '（請把盤面做成普通矩形，不要挖 void、不要做特殊形狀，正常放元素與少量障礙物即可。）'),
    ('十字', _shape_directive('十字')),
    ('菱形', _shape_directive('菱形')),
    ('愛心', _shape_directive('愛心')),
    ('Google G', '（請把「可遊玩盤面範圍」做成大寫「G」形狀：用 void 把 G 以外挖空。'
                   'G 的長相＝像一個「C」（上、左、下三邊各一條粗邊框，整體右邊是開口）'
                   '＋右下角有一條往內、往上的短橫筆（G 的小尾巴/橫槓）。'
                   '所以「右上角必須是缺口（開口）」、右下角才有那段短橫筆，千萬不要把右邊整條封起來變成「O/方框」。'
                   'G 的每一段筆畫務必「至少 2~3 格寬」，絕對不要 1 格寬的細線；'
                   '盤面放大到約 12×12（最大 12×12）來容納夠粗的筆畫、G 做大一點比較好認。'
                   '筆畫內部正常放元素、只放少量障礙物，務必留足夠空地能消除。）'),
]

# 生成後的「微調 — 難度」快捷鈕（絕對難度；點了在原需求基礎上加這句、重生一次）。
DIFFICULTY_OPTIONS = [
    ('簡單', '（請把這關做成「簡單」難度：步數寬鬆、障礙少、目標單純，新手也能輕鬆過關。）'),
    ('普通', '（請把這關做成「普通」難度：需要稍微動點腦、有一點挑戰，但不會卡死。）'),
    ('困難', '（請把這關做成「困難」難度：步數抓緊、需要規劃，但仍保證有解、一定過得了。）'),
]


# AI 勝率 → (難度文字, 主色, emoji, 一句白話)。報表用，顏色配 Google 四色。
def _difficulty_badge(win_rate: float):
    if win_rate >= 0.8:
        return ('輕鬆', '#34A853', '😄', '大多數人可輕鬆過關')
    if win_rate >= 0.5:
        return ('適中', '#4285F4', '🙂', '需要一些策略')
    if win_rate >= 0.25:
        return ('有挑戰', '#F9AB00', '😤', '可能要試幾次')
    return ('極難', '#EA4335', '🔥', '需要運氣＋策略')


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
        'booth_last_full_prompt': '',  # 這一輪實際送出的完整需求(查看用)
        'booth_theme': '',          # 目前美術風格(''=預設 candy；其餘=themes/<name>)
        'booth_godot_buster': 0,    # 遞增 → iframe URL 改變 → Godot 乾淨重載(換風格/換下一位共用)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


@st.cache_data
def _load_theme_index():
    """讀 live_sprites/themes.json（換風格下拉選單用）。沒有就只給預設 candy。"""
    import pathlib
    p = pathlib.Path('godot_demo/web/live_sprites/themes.json')
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, list) and data:
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return [{'name': '', 'label': '糖果 Candy', 'default': True}]


def _reset_for_next_visitor():
    """攤位『換下一位訪客』：清掉上一位的所有資訊，並讓 Godot 回待機畫面。"""
    st.session_state.booth_level = None
    st.session_state.booth_validation = None
    st.session_state.booth_sim_results = None
    st.session_state.booth_env = None
    st.session_state.booth_selected = None
    st.session_state.booth_agent_log = []
    st.session_state.booth_chat_history = []
    st.session_state.booth_replay = None
    st.session_state.booth_replay_step = 0
    st.session_state.booth_ai_mode = False
    st.session_state.booth_sim_pending = False
    st.session_state.booth_last_prompt = ''
    st.session_state.booth_last_full_prompt = ''
    st.session_state['_booth_level_pushed'] = None
    # 進階選項 / 輸入框等 widget 狀態
    st.session_state['booth_shape_pill'] = None
    st.session_state['booth_diff_pill'] = None
    st.session_state['booth_custom_shape'] = ''
    st.session_state['booth_custom_diff'] = ''
    st.session_state['booth_adv_open'] = False       # 進階選項收合
    st.session_state['_booth_clear_input'] = True   # 下一輪在 text_area 建立前清空
    # 遞增 buster → 改變 iframe URL → Godot 乾淨重載回待機（保留目前風格）
    st.session_state['booth_godot_buster'] = st.session_state.get('booth_godot_buster', 0) + 1


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
        'action_desc': '初始盤面',
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
            desc = f'交換 ({r1},{c1}) ({r2},{c2})'
        else:
            r, c = action['pos']
            desc = f'啟動道具 ({r},{c})'

        obs, reward, done, info = env.step(action)
        step += 1
        eliminated = info.get('eliminated', {})
        elim_str = ', '.join(f'{k}×{v}' for k, v in eliminated.items()) if eliminated else '—'

        replay.append({
            'step': step,
            'action': action,
            'action_desc': f'{desc}　　消除: {elim_str}',
            'goals_current': dict(env.goals_current),
            'goals_required': dict(env.goals_required),
            'steps_left': env.max_steps - env.steps_taken,
            'won': env.win,
        })

    return replay


def _do_generate(user_msg: str, live: bool = False, status=None, big_board: bool = False):
    """生成關卡 + 驗證 + 難度預估（Agent Pipeline 流程）。
    live=True 時，每一步都即時顯示在畫面上（照真實時間出現，不是最後一次跳出）。
    status：傳入 st.status 容器時，會即時更新最上方的階段標籤。
    big_board=True（選了特殊形狀時）：給較大盤面（形狀筆畫才畫得粗、好認）。"""
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

    # 攤位短關卡：小盤面 + easy；選了特殊形狀則放大到 12×12（筆畫才畫得粗、形狀好認）。
    _rc = 12 if big_board else 8
    params = {
        'rows': _rc, 'cols': _rc,
        'difficulty': 'medium',
        'num_colors': 4,
        'obstacle_types': [],
        'goal_types': [],
    }
    # 大盤面(形狀關)用不含「小盤面」的指示，避免和形狀放大需求打架
    _hint = BOOTH_LEVEL_HINT_SHAPE if big_board else BOOTH_LEVEL_HINT

    # Step 1+2: 生成 驗證；失敗就「帶著錯誤訊息」自動重新生成（最多 MAX_ATTEMPTS 次）
    model = BOOTH_MODEL
    MAX_ATTEMPTS = 2

    # 逐字串流：放進「固定高度可捲動容器」，思考再長也不會把下面內容往下擠
    thought_box = None
    stream_box = None
    if live:
        try:
            _zone = st.container(height=240)
        except TypeError:
            _zone = st.container()  # 舊版 Streamlit 不支援 height 退回一般容器
        with _zone:
            thought_box = st.empty()   # 思考過程（在上）
            stream_box = st.empty()     # JSON 答案（在下）
    _thought_acc = []
    _stream_acc = []

    # 串流節流：用「時間」節流（最多每 0.1 秒刷一次），保留即時打字的酷炫感，
    # 又不會逐 token 狂刷 WebSocket 把同頁的 Godot WASM 一起拖垮 / 灌爆瀏覽器。
    _last_flush = [0.0]

    def _flush_stream():
        if thought_box is not None and _thought_acc:
            thought_box.markdown('**AI 思考中…**\n\n' + ''.join(_thought_acc)[-600:])
        if stream_box is not None and _stream_acc:
            stream_box.code(''.join(_stream_acc)[-350:], language='json')

    def _on_chunk(piece: str, is_thought: bool = False):
        if is_thought:
            _thought_acc.append(piece)
        else:
            _stream_acc.append(piece)
        now = time.time()
        if now - _last_flush[0] >= 0.1:   # ~10 fps：看起來即時，但有上限
            _last_flush[0] = now
            _flush_stream()

    level_dict = None
    validation = None
    feedback = ''  # 重試時把上一次的錯誤回饋給模型，讓它「看著錯誤」修正
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _thought_acc.clear()
        _stream_acc.clear()
        if attempt == 1:
            _phase('生成關卡中…')
            emit('thinking', '正在理解你的需求...')
            emit('tool', '呼叫 AI 生成關卡...')
        else:
            _phase(f'自動修正重生（第 {attempt} 次）…')
            emit('tool', f'上次有問題，帶著錯誤重新生成（第 {attempt} 次）...')

        try:
            # 每次生成用「獨立的空歷史」：攤位是單次生成，不該累積對話。
            assistant_text, level_dict = generate_level(
                user_message=user_msg + _hint + feedback,
                chat_history=[],
                params=params,
                model=model,
                stream_callback=_on_chunk if live else None,
            )
            _flush_stream()  # 串流結束補刷一次，確保最後內容完整顯示
        except Exception as e:
            emit('error', f'生成失敗：{e}')
            return False

        # (A) 解析失敗（沒有有效 JSON）回饋並重試
        if not level_dict:
            emit('warning', f'第 {attempt} 次沒解析出有效 JSON。')
            if attempt < MAX_ATTEMPTS:
                feedback = ('\n\n【系統提醒】你上一次沒有輸出可解析的 JSON。請「只」輸出一個完整的 '
                            '```json ... ``` 區塊；JSON 後面不要再加任何說明或文字。')
                continue
            emit('error', '連續沒吐有效 JSON — 請再按一次「生成」或換句話描述')
            return False

        # (B) 驗證格式，把「哪裡不對」逐條印出來
        _phase('驗證格式中…')
        emit('tool', '呼叫驗證工具檢查格式...')
        validation = validate_level(level_dict)
        st.session_state.booth_validation = validation

        if validation.valid:
            emit('success', f'關卡已生成並通過驗證：{level_dict.get("rows", "?")}×{level_dict.get("cols", "?")} 盤面')
            break

        # 驗證失敗 印出每一條問題，並把它回饋給模型自動重生
        for err in validation.errors[:6]:
            emit('warning', f'　• {err}')
        if len(validation.errors) > 6:
            emit('warning', f'　…等共 {len(validation.errors)} 個問題')
        if attempt < MAX_ATTEMPTS:
            feedback = ('\n\n【系統提醒】你上一次產生的關卡有以下格式問題，請務必修正後重新輸出完整 JSON：\n- '
                        + '\n- '.join(validation.errors[:8]))
            continue
        # 次數用完仍有警告 仍讓玩家玩，只是提示可能略有瑕疵
        emit('warning', '自動修正後仍有格式警告，先讓你玩玩看（可能略有瑕疵）')

    st.session_state.booth_level = level_dict

    # 關卡就緒 先讓玩家玩；難度測試改成報表裡按鈕觸發（不自動跑，不卡畫面）
    if validation.valid:
        st.session_state.booth_sim_results = None
        st.session_state.booth_sim_pending = False
        emit('success', '關卡就緒，可以開始玩了！')
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

    # 縮小 Streamlit 預設留白 攤位一螢幕(16:9)塞得下、不用捲動
    st.markdown(
        '''<style>
        .block-container { padding-top: 1.2rem !important; padding-bottom: 0.8rem !important;
                           max-width: 100% !important; }
        h1 { margin-bottom: 0 !important; }
        div[data-testid="stVerticalBlock"] { gap: 0.5rem; }
        /* 直式遊戲 iframe 置中（寬度已鎖 9:16，這裡把左右白邊平均分配） */
        iframe { display: block; margin-left: auto; margin-right: auto; }
        </style>''',
        unsafe_allow_html=True,
    )

    # 頂部標題
    st.markdown(
        f'''
        <div style="text-align:center; padding: 10px 0 6px 0;">
          <h1 style="margin:0; font-size: 2.6em; font-weight:800; letter-spacing:0.5px;
                     background:linear-gradient(90deg,#4285F4 0%,#34A853 33%,#FBBC04 66%,#EA4335 100%);
                     -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                     background-clip:text;">
            Match3 AI Level Designer
          </h1>
          <p style="color:#5f6368; margin:8px 0 0 0; font-size:1.08em; font-weight:500;">
            ✨ 用一句話，設計你的專屬遊戲關卡
          </p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # 攤位操作鈕：換下一位訪客（清空上一位的所有資訊 + 遊戲回待機）
    _rl, _rr = st.columns([4, 1])
    with _rr:
        if st.button('🔄 換下一位訪客', use_container_width=True,
                     help='清空上一位訪客的需求、關卡與報表，遊戲畫面回到待機'):
            _reset_for_next_visitor()
            st.rerun()

    # 檢查 API key / GCP credentials
    provider = get_model_provider(BOOTH_MODEL)
    has_key = _get_key(provider) or _get_key('gcp_project')
    if not has_key:
        st.warning(
            '尚未設定 GOOGLE_API_KEY。'
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
        # 清除鍵按下後 下一輪、在 text_area 建立「之前」把輸入框清空
        if st.session_state.pop('_booth_clear_input', False):
            st.session_state['booth_input'] = ''

        st.markdown('#### ✏️ 描述你想要的關卡')
        st.caption('點範本填進下面的框 可直接改 按生成')

        # 範本：2 欄排列（省高度）。點了把實際 prompt 填進輸入框，看清楚再生成
        _qp_cols = st.columns(2)
        for i, (label, _desc, prompt_text) in enumerate(QUICK_PROMPTS):
            with _qp_cols[i % 2]:
                if st.button(label, key=f'qp_{i}', use_container_width=True):
                    st.session_state['booth_input'] = prompt_text

        # 上次送出的需求 — 用小字（省高度）
        if st.session_state.get('booth_last_prompt'):
            st.caption(f'上次送出：{st.session_state.booth_last_prompt}')

        # 輸入框（範本會填進這裡，可直接編輯）
        user_input = st.text_area(
            '描述（可直接編輯）',
            key='booth_input',
            placeholder='例：做一個消除起來很爽的關卡 / 給我一個愛心形狀的盤面...',
            height=80,
            label_visibility='collapsed',
        )

        # 形狀 / 難度：收進「進階選項」，預設收起；選了之後在外面顯示摘要。
        _SHAPE_DIR = dict(SHAPE_OPTIONS)
        _DIFF_DIR = dict(DIFFICULTY_OPTIONS)
        # 展開控制：使用者「主動改了選擇」→ 保持展開；按生成 → 強制收合
        #（用 label 後面加隱形零寬字元換掉 widget 身份，保證收合不被前端 sticky 卡住）
        _adv_sig = (st.session_state.get('booth_shape_pill'), st.session_state.get('booth_diff_pill'),
                    (st.session_state.get('booth_custom_shape') or '').strip(),
                    (st.session_state.get('booth_custom_diff') or '').strip())
        if _adv_sig != st.session_state.get('_adv_sig_prev') and any(_adv_sig):
            st.session_state['booth_adv_open'] = True
        st.session_state['_adv_sig_prev'] = _adv_sig
        _adv_label = '⚙️ 進階選項：指定形狀 / 難度（可不選）' \
            + ('​' * st.session_state.get('booth_adv_collapse_n', 0))
        with st.expander(_adv_label, expanded=st.session_state.get('booth_adv_open', False)):
            if SAFE_MODE:
                _sel_shape = None
                _custom_shape = ''
                st.caption('🔷 形狀：demo 安全模式期間停用（形狀會挖 void → 卡死）')
            else:
                _sel_shape = st.pills('🔷 形狀', list(_SHAPE_DIR.keys()) + ['其他'],
                                      selection_mode='single', key='booth_shape_pill')
                _custom_shape = ''
                if _sel_shape == '其他':
                    _custom_shape = st.text_input('自己打一個形狀', key='booth_custom_shape',
                                                  placeholder='例：星星、貓、閃電…')
            _sel_diff = st.pills('🎚️ 難度', list(_DIFF_DIR.keys()) + ['其他'],
                                 selection_mode='single', key='booth_diff_pill')
            _custom_diff = ''
            if _sel_diff == '其他':
                _custom_diff = st.text_input('自己打一個難度', key='booth_custom_diff',
                                             placeholder='例：地獄級、輕鬆休閒…')

        # 換成附加給 AI 的指示（選「其他」就用自己打的）
        if _sel_shape == '其他' and (_custom_shape or '').strip():
            _shape_dir = _shape_directive(_custom_shape.strip())
        elif _sel_shape in _SHAPE_DIR:
            _shape_dir = _SHAPE_DIR[_sel_shape]
        else:
            _shape_dir = ''
        if _sel_diff == '其他' and (_custom_diff or '').strip():
            _diff_dir = f'（請把這關的難度調整成「{_custom_diff.strip()}」，但仍要保證有解、一定過得了。）'
        elif _sel_diff in _DIFF_DIR:
            _diff_dir = _DIFF_DIR[_sel_diff]
        else:
            _diff_dir = ''

        # 選了就在外面顯示摘要（進階選項收起來也看得到）
        _shape_label = ((_custom_shape or '').strip() if _sel_shape == '其他'
                        else (_sel_shape if _sel_shape in _SHAPE_DIR else None))
        _diff_label = ((_custom_diff or '').strip() if _sel_diff == '其他'
                       else (_sel_diff if _sel_diff in _DIFF_DIR else None))
        if _shape_label or _diff_label:
            _parts = []
            if _shape_label:
                _parts.append(f'🔷 形狀：**{_shape_label}**')
            if _diff_label:
                _parts.append(f'🎚️ 難度：**{_diff_label}**')
            st.caption('已指定　' + '　｜　'.join(_parts))

        # 生成 / 清除
        # 需求文字、形狀、難度三者只要有一個就能生成；全空才 disable（避免沒輸入就亂點）。
        _has_input = bool((user_input or '').strip())
        _can_gen = _has_input or bool(_shape_dir) or bool(_diff_dir)
        gen_cols = st.columns([3, 1])
        with gen_cols[0]:
            generate_clicked = st.button(
                '✨ 生成' if _can_gen else '✨ 先輸入需求 或 選形狀 / 難度…',
                use_container_width=True, type='primary',
                disabled=not _can_gen,
            )
        with gen_cols[1]:
            if st.button('🗑️ 清除', use_container_width=True, help='清空需求與這一關'):
                st.session_state.booth_chat_history = []
                st.session_state.booth_level = None
                st.session_state.booth_agent_log = []
                st.session_state.booth_sim_results = None
                st.session_state.booth_env = None
                st.session_state.booth_last_prompt = ''
                st.session_state['booth_last_full_prompt'] = ''
                st.session_state['_booth_clear_input'] = True  # 下一輪清空輸入框
                st.rerun()

        # 觸發生成 — 需求文字（空就用通用 base）＋ 形狀 ＋ 難度，組成這一輪 prompt。
        # 生成後想調整：改上面的形狀 / 難度 / 文字，再按一次「生成」即可。
        just_generated = False
        if generate_clicked and _can_gen:
            # 按生成 → 收合進階選項（換 label nonce 強制收合，避免擠到下面的字）
            st.session_state['booth_adv_open'] = False
            st.session_state['booth_adv_collapse_n'] = \
                st.session_state.get('booth_adv_collapse_n', 0) + 1
            _base = user_input.strip() if _has_input else '做一個好玩、有挑戰的小關卡。'
            if SAFE_MODE:
                _shape_dir = ''   # 安全模式：形狀要挖 void → 會觸發遊戲端死鎖，一律不套形狀
            _prompt = _base + _shape_dir + _diff_dir
            st.session_state.booth_last_prompt = _base
            # 記下這一輪「實際送出的需求」，生成後在下面的小框框可展開查看
            st.session_state['booth_last_full_prompt'] = _prompt
            # 用「一直可見的區塊」而非 st.status，直接攤在外面、跑完留著。
            st.markdown('##### ✨ AI 正在即時創作這一關…')
            _ok = _do_generate(_prompt, live=True, big_board=bool(_shape_dir))
            if _ok:
                st.success('關卡完成，可以開始玩了！')
            else:
                st.error('這次沒生成成功（模型沒吐有效 JSON）— 再按一次「生成」試試')
            just_generated = True

        # Agent 執行紀錄（剛生成的已即時顯示過 避免重複；其餘靜態重畫）
        st.markdown('---')
        if not just_generated:
            _render_agent_log()

        # 想看細節的人才點：這一關「實際送給 AI 的完整 prompt」（生成後才出現、平常收起來）
        if st.session_state.get('booth_last_full_prompt'):
            with st.expander('🔍 查看這一關實際送給 AI 的完整 prompt'):
                st.caption('① 你的需求（含形狀 / 難度）＋ 攤位短關卡指示')
                st.code(st.session_state['booth_last_full_prompt'] + BOOTH_LEVEL_HINT, language='text')
                st.caption('② 系統提示（含完整設計規範）')
                _params_preview = {'rows': 8, 'cols': 8, 'difficulty': 'medium',
                                   'num_colors': 4, 'obstacle_types': [], 'goal_types': []}
                st.code(build_system_prompt(_params_preview), language='text')

    with col_right:
        # Godot iframe — 一進頁面就載入（不用等關卡）
        st.markdown('##### 🕹️ 遊戲區')

        # 🎨 美術風格下拉：外面選 → 重載遊戲套用（跟 AI Art Lab 同機制，乾淨重開不 GPU 當機）
        _theme_opts = _load_theme_index()
        if len(_theme_opts) > 1:
            _t_labels = [t.get('label', t.get('name', '')) for t in _theme_opts]
            _t_names = [t.get('name', '') for t in _theme_opts]
            _t_cur = st.session_state.get('booth_theme', '')
            _t_idx = _t_names.index(_t_cur) if _t_cur in _t_names else 0
            _t_pick = st.selectbox('🎨 遊戲美術風格（切換會重載遊戲）', _t_labels,
                                   index=_t_idx, key='booth_theme_pick')
            _t_picked = _t_names[_t_labels.index(_t_pick)]
            if _t_picked != _t_cur:
                st.session_state['booth_theme'] = _t_picked
                st.session_state['booth_godot_buster'] = \
                    st.session_state.get('booth_godot_buster', 0) + 1
                st.session_state['_booth_level_pushed'] = None  # 重載後讓關卡重推（若有）
                st.rerun()

        # iframe URL：v=buster 一變就重載（換風格/換下一位共用）；theme= 指定美術；?booth=1 攤位模式。
        # 遊戲是直式(720×1280)，iframe 寬度鎖成 9:16，左右不會有黑邊；用 CSS 置中。
        _buster = st.session_state.get('booth_godot_buster', 0)
        _theme = st.session_state.get('booth_theme', '')
        _qs = ['booth=1', f'v={_buster}']
        if _theme:
            _qs.append(f'theme={_theme}')
        godot_url = f'{GODOT_DEMO_URL}?' + '&'.join(_qs)
        _GH = 820
        _GW = round(_GH * 720 / 1280)  # 9:16 ≈ 461；再放大，12×12 大盤面也塞得下
        st.components.v1.iframe(godot_url, width=_GW, height=_GH, scrolling=False)
        # （全螢幕按鈕暫移除：Godot 畫布在全螢幕沒置中、會跑到左上。demo 用這個直式視窗即可。）

        level = st.session_state.booth_level

        # 關卡已載入時：用 postMessage 傳送到 Godot（不重新載入 iframe）
        if level and st.session_state.get('_booth_level_pushed') != id(level):
            st.session_state['_booth_level_pushed'] = id(level)
            level_json_str = json.dumps(level, ensure_ascii=False)
            # 注入 JS 發送 postMessage 給 iframe
            st.components.v1.html(
                f'''<script>
                (function() {{
                    var payload = {{type:'load_level',
                                   level_json: JSON.stringify({json.dumps(level, ensure_ascii=False)})}};
                    function push() {{
                        var frames = window.parent.document.querySelectorAll('iframe');
                        for (var i = 0; i < frames.length; i++) {{
                            if (frames[i].src && frames[i].src.indexOf('{GODOT_HOST_MARKER}') !== -1) {{
                                try {{ frames[i].contentWindow.postMessage(payload, '*'); }} catch(e) {{}}
                                break;
                            }}
                        }}
                    }}
                    // 立即 + 多次重試：換風格/重載後 Godot 要 ~3 秒才收得到，重試確保關卡回得來。
                    // Godot 端對「同一關卡」會去重，不會重啟。
                    [0, 1200, 2400, 3600, 4800, 6000].forEach(function(t){{ setTimeout(push, t); }});
                }})();
                </script>''',
                height=0,
            )

        # 觀看 AI 解關 → 用遊戲畫面右上角 Godot 內建的「AI 解關」按鈕即可（不在外面重複放一顆）

        if level is None:
            st.info('👈 在左邊描述你想要的關卡，按「✨ 生成」就會出現在這裡')
        else:
            # === 關卡報表（可收合；收起來時標題仍顯示難度結論）===
            sim = st.session_state.booth_sim_results
            _ms = level.get('max_steps', None)
            goals = level.get('goals', {})

            if sim:
                _bl, _bc, _be, _bd = _difficulty_badge(sim.win_rate)
                _rep_label = f'📊 關卡報表　·　{_be} 難度：{_bl}（AI 勝率 {sim.win_rate:.0%}）'
            else:
                _rep_label = '📊 關卡報表'

            with st.expander(_rep_label, expanded=True):
                # 規格列
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric('盤面', f"{level.get('rows', '?')}×{level.get('cols', '?')}")
                sc2.metric('步數', _ms if _ms is not None else '?')
                sc3.metric('目標數', len(goals))
                if goals:
                    st.markdown('🎯 **目標**　' + '　'.join(f'`{k}` ×{v}' for k, v in goals.items()))

                # 驗證狀態
                v = st.session_state.booth_validation
                if v:
                    if v.valid and not v.warnings:
                        st.success('格式驗證通過，可以遊玩')
                    elif v.valid:
                        st.warning(f'通過，可以玩，但有 {len(v.warnings)} 個建議：')
                        for w in v.warnings[:3]:
                            st.caption(f'　· {w}')
                    else:
                        st.error(f'{len(v.errors)} 個格式錯誤')
                        for err in v.errors[:3]:
                            st.caption(f'　· {err}')

                # 難度 + AI 測試報表（按鈕觸發；不自動跑，避免一載入就模擬把畫面卡住）
                if sim is None:
                    if st.button('🤖 讓 AI 自動試玩、測這關難度（15 場）',
                                 use_container_width=True, key='run_sim_btn'):
                        with st.spinner('AI 試玩中…（約 1 秒）'):
                            try:
                                st.session_state.booth_sim_results = run_simulation_batch(
                                    level_dict=level, n_games=15,
                                    steps_multiplier=1.0, max_workers=2)
                            except Exception as _e:
                                st.error(f'測試失敗：{_e}')
                        st.rerun()
                elif sim:
                    wr = sim.win_rate
                    _lbl, _clr, _emo, _desc = _difficulty_badge(wr)
                    # 難度橫幅（彩色）
                    st.markdown(
                        f'<div style="background:{_clr}18;border-left:6px solid {_clr};'
                        f'padding:10px 14px;border-radius:8px;margin:8px 0 6px 0;">'
                        f'<span style="font-size:1.15em;font-weight:700;color:{_clr};">'
                        f'{_emo}　難度：{_lbl}</span>'
                        f'<span style="color:#555;margin-left:10px;">{_desc}</span></div>',
                        unsafe_allow_html=True)
                    st.progress(min(wr, 1.0),
                                text=f'AI 勝率 {wr:.0%}　·　自動試玩 {sim.n_games} 場')

                    # 關鍵數字
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric('AI 平均步數',
                               f'{sim.avg_steps_won:.0f}' if sim.avg_steps_won else '—',
                               help=f'只算贏的場；這關給 {_ms} 步' if _ms else '只算贏的場')
                    if sim.avg_steps_won and isinstance(_ms, int):
                        mc2.metric('步數寬裕', f'+{_ms - sim.avg_steps_won:.0f}',
                                   help='給的步數 − AI 平均用的步數；太大代表步數給太多、偏鬆')
                    else:
                        mc2.metric('步數寬裕', '—')
                    mc3.metric('最快 / 最慢',
                               f'{sim.min_steps} / {sim.max_steps_seen}' if sim.min_steps else '—',
                               help='所有試玩場次中，最少與最多的步數')

                    # 步數分佈小圖（資料化調校的視覺證據）
                    if sim.step_histogram:
                        try:
                            import pandas as _pd
                            _items = sorted(sim.step_histogram.items())
                            _df = _pd.DataFrame(
                                {'場數': [c for _, c in _items]},
                                index=[s for s, _ in _items])
                            _df.index.name = '步數'
                            st.caption('步數分佈')
                            st.bar_chart(_df, height=130, color=_clr)
                        except Exception:
                            pass

                    # 卡關點 / 各目標達成率
                    hg = sim.hardest_goal()
                    if hg and len(sim.goal_stats) > 1:
                        tid, sgs = hg
                        if sgs['met_rate'] >= 0.95:
                            st.success(f'最難目標：**{tid}**（需 {sgs["required"]}）'
                                       f'— 達成率 {sgs["met_rate"]:.0%}，不算卡關')
                        else:
                            st.warning(f'卡關點：**{tid}**（需 {sgs["required"]}）'
                                       f'— 只有 {sgs["met_rate"]:.0%} 場達成、平均做到 {sgs["avg_progress"]:.0%}')
                    if len(sim.goal_stats) > 1:
                        st.caption('各目標達成率：' + '　'.join(
                            f'{t} {s["met_rate"]:.0%}' for t, s in sim.goal_stats.items()))

            # AI 解關回放
            replay = st.session_state.booth_replay
            if replay:
                st.markdown('---')
                st.markdown('#### AI 解關紀錄')

                last = replay[-1]
                if last['won']:
                    st.success(f"AI 在 {last['step']} 步內通關！")
                else:
                    st.warning(f"AI 用了 {last['step']} 步但未通關")

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

    # （難度測試改成報表裡的按鈕觸發，不再一載入就自動背景模擬把畫面卡住）

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
