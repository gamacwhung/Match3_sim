"""
AI Game Art Lab — 生成三消基本元素美術,即時套用到遊戲。

左側:美術生成操作介面(art_pipeline API)
右側:可實際遊玩的盤面 —— 套用後立即看到新元素

流程:生成 → 套用到遊戲 → 右側盤面即時更新(可點擊交換試玩)

前置:./run.sh  (Streamlit 8501)
備註:Godot 預覽預設用 pck 打包美術;按「套用到遊戲」後 iframe 才帶 ?live=1 載入 live_sprites。
"""

from __future__ import annotations

import base64
import io
import pathlib
import socket
import sys
import tempfile
import time

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

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
LIVE_SPRITES_DIR = _ROOT / 'godot_demo' / 'web' / 'live_sprites'
GODOT_VIEWPORT_W = 720
GODOT_VIEWPORT_H = 1280

HEADER_WALL_DIR = _ROOT / 'web_static' / 'art_lab_header_wall' / 'sprites'
HEADER_WALL_THUMB_PX = 88
HEADER_WALL_GAP_PX = 12
HEADER_WALL_ANIM_SECS = 90

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

RESULT_FILTERS = ('全部', '通過', '待審', '失敗')
RESULT_FILTER_STATUS = {
    '通過': 'pass',
    '待審': 'needs_review',
    '失敗': 'failed',
}

STATUS_ICON = {'pass': '✅', 'needs_review': '🟡', 'failed': '❌'}


def _page_css() -> str:
    return '''
        <style>
        .block-container {
            padding-top: 0 !important;
            max-width: 100% !important;
        }
        .block-container > div > div:first-child {
            margin-top: 0 !important;
        }
        div[data-testid="stVerticalBlock"] { gap: 0.5rem; }
        .art-header-shell {
            position: relative;
            overflow: hidden;
            border-radius: 0 0 12px 12px;
            margin: var(--st-topbar-height, 3.75rem) -1rem 12px -1rem;
            min-height: 132px;
            background: #f4f4f5;
        }
        .art-header-wall {
            position: absolute;
            inset: 0;
            overflow: hidden;
        }
        .art-header-wall::after {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(
                90deg,
                rgba(255, 255, 255, 0.92) 0%,
                rgba(255, 255, 255, 0.55) 18%,
                rgba(255, 255, 255, 0.55) 82%,
                rgba(255, 255, 255, 0.92) 100%
            );
            pointer-events: none;
        }
        .art-header-track {
            display: flex;
            width: max-content;
            height: 100%;
            align-items: center;
            animation: art-wall-scroll var(--art-wall-duration, 50s) linear infinite;
        }
        .art-header-strip {
            display: flex;
            align-items: center;
            gap: 12px;
            padding-right: 12px;
        }
        .art-header-strip img {
            height: 88px;
            width: 88px;
            object-fit: contain;
            flex-shrink: 0;
            background: rgba(255, 255, 255, 0.72);
            border-radius: 10px;
            padding: 6px;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
        }
        @keyframes art-wall-scroll {
            from { transform: translateX(0); }
            to { transform: translateX(-50%); }
        }
        @media (prefers-reduced-motion: reduce) {
            .art-header-track { animation: none; }
        }
        .art-header-overlay {
            position: relative;
            z-index: 1;
            text-align: center;
            padding: 28px 16px 22px;
        }
        .art-header-overlay h1 {
            margin: 0;
            font-size: 2.2em;
            line-height: 1.15;
            text-shadow: 0 1px 10px rgba(255, 255, 255, 0.95);
        }
        .art-header-overlay p {
            color: #666;
            margin: 6px 0 0 0;
            font-size: 1.05em;
            text-shadow: 0 1px 8px rgba(255, 255, 255, 0.95);
        }
        .art-section-label {
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            color: #888;
            margin: 0 0 6px 0;
            text-transform: uppercase;
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
        '''


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
        'art_use_reference_image': False,
        'art_generation_mode': 'restyle',
        'art_theme_text': '',
        'art_expand_theme': True,
        'art_theme_plan': None,
        'art_reference_run': '',
        'art_max_iters': 3,
        'art_force': False,
        'art_image_model': '',
        'art_critic_model': '',
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


def _godot_embed_url() -> str:
    """Godot iframe URL; ?live=1 only after「套用到遊戲」so web load skips live_sprites."""
    buster = st.session_state.art_godot_buster
    params = [f'v={buster}']
    if st.session_state.art_applied_run:
        params.append('live=1')
        rev_path = LIVE_SPRITES_DIR / 'revision.txt'
        if rev_path.is_file():
            params.append(f'rev={rev_path.read_text(encoding="utf-8").strip()}')
    return f'{GODOT_URL}?{"&".join(params)}'


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

@st.cache_data
def _asset_catalog() -> tuple[list[str], dict[str, str]]:
    return api.asset_catalog()


@st.cache_data
def _asset_images(reference_run: str = '') -> dict[str, str]:
    return api.asset_thumbnail_map(reference_run or None)


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


def _render_generation_mode_panel(selected_assets: list[str]) -> None:
    st.markdown('<p class="art-section-label">MODE</p>', unsafe_allow_html=True)
    mode_options = {
        'restyle': '換皮（保留物件，只改風格）',
        'theme_swap': '主題換物件（依玩法角色換成新主題物件）',
    }
    mode_keys = list(mode_options.keys())

    mode = st.radio(
        '生成模式',
        mode_keys,
        format_func=lambda k: mode_options[k],
        key='art_generation_mode',
        label_visibility='collapsed',
    )

    if mode == 'restyle':
        ref_runs = api.list_reference_runs()
        saved_ref = st.session_state.get('art_reference_run') or ''
        if saved_ref and saved_ref not in ref_runs:
            ref_runs = [saved_ref] + ref_runs
        ref_choices = [''] + ref_runs

        def _ref_a_label(run_name: str) -> str:
            if not run_name:
                return f'遊戲預設（{api.default_packed_art_run()}）'
            n = len(list(api.run_dir(run_name).glob('sprites/*.png')))
            return f'{run_name}（{n} 張）'

        st.selectbox(
            'Reference A 來源',
            ref_choices,
            format_func=_ref_a_label,
            key='art_reference_run',
            help='選先前 run 可在主題生成後再換畫風；該 run 沒有的 asset 會跳過，不 fallback 官方圖',
        )
        ref_run = st.session_state.get('art_reference_run') or ''
        if ref_run:
            st.caption(f'換皮基準：**{ref_run}** /sprites/')

    if mode != 'theme_swap':
        return

    theme = st.text_input(
        '主題概念',
        key='art_theme_text',
        placeholder='例如：糖果屋、海洋世界、太空站…',
        help='可寫概念讓 LLM 展開，或手動指定 Red=草莓, Grn=薄荷糖…',
    )

    theme_stripped = theme.strip()
    manual_assign = '=' in theme_stripped
    if manual_assign:
        st.session_state.art_expand_theme = False
        st.caption('已偵測到手動指定（含 =），不會自動展開')
    else:
        expand = st.checkbox(
            'LLM 自動展開主題',
            key='art_expand_theme',
            help='將「糖果屋」自動展開為每個元素的物件指派',
        )

        preview_assets = selected_assets or list(api.BASIC_ELEMENTS)
        if theme_stripped and expand:
            if st.button('預覽主題展開', key='art_preview_theme', use_container_width=True):
                try:
                    plan = api.preview_theme_plan(
                        theme_stripped, st.session_state.art_style, preview_assets,
                    )
                    st.session_state.art_theme_plan = plan
                    st.toast('主題已展開', icon='🎯')
                except Exception as exc:
                    st.error(f'展開失敗: {exc}')

    plan = st.session_state.art_theme_plan
    if plan and plan.get('concept') == theme_stripped:
        direction = plan.get('theme_direction', '')
        if direction:
            st.caption(f'展開方向：{direction}')
        assignments = plan.get('assignments') or {}
        if assignments:
            lines = [f'**{name}** → {obj}' for name, obj in sorted(assignments.items())]
            st.markdown(' · '.join(lines))


def _reference_run_for_thumbnails() -> str:
    if st.session_state.get('art_generation_mode') != 'restyle':
        return ''
    return st.session_state.get('art_reference_run') or ''


def _render_asset_picker(
    asset_names: list[str],
    asset_labels: dict[str, str],
    asset_imgs: dict[str, str],
    *,
    reference_run: str = '',
) -> list[str]:
    st.markdown('<p class="art-section-label">ASSETS</p>', unsafe_allow_html=True)

    if not st.session_state.get('art_picks_init'):
        _set_all_picks(asset_names, list(api.BASIC_ELEMENTS))
        st.session_state.art_picks_init = True

    if reference_run:
        st.caption(
            f'縮圖來自 **{reference_run}**；此 run 沒有的 asset 不顯示縮圖，生成時也會跳過。'
        )
    else:
        st.caption('預設已勾選 5 色基本元素，可切換分類選取更多資產。')

    families = _asset_families()
    family_keys = sorted(families.keys(), key=lambda f: api.FAMILY_LABELS.get(f, f))

    fam_key = st.radio(
        '分類',
        family_keys,
        format_func=lambda k: api.FAMILY_LABELS.get(k, k),
        key='art_asset_family',
        horizontal=True,
        label_visibility='collapsed',
    )
    family_names = families[fam_key]

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
    pending = st.session_state.pop('_art_pending_load', None)
    if pending:
        _load_run(pending)

    asset_names, asset_labels = _asset_catalog()
    preview_assets = [
        n for n in asset_names if st.session_state.get(f'art_pick_{n}')
    ] or list(api.BASIC_ELEMENTS)
    _render_generation_mode_panel(preview_assets)

    style_upload = _render_style_studio()

    ref_for_thumbs = _reference_run_for_thumbnails()
    asset_imgs = _asset_images(ref_for_thumbs)
    elements = _render_asset_picker(
        asset_names, asset_labels, asset_imgs, reference_run=ref_for_thumbs,
    )

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
    if st.session_state.art_generation_mode == 'theme_swap':
        if not st.session_state.art_theme_text.strip():
            st.error('主題換物件模式請輸入主題概念')
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

    from art_pipeline.pipeline import resolve_expand_theme

    st.session_state.art_generating = True
    mode = st.session_state.art_generation_mode
    theme_text = st.session_state.art_theme_text.strip() or None
    expand_theme = resolve_expand_theme(
        mode, theme_text,
        no_expand_theme=not st.session_state.art_expand_theme,
    )
    mode_label = '主題換物件' if mode == 'theme_swap' else '換皮'
    ref_run = (st.session_state.get('art_reference_run') or None) if mode == 'restyle' else None
    ref_a_label = f'Ref A: {ref_run}' if ref_run else 'Ref A: 官方'
    ref_b_label = '含參考圖' if st.session_state.art_use_reference_image else '純文字風格'
    progress = st.progress(0, text=f'準備中…（{mode_label} · {ref_a_label} · {ref_b_label}）')
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
        image_model = st.session_state.art_image_model.strip() or None
        critic_model = st.session_state.art_critic_model.strip() or None
        summary = api.generate(
            style.strip(), run_name.strip(),
            asset_names=elements, style_image_path=style_path,
            reference_image=st.session_state.art_use_reference_image,
            mode=mode, theme_text=theme_text, expand_theme=expand_theme,
            reference_run=ref_run,
            image_model=image_model,
            critic_model=critic_model,
            max_iters=st.session_state.art_max_iters,
            force=st.session_state.art_force,
            on_progress=on_progress,
        )
        st.session_state.art_summary = summary
        st.session_state.art_results = summary.results
        if summary.theme_plan:
            st.session_state.art_theme_plan = summary.theme_plan
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
        mode = getattr(summary, 'generation_mode', 'restyle')
        if mode == 'theme_swap' and summary.theme_text:
            theme_line = f'主題 **{summary.theme_text}**'
            if summary.theme_expanded and summary.theme_expanded != summary.theme_text:
                theme_line += f' → {summary.theme_expanded}'
            st.caption(theme_line)
        elif mode == 'restyle' and getattr(summary, 'reference_run', None):
            st.caption(f'Reference A 來自 **{summary.reference_run}**')
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


def _queue_load_run() -> None:
    pick = st.session_state.get('art_load_pick')
    if pick and pick != '—':
        st.session_state._art_pending_load = pick


def _render_advanced_inner() -> None:
    from art_pipeline import gemini_api

    st.number_input(
        '每張最多迭代次數',
        min_value=1,
        max_value=10,
        value=st.session_state.art_max_iters,
        key='art_max_iters',
        help='與 CLI --max-iters 相同',
    )
    st.checkbox(
        '強制重生已通過的資產',
        value=st.session_state.art_force,
        key='art_force',
        help='與 CLI --force 相同',
    )
    st.text_input(
        '生圖模型',
        value=st.session_state.art_image_model,
        key='art_image_model',
        placeholder=gemini_api.DEFAULT_IMAGE_MODEL,
        help='留空使用預設模型',
    )
    st.text_input(
        '評審模型',
        value=st.session_state.art_critic_model,
        key='art_critic_model',
        placeholder=gemini_api.DEFAULT_CRITIC_MODEL,
        help='留空使用預設模型',
    )

    prev_runs = api.list_runs()
    if prev_runs:
        st.selectbox(
            '載入既有版本',
            ['—'] + prev_runs,
            key='art_load_pick',
            on_change=_queue_load_run,
        )
    else:
        st.caption('尚無既有版本')

    if st.button('還原遊戲預設美術', use_container_width=True, key='art_restore'):
        try:
            api.restore_original_art()
            st.session_state.art_asset_version = int(time.time())
            st.session_state.art_applied_run = None
            st.session_state.art_godot_buster = int(time.time())
            st.toast(f'已還原遊戲預設（{api.default_packed_art_run()}）', icon='↩️')
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
        generation_mode=report.get('generation_mode', 'restyle'),
        theme_text=report.get('theme'),
        theme_plan=report.get('theme_plan'),
        theme_expanded=report.get('theme_expanded'),
        reference_run=report.get('reference_run'),
    )
    st.session_state.art_generation_mode = report.get('generation_mode', 'restyle')
    st.session_state.art_theme_text = report.get('theme', '') or ''
    st.session_state.art_theme_plan = report.get('theme_plan')
    st.session_state.art_reference_run = report.get('reference_run') or ''
    st.session_state.art_run_name = run_name
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

    ref_run = ''
    summary = st.session_state.get('art_summary')
    if summary:
        ref_run = getattr(summary, 'reference_run', None) or ''
    asset_imgs = _asset_images(ref_run)
    results = st.session_state.art_results
    show_names = [n for n in api.BASIC_ELEMENTS if n in results and results[n].image]
    if not show_names:
        return

    before_label = ref_run if ref_run else '原版'
    st.caption(f'基本元素 · {before_label} → 新版')
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
        embed_url = _godot_embed_url()
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
        st.caption('Godot 本機渲染 — 套用美術後會以 live 覆蓋重新載入預覽')
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


def _header_wall_stamp(sprites_dir: pathlib.Path) -> str:
    pngs = sorted(sprites_dir.glob('*.png'))
    if not pngs:
        return ''
    return f'{len(pngs)}:{max(p.stat().st_mtime for p in pngs):.0f}'


@st.cache_data(show_spinner=False)
def _header_wall_data_urls(sprites_dir: str, thumb_px: int, stamp: str) -> tuple[str, ...]:
    if not stamp:
        return ()
    root = pathlib.Path(sprites_dir)
    urls: list[str] = []
    for path in sorted(root.glob('*.png')):
        try:
            with Image.open(path) as im:
                im = im.convert('RGBA')
                im.thumbnail((thumb_px, thumb_px), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format='PNG', optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode('ascii')
                urls.append(f'data:image/png;base64,{b64}')
        except OSError:
            continue
    return tuple(urls)


def _header_wall_strip(urls: tuple[str, ...]) -> str:
    if not urls:
        return ''
    return ''.join(f'<img src="{url}" alt="" />' for url in urls)


def _render_page_header() -> None:
    stamp = _header_wall_stamp(HEADER_WALL_DIR)
    urls = _header_wall_data_urls(str(HEADER_WALL_DIR), HEADER_WALL_THUMB_PX, stamp)
    strip = _header_wall_strip(urls)
    wall_html = ''
    if strip:
        wall_html = (
            f'<div class="art-header-wall" style="--art-wall-duration: {HEADER_WALL_ANIM_SECS}s;">'
            f'<div class="art-header-track">'
            f'<div class="art-header-strip">{strip}</div>'
            f'<div class="art-header-strip" aria-hidden="true">{strip}</div>'
            f'</div></div>'
        )
    st.markdown(
        _page_css()
        + f'''
        <div class="art-header-shell">
          {wall_html}
          <div class="art-header-overlay">
            <h1>AI Game Art Lab</h1>
            <p>一鍵打造你的專屬遊戲美術</p>
          </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def main() -> None:
    _init_state()
    _render_page_header()

    left, right = st.columns([0.95, 1.05], gap='large')
    with left:
        _generation_panel_fragment()
    with right:
        _game_panel_fragment()


main()
