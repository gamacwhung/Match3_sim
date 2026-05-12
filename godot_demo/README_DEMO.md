# Match3 Godot Demo — 安裝與匯出教學

這個資料夾是 **fork yuehpo_match3 + 接上我們的美術 / JSON 關卡格式** 的 Godot 4.6 Demo 專案。

---

## 一、概覽

**改造範圍**(相對於 yuehpo 原版)
- ✅ `candy_renderer.gd` — 4 色用我們的 M8 sprite(Red/Grn/Blu/Yel)
- ✅ 特殊糖果 sprite — STRIPED → Soda 火箭、WRAPPED → TNT、COLOR_BOMB → LtBl 光球
- ✅ `json_level_loader.gd` — 直接讀 `res://levels/level_*.json`(專案的 JSON 格式)
- ✅ `demo_main.gd` / `demo_main.tscn` — 跳過 menu/world_map,直接循環試玩 levels
- ✅ `board_bg.gd` — 障礙物用我們的 sprite(Crt 紙箱、Puddle、Pool 等)
- ✅ `obstacle.gd` — 保留 `tile_id` 給 board_bg sprite 渲染用
- ✅ `project.godot` — main_scene 改指向 `scenes/demo_main.tscn`

**未做(留 v2)**
- 2×2 共享血量(WaterChiller / BeverageChiller / Pool 目前當單格 jelly)
- BeverageChiller 內部連通 / per-cell bottle color
- TrPr 飛行階段、LtBl+元素 雙合成的精細規則
- 道具 sprite(Soda/TNT/LtBl)只在「特殊糖果生成」時顯示,JSON 裡寫的 `Soda0d` 等暫時被忽略
- yuehpo 原本的 main_menu / world_map 流程仍保留(只是 demo_main 不走那條),可以日後切回去

**Streamlit fallback**:不論 Godot 是否 export 成功,Streamlit 的 `pages/1_Demo.py` 都已經能 demo,不會卡住。

---

## 二、安裝 Godot 4.6

### 2.1 下載 Godot 4.6 編輯器

到 https://godotengine.org/download/windows/ 下載 **Godot Engine 4.6 Standard**(非 .NET 版即可)。

解壓後得到 `Godot_v4.6-stable_win64.exe`。建議放在 `C:\Tools\Godot\` 之類固定位置。

### 2.2 下載 Web Export Templates(關鍵!)

Godot 沒帶 export template,要另外下載。

1. 下載 https://godotengine.org/download/windows/ 同頁面的 **Export Templates** TPZ 檔
2. 開啟 Godot 編輯器(空白 Project Manager 階段) → `Editor → Manage Export Templates → Install from File...`
3. 指向剛下載的 `.tpz` 檔安裝

確認:`Editor → Manage Export Templates` 顯示 `4.6.stable` 已安裝。

---

## 三、開啟並測試 godot_demo 專案

### 3.1 從 Godot 編輯器匯入

1. Godot 編輯器 Project Manager → **Import**
2. 選 `c:\Users\GHQ_User\Desktop\cwhung\match3\Match3_sim\godot_demo\project.godot`
3. 第一次匯入,Godot 會掃描所有 `.png` 並建 `.import` 檔(可能花 30 秒)

### 3.2 在編輯器內試跑

按 **F5** 或左上 **▶ Play**。
預期看到:
- 黑底 + 紫色背景波動
- 載入 `levels/level_01.json`(紙箱關)
- 4 色我們的 M8 美術元素 + 棋盤下方 5 排紙箱
- 點兩格鄰近元素可交換 → 三連消除
- 元素消到紙箱旁 → 紙箱被打破

如果有任何 GDScript 錯誤,Godot console 會顯示。**把錯誤訊息貼給我,我馬上修**。

### 3.3 常見問題

**「找不到 res://levels/...」** 
→ 確認 `godot_demo/levels/` 下有 `level_01.json` ~ `level_06.json`。
→ Editor 內按 `Project → Reload Current Project` 重新掃描。

**「sprite 沒顯示,還是看到 yuehpo 的向量糖果」**
→ Editor 內 `FileSystem` 面板點 `resources/sprites/` 確認 30 個 PNG 都在。
→ 重新跑(F5)。

**「點不動 / 沒反應」**
→ 切到 `scenes/demo_main.tscn` → 確認 root 節點 script 是 `scripts/demo_main.gd`。

---

## 四、Export Web 版

### 4.1 設定 Web export preset

1. 編輯器 → `Project → Export...`
2. 點 `Add...` → `Web`
3. 命名 `Web` 即可,其他保持預設
4. **Export Path** 設成 `web/index.html`(專案內既有 `web/` 資料夾)
5. 點下方 `Export Project`(不是 Export PCK)

匯出後 `godot_demo/web/` 會被覆蓋成新版,內容應有:
- `index.html`
- `index.js`、`index.wasm`、`index.pck`(`.pck` 含我們的 levels + sprites)
- 各種 icon

### 4.2 在本機測試 web build

Godot web build 不能直接打開 `index.html`(file:// 協定不支援 SharedArrayBuffer)。要起 HTTP server。

最簡單:用 Python(專案目錄已有 Python)
```powershell
cd c:\Users\GHQ_User\Desktop\cwhung\match3\Match3_sim\godot_demo\web
python -m http.server 8765
```

> 用 8765 是為避免和你電腦上其他服務衝突(8000、8080 常被佔)。
> Streamlit Demo 頁的進階模式預設也是 8765。

然後瀏覽器開 `http://localhost:8765/`。
**首次載入會卡幾秒**(下載 wasm + pck),之後正常。

---

## 五、用 start_demo.ps1 一鍵啟動所有 server

專案根有 `start_demo.ps1`,可同時起 Streamlit + Godot HTTP server:

```powershell
cd c:\Users\GHQ_User\Desktop\cwhung\match3\Match3_sim
.\start_demo.ps1                  # 同時起 Streamlit (8501) + Godot Web (8765)
.\start_demo.ps1 -StreamlitOnly   # 只起 Streamlit(還沒 export Godot 時用)
.\start_demo.ps1 -Stop            # 全部關掉
```

Demo 時 3 個瀏覽器 tab:
- `http://localhost:8501/`              Streamlit 主頁(AI 關卡生成 + 試玩)
- `http://localhost:8501/AI_Auto_Test`  AI 自動測試報表
- `http://localhost:8765/`              Godot 美術版

---

## 六、嵌進 Streamlit Demo 頁

`pages/1_Demo.py` 的「進階模式」區有兩種嵌入模式可選:

1. **🪟 直接嵌在頁內(iframe)** — 預設,Streamlit 內直接看到 Godot
2. **🔗 在新分頁打開** — 備案,若 iframe 出問題用這個

**為什麼 iframe 嵌入這次能跑?**
我們的 `export_presets.cfg` 是 single-thread 模式(`variant/thread_support=false`),**不需要 SharedArrayBuffer**,所以 Streamlit 預設不送 COOP/COEP header 也 OK。實測 single-thread Godot 4.6 export 可以乾淨地 iframe 嵌入。

若哪天改成 multi-thread / PWA 模式(需 cross-origin isolation),iframe 嵌入會失效,那時切回「新分頁打開」即可。

---

## 七、Demo 流程建議(Google Cloud Day 故事線)

3-5 分鐘 demo:

1. **痛點開場(30s)**:企劃手動設關卡 30 分/關、QA 用人工試玩,難度全憑感覺
2. **AI 生成(60s)**:`localhost:8501/` Level Generator → 輸入文字描述 → 15 秒出 JSON
3. **真實試玩(90s)**:切去 `localhost:8765/` Godot 美術版 → 點剛剛生成的關卡 → 真的能玩
4. **AI 自動測試(60s)**:切去 `localhost:8501/AI_Auto_Test` → 跑 50 次 → 出勝率/平均步數/卡關率
5. **收尾(30s)**:整條 AI-Native pipeline,從 Spec → 玩 → 驗收,人類不介入

詳細 demo script 看根目錄的 `DEMO_SCRIPT.md`。

---

## 八、若 Godot export 失敗的 Fallback

直接跑 Streamlit,Godot 那塊跳過:
```powershell
.\start_demo.ps1 -StreamlitOnly
```

Streamlit 內建的 board component 仍能 demo `AI 生成 + 試玩 + AI 自動測試` 三大塊,只是視覺沒 Godot 漂亮。Demo 仍 100% 可跑。
