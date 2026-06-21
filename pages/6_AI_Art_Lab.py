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


def _score_caption(verdict: dict | None) -> str:
    return api.format_verdict_scores(verdict)


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
    ref_hint = '已上傳參考圖 — critic 會評 reference score' if style_upload else (
        '未上傳時,若存在 `game_art_reference.png` 會自動作為參考圖並評 reference score'
    )
    st.caption(ref_hint)

    asset_names, asset_labels = _asset_catalog()
    if 'art_asset_multiselect' not in st.session_state:
        st.session_state.art_asset_multiselect = list(api.BASIC_ELEMENTS)

    pick_cols = st.columns(4)
    with pick_cols[0]:
        if st.button('選基本元素', use_container_width=True):
            st.session_state.art_asset_multiselect = list(api.BASIC_ELEMENTS)
            st.rerun()
    with pick_cols[1]:
        if st.button('選全部', use_container_width=True):
            st.session_state.art_asset_multiselect = asset_names
            st.rerun()
    with pick_cols[2]:
        if st.button('清除', use_container_width=True):
            st.session_state.art_asset_multiselect = []
            st.rerun()
    with pick_cols[3]:
        st.caption(f'共 {len(asset_names)} 張')

    elements = st.multiselect(
        '目標資產',
        options=asset_names,
        format_func=lambda n: asset_labels[n],
        key='art_asset_multiselect',
        help='來自 godot_demo/resources/sprites/ 的全部遊戲美術',
    )

    if st.button('生成美術', type='primary', use_container_width=True):
        _run_generation(style, run_name, elements, style_upload)

    _render_results()
    _render_advanced()


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


def _render_results() -> None:
    if not st.session_state.art_results:
        return
    st.markdown('##### 生成結果')
    results = st.session_state.art_results
    cols = st.columns(len(results))
    for col, (name, result) in zip(cols, results.items()):
        with col:
            icon = STATUS_ICON.get(result.status, '•')
            if result.image:
                st.image(result.image, caption=f'{icon} {name}', width=72)
            else:
                st.caption(f'{icon} {name} —')
            v = result.verdict or {}
            if v:
                st.caption(_score_caption(v))

    st.markdown('---')
    if st.button('套用到遊戲 →', type='primary', use_container_width=True,
                 disabled=not st.session_state.art_summary):
        _apply_to_game()


def _render_advanced() -> None:
    with st.expander('載入既有 run / 還原', expanded=not st.session_state.art_results):
        prev_runs = api.list_runs()
        if prev_runs:
            pick = st.selectbox('載入既有 run', ['—'] + prev_runs)
            if pick != '—' and st.button('載入預覽', key='load_prev_run'):
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
    try:
        result = api.apply_run_to_game(
            run, to_component=True, to_live=True, to_project=False, asset_names=names,
        )
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
    st.rerun()


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


def _render_game_panel() -> None:
    st.subheader('2 · 遊戲遊玩畫面')

    top = st.columns([1, 1, 2])
    with top[0]:
        if st.button('新盤面', use_container_width=True):
            _new_board()
            st.rerun()
    with top[1]:
        if st.button('打亂', use_container_width=True):
            st.session_state.art_env.board.shuffle()
            st.session_state.art_selected = None
            st.rerun()
    with top[2]:
        if st.session_state.art_applied_run:
            st.caption(f'已套用 run: `{st.session_state.art_applied_run}`')
        else:
            st.caption('生成後按「套用到遊戲」即可在此看到新元素')

    env = st.session_state.art_env
    click = match3_board(
        env,
        mode='play',
        selected=st.session_state.art_selected,
        cell_size=60,
        asset_version=st.session_state.art_asset_version,
        key='art_lab_board',
    )
    if click and click.get('type') == 'click':
        _handle_click(click['r'], click['c'])
        st.rerun()

    st.caption('點兩個相鄰元素交換試玩。此盤面即時反映已套用的美術,不需 Godot 重新匯出。')

    with st.expander('Godot 美術版(需 CI 重新 Export 後才會反映新美術)', expanded=False):
        cols = st.columns([2, 1])
        with cols[0]:
            if _godot_up():
                st.success('Godot server 運行中')
            else:
                st.info('Godot server 未啟動(`./run.sh`)')
        with cols[1]:
            st.link_button('新分頁開啟', url=GODOT_URL, use_container_width=True)
        if _godot_up():
            buster = st.session_state.art_godot_buster
            components.iframe(f'{GODOT_URL}?v={buster}', height=640, scrolling=False)
        st.caption(
            '目前線上的 `index.pck` 是舊版,尚未含 ArtTheme autoload。'
            '需透過 GitHub Actions(deploy-godot-pages)重新 Export 才會載入 live_sprites。'
        )


def main() -> None:
    _init_state()
    st.title('AI Game Art Lab')
    st.caption('用 art_pipeline 生成遊戲美術,即時套用到可玩盤面')

    left, right = st.columns([1, 1.4], gap='large')
    with left:
        _render_generation_panel()
    with right:
        _render_game_panel()


main()
