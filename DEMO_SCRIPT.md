# Match3 模擬器 — Google Cloud Day Demo 講稿

**目標觀眾**:Google Marketing 同事(非工程背景)
**時長**:3-5 分鐘
**核心定位**:**AI-Native 遊戲開發 Pipeline** — 對齊 Google Cloud Day 的「AI 生程式應用 / Solution」主題

**三大模組(各自獨立、串起來就是 pipeline)**

| 模組 | Demo 對應頁面 | 對 marketing/業務的 message |
|---|---|---|
| AI 關卡生成器 | `localhost:8501/Level_Generator` | LLM 替企劃出關卡,30 分 → 30 秒 |
| 模擬器(Streamlit + Godot) | `localhost:8501/Demo` + `localhost:8765/` | 同份 Spec 兩種視覺,即時試玩 |
| AI 自動測試 | `localhost:8501/AI_Auto_Test` | AI 跑 50 次量化難度,取代人工 QA |

**Demo 前一鍵啟動**:`.\start_demo.ps1`(根目錄)

---

## 開場 30 秒 — 建立場景

> 「大家好。三消遊戲(像 Candy Crush)的關卡設計師,現在的工作流程是這樣:
> 設計師花一天設計一個關卡 → 美術做圖 → QA 玩 100 場確認難度 → 太簡單就退回重做。
> **一個關卡跑完整個 pipeline 要 1 週**。
> 我們做的這個工具,是把這 1 週壓縮成 1 分鐘 — 而且每一塊都跑在 Google Cloud 上。」

(打開 `http://localhost:8501`,看到首頁兩個大按鈕)

---

## 段落 1(60 秒)— Demo 模式:這就是玩家會看到的

按下「**🎬 進入 Demo 模式**」 → 看到漂亮 intro 頁

> 「這是我們的 Demo 模式。背後是我們設計的核心引擎,**包括 100 個官方標準關卡 + 我們自己生成的關卡**,
> 都能直接在這裡試玩。」

按下「**▶ 開始試玩**」 → 載入紙箱關 #1

> 「這是第 1 關 — 紙箱關。要消除整片紙箱才能通關。」
> (示範:點兩個鄰近元素 → 三連 → 紙箱被打破)
> 「**注意這些紙箱**:它們是我們專案的美術圖,直接餵給 AI 看圖學會,讓 AI 知道我們的視覺風格。」

(示範:玩到通關 → 自動跳出「下一關」按鈕)
按下「**下一關 →**」 → 載入第 2 關

> 「8 個精選關卡循環,**通關後一鍵下一關**。
> 重點不是這個 demo 本身有多難,是『你看到的整個盤面、所有障礙物、所有規則,都是我們的引擎模擬的』。」

---

## 段落 2(80 秒)— AI 關卡生成器:5 秒生一個

從 Demo 頁的「**進階模式**」展開 → 切到 **Level Generator** 頁
(或者乾脆從 sidebar 切過去)

> 「現在切到 AI 關卡生成器。
> **左邊有一些參數**:行數、列數、難度、顏色數、要哪些障礙物 — 都可以勾選『隨機』,讓 AI 自己決定。
> 然後在這裡」(指 Chat 輸入框)
> 「**用自然語言告訴 AI 你要什麼**。」

範例輸入:
> ```
> 生成一個有 6 個紙箱 + 2 個水漥的中等難度關卡,主色用紅綠藍
> ```

按 Enter → AI 開始生成(約 5-10 秒)

> 「我們支援 Claude Sonnet 4 / Opus 4 / GPT-4o / GPT-5,看哪個 model 比較適合。
> AI 會直接吐出符合我們格式的 JSON,**包含完整盤面 + 障礙物位置 + 目標 + 步數限制**。」

(等待 AI 出來) → 自動切到「JSON + 預覽 & 遊玩」tab

> 「看,生出來了。
> 右側顯示驗證結果(綠 = 過、黃 = 警告、紅 = 錯誤),
> 下方是預覽盤面,直接可以點『開始遊玩』試玩。」

按「**🎮 開始遊玩**」 → 觀眾可以指揮你怎麼玩

> 「你們可以指揮我怎麼玩,看 AI 生的關卡好不好。」
> (玩 5-10 步)

---

## 段落 3(60 秒)— AI 自動測試:取代人工 QA

從 sidebar 切到「**🤖 AI 自動測試**」(或直接 `localhost:8501/AI_Auto_Test`)

> 「但企劃最擔心的是『AI 生的關卡會不會太簡單,玩家 1 秒過』,或『太難,玩家放棄』。
> 過去這要 QA 人員手動玩 100 次。
> 我們做了一個 AI Agent — **它的策略仿自我們同團隊另一支真實遊戲的自動測試 AI(match3_AI 專案)**,
> 用 score-based heuristic 暴力搜索,**每一步都模擬所有可能,選最高分動作**。」

選剛剛 AI 生成的關卡 → 設 50 次 → 按「**🚀 開始跑**」

> 「一邊跑你會看到 live 進度,**50 場大約 5-10 秒**(每場 < 100ms)。」

(等跑完,通常 10 秒內)

> 「看結果:
> - **勝率 X%、平均用 Y 步**(這關上限 Z 步)
> - 步數分佈長條圖 → 看玩家會在哪步通關
> - 系統還會自動建議『太簡單 / 合理 / 太硬』
>
> 這就是 **AI 取代人工 QA 的真實 demo**。對接下來要做 100 個關卡的工作室來說,**省下幾百小時的測試人力**。」

(若時間夠,切「批次 × 多關」mode,跑前 20 關各 10 次,出整套難度曲線)

> 「批次測試還能畫出整套關卡的難度曲線。
> 像這條線:第 1-10 關勝率 100%(熱身)、第 30 關開始降到 60%(挑戰)、第 50 關剩 20%(付費關卡)。
> **這條曲線過去要花 1 個月人工跑,現在 3 分鐘出來**。」

---

## 段落 4(40 秒)— Godot 美術版

切瀏覽器到 `localhost:8765/` 分頁(start_demo.ps1 已自動起好)

> 「這個是 Godot 引擎跑的美術版。Godot 是真正的商用遊戲引擎,
> 可以做粒子特效、shader、tween — 跟前面 Streamlit 的版本**吃同一份 JSON 關卡檔**。」

(展示一兩關 — 通關動畫、紙箱被打破的特效)

> 「重點不是 Godot 多漂亮 — 重點是『**設計師改一份 JSON, 兩邊同步**』。
> Marketing 要 GIF 廣告素材?從 Godot 錄;
> 要 deck 上的 screenshot?Streamlit 截。
> 同一份內容,**兩種輸出管道,零重做**。」

---

## 收尾 30 秒 — Pitch(對齊 Google Cloud Day)

> 「總結這個 AI-Native Pipeline:
>
> ```
> AI Level Generator  →  Match3 Simulator  →  AI Auto-Test  →  難度報表回饋
>      (Gemini/Claude)      (Python + Godot)      (Score-based)        ↓
>                                                                    重新生成
> ```
>
> 三個都 **跑在 Google Cloud 上**:
> - **Vertex AI / Anthropic on GCP** 接 LLM 生成
> - **Cloud Run** 部署 Streamlit + Godot Web
> - **Cloud Storage** 存關卡 / 美術 / AI 測試報表
>
> 設計師原本一週的工作,現在 **1 分鐘 + $0.01 cost**。
>
> 任何一家做手遊、休閒遊戲、廣告 ad creative 的客戶,**都會需要這個**。
> 我們有 demo、有開源 repo、可以馬上 partner up。」

---

## 觀眾互動點(隨機應變)

**Q: AI 生的關卡好玩嗎?**
> 「BasicAgent 模擬可以證明難度合理。好玩程度的人類測試我們也跑過 — 100 個官方關卡 100% 可匯入,反向也能匯出標準格式回去。」

**Q: 我可以馬上試嗎?**
> 「可以。網址 https://match3sim.streamlit.app — 開源在 GitHub,等等發給你。」

**Q: 為什麼選 Streamlit + Godot 兩套?**
> 「Streamlit 做開發者工具最快,讓 designer / PM 內部用 — 改一行程式碼立刻 reload。
> Godot 才是給玩家看的成品 — 真的遊戲引擎,粒子、shader 都齊。
> 兩個工具吃同一份 JSON,**設計者改 JSON, 兩邊同步**。」

**Q: AI cost?**
> 「Claude Sonnet 一次生成 ~$0.01,GPT-4o-mini ~$0.001。
> 跑 100 個關卡 = $1。便宜到可以 burst。」

---

## Demo 前 Checklist(預演前 30 分鐘)

- [ ] `.\start_demo.ps1` 跑起來,3 個 URL 都能開
  - `http://localhost:8501/`              Streamlit 主頁
  - `http://localhost:8501/AI_Auto_Test`  AI 自動測試
  - `http://localhost:8765/`              Godot 美術版
- [ ] AI key 設定好(`config.toml` 或環境變數)
- [ ] 跑一次「Demo 模式 → 載入第 1 關 → 通關」
- [ ] AI 生成測試:「生一個有 5 個紙箱的關卡」 → 確認 5-10 秒內出 JSON
- [ ] AI 自動測試:選一個關卡跑 20 次 → 確認 progress + 圖表都出
- [ ] **(Godot 跑得起來時)** 點兩關看美術 + 動畫沒崩
- [ ] **(備案)** 確認線上版 https://match3sim.streamlit.app 還活著
- [ ] 螢幕分享測試 — 字夠大、滑鼠順暢、關通知

## 失敗時的 fallback

| 失敗點 | Fallback |
|---|---|
| AI 生成卡住 / 超時 | 從「載入官方關卡」載一個展示用 |
| AI 自動測試太慢 | 把次數從 50 調到 10 |
| Godot Web 不會載 | `.\start_demo.ps1 -StreamlitOnly`,跳過 Godot 段落 |
| 全部都炸 | 線上版 https://match3sim.streamlit.app 雙重備案 |
