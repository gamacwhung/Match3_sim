"""
AI Game Art Lab — 生成三消基本元素美術,即時套用到遊戲。

左側:美術生成操作介面(art_pipeline API)
右側:可實際遊玩的盤面 —— 套用後立即看到新元素

流程:生成 → 套用到遊戲 → 右側盤面即時更新(可點擊交換試玩)

前置:./run.sh  (Streamlit 8501)
備註:Godot web build 的新美術需 CI 重新 Export(含 ArtTheme autoload)才會生效,
      本機可玩盤面則即時生效,不需重新匯出。
"""

from __future__ import annotations

import pathlib
import socket
import sys
import tempfile
import time

import streamlit as st
import streamlit.components.v1 as components

_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from art_pipeline import api
from match3_board_component import match3_board
from match3_env import Match3Env
from tile_defs import is_powerup

st.set_page_config(
    page_title='AI Game Art Lab',
    page_icon='🖌️',
    layout='wide',
    initial_sidebar_state='collapsed',
)

GODOT_PORT = 8765
GODOT_URL = f'http://localhost:{GODOT_PORT}/'

STYLE_PRESETS = [
    '像素風格 pixel art, crisp edges, retro game',
    '水彩手繪 watercolor, soft edges, pastel',
    '賽博龐克 neon glow, dark background accents',
    '黏土 3D clay render, rounded, toy-like',
    '日式和風 ukiyo-e flat color, bold outline',
]

STATUS_ICON = {'pass': '✅', 'needs_review': '🟡', 'failed': '❌'}


def _init_state() -> None:
    defaults = {
        'art_run_name': api.suggest_run_name('pixel'),
        'art_style': STYLE_PRESETS[0],
        'art_last_preset': STYLE_PRESETS[0],
        'art_results': None,
        'art_summary': None,
        'art_asset_version': 0,
        'art_applied_run': None,
        'art_env': None,
        'art_selected': None,
        'art_status_msg': '',
        'art_godot_buster': int(time.time()),
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
    if st.session_state.art_env is None:
        st.session_state.art_env = Match3Env(rows=8, cols=8, num_colors=5, max_steps=999)


def _godot_up() -> bool:
    try:
        with socket.create_connection(('127.0.0.1', GODOT_PORT), timeout=0.4):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

@st.cache_data
def _asset_catalog() -> tuple[list[str], dict[str, str]]:
    return api.asset_catalog()


@st.cache_data
def _asset_images() -> dict[str, str]:
    return api.asset_image_map()


def _score_caption(verdict: dict | None) -> str:
    return api.format_verdict_scores(verdict)


def _set_all_picks(asset_names: list[str], selected: list[str]) -> None:
    sel = set(selected)
    for n in asset_names:
        st.session_state[f'art_pick_{n}'] = n in sel


def _render_asset_picker(
    asset_names: list[str],
    asset_labels: dict[str, str],
    asset_imgs: dict[str, str],
) -> list[str]:
    """縮圖網格選擇器:每張資產顯示縮圖 + 勾選框,回傳已選名稱。"""
    st.markdown('##### 目標資產')

    if not st.session_state.get('art_picks_init'):
        _set_all_picks(asset_names, list(api.BASIC_ELEMENTS))
        st.session_state.art_picks_init = True

    btn_cols = st.columns([1, 1, 1, 1.4])
    with btn_cols[0]:
        if st.button('選基本元素', use_container_width=True):
            _set_all_picks(asset_names, list(api.BASIC_ELEMENTS))
            st.rerun()
    with btn_cols[1]:
        if st.button('選全部', use_container_width=True):
            _set_all_picks(asset_names, asset_names)
            st.rerun()
    with btn_cols[2]:
        if st.button('清除', use_container_width=True):
            _set_all_picks(asset_names, [])
            st.rerun()
    with btn_cols[3]:
        st.caption(f'共 {len(asset_names)} 張')

    query = st.text_input('搜尋資產', key='art_asset_filter', placeholder='輸入名稱關鍵字過濾…').strip().lower()
    filtered = [
        n for n in asset_names
        if not query or query in n.lower() or query in asset_labels[n].lower()
    ]

    ncols = 4
    with st.container(height=360):
        if not filtered:
            st.caption('沒有符合的資產')
        for i in range(0, len(filtered), ncols):
            row = filtered[i:i + ncols]
            cols = st.columns(ncols)
            for col, name in zip(cols, row):
                with col:
                    img = asset_imgs.get(name)
                    if img:
                        st.image(img, width=56)
                    st.checkbox(name, key=f'art_pick_{name}', help=asset_labels[name])

    elements = [n for n in asset_names if st.session_state.get(f'art_pick_{n}')]
    st.caption(f'已選 {len(elements)} 個' + (f':{", ".join(elements)}' if elements else ''))
    return elements


def _render_generation_panel() -> None:
    st.subheader('1 · 美術生成')

    if not api.has_credentials():
        st.warning(
            '尚未設定 Google API。請在 `config.py`、環境變數 `GOOGLE_API_KEY` '
            '或 Streamlit secrets 設定 Vertex / AI Studio 金鑰。'
        )

    preset = st.selectbox('風格快捷', STYLE_PRESETS)
    if preset != st.session_state.art_last_preset:
        st.session_state.art_style = preset
        st.session_state.art_last_preset = preset

    style = st.text_area('風格描述', value=st.session_state.art_style, height=80)
    st.session_state.art_style = style

    run_name = st.text_input('Run 名稱', value=st.session_state.art_run_name)
    st.session_state.art_run_name = run_name

    style_upload = st.file_uploader('元素參考圖(可選)', type=['png', 'jpg', 'jpeg', 'webp'])
    if style_upload:
        st.image(style_upload, caption=f'已上傳參考圖:{style_upload.name}', width=160)
        st.caption('已上傳參考圖 — critic 會評 reference score')
    else:
        default_ref = api.default_style_image()
        if default_ref:
            st.image(str(default_ref), caption=f'預設參考圖:{default_ref.name}', width=160)
            st.caption('未上傳時,將自動以此 `game_art_reference.png` 作為參考圖並評 reference score')
        else:
            st.caption('未上傳,且找不到預設 `game_art_reference.png` — 將不使用參考圖')

    asset_names, asset_labels = _asset_catalog()
    asset_imgs = _asset_images()
    elements = _render_asset_picker(asset_names, asset_labels, asset_imgs)

    if st.button('生成美術', type='primary', use_container_width=True):
        _run_generation(style, run_name, elements, style_upload)

    _render_advanced()
    _render_results()


def _run_generation(style, run_name, elements, style_upload) -> None:
    if not style.strip():
        st.error('請輸入風格描述')
        return
    if not elements:
        st.error('請至少選一個元素')
        return
    if not api.has_credentials():
        st.error('缺少 API 金鑰')
        return

    style_path = None
    tmp: pathlib.Path | None = None
    if style_upload:
        suffix = pathlib.Path(style_upload.name).suffix or '.png'
        tmp = pathlib.Path(tempfile.mkstemp(suffix=suffix)[1])
        tmp.write_bytes(style_upload.getvalue())
        style_path = tmp

    progress = st.progress(0, text='準備中…')
    status = st.empty()

    def on_progress(cur, total, name, result):
        if result is None:
            progress.progress(int((cur - 1) / total * 100), text=f'生成 {name} ({cur}/{total})…')
            status.caption(f'正在生成 **{name}**…')
        else:
            icon = STATUS_ICON.get(result.status, '•')
            scores = _score_caption(result.verdict)
            status.caption(f'{icon} {name} — {result.status} ({result.iters} iters)' + (f' · {scores}' if scores else ''))

    try:
        summary = api.generate(
            style.strip(), run_name.strip(),
            asset_names=elements, style_image_path=style_path,
            max_iters=3, on_progress=on_progress,
        )
        st.session_state.art_summary = summary
        st.session_state.art_results = summary.results
        progress.progress(100, text='完成')
        st.success(f'完成: pass={summary.passed}  review={summary.needs_review}  fail={summary.failed}')
    except Exception as exc:
        st.error(f'生成失敗: {exc}')
    finally:
        if tmp and tmp.is_file():
            tmp.unlink()


def _render_result_thumb(name: str, result) -> None:
    icon = STATUS_ICON.get(result.status, '•')
    if not result.image:
        st.caption(f'{icon} {name} —')
        return
    # 用 st.image 避免 base64 內嵌整頁(大量圖會讓 rerun 卡死/崩潰)
    scores = _score_caption(result.verdict)
    cap = f'{icon} {name}'
    if scores:
        cap += f' · {scores}'
    st.image(result.image, width=72, caption=cap)


def _render_results() -> None:
    if not st.session_state.art_results:
        return
    st.markdown('##### 生成結果')
    items = list(st.session_state.art_results.items())
    ncols = 4
    with st.container(height=320):
        for i in range(0, len(items), ncols):
            cols = st.columns(ncols)
            for col, (name, result) in zip(cols, items[i:i + ncols]):
                with col:
                    _render_result_thumb(name, result)

    st.markdown('---')
    if st.button('套用到遊戲 →', type='primary', use_container_width=True,
                 disabled=not st.session_state.art_summary):
        _apply_to_game()


def _render_advanced() -> None:
    with st.expander('載入既有 run / 還原', expanded=not st.session_state.art_results):
        prev_runs = api.list_runs()
        if prev_runs:
            pick = st.selectbox('載入既有 run', ['—'] + prev_runs, key='art_load_pick')
            if pick != '—' and pick != st.session_state.get('art_loaded_run'):
                _load_run(pick)
        else:
            st.caption('尚無既有 run')

        if st.button('還原原版美術', use_container_width=True):
            try:
                api.restore_original_art()
                st.session_state.art_asset_version = int(time.time())
                st.success('已還原原版美術')
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _apply_to_game() -> None:
    run = st.session_state.art_summary.run_name
    names = list(st.session_state.art_summary.results.keys())
    total = len(names)
    progress = st.progress(0, text=f'[0/{total}] 張圖片正在套入…')
    status = st.empty()

    def on_progress(cur: int, tot: int, name: str) -> None:
        pct = int((cur - 1) / tot * 100) if tot else 0
        progress.progress(pct, text=f'[{cur}/{tot}] 張圖片正在套入…')
        status.caption(f'正在套用 **{name}**')

    try:
        result = api.apply_run_to_game(
            run, to_component=True, to_live=True, to_project=False, asset_names=names,
            on_progress=on_progress,
        )
        progress.progress(100, text=f'[{total}/{total}] 套用完成')
        status.empty()
        st.session_state.art_applied_run = run
        # 遞增版本號 → 盤面 sprite 帶上 ?v= 強制重新載入
        st.session_state.art_asset_version = int(time.time())
        st.session_state.art_godot_buster = int(time.time())
        st.success(
            f'已套用 {len(result.component_applied)} 張到可玩盤面'
            + (f',{len(result.live_applied)} 張到 Godot live_sprites' if result.live_applied else '')
            + ' — 右側盤面已更新'
        )
        st.rerun()
    except Exception as exc:
        progress.empty()
        status.empty()
        st.error(f'套用失敗: {exc}')


def _load_run(run_name: str) -> None:
    report = api.load_report(run_name)
    loaded = {}
    for name in report.get('results', {}):
        data = api.load_sprite_bytes(run_name, name)
        if data:
            r = report['results'][name]
            loaded[name] = api.AssetResult(
                name=name, status=r.get('status', '?'), iters=r.get('iters', 0),
                image=data, verdict=r.get('verdict'),
            )
    st.session_state.art_results = loaded
    st.session_state.art_summary = api.GenerationSummary(
        run_name=run_name, run_dir=api.run_dir(run_name),
        style=report.get('style', ''), results=loaded,
    )
    st.session_state.art_loaded_run = run_name


@st.fragment
def _generation_panel_fragment() -> None:
    _render_generation_panel()


@st.fragment
def _game_panel_fragment() -> None:
    _render_game_panel()


# ---------------------------------------------------------------------------
# 遊戲(可玩盤面)
# ---------------------------------------------------------------------------

def _new_board() -> None:
    st.session_state.art_env = Match3Env(rows=8, cols=8, num_colors=5, max_steps=999)
    st.session_state.art_selected = None
    st.session_state.art_status_msg = '已開新盤面'


def _handle_click(r: int, c: int) -> None:
    env = st.session_state.art_env
    selected = st.session_state.art_selected
    if selected is None:
        st.session_state.art_selected = (r, c)
        return
    sr, sc = selected
    if (sr, sc) == (r, c):
        tile = env.board.get_middle(sr, sc)
        if tile and is_powerup(tile.tile_id):
            env.step({'type': 'activate', 'pos': (sr, sc)})
        st.session_state.art_selected = None
    elif abs(sr - r) + abs(sc - c) == 1:
        env.step({'type': 'swap', 'pos1': (sr, sc), 'pos2': (r, c)})
        st.session_state.art_selected = None
    else:
        st.session_state.art_selected = (r, c)


@st.fragment
def _render_godot_embed() -> None:
    """獨立 fragment:重載只更新 iframe,不重繪左側大量預覽圖。"""
    top = st.columns([1, 1, 2])
    with top[0]:
        if st.button('重新載入遊戲', use_container_width=True, key='godot_reload'):
            st.session_state.art_godot_buster = int(time.time())
            st.rerun(scope='fragment')
    with top[1]:
        st.link_button('新分頁開啟', url=GODOT_URL, use_container_width=True)
    with top[2]:
        if st.session_state.art_applied_run:
            st.caption(f'已套用 run: `{st.session_state.art_applied_run}` — 重載後看新元素')
        else:
            st.caption('生成 → 套用到遊戲 → 按「重新載入遊戲」')

    if _godot_up():
        st.success('Godot server 運行中 (localhost:8765)')
        buster = st.session_state.art_godot_buster
        components.iframe(
            f'{GODOT_URL}?v={buster}',
            height=820,
            scrolling=False,
        )
        st.caption(
            '這是 **Godot 本機遊戲**（與正式版相同渲染）。'
            '套用美術會寫入 `live_sprites/`，重載 iframe 即可看到新 5 色元素。'
        )
    else:
        st.warning(
            'Godot server 未啟動。請在專案根目錄執行 `./run.sh`（不要只用 `--streamlit-only`）。'
        )
        st.code('./run.sh\n# 然後重新整理此頁', language='bash')


def _render_game_panel() -> None:
    st.subheader('2 · 遊戲遊玩畫面')
    _render_godot_embed()

    with st.expander('Streamlit 簡易盤面（備用預覽,非 Godot 渲染）', expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            if st.button('新盤面', key='art_new_board', use_container_width=True):
                _new_board()
                st.rerun()
        with c2:
            if st.button('打亂', key='art_shuffle', use_container_width=True):
                st.session_state.art_env.board.shuffle()
                st.session_state.art_selected = None
                st.rerun()
        env = st.session_state.art_env
        click = match3_board(
            env, mode='play', selected=st.session_state.art_selected,
            cell_size=56, asset_version=st.session_state.art_asset_version,
            key='art_lab_board',
        )
        if click and click.get('type') == 'click':
            _handle_click(click['r'], click['c'])
            st.rerun()


def main() -> None:
    _init_state()
    st.title('AI Game Art Lab')
    st.caption('用 art_pipeline 生成美術 → 套用到 Godot 遊戲（右側）')

    left, right = st.columns([1, 1.4], gap='large')
    with left:
        _generation_panel_fragment()
    with right:
        _game_panel_fragment()


main()
