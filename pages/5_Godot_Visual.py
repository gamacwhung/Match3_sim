"""
🎨 Godot 美術版 — 在 Streamlit 內直接 iframe 嵌入 Godot 4 web build

demo 時 sidebar 直接點進來,iframe 接近全螢幕。
依賴另一個 HTTP server 在跑(預設 port 8765),
用根目錄的 `.\\start_demo.ps1` 一鍵起,或:
    cd godot_demo/web
    python -m http.server 8765
"""

from __future__ import annotations

import socket
import time

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title='Match3 — Godot 美術版',
    page_icon='🎨',
    layout='wide',
    initial_sidebar_state='collapsed',
)


# ===========================================================================
# 小工具
# ===========================================================================

def _check_server(host: str, port: int, timeout: float = 0.5) -> bool:
    """快速確認 Godot HTTP server 是否在 listen。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


# ===========================================================================
# Backend 來源:本機 vs GitHub Pages(deploy 之後)
# ===========================================================================
# - 本機 demo:預設用 localhost:8765,需先跑 .\start_demo.ps1
# - 雲端 demo(Streamlit Cloud / 任何 https):必須用 GitHub Pages 連結,
#   因為 https 頁面內嵌 http://localhost iframe 會被 Chrome Mixed Content 擋,
#   且 localhost 從訪客瀏覽器看出去是訪客自己的電腦(不會有 godot server)
BACKEND_OPTIONS = {
    '本機 (localhost:8765)': 'http://localhost:8765/',
    'GitHub Pages (公開,任何人都看得到)': 'https://gamacwhung.github.io/Match3_sim/',
}

# Session state
if 'godot_backend' not in st.session_state:
    st.session_state.godot_backend = '本機 (localhost:8765)'
if 'godot_url' not in st.session_state:
    st.session_state.godot_url = BACKEND_OPTIONS[st.session_state.godot_backend]
if 'godot_height' not in st.session_state:
    st.session_state.godot_height = 900
if 'godot_cache_buster' not in st.session_state:
    st.session_state.godot_cache_buster = int(time.time())


# ===========================================================================
# 設定列(小寫、不搶版面)
# ===========================================================================

with st.container():
    cols = st.columns([3, 3, 2, 2])
    with cols[0]:
        st.markdown(
            '## 🎨 Godot 美術版'
            '<span style="color:#888; font-size:0.8em; margin-left:12px">'
            'Godot 4 web build'
            '</span>',
            unsafe_allow_html=True,
        )
    with cols[1]:
        # 切換 backend (本機 vs GitHub Pages)
        backend = st.radio(
            'Backend',
            options=list(BACKEND_OPTIONS.keys()),
            index=list(BACKEND_OPTIONS.keys()).index(st.session_state.godot_backend),
            horizontal=True,
            label_visibility='collapsed',
            key='_godot_backend_radio',
        )
        if backend != st.session_state.godot_backend:
            st.session_state.godot_backend = backend
            st.session_state.godot_url = BACKEND_OPTIONS[backend]
            st.session_state.godot_cache_buster = int(time.time())
            st.rerun()
    with cols[2]:
        # Server status — 只對本機有意義
        is_local = st.session_state.godot_url.startswith('http://localhost')
        if is_local:
            if _check_server('localhost', 8765):
                st.success('🟢 server up', icon=None)
            else:
                st.error('🔴 server down', icon=None)
        else:
            st.info('☁️ GitHub Pages', icon=None)
    with cols[3]:
        if st.button(
            '🔁 強制重載',
            use_container_width=True,
            help='重 export Godot 後若 iframe 還是舊版,點這個強制 fetch 新 PCK',
        ):
            st.session_state.godot_cache_buster = int(time.time())
            st.rerun()

# 進階設定(預設折疊)
with st.expander('⚙️ 設定 / 新分頁打開', expanded=False):
    c1, c2, c3 = st.columns([3, 1, 2])
    with c1:
        st.session_state.godot_url = st.text_input(
            'Godot web build URL',
            value=st.session_state.godot_url,
            help='可手動指定其他 URL(例如 Cloudflare Tunnel)',
        )
    with c2:
        st.session_state.godot_height = st.number_input(
            '高度 (px)',
            min_value=400,
            max_value=2000,
            value=st.session_state.godot_height,
            step=40,
        )
    with c3:
        st.link_button(
            '🔗 新分頁打開',
            url=st.session_state.godot_url,
            use_container_width=True,
            help='iframe 出問題時的備案',
        )


# ===========================================================================
# iframe 主體
# ===========================================================================

_is_local_backend = st.session_state.godot_url.startswith('http://localhost')
if _is_local_backend and not _check_server('localhost', 8765):
    st.warning(
        '**本機 Godot HTTP server 沒起來** — iframe 會 fail。\n\n'
        '到根目錄跑一下:\n\n'
        '```powershell\n'
        '.\\start_demo.ps1\n'
        '```\n\n'
        '或上方切到 **GitHub Pages** backend(雲端版,不用本機 server)'
    )

# 加 cache buster query 強迫 iframe 重新 fetch(避免瀏覽器 cache / service worker 抓舊 PCK)
_url = st.session_state.godot_url
_buster = st.session_state.godot_cache_buster
if '?' in _url:
    _iframe_url = f"{_url}&v={_buster}"
else:
    # 保證 path 以 / 結尾
    _root = _url if _url.endswith('/') else _url + '/'
    _iframe_url = f"{_root}?v={_buster}"

components.iframe(
    _iframe_url,
    height=int(st.session_state.godot_height),
    scrolling=False,
)
st.caption(f'iframe URL: `{_iframe_url}` — 重 export Godot 後按上面「🔁 強制重載」清 cache')


# ===========================================================================
# 頁底:Demo 操作說明 + 重 export 提醒
# ===========================================================================

st.markdown('---')

guide_cols = st.columns([2, 1])
with guide_cols[0]:
    st.markdown(
        '''
        ### 操作說明
        - **選關**:打開後出現關卡列表,點任一關開始
        - **遊戲中切換關卡**:右上「☰ 選關」浮動按鈕
        - **swipe / drag**:相鄰元素互換
        - **double-tap 道具**:直接啟動道具效果(TNT / Soda / 紙飛機 / 光球)
        '''
    )
with guide_cols[1]:
    st.markdown(
        '''
        ### 看到 Row Match 主選單?
        表示 `web/index.pck` 還是 yuehpo 原版 export。
        到 Godot Editor `Project → Export...` → Web → **確認 Main Scene 是
        `res://scenes/demo_main.tscn`** → 點 Export Project。

        重 export 後**不用重啟 Streamlit**,只要 Ctrl+Shift+R 重整本頁。
        '''
    )
