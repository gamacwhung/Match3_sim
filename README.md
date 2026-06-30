# Match3_sim — AI-Native 三消遊戲開發 Pipeline

> 為 Google Cloud Day demo 準備的全套示範。三大模組(生成 / 模擬 / 自動測試)串成 AI-Native 遊戲開發 Pipeline。

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  AI Level Generator  │ ──▶ │  Match3 Simulator    │ ──▶ │  AI Auto-Test Agent  │
│  (LLM,5~10 秒生關卡) │     │  (Streamlit + Godot) │     │  (Score-based,50 場) │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
                                                                       │
                                          ◀──── 難度報表回饋(勝率/卡關點) ────┘
```

---

## 一鍵 Demo

```powershell
# Windows PowerShell
.\start_demo.ps1
```

三個瀏覽器分頁:

| URL | 內容 |
|---|---|
| http://localhost:8501/ | Streamlit 主頁(Demo 模式 + AI 關卡生成器) |
| http://localhost:8501/AI_Auto_Test | **AI 自動測試報表**(Demo 賣點) |
| http://localhost:8765/ | Godot 美術版(需先 Web Export,見下文) |

關閉:`.\start_demo.ps1 -Stop`

詳細 demo 流程看 **[`DEMO_SCRIPT.md`](DEMO_SCRIPT.md)** 。

---

## 三大模組

### 1. AI 關卡生成器 — 用 LLM 出關卡

- **頁面**:`pages/4_Level_Generator.py`(`localhost:8501/Level_Generator`)
- **支援模型**:Claude Sonnet 4 / Opus 4 / GPT-4o / GPT-5(Vertex AI 也可接)
- **輸入**:自然語言 + 參數(行列、難度、障礙物選擇)
- **輸出**:符合 `levels/*.json` 格式的關卡 JSON,直接可玩
- **成本**:Claude Sonnet ~$0.01 / 關,GPT-4o-mini ~$0.001 / 關

### 2. Match3 模擬器 — 兩種視覺,同一份 Spec

#### 2.1 Streamlit 版(開發者 / 企劃用)
- **頁面**:`streamlit_app.py` + `pages/`
- **核心**:`match_engine.py` + `match3_env.py` + `board.py`
- **特點**:JS Custom Component(`match3_board_component/`),熱重載
- **適用**:內部 design / debug / data view

#### 2.2 Godot 版(玩家用)
- **資料夾**:`godot_demo/`(Godot 4.6 專案)
- **特點**:粒子特效 / shader / tween,M8 美術全套
- **吃同一份**:`godot_demo/levels/*.json`(跟 `levels/` 同格式)
- **Web Export**:見 `godot_demo/README_DEMO.md`

### 3. AI 自動測試 — 取代人工 QA

- **頁面**:`pages/3_AI_Auto_Test.py`(`localhost:8501/AI_Auto_Test`)
- **CLI**:`python scripts/ai_auto_test.py LEVEL_JSON --runs 50`
- **核心**:`scripts/ai_player.py`(score-based heuristic,仿 `../match3_AI` 策略)
- **效能**:< 100ms / 場,50 場 < 10 秒
- **輸出**:勝率、平均步數、剩餘目標、步數分佈、難度建議

---

## 目錄結構

```
Match3_sim/
├── README.md                    # 你正在看的這份
├── DEMO_SCRIPT.md               # Google Cloud Day demo 講稿(3-5 分鐘)
├── start_demo.ps1               # 一鍵啟動所有 server
│
├── streamlit_app.py             # Streamlit 主入口
├── pages/                       # Streamlit 頁面
│   ├── 2_Level_Generator.py     # AI 關卡生成
│   ├── 3_Demo.py                # Demo 模式(觀眾用)
│   └── 4_AI_Auto_Test.py        # AI 自動測試報表
│
├── match_engine.py              # 核心 — match / resolve / activate
├── match3_env.py                # Env API(step / reset / goals)
├── board.py                     # 盤面(多層 Cell + gravity + fill)
├── tile_defs.py                 # Tile 定義 + 規則表
├── level_generator.py           # AI 關卡生成 backend
│
├── match3_board_component/      # Streamlit JS custom component
├── levels/                      # 內部用關卡(level_01..06.json)
├── 關卡格式資料/                  # 官方 100 關原始 JSON
│
├── godot_demo/                  # Godot 4.6 demo 專案
│   ├── README_DEMO.md           # Godot 安裝 / export 教學
│   ├── scripts/                 # GDScript
│   ├── resources/sprites/       # M8 美術
│   ├── levels/                  # 已轉好的關卡(Level_001..100.json)
│   └── web/                     # Web export 輸出(gitignore)
│
├── scripts/                     # CLI 工具
│   ├── ai_player.py             # Score-based AI agent
│   ├── ai_auto_test.py          # 跑批次 + 統計
│   ├── ai_art_gen.py            # AI 美術生成 CLI
│   ├── test_theme_elements.py   # 批次測試多主題元素生成
│   └── import_official_to_godot.py  # 官方 → 內部格式轉換
│
├── tests/                       # pytest
└── requirements.txt
```

---

## 首次安裝

```powershell
# 1. Python deps
pip install -r requirements.txt

# 2. LLM API key
# 編輯 config.py(已 gitignore),設定 ANTHROPIC_API_KEY / OPENAI_API_KEY
# 或用環境變數

# 3. (選用)Godot 美術版 — 詳見 godot_demo/README_DEMO.md
#    - 安裝 Godot 4.6 + Web Export Templates
#    - 用 Editor 開 godot_demo/ → Export → Web → 輸出到 godot_demo/web/
```

---

## CLI 範例

### AI 遊戲關卡生成
```powershell
# AI 自動測試:單關 50 次
python scripts/ai_auto_test.py levels/level_01.json --runs 50

# AI 自動測試:跑前 20 關官方關卡,各 10 次,出 JSON 報告
python scripts/ai_auto_test.py --batch godot_demo/levels --runs 10 --out ai_test_reports/batch_20.json

# 轉換官方關卡格式
python scripts/import_official_to_godot.py
```

### AI 遊戲美術生成

需設定 `GOOGLE_API_KEY`(或 Vertex AI) — 見 `config.py` / `.streamlit/secrets.toml`。

#### 兩種生成模式

| 模式 | CLI | 說明 |
|------|-----|------|
| **restyle**(預設) | `--mode restyle` | 保留原 sprite 物件,只換畫風 |
| **theme-swap** | `--mode theme-swap` | 依 gameplay role 發明**新主題物件**,不參考原圖 |

#### `ai_art_gen.py` — 通用美術生成

```bash
# 列出 asset / role class
python scripts/ai_art_gen.py list-assets
python scripts/ai_art_gen.py list-roles

# restyle — 保留原物件,只換風格
python scripts/ai_art_gen.py generate \
  --style "像素風格 pixel art" \
  --run my_run \
  --family elements

# theme-swap — 手動寫每色物件(不經 LLM 展開)
python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "2D Disney cartoon style" \
  --theme "Red=red gumdrop, Grn=green candy cane, Blu=blue lollipop, Yel=yellow lemon drop, Pur=purple jelly" \
  --run candy_manual \
  --family elements \
  --no-reference-image \
  --no-expand-theme

# theme-swap — 只給主題概念,LLM 自動想每個 element 放什麼
python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "2D Disney cartoon style" \
  --theme "糖果屋" \
  --run candy_house \
  --family elements \
  --no-reference-image

python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "2D Disney cartoon style" \
  --theme "糖果屋" \
  --run candy_house \
  --family elements \
  --no-reference-image

# 先 dry-run 看 prompt / 展開結果
python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "2D Disney cartoon style" \
  --theme "糖果屋" \
  --run candy_house \
  --family elements \
  --dry-run

# 套用 / 還原
python scripts/ai_art_gen.py apply --run candy_house
python scripts/ai_art_gen.py restore
```

`ai_art_gen.py generate` 常用選項:

| 選項 | 說明 |
|------|------|
| `--style TEXT` | 畫風描述(必填) |
| `--run NAME` | 輸出目錄 `generated_art/<NAME>/` |
| `--mode restyle\|theme-swap` | 生成模式(預設 restyle) |
| `--theme TEXT` | theme-swap 主題方向或概念(如「糖果屋」) |
| `--family FAMILY` | 只生某個 family(`elements`, `powerups`…) |
| `--assets Red,Grn,...` | 只生指定 asset |
| `--no-reference-image` | 不用參考圖(預設會用 `game_art_reference.png`) |
| `--style-image PATH` | 自訂參考圖(需未加 `--no-reference-image`) |
| `--expand-theme` | 強制用 LLM 展開 `--theme` |
| `--no-expand-theme` | 不展開,`--theme` 原樣使用 |
| `--no-refine-style` | 不精煉 `--style`（預設會 LLM 展開成鎖定畫風規格） |
| `--dry-run` | 只印 prompt,不呼叫生圖 API |
| `--force` | 重生已 pass 的 asset |

**主題展開規則**: `--theme` 若為概念型文字(如「糖果屋」,不含 `Red=`),
會自動呼叫 LLM 展開成 `Red=..., Grn=..., ...`,寫入 `report.json` 的 `theme_plan`。

**畫風精煉規則**: `--style` 預設會經 LLM 精煉成鎖定的 `style_brief`（寫入 `report.json` 的 `style_plan` / `style_resolved`），整批 asset 共用；`--no-refine-style` 可關閉。

詳細 prompt 組裝與四層控制邏輯見 [docs/design/theme_swap_prompt.md](docs/design/theme_swap_prompt.md)。

**Family 視覺分層**：同 family 內以 anchor 圖鏈式對齊風格；跨 family 以 `visual_categories` 規則與 critic `cohesion`/`distinction` 分數把關（預設開啟，見 `art_pipeline/visual_guidance.py`）。

#### `test_theme_elements.py` — 批次測 5 色元素

只生成 `Red, Grn, Blu, Yel, Pur`,固定走 **theme-swap**,**預設不用參考圖**。

**A. 跑預設主題 preset**

```bash
# 列出預設主題
python scripts/test_theme_elements.py --list

# 跑全部(8 組 × 5 張 ≈ 40 張)
python scripts/test_theme_elements.py

# 只跑指定主題
python scripts/test_theme_elements.py --themes ocean,candy

# 強制重生
python scripts/test_theme_elements.py --themes ocean --force
```

預設 slug:`ocean`, `forest`, `space`, `dessert`, `farm`, `winter`, `steampunk`, `candy`

**B. 自訂 style + 主題概念(推薦)**

```bash
# LLM 自動想每個 element 要放什麼物件
python scripts/test_theme_elements.py \
  --style "2D Disney cartoon style" \
  --theme "糖果屋" \
  --run candy_house

# 先 dry-run 看展開結果與 prompt
python scripts/test_theme_elements.py \
  --style "2D Disney cartoon style" \
  --theme "糖果屋" \
  --run candy_house \
  --dry-run
```

**C. 手動指定每色物件**

```bash
python scripts/test_theme_elements.py \
  --style "2D Disney cartoon style" \
  --theme "Red=red gumdrop, Grn=green candy cane, Blu=blue lollipop, Yel=yellow lemon drop, Pur=purple jelly" \
  --run candy_manual \
  --no-expand-theme
```

`test_theme_elements.py` 常用選項:

| 選項 | 說明 |
|------|------|
| `--list` | 列出預設主題 |
| `--themes ocean,candy` | 跑 preset slug(與 `--style/--theme` 互斥) |
| `--style` + `--theme` | 自訂模式(需同時提供) |
| `--run SLUG` | 自訂輸出名(預設用 theme 文字) |
| `--expand-theme` | 強制 LLM 展開 |
| `--no-expand-theme` | 不展開(或 theme 已含 `Red=...`) |
| `--dry-run` | 只印 prompt |
| `--force` | 重生 |
| `--use-reference-image` | 啟用參考圖(預設關閉) |
| `--style-image PATH` | 自訂參考圖 |

產出目錄:

| 模式 | 路徑 |
|------|------|
| 無參考圖(預設) | `generated_art/theme_test_noref_<slug>/sprites/` |
| 有參考圖 | `generated_art/theme_test_<slug>/sprites/` |
| `ai_art_gen.py` | `generated_art/<run>/sprites/` |

展開結果範例(`report.json`):

```json
{
  "theme": "糖果屋",
  "theme_expanded": "Red=red gingerbread tile, Grn=green candy cane, ...",
  "theme_plan": {
    "concept": "糖果屋",
    "summary": "A whimsical candy-house match set ...",
    "assignments": { "Red": "...", "Grn": "...", ... }
  }
}
```

#### 網頁版 AI Art Lab

`localhost:8501/AI_Art_Lab` — 選風格、勾選元素、生成並套用到右側 Godot 預覽。

- **使用參考圖風格**:預設**關閉**;勾選後才用 `game_art_reference.png` 或上傳圖
- theme-swap / LLM 主題展開:目前以 CLI 為主

---

## 對 Google Cloud Day 的故事線

**問題**:三消遊戲(Candy Crush 級別)的關卡 pipeline 一週一關 — 企劃 1 天設、美術 2 天作、QA 玩 3 天驗。

**解法**:這套 pipeline 把 1 週壓到 1 分鐘:

1. **生** — LLM 看 spec 文件 + 美術風格,15 秒出符合格式的 JSON 關卡
2. **玩** — Python 引擎 + Godot 視覺,**同份 JSON 兩種輸出**(內部工具 / 玩家用)
3. **測** — AI Agent 跑 50 次,出真實勝率 + 步數分佈,**取代人工 QA**

三個都跑在 **Google Cloud**(Vertex AI 接 LLM、Cloud Run 跑 Streamlit + Godot Web、Cloud Storage 存資產)。

**成本**:Claude Sonnet $0.01/關,跑 100 關 $1。

詳細看 `DEMO_SCRIPT.md`。

---

## 相關專案

- **`../match3_AI`** — 同團隊另一支 AI agent,做真實遊戲畫面辨識(YOLO)+ 自動操作。本專案的 `scripts/ai_player.py` **策略仿自這個專案的核心思路**(score-based heuristic),但**不依賴 YOLO**,因為我們有完整 board state。
