# Match3_sim 文件索引

> 給人與 AI 用的精簡入口。規則真值以 `tile_defs.py` + `match_engine.py` 為準；Godot 對齊在 `godot_demo/scripts/board/game_board.gd`。

## 快速導覽

| 想查什麼 | 讀這裡 |
|---------|--------|
| 消除規則（match / 延伸 / 道具 / 相鄰） | [mechanics/elimination_rules.md](mechanics/elimination_rules.md) |
| 官方 goal 語意、落下關卡 | [mechanics/official_goals.md](mechanics/official_goals.md) |
| 三層視覺、罐頭、空格 | [mechanics/layers.md](mechanics/layers.md) |
| 物件 ID、層、可否相鄰消 | [mechanics/objects_index.md](mechanics/objects_index.md) |
| 關卡 JSON 格式、生成指引 | [level_design_guide.md](level_design_guide.md) |
| 官方 Excel 設計稿（本機） | `docs/design/盤面物件設計文件*.xlsx`（gitignore，需自行放置） |

## 程式與資料夾地圖

```
Match3_sim/
├── tile_defs.py          # 物件註冊表（規則欄位）
├── match_engine.py       # Python 模擬引擎（消除、重力、目標）
├── streamlit_app.py      # 內部測試 UI
├── publish_godot.ps1     # 匯出 Web → godot_demo/web/
├── godot_demo/           # 對外 Demo（GitHub Pages）
│   ├── levels/           # Level_001.json … 官方轉換關卡
│   └── scripts/board/    # game_board.gd 盤面邏輯
├── levels/               # 舊 Streamlit 範例 6 關（可忽略）
├── 關卡格式資料/          # 官方原始 JSON（轉換前）
├── level_generator/      # 關卡轉換 / 生成工具
└── M8/                   # 美術原始檔（gitignore）
```

## 雙引擎對照

| 能力 | Python | Godot |
|------|--------|-------|
| 三連相鄰消障礙 | `match_engine.py` L409–424 | `_trigger_obstacle_adjacent` |
| 郵戳製造機 | manufacturer + goal | `obstacle type=manufacturer` |
| 道具原地消 | prop elim | `EXPLODE_MODE_SPECIAL` |
| 合成十字 4 鄰 | 對齊 match 語意 | `EXPLODE_MODE_MATCH`（2×2 / 紙飛機連鎖） |

## 維護注意

- 新增障礙物：先改 `tile_defs.py`，再改 Godot `obstacle.gd` / loader / 素材。
- 設計 xlsx 無法進 git 時，把結論補進 `docs/mechanics/`，避免只靠 Excel。
- 手動截圖勿放 repo 根目錄；已列入 `.gitignore` 常見檔名。
