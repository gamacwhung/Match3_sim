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
GODOT_VIEWPORT_W = 720
GODOT_VIEWPORT_H = 1280

# (chip label, full style prompt)
STYLE_CHIPS: list[tuple[str, str]] = [
    ('像素復古', '像素風格 pixel art, crisp edges, retro game'),
    ('水彩柔和', '水彩手繪 watercolor, soft edges, pastel'),
    ('霓虹賽博', '賽博龐克 neon glow, dark background accents'),
    ('黏土 3D', '黏土 3D clay render, rounded, toy-like'),
    ('日式平面', '日式和風 ukiyo-e flat color, bold outline'),
]

ELEMENT_LABELS: dict[str, str] = {
    'Red': '紅', 'Grn': '綠', 'Blu': '藍', 'Yel': '黃', 'Pur': '紫',
}

WORKFLOW_STEPS = ('① 選風格', '② 生成', '③ 審核', '④ 套用', '⑤ 試玩')

STATUS_ICON = {'pass': '✅', 'needs_review': '🟡', 'failed': '❌'}

RESULT_FILTERS = ('全部', '通過', '待審', '失敗')
RESULT_FILTER_STATUS = {
    '通過': 'pass',
    '待審': 'needs_review',
    '失敗': 'failed',
}


def _inject_css() -> None:
    st.markdown(
        '''
        <style>
        .art-section-label {
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            color: #888;
            margin: 0 0 6px 0;
            text-transform: uppercase;
        }
        .art-workflow {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin: 12px 0 16px 0;
        }
        .art-step {
            flex: 1;
            min-width: 72px;
            text-align: center;
            padding: 8px 4px;
            border-radius: 8px;
            font-size: 0.82rem;
            background: #f4f4f5;
            color: #888;
            border: 1px solid #e8e8ea;
        }
        .art-step.active {
            background: #e8f0fe;
            color: #1a73e8;
            border-color: #1a73e8;
            font-weight: 600;
        }
        .art-step.done {
            background: #e6f4ea;
            color: #0d904f;
            border-color: #c8e6c9;
        }
        .art-godot-dot {
            display: inline-block;
            width: 8px; height: 8px;
            border-radius: 50%;
            margin-right: 6px;
            vertical-align: middle;
        }
        .art-godot-dot.on { background: #0d904f; }
        .art-godot-dot.off { background: #e37400; }
        .art-before-after {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin: 8px 0 12px 0;
            padding: 10px;
            background: #fafafa;
            border-radius: 8px;
            border: 1px solid #eee;
        }
        .art-ba-item {
            text-align: center;
            font-size: 0.75rem;
            color: #666;
        }
        .art-ba-pair {
            display: flex;
            align-items: center;
            gap: 4px;
            justify-content: center;
        }
        .art-ba-arrow { color: #aaa; font-size: 0.7rem; }
        </style>
        ''',
        unsafe_allow_html=True,
    )


def _init_state() -> None:
    defaults = {
        'art_run_name': api.suggest_run_name('pixel'),
        'art_style': STYLE_CHIPS[0][1],
        'art_selected_chip': STYLE_CHIPS[0][0],
        'art_custom_style': False,
        'art_results': None,
        'art_summary': None,
        'art_asset_version': 0,
        'art_applied_run': None,
        'art_env': None,
        'art_selected': None,
        'art_status_msg': '',
        'art_godot_buster': int(time.time()),
        'art_generating': False,
        'art_result_filter': '全部',
        'art_asset_family': 'elements',
        'art_show_more_assets': False,
        'art_use_reference_image': False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
    if st.session_state.art_env is None:
        st.session_state.art_env = Match3Env(rows=8, cols=8, num_colors=5, max_steps=999)


def _workflow_step() -> int:
    if st.session_state.get('art_applied_run'):
        return 5
    if st.session_state.art_results:
        return 3
    if st.session_state.get('art_generating'):
        return 2
    return 1


def _render_workflow_stepper() -> None:
    current = _workflow_step()
    parts = []
    for i, label in enumerate(WORKFLOW_STEPS, start=1):
        if i < current:
            cls = 'art-step done'
        elif i == current:
            cls = 'art-step active'
        else:
            cls = 'art-step'
        parts.append(f'<div class="{cls}">{label}</div>')
    st.markdown(
        f'<div class="art-workflow">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


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


@st.cache_data
def _asset_families() -> dict[str, list[str]]:
    return api.list_families()


def _score_caption(verdict: dict | None) -> str:
    return api.format_verdict_scores(verdict)


def _set_all_picks(asset_names: list[str], selected: list[str]) -> None:
    sel = set(selected)
    for n in asset_names:
        st.session_state[f'art_pick_{n}'] = n in sel


def _render_style_studio() -> str:
    st.markdown('<p class="art-section-label">STYLE</p>', unsafe_allow_html=True)

    if not api.has_credentials():
        st.warning(
            '尚未連接 Google AI。請在 `config.py`、環境變數 `GOOGLE_API_KEY` '
            '或 Streamlit secrets 設定金鑰。'
        )

    chip_cols = st.columns(len(STYLE_CHIPS))
    for col, (label, prompt) in zip(chip_cols, STYLE_CHIPS):
        with col:
            selected = st.session_state.art_selected_chip == label
            if st.button(
                label,
                key=f'art_chip_{label}',
                use_container_width=True,
                type='primary' if selected else 'secondary',
            ):
                st.session_state.art_selected_chip = label
                st.session_state.art_style = prompt
                st.session_state.art_custom_style = False
                st.rerun()

    custom = st.checkbox('自訂風格描述', value=st.session_state.art_custom_style)
    st.session_state.art_custom_style = custom

    if custom:
        style = st.text_area(
            '風格描述',
            value=st.session_state.art_style,
            height=72,
            label_visibility='collapsed',
        )
        st.session_state.art_style = style
    else:
        st.caption(st.session_state.art_style)

    style_upload = None
    with st.expander('＋ 參考圖風格（選填）', expanded=False):
        use_ref = st.checkbox(
            '使用參考圖風格',
            value=st.session_state.art_use_reference_image,
            help='關閉後只靠文字風格描述生成，不使用 game_art_reference.png 或上傳圖',
            key='art_use_reference_image_cb',
        )
        st.session_state.art_use_reference_image = use_ref

        if use_ref:
            style_upload = st.file_uploader(
                '元素參考圖',
                type=['png', 'jpg', 'jpeg', 'webp'],
                label_visibility='collapsed',
            )
            if style_upload:
                st.image(style_upload, caption=f'已上傳：{style_upload.name}', width=140)
                st.caption('AI 會比對參考圖風格是否一致')
            else:
                default_ref = api.default_style_image()
                if default_ref:
                    st.image(str(default_ref), caption=f'預設：{default_ref.name}', width=140)
                    st.caption('未上傳時使用專案預設參考圖')
                else:
                    st.caption('未上傳參考圖 — 將僅依文字風格描述生成')
        else:
            st.caption('已關閉參考圖 — 僅依上方風格文字生成，不載入預設參考圖')

    return style_upload


def _render_hero_elements(asset_imgs: dict[str, str]) -> None:
    """五色基本元素 — 大縮圖快速選取。"""
    cols = st.columns(5)
    for col, name in zip(cols, api.BASIC_ELEMENTS):
        with col:
            img = asset_imgs.get(name)
            if img:
                st.image(img, width=64)
            label = ELEMENT_LABELS.get(name, name)
            st.checkbox(
                f'{label} {name}',
                key=f'art_pick_{name}',
                help=f'基本元素 · {name}',
            )


def _render_asset_picker(
    asset_names: list[str],
    asset_labels: dict[str, str],
    asset_imgs: dict[str, str],
) -> list[str]:
    st.markdown('<p class="art-section-label">ASSETS</p>', unsafe_allow_html=True)

    if not st.session_state.get('art_picks_init'):
        _set_all_picks(asset_names, list(api.BASIC_ELEMENTS))
        st.session_state.art_picks_init = True

    st.caption('先從 5 色基本元素開始，約 1–2 分鐘可看到遊戲內效果。')
    _render_hero_elements(asset_imgs)

    show_more = st.checkbox(
        '更多資產（道具、障礙…）',
        value=st.session_state.art_show_more_assets,
        key='art_show_more_assets',
    )

    if show_more:
        families = _asset_families()
        family_keys = sorted(families.keys(), key=lambda f: api.FAMILY_LABELS.get(f, f))
        family_labels = [api.FAMILY_LABELS.get(f, f) for f in family_keys]
        label_for_family = api.FAMILY_LABELS.get(
            st.session_state.art_asset_family, '基本元素',
        )
        fam_idx = family_labels.index(label_for_family) if label_for_family in family_labels else 0

        picked_label = st.radio(
            '分類',
            family_labels,
            index=fam_idx,
            horizontal=True,
            label_visibility='collapsed',
        )
        fam_key = family_keys[family_labels.index(picked_label)]
        st.session_state.art_asset_family = fam_key
        family_names = [n for n in families[fam_key] if n not in api.BASIC_ELEMENTS]

        btn_cols = st.columns([1, 1, 1])
        with btn_cols[0]:
            if st.button('選此分類', use_container_width=True, key='art_pick_family'):
                current = [n for n in asset_names if st.session_state.get(f'art_pick_{n}')]
                merged = list(dict.fromkeys(current + family_names))
                _set_all_picks(asset_names, merged)
                st.rerun()
        with btn_cols[1]:
            if st.button('選全部', use_container_width=True, key='art_pick_all'):
                _set_all_picks(asset_names, asset_names)
                st.rerun()
        with btn_cols[2]:
            if st.button('清除', use_container_width=True, key='art_pick_clear'):
                _set_all_picks(asset_names, [])
                st.rerun()

        query = st.text_input(
            '搜尋',
            key='art_asset_filter',
            placeholder='名稱關鍵字…',
            label_visibility='collapsed',
        ).strip().lower()
        filtered = [
            n for n in family_names
            if not query or query in n.lower() or query in asset_labels[n].lower()
        ]

        ncols = 4
        with st.container(height=280):
            if not filtered:
                st.caption('此分類沒有符合的資產')
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
    st.caption(f'已選 **{len(elements)}** 個資產')
    return elements


def _render_action_bar(style: str, run_name: str, elements: list[str], style_upload) -> None:
    st.markdown('<p class="art-section-label">ACTIONS</p>', unsafe_allow_html=True)
    gen_col, apply_col = st.columns(2)
    with gen_col:
        if st.button('生成美術', type='primary', use_container_width=True, key='art_btn_generate'):
            _run_generation(style, run_name, elements, style_upload)
    with apply_col:
        has_results = bool(st.session_state.art_summary)
        if st.button(
            '套用到遊戲並預覽',
            type='primary' if has_results else 'secondary',
            use_container_width=True,
            disabled=not has_results,
            key='art_btn_apply',
        ):
            _apply_to_game()


def _render_generation_panel() -> None:
    style_upload = _render_style_studio()

    asset_names, asset_labels = _asset_catalog()
    asset_imgs = _asset_images()
    elements = _render_asset_picker(asset_names, asset_labels, asset_imgs)

    with st.expander('進階設定', expanded=False):
        run_name = st.text_input('版本名稱', value=st.session_state.art_run_name)
        st.session_state.art_run_name = run_name
        _render_advanced_inner()

    _render_action_bar(
        st.session_state.art_style,
        st.session_state.art_run_name,
        elements,
        style_upload,
    )
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
    if st.session_state.art_use_reference_image and style_upload:
        suffix = pathlib.Path(style_upload.name).suffix or '.png'
        tmp = pathlib.Path(tempfile.mkstemp(suffix=suffix)[1])
        tmp.write_bytes(style_upload.getvalue())
        style_path = tmp

    st.session_state.art_generating = True
    ref_label = '含參考圖' if st.session_state.art_use_reference_image else '純文字風格'
    progress = st.progress(0, text=f'準備中…（{ref_label}）')
    status = st.empty()

    def on_progress(cur, total, name, result):
        if result is None:
            progress.progress(int((cur - 1) / total * 100), text=f'生成 {name} ({cur}/{total})…')
            status.caption(f'正在生成 **{name}**…')
        else:
            icon = STATUS_ICON.get(result.status, '•')
            scores = _score_caption(result.verdict)
            status.caption(
                f'{icon} {name} — {result.status} ({result.iters} iters)'
                + (f' · {scores}' if scores else '')
            )

    try:
        summary = api.generate(
            style.strip(), run_name.strip(),
            asset_names=elements, style_image_path=style_path,
            reference_image=st.session_state.art_use_reference_image,
            max_iters=3, on_progress=on_progress,
        )
        st.session_state.art_summary = summary
        st.session_state.art_results = summary.results
        progress.progress(100, text='完成')
        st.toast(
            f'生成完成：通過 {summary.passed} · 待審 {summary.needs_review} · 失敗 {summary.failed}',
            icon='✅',
        )
    except Exception as exc:
        st.error(f'生成失敗: {exc}')
    finally:
        st.session_state.art_generating = False
        if tmp and tmp.is_file():
            tmp.unlink()


def _filter_results(items: list[tuple[str, object]]) -> list[tuple[str, object]]:
    filt = st.session_state.art_result_filter
    if filt == '全部':
        return items
    want = RESULT_FILTER_STATUS[filt]
    return [(n, r) for n, r in items if r.status == want]


def _render_result_thumb(name: str, result) -> None:
    icon = STATUS_ICON.get(result.status, '•')
    if not result.image:
        st.caption(f'{icon} {name} —')
        return
    scores = _score_caption(result.verdict)
    cap = f'{icon} {name}'
    if scores:
        cap += f'\n{scores}'
    st.image(result.image, width=88, caption=cap)


def _render_results() -> None:
    if not st.session_state.art_results:
        return

    summary = st.session_state.art_summary
    st.markdown('<p class="art-section-label">RESULTS</p>', unsafe_allow_html=True)
    if summary:
        st.caption(
            f'通過 **{summary.passed}** · 待審 **{summary.needs_review}** · 失敗 **{summary.failed}**'
        )

    counts = {label: 0 for label in RESULT_FILTERS}
    counts['全部'] = len(st.session_state.art_results)
    for r in st.session_state.art_results.values():
        for label, status in RESULT_FILTER_STATUS.items():
            if r.status == status:
                counts[label] += 1

    filter_labels = [f'{label} ({counts[label]})' for label in RESULT_FILTERS]
    picked = st.radio(
        '篩選',
        filter_labels,
        horizontal=True,
        label_visibility='collapsed',
        key='art_result_filter_radio',
    )
    st.session_state.art_result_filter = picked.split(' ')[0]

    items = _filter_results(list(st.session_state.art_results.items()))
    ncols = 4
    with st.container(height=300):
        if not items:
            st.caption('此篩選沒有結果')
        for i in range(0, len(items), ncols):
            cols = st.columns(ncols)
            for col, (name, result) in zip(cols, items[i:i + ncols]):
                with col:
                    _render_result_thumb(name, result)


def _render_advanced_inner() -> None:
    prev_runs = api.list_runs()
    if prev_runs:
        pick = st.selectbox('載入既有版本', ['—'] + prev_runs, key='art_load_pick')
        if pick != '—' and pick != st.session_state.get('art_loaded_run'):
            _load_run(pick)
    else:
        st.caption('尚無既有版本')

    if st.button('還原原版美術', use_container_width=True, key='art_restore'):
        try:
            api.restore_original_art()
            st.session_state.art_asset_version = int(time.time())
            st.session_state.art_applied_run = None
            st.toast('已還原原版美術', icon='↩️')
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
        st.session_state.art_asset_version = int(time.time())
        st.session_state.art_godot_buster = int(time.time())
        st.toast('已套用 — 右側遊戲預覽已重新載入', icon='🎮')
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


def _render_before_after_strip() -> None:
    if not st.session_state.art_applied_run or not st.session_state.art_results:
        return

    asset_imgs = _asset_images()
    results = st.session_state.art_results
    show_names = [n for n in api.BASIC_ELEMENTS if n in results and results[n].image]
    if not show_names:
        return

    st.caption('基本元素 · 原版 → 新版')
    cols = st.columns(len(show_names))
    for col, name in zip(cols, show_names):
        with col:
            orig_path = asset_imgs.get(name)
            result = results[name]
            sub = st.columns([1, 0.3, 1])
            with sub[0]:
                if orig_path:
                    st.image(orig_path, width=40)
            with sub[1]:
                st.markdown('<div style="padding-top:12px;color:#aaa;">→</div>', unsafe_allow_html=True)
            with sub[2]:
                if result.image:
                    st.image(result.image, width=40)
            st.caption(ELEMENT_LABELS.get(name, name))


@st.fragment
def _render_godot_embed() -> None:
    """獨立 fragment:重載只更新 iframe,不重繪左側大量預覽圖。"""
    dot_cls = 'on' if _godot_up() else 'off'
    status_text = '已連線' if _godot_up() else '未啟動'
    top = st.columns([1, 1, 2])
    with top[0]:
        if st.button('重新載入預覽', use_container_width=True, key='godot_reload'):
            st.session_state.art_godot_buster = int(time.time())
            st.rerun(scope='fragment')
    with top[1]:
        st.link_button('新分頁開啟', url=GODOT_URL, use_container_width=True)
    with top[2]:
        run = st.session_state.art_applied_run
        if run:
            st.markdown(
                f'<span class="art-godot-dot {dot_cls}"></span>'
                f'<span style="font-size:0.85rem;color:#666;">{status_text} · 版本 {run}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span class="art-godot-dot {dot_cls}"></span>'
                f'<span style="font-size:0.85rem;color:#666;">{status_text}</span>',
                unsafe_allow_html=True,
            )

    _render_before_after_strip()

    if _godot_up():
        buster = st.session_state.art_godot_buster
        embed_url = f'{GODOT_URL}?v={buster}'
        # iframe 維持與 Godot 專案相同的直向比例,避免 expand 裁切左右
        components.html(
            f'''
            <div id="godot-embed" style="width:100%;aspect-ratio:{GODOT_VIEWPORT_W}/{GODOT_VIEWPORT_H};
                        max-height:92vh;margin:0 auto;background:#000;border-radius:8px;overflow:hidden;">
              <iframe src="{embed_url}" style="width:100%;height:100%;border:0;display:block;"
                      allow="autoplay" loading="lazy"></iframe>
            </div>
            <script>
            (function() {{
              const wrap = document.getElementById('godot-embed');
              const sendHeight = () => {{
                const h = Math.ceil(wrap.getBoundingClientRect().height) + 4;
                window.parent.postMessage({{type: 'streamlit:setFrameHeight', height: h}}, '*');
              }};
              new ResizeObserver(sendHeight).observe(wrap);
              sendHeight();
            }})();
            </script>
            ''',
            height=int(520 * GODOT_VIEWPORT_H / GODOT_VIEWPORT_W),
            scrolling=False,
        )
        st.caption('Godot 本機渲染 — 套用美術後會自動重新載入預覽')
    else:
        st.warning('遊戲預覽未啟動。請在專案根目錄執行：')
        st.code('./run.sh', language='bash')


def _render_game_panel() -> None:
    st.markdown('<p class="art-section-label">LIVE PREVIEW</p>', unsafe_allow_html=True)
    _render_godot_embed()

    with st.expander('離線快速預覽（Godot 未啟動時可用）', expanded=False):
        st.caption('渲染與正式版略有差異，僅供快速確認元素外觀。')
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
    _inject_css()

    st.markdown(
        '''
        <div style="padding: 8px 0 0 0;">
          <h1 style="margin:0; font-size: 1.9em;">🖌️ AI Game Art Lab</h1>
          <p style="color:#666; margin: 4px 0 0 0;">
            選一個風格 → 生成 5 色元素 → 右側立刻試玩
          </p>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    _render_workflow_stepper()

    left, right = st.columns([0.95, 1.05], gap='large')
    with left:
        _generation_panel_fragment()
    with right:
        _game_panel_fragment()


main()
