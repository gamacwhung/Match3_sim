# AI Game Art Lab — 兩週進度報告

> 依據 `pages/6_AI_Art_Lab.py` 及其背後的 `art_pipeline` 模組整理。  
> 撰寫日期：2026-06-26

---

## 一、專案定位與整體架構

- 建立 **「AI Game Art Lab」** 網頁工作台：左側生成美術、右側即時預覽可玩盤面。
- 核心流程：**選風格 → 選資產 → AI 生成 → 套用到遊戲 → 右側預覽即時更新**。
- 採 **雙欄寬版布局**（左 0.95 / 右 1.05），側邊欄預設收合。
- 透過 `./run.sh` 一鍵啟動 **Streamlit（8501）+ Godot Web（8765）**。
- 頁面入口：`http://localhost:8501/AI_Art_Lab`。

---

## 二、後端 AI 美術 Pipeline（`art_pipeline/`）

### 2.1 生成引擎

- 完成 **迭代式生成迴圈**：生成 → 程式化驗證（`postprocess`）→ Vision 評審（`critic`）→ 帶修正指示重生成。
- 每張圖最多迭代 N 次（預設 3，UI 可調 1–10）。
- 兩層評分門檻：style / function / element 各需 ≥ 7 分才算通過。
- 失敗時保留 **分數最高版本**，標記為 `needs_review`。
- 結果寫入 `generated_art/<run_name>/`，**不直接覆寫原版美術**。
- 已通過的 asset 重跑時自動跳過（`--force` / UI「強制重生」可覆寫）。

### 2.2 兩種生成模式

| 模式 | 說明 |
|------|------|
| **restyle（換皮）** | 以原 sprite 為結構參考，只改畫風，功能偏離小 |
| **theme_swap（主題換物件）** | 依 gameplay role 發明新主題物件，可不參考原圖 |

### 2.3 主題規劃器（`theme_planner.py`）

- LLM 將概念（如「糖果屋」）展開為每色元素物件指派：`Red=..., Grn=..., ...`。
- 支援手動指定（含 `=` 時不自動展開）。
- 展開結果寫入 `report.json` 的 `theme_plan` / `theme_expanded`。

### 2.4 Reference A 鏈式換皮

- restyle 模式可選 **先前 run 的 sprites** 作為 Reference A。
- 該 run 沒有的 asset 會跳過，**不 fallback 到官方圖**。
- 支援「先主題換物件 → 再換畫風」的工作流。

### 2.5 參考圖策略

- 預設 **關閉參考圖**（純文字風格生成）。
- 可勾選啟用：使用 `game_art_reference.png` 或上傳自訂參考圖。
- AI 會比對參考圖風格一致性（`reference_element_score`）。

### 2.6 統一 API 層（`art_pipeline/api.py`）

- 將 CLI 與 Web UI 收斂到同一套 `api.generate()` / `api.apply_run_to_game()`。
- 提供資產目錄、family 分類、run 列表、報告載入等 discovery API。
- 支援自訂 **生圖模型** / **評審模型**（留空用 Gemini 預設）。

### 2.7 資產清單（manifest）

涵蓋 **14 個 family**，共數十種遊戲 sprite：

- 基本元素、道具、紙箱、可移動障礙、鮭魚罐頭、水漥、繩索、泥巴、郵戳、游泳池、礦泉水櫃、飲料櫃、背景、其他。

### 2.8 Family 視覺分層（2026-06 新增）

讓 **同 family 更一致、跨 family 更易區分**，五色元素仍可辨識。適用 restyle 與 theme_swap。

| 機制 | 模組 | 說明 |
|------|------|------|
| 靜態規則 | `asset_roles.json` | `visual_categories` + 各 family 的 `anchor_asset` / `cohesion` |
| Run 級規劃 | `family_style_planner.py` | 有主題且 batch ≥2 時 LLM 產出 `family_style_plan` |
| Anchor 鏈 | `visual_guidance.py` + `pipeline.py` | 每 family 錨點圖（如 `Red`）先生，後續附圖對齊材質 |
| Critic 閉環 | `gemini_api.py` | `cohesion_score`（≥7）、`distinction_score`（≥6） |

- UI：主題換物件面板可「預覽 family 視覺」；結果分數顯示 `coh` / `dist`。
- 詳細設計見 [theme_swap_prompt.md](theme_swap_prompt.md) 的 Family 視覺分層章節。

---

## 三、套用與預覽機制（`art_pipeline/apply.py`）

### 3.1 三層套用目標

| 目標 | 路徑 | 用途 |
|------|------|------|
| **Component** | `match3_board_component/frontend/assets/` | Streamlit 離線盤面即時更新 |
| **Live** | `godot_demo/web/live_sprites/` | Godot Web 熱更新，免 re-export |
| **Project** | `godot_demo/resources/sprites/` | 寫入 Godot 專案（需重新 Export） |

- UI「套用到遊戲並預覽」走 **component + live**，不動 project sprites。
- 套用前自動備份原版到 `sprites_original_backup/`（只備份一次）。
- Live sprite 自動縮圖（最大邊 512px）避免 WASM 記憶體問題。

### 3.2 Godot 即時預覽

- iframe 嵌入 `localhost:8765`，直向比例 720×1280。
- 套用後 URL 帶 `?live=1&rev=<revision>` 載入 live_sprites。
- 連線狀態指示燈（綠/橙）、重新載入、新分頁開啟。
- 未啟動 Godot 時顯示 `./run.sh` 啟動指引。

### 3.3 離線快速預覽（fallback）

- Godot 未啟動時，展開 **Streamlit 可玩盤面**（`match3_board` component）。
- 支援點擊交換、道具啟動、新盤面、打亂。
- 套用美術後透過 `art_asset_version` 觸發 component 重載。

---

## 四、網頁 UI 功能區塊（`6_AI_Art_Lab.py`）

### 4.1 頁首動態美術牆

- 從 `web_static/art_lab_header_wall/sprites/` 讀取遊戲 sprite。
- 無限水平滾動動畫（90 秒一輪），雙 strip 無縫循環。
- 漸層遮罩 + 標題疊加：「AI Game Art Lab — 一鍵打造你的專屬遊戲美術」。
- 支援 `prefers-reduced-motion` 關閉動畫。
- 縮圖 base64 內嵌 + `@st.cache_data` 快取。

### 4.2 STYLE — 風格工作室

- **5 組預設風格 chip**：像素復古、水彩柔和、霓虹賽博、黏土 3D、日式平面。
- 自訂風格描述（checkbox 切換文字區）。
- 可選參考圖風格（預設關閉，可上傳 PNG/JPG/WebP）。
- 未設定 API 金鑰時顯示警告。

### 4.3 MODE — 生成模式面板

- Radio 切換 restyle / theme_swap。
- restyle：Reference A 下拉選先前 run 或遊戲預設。
- theme_swap：主題概念輸入、LLM 自動展開、預覽展開結果、手動 `Red=...` 偵測。

### 4.4 ASSETS — 資產選取器

- 依 family 分類切換（橫向 radio）。
- 批次操作：選此分類 / 選全部 / 清除。
- 關鍵字搜尋過濾。
- 4 欄網格：縮圖 + checkbox，預設勾選 5 色基本元素。
- restyle 模式下縮圖來自 Reference A run。

### 4.5 ACTIONS — 操作列

- **生成美術**：進度條 + 逐張狀態（通過/待審/失敗 + 評分）。
- **套用到遊戲並預覽**：有結果才可按，套用進度條。

### 4.6 RESULTS — 結果面板

- 篩選：全部 / 通過 / 待審 / 失敗（含計數）。
- 4 欄縮圖網格，顯示狀態圖示與 style/func/ref 分數。
- 顯示主題資訊或 Reference A 來源。

### 4.7 進階設定（expander）

- 版本名稱（自動建議 `lab_<style>_<timestamp>`）。
- 每張最多迭代次數、強制重生、生圖/評審模型覆寫。
- 載入既有版本（從 `generated_art/` 還原結果到 UI）。
- **還原遊戲預設美術**（`pixar_cartoon` / `candy_cartoon` 打包版）。

### 4.8 LIVE PREVIEW — 右側遊戲面板

- Before/After 對比條：5 色基本元素原版 → 新版。
- Godot iframe 嵌入（獨立 `@st.fragment`，重載不影響左側）。
- 離線盤面 expander（Godot 未啟動時可用）。

---

## 五、效能與 UX 優化

- **`@st.fragment`** 拆分左右面板：Godot 重載 / 盤面操作不觸發左側大量預覽圖重繪。
- **`@st.cache_data`** 快取資產目錄、縮圖 map、header wall 圖片。
- iframe `ResizeObserver` 自動調整 Streamlit frame 高度。
- Cache busting：`art_godot_buster` + `revision.txt` 避免瀏覽器快取舊美術。
- 自訂 CSS：section label、狀態燈、before/after 條、header 動畫。

---

## 六、CLI 工具鏈（與 UI 共用 pipeline）

| 腳本 | 用途 |
|------|------|
| `scripts/ai_art_gen.py` | 通用美術生成 CLI（list/generate/apply/restore/dry-run） |
| `scripts/test_theme_elements.py` | 批次測 8 組預設主題 × 5 色元素 |
| `scripts/import_themes.py` | 主題匯入 |
| `scripts/export_godot_web.sh` | Godot Web Export |

---

## 七、基礎設施與穩定性修正（git 紀錄摘要）

- 預設美術切換為 **candy_cartoon** 主題。
- 修復 `live_sprites` 被 export 清掉、hot loading 時序、sprite 未及時渲染等問題。
- `.gitignore` 擴充：`generated_art/`、`*.zip`、runtime artifacts。
- Godot booth 模式：待機畫面、attract mode、換風格下拉重載、直式自適應盤面。
- ObjectivesBar UI 改用 generated live sprite 驗證套用路徑。

---

## 八、目前能力邊界（已知限制）

- Godot 預覽預設用 **pck 打包美術**；按「套用到遊戲」後 iframe 才帶 `live=1` 載入 live_sprites。
- 寫入 `godot_demo/resources/sprites/` 後仍需 **Godot Editor 重新 Export** 才會進 index.pck。
- 離線 Streamlit 盤面與 Godot 正式版渲染 **略有差異**，僅供快速確認外觀。
- 需設定 `GOOGLE_API_KEY`（或 Vertex AI）才能實際生成。

---

## 九、成果摘要

| 維度 | 完成度 |
|------|--------|
| AI 生成 pipeline（雙模式 + 迭代驗證） | ✅ 完成 |
| 主題 LLM 展開 | ✅ 完成（UI + CLI） |
| Reference A 鏈式換皮 | ✅ 完成 |
| 網頁工作台（風格/資產/生成/結果） | ✅ 完成 |
| 三層套用（component / live / project） | ✅ 完成 |
| Godot 即時預覽 + 離線 fallback | ✅ 完成 |
| 版本管理（載入/還原/備份） | ✅ 完成 |
| CLI 工具鏈 | ✅ 完成 |
| 頁首動態美術牆 | ✅ 完成 |

---

## 十、結語

整體而言，這兩週已打通 **「從文字描述到可玩遊戲預覽」** 的完整閉環：企劃/美術可在瀏覽器選風格、勾資產、一鍵生成，並在右側 Godot 或 Streamlit 盤面即時驗收，無需手動替換 sprite 或重新打包。
