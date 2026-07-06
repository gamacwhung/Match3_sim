# AI 遊戲美術生成 — 兩週績效週報

> 期間：2026-06-19 ~ 2026-07-03（兩週）
> 負責人：tklovln
> 主題：AI Game Art Generation Pipeline & Art Lab 工作台

---

## 一句話總結

獨立打通「**一句文字風格描述 → 一鍵生成整套遊戲美術 → 遊戲內即時驗收**」的完整閉環，把過去需要美術外包、逐張手繪、手動替換 sprite 的流程，壓縮成瀏覽器上分鐘級的自助操作。

---

## 一、關鍵成果與商業影響

| 成果 | 產出 | 對團隊 / 產品的價值 |
|------|------|----------------------|
| **AI 美術生成 pipeline（雙模式 + 迭代自審）** | 生成→程式化驗證→Vision 評審→帶修正重生的閉環 | 美術產能不再受限於外包排期；一套風格可覆蓋全部 **63 個 sprite / 12 個 family** |
| **Art Lab 網頁工作台** | 選風格→勾資產→生成→套用→右側遊戲即時預覽 | 企劃 / 美術「零程式碼」即可換整套遊戲皮膚，換風格 demo 從數天縮到分鐘級 |
| **主題換物件（theme_swap）+ LLM 主題展開** | 輸入「糖果屋」自動展開為每色元素的新物件 | 一個玩法骨架可快速衍生多個 IP / 主題版本，直接支撐商務提案與展場 demo |
| **Family 視覺分層** | anchor 錨點鏈 + cohesion/distinction 評分閉環 | 解決「AI 生圖各自為政」的一致性痛點，成品達到可直接進遊戲的品質門檻 |
| **三層套用 + Godot 熱更新預覽** | component / live / project 三目標 + iframe 即時預覽 | 免 re-export、免手動替換檔案，所見即所得驗收 |

**量化規模**：兩週 25 個 commit、`art_pipeline` 核心模組淨增約 **+5,400 / −1,100 行**、新增 6 個核心模組、累積 **13 個生成 run** 驗證流程可重複可回歸。

---

## 二、本期完成的重點工作

### 1. 生成引擎穩健化（robustness）
- 每張圖跑迭代迴圈，最多 N 次（UI 可調 1–10），**失敗保留分數最高版本並標記 `needs_review`**，不會產出空結果。
- 雙層把關：`postprocess`（去背 / 尺寸等客觀檢查）+ `critic`（style / function / element 語意評分，需 ≥7 分）。
- 結果寫入 staging 目錄，**絕不覆寫原圖**；已通過的資產重跑自動跳過，可 `--force` 覆寫。

### 2. 兩種生成模式，覆蓋不同商業場景
- **restyle（換皮）**：保留原結構只換畫風，功能不走樣。
- **theme_swap（主題換物件）**：依 gameplay role 發明全新主題物件，支援 LLM 自動展開主題概念。
- 支援 **Reference A 鏈式換皮**：先主題換物件、再套畫風的多段工作流。

### 3. Family 視覺分層（本期新增，最具技術含量）
- 用 `asset_roles.json` 定義視覺類別與各 family 的錨點；`family_style_planner` 在有主題且批量 ≥2 時用 LLM 產出 per-family 視覺語言。
- **anchor 鏈**：每個 family 先生錨點圖，後續同族附錨點圖對齊材質。
- critic 閉環新增 `cohesion_score`（≥7）與 `distinction_score`（≥6），量化「同族一致、跨族可辨」。

### 4. 風格精煉 + 可重現性
- 新增 `style_planner`：把模糊的風格描述（如「復古一點」）用 LLM 精煉成鎖定的畫風規格並快取。
- 新增 `run_config` 快照：把每次 run 的完整參數寫進 `report.json`，任何結果都可**追溯與重現**。
- 新增整批 **sprite contact sheet**，一張圖檢視整組風格一致性，加速人工驗收。

### 5. 工作台與體驗
- Art Lab 頁面：風格 chip、資產分類選取器、生成進度與逐張評分、結果篩選（通過 / 待審 / 失敗）。
- 頁首動態美術牆、`@st.fragment` 拆分左右面板、`@st.cache_data` 快取，重載不卡頓。
- CLI 與 Web UI 收斂到同一套 `api.generate()` / `api.apply_run_to_game()`，一份邏輯兩處共用。

---

## 三、解決的關鍵問題

- **一致性**：AI 逐張生圖風格漂移 → 以 anchor 鏈 + cohesion 評分收斂到可用品質。
- **穩定性**：修復 `live_sprites` 被 export 清掉、hot-loading 時序、sprite 未及時渲染、載入崩潰等問題，確保展場 demo 可靠運行。
- **可維護性**：去除 CLI / UI 重複邏輯，統一 API 層，降低後續迭代成本。

---

## 四、下一步（Next）

- 擴大 theme_swap 主題庫與批次測試覆蓋，沉澱可交付的風格 preset。
- 針對 `needs_review` 樣本分析評審門檻，進一步降低人工驗收比例。
- 將 project sprites 寫入 + Godot 自動 re-export 串成一鍵發佈，補上目前最後的人工環節。

---

## 五、能力邊界（誠實揭露）

- 寫入 `godot_demo/resources/sprites/` 後仍需 Godot Editor 重新 Export 才進正式包。
- 離線 Streamlit 盤面與 Godot 正式渲染略有差異，僅供快速確認。
- 需設定 `GOOGLE_API_KEY`（或 Vertex AI）才能實際生成。
