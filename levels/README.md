# 關卡文件格式說明

## 文件格式

關卡文件使用 JSON 格式，包含以下欄位：

```json
{
  "name": "關卡名稱",
  "description": "關卡描述",
  "rows": 10,
  "cols": 9,
  "max_steps": 15,
  "goals": {
    "Red": 10,
    "Crt1": 5,
    "Crt2": 2
  },
  "board": [
    ["Grn", "Red", "Blu", ...],
    ["Yel", "Grn", "Red", ...],
    ...
  ]
}
```

## 欄位說明

- **name** (string): 關卡名稱（可選）
- **description** (string): 關卡描述（可選）
- **rows** (int): 盤面行數（必需）
- **cols** (int): 盤面列數（必需）
- **max_steps** (int): 最大步數限制（必需）
- **goals** (dict): 關卡目標，格式為 `{"TileName": required_count}`（必需）
  - 支援的 TileName: `Red`, `Grn`, `Blu`, `Yel`, `Crt1`, `Crt2`, `TNT`, `Soda0d`, `Soda90`, `TrPr`, `LtBl`
- **board** (2D array): 初始盤面配置（可選，如果不提供則隨機生成）
  - 每個元素是 tile 名稱（字符串）或 `null`（空格）
  - 如果提供的盤面大小與 rows/cols 不匹配，會自動調整

## 使用方式

### 在 Python 代碼中使用：

```python
from Match3_sim.match3_env import Match3Env

# 方式 1: 在初始化時載入關卡
env = Match3Env(level_file='levels/level_01.json')

# 方式 2: 在 reset 時載入關卡
env = Match3Env(rows=10, cols=9)
state = env.reset(level_file='levels/level_01.json')

# 方式 3: 重置到已載入的關卡
env = Match3Env(level_file='levels/level_01.json')
state = env.reset()  # 會重新載入 level_01.json
```

## 關卡完成條件

關卡會在以下情況結束：

1. **勝利**: 所有目標都達成（`goals_met()` 返回 True）
2. **失敗**: 步數達到 `max_steps` 但目標未達成

## 範例關卡

- `level_01.json`: 基礎消除關卡
- `level_02.json`: 包含障礙物的關卡
- `level_03.json`: 高難度挑戰關卡


