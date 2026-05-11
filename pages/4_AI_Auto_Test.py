"""
AI 自動測試 — Streamlit 頁面

讓 demo 觀眾看到「AI 對同一關卡跑 N 次,出真實難度報表」的流程。
這頁是 Google Cloud Day 故事線中的「自動 QA」段落。

對應的 CLI:
  python scripts/ai_auto_test.py LEVEL_JSON --runs N
"""

import sys
import pathlib
import time

import streamlit as st
import pandas as pd

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ai_auto_test import run_batch, run_levels


# ===========================================================================
# Helpers
# ===========================================================================

def _list_level_files() -> dict[str, list[str]]:
    """掃出可玩的關卡 JSON,依資料夾分類。"""
    out: dict[str, list[str]] = {}
    for folder in ['levels', 'godot_demo/levels']:
        p = _PROJECT_ROOT / folder
        if not p.exists():
            continue
        files = sorted(p.glob('*.json'))
        if files:
            out[folder] = [str(f) for f in files]
    return out


def _format_short_name(path: str) -> str:
    return pathlib.Path(path).stem


# ===========================================================================
# UI
# ===========================================================================

st.set_page_config(page_title='AI 自動測試', page_icon='🤖', layout='wide')

st.title('🤖 AI 自動測試 — 一鍵跑出關卡難度報表')

st.markdown(
    '''
    這頁示範 **AI 取代人工 QA**:一個 score-based heuristic agent(仿 `match3_AI` 策略)
    對任一關卡跑 N 次,出真實統計 — 勝率、平均步數、卡關率。
    
    對企劃的用法:
    - 設計完關卡 → 跑 50 次 → 看勝率是否落在預期(例:第 10 關期望 80~95%)
    - 勝率太低 → 關卡太硬;勝率 100% → 太簡單,少給 1-2 步看看
    '''
)

# === Sidebar 設定 ===
with st.sidebar:
    st.header('參數')
    
    level_groups = _list_level_files()
    if not level_groups:
        st.error('找不到關卡 JSON。請確認 `levels/` 或 `godot_demo/levels/` 內有檔案。')
        st.stop()
    
    folder = st.selectbox('關卡資料夾', list(level_groups.keys()))
    level_files = level_groups[folder]
    
    mode = st.radio(
        '模式',
        ['單關 × N 次', '批次 × 多關'],
        help='單關 = 同一關跑多次看穩定度;批次 = 多關各跑幾次看整體難度曲線',
    )
    
    n_runs = st.slider('跑幾次', min_value=1, max_value=200, value=20, step=5)
    
    use_seed = st.checkbox('固定 base seed(可重現)', value=False)
    base_seed = None
    if use_seed:
        base_seed = st.number_input('Base seed', value=42, step=1)


# === 主區塊 ===
if mode == '單關 × N 次':
    level_path = st.selectbox(
        '選關卡',
        level_files,
        format_func=_format_short_name,
    )
    
    if st.button('🚀 開始跑', type='primary', use_container_width=True):
        progress = st.progress(0.0, text='Starting...')
        t0 = time.perf_counter()
        
        # 用 mutable dict 在 callback 內累計(避免 closure rebind 問題)
        _state = {'wins': 0, 'moves': []}
        
        def cb(i: int, total: int, result):
            _state['wins'] += int(result.won)
            _state['moves'].append(result.moves_used)
            cur_win_rate = _state['wins'] / i * 100
            avg_moves = sum(_state['moves']) / len(_state['moves'])
            progress.progress(
                i / total,
                text=f'{i}/{total} | win rate {cur_win_rate:.0f}% | avg moves {avg_moves:.1f}',
            )
        
        report = run_batch(
            level_path,
            n_runs=int(n_runs),
            base_seed=int(base_seed) if base_seed is not None else None,
            progress_callback=cb,
        )
        elapsed = time.perf_counter() - t0
        progress.progress(1.0, text=f'Done in {elapsed:.1f}s')
        
        # === 出結果 ===
        st.success(f'完成!共跑 {report.n_runs} 場,耗時 {elapsed:.1f} 秒')
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric('勝率', f'{report.win_rate*100:.1f}%', f'{report.n_wins} / {report.n_runs}')
        col2.metric('平均使用步數', f'{report.avg_moves_used:.1f}',
                    f'max {report.results[0].max_moves}')
        col3.metric('平均剩餘步數', f'{report.avg_moves_left:.1f}')
        col4.metric('平均剩餘目標', f'{report.avg_obstacles_left:.1f}')
        
        # === 步數分佈 ===
        st.subheader('使用步數分佈')
        moves_df = pd.DataFrame({'moves': report.moves_distribution})
        st.bar_chart(moves_df['moves'].value_counts().sort_index())
        
        # === 每場結果 ===
        with st.expander('每場明細', expanded=False):
            rows = []
            for i, r in enumerate(report.results):
                rows.append({
                    '場次': i + 1,
                    '結果': '✅ WIN' if r.won else '❌ LOSS',
                    '使用步數': r.moves_used,
                    '剩餘步數': r.moves_left,
                    '剩餘目標': r.obstacles_left,
                    '無動作次數': r.no_action_count,
                    '耗時(ms)': f'{r.elapsed_ms:.0f}',
                    'seed': r.seed,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        
        # === 設計建議 ===
        st.subheader('設計建議(自動產生)')
        wr = report.win_rate * 100
        if wr >= 95:
            st.info(f'勝率 {wr:.0f}% → 過於簡單。建議:減少 1-2 步,或增加目標障礙物數')
        elif wr >= 70:
            st.success(f'勝率 {wr:.0f}% → 落在常見 商業關卡 設計區間,難度合理')
        elif wr >= 30:
            st.warning(f'勝率 {wr:.0f}% → 偏難。建議:多 2-3 步,或減少目標數')
        else:
            st.error(f'勝率 {wr:.0f}% → 太硬,玩家可能直接放棄。建議重新檢視關卡')


else:  # 批次 × 多關
    st.markdown('### 批次測試')
    
    n_levels = st.slider('一次跑前 N 關', min_value=5, max_value=len(level_files), 
                          value=min(20, len(level_files)), step=5)
    
    if st.button('🚀 批次開跑', type='primary', use_container_width=True):
        selected = level_files[:n_levels]
        progress = st.progress(0.0, text='Starting batch...')
        
        def cb(i, total, lf, report):
            progress.progress(
                i / total,
                text=f'[{i}/{total}] {_format_short_name(lf)} → win {report.win_rate*100:.0f}%',
            )
        
        t0 = time.perf_counter()
        reports = run_levels(
            selected,
            n_runs_per_level=int(n_runs),
            base_seed=int(base_seed) if base_seed is not None else None,
            progress_callback=cb,
        )
        elapsed = time.perf_counter() - t0
        progress.progress(1.0, text=f'Done in {elapsed:.1f}s')
        
        st.success(f'完成 {len(reports)} 關 × {n_runs} 次,共耗時 {elapsed:.1f} 秒')
        
        rows = []
        for name, r in reports.items():
            rows.append({
                '關卡': name,
                '勝率': f'{r.win_rate*100:.0f}%',
                '勝場': r.n_wins,
                '平均步數': f'{r.avg_moves_used:.1f}',
                '平均剩餘步數': f'{r.avg_moves_left:.1f}',
                '平均剩餘目標': f'{r.avg_obstacles_left:.1f}',
                '平均耗時(ms)': f'{r.avg_elapsed_ms:.0f}',
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        
        # 勝率走勢圖
        st.subheader('關卡難度曲線(勝率)')
        chart_df = pd.DataFrame({
            'level': [name for name in reports.keys()],
            'win_rate': [r.win_rate * 100 for r in reports.values()],
        }).set_index('level')
        st.line_chart(chart_df)


st.markdown('---')
with st.expander('AI 策略說明', expanded=False):
    st.markdown(
        '''
        **AI Player** 使用 score-based heuristic 策略(`scripts/ai_player.py`),仿 `match3_AI`:
        
        1. **窮舉所有可 swap 的相鄰格** → 模擬 swap → 計算消除分(目標障礙 +20、一般障礙 +5、元素 +1)
        2. **加道具合成獎勵**:5+ 連 +15、L/T +8、4 連 +5、2x2 +6
        3. **加道具直接活化評分**:每個 powerup 估爆炸範圍能打到的目標數
        4. **殘局 / 斬殺判定**:場上目標 ≤ 10 → 道具不扣成本,放手用
        5. 取最高分動作執行
        
        這策略**不是 RL,也不需要訓練資料** — 純規則 + 模擬,任何關卡都能直接跑。
        對「快速 QA / 平衡測試」場景非常合適,因為:
        - 一場 < 100ms,50 場 < 5 秒
        - 完全 deterministic(可固定 seed 重現)
        - 不依賴遊戲畫面/截圖,直接吃 board state
        '''
    )
