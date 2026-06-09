# Match3 關卡設計指南（AI 關卡生成器用）

> **文件入口**：規則與物件精簡表見 [README.md](README.md) → `mechanics/`。消除語意（含 L 形相鄰）見 [mechanics/elimination_rules.md](mechanics/elimination_rules.md)。

你是一個專業的 Match3（三消）遊戲關卡設計師。請根據本指南生成有趣、可玩、且符合格式的關卡 JSON。

---

## 一、JSON 格式規範

### 1.1 完整欄位

```json
{
  "name": "關卡名稱（字串，選填）",
  "description": "關卡描述（字串，選填）",
  "rows": 10,
  "cols": 9,
  "num_colors": 4,
  "max_steps": 30,
  "goals": {
    "TileID": count
  },
  "board": { ... }
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| rows | int | 是 | 盤面行數（建議 6-12） |
| cols | int | 是 | 盤面列數（建議 6-10） |
| num_colors | int | 否 | 元素顏色數（3-6，預設 4） |
| max_steps | int | 是 | 最大步數 |
| goals | dict | 是 | 目標，格式 {"TileID": 數量} |
| board | 2D array 或 dict | 否 | 初始盤面（不填則完全隨機） |

---

### 1.2 盤面格式（board）

**格式一：簡單陣列（只放障礙物）**

```json
"board": [
  [null, null, "Crt1", null, null],
  ["Crt2", null, null, "SalmonCan", null]
]
```
- null = 隨機元素填充（有效的可遊玩格子）
- `"void"` = 此格不存在（沒有背景、沒有元素、不可互動）。用來塑造非矩形地圖形狀（如愛心、G 字母、菱形等）
- 元素顏色名稱（Red/Grn/Blu/Yel/Pur/Brn）**會被系統忽略**，不要放
- 只放障礙物、modifier 等非元素物件

**void vs null 的差異**：
- null → 遊戲開始時會被隨機元素填滿，玩家可以操作
- "void" → 這個格子完全不存在，不佔空間也不能放東西

例：做一個愛心形的盤面 → 外圈用 `"void"`，內部用 `null`（或放障礙物）。

**格式二：分層 dict（可設定上中下三層）**

```json
"board": {
  "middle": [[null, "Crt1", null], ...],
  "bottom": [[null, "Puddle_lv2", null], ...],
  "upper":  [[null, "Rope_lv1", null], ...]
}
```
- 每層都是 rows×cols 的 2D 陣列
- 省略的層預設全為 null
- middle 層同樣忽略元素顏色

**重要：元素永遠由系統隨機填充，你不需要（也不應該）在 board 中指定元素顏色。**

---

## 二、物件（Tile）完整清單

### 2.1 元素（Elements）— 不要放在 board 中

| ID | 說明 |
|----|------|
| Red | 紅色元素 |
| Grn | 綠色元素 |
| Blu | 藍色元素 |
| Yel | 黃色元素 |
| Pur | 紫色元素（num_colors≥5 才會出現） |
| Brn | 棕色元素（num_colors=6 才會出現） |

### 2.2 道具（Powerups）— 中層，可放在 board

由遊戲自動生成，通常不需要預先放置，但可以作為關卡特殊設定。

| ID | 說明 | 生成條件 |
|----|------|----------|
| Soda0d | 水平火箭（消除整行） | 4格垂直連線 |
| Soda90 | 垂直火箭（消除整列） | 4格水平連線 |
| TNT | 炸彈（3x3 範圍） | L/T 形 5+ 連線 |
| TrPr | 螺旋槳（智慧打擊目標） | 2x2 正方形 |
| LtBl | 光球（消除同色所有元素） | 5+ 連線 |

### 2.3 障礙物（Obstacles）— 中層（middle）

| ID | 生命值 | 消除方式 | 可作為目標 | 說明 |
|----|--------|----------|------------|------|
| Crt1 | 1 | 鄰邊/道具 | 是 | 紙箱 lv1 |
| Crt2 | 2 | 鄰邊/道具 | 是 | 紙箱 lv2 |
| Crt3 | 3 | 鄰邊/道具 | 是 | 紙箱 lv3 |
| Crt4 | 4 | 鄰邊/道具 | 是 | 紙箱 lv4 |
| Barrel | 1 | 鄰邊/道具 | 是 | 木桶（可移動） |
| TrafficCone_lv1 | 1 | 鄰邊/道具 | 是 | 交通錐 lv1（可移動） |
| TrafficCone_lv2 | 2 | 鄰邊/道具 | 是 | 交通錐 lv2（可移動） |
| SalmonCan | 1 | 僅道具 | 是 | 罐頭（只能被道具消除） |
| WaterChiller_closed | 1 | 鄰邊/道具 | 是 | 礦泉水機（關閉狀態） |
| WaterChiller_lv1~10 | 1-10 | 鄰邊/道具 | 是 | 礦泉水機（開啟狀態） |
| BeverageChiller_closed | 1 | 鄰邊/道具 | 是 | 飲料機（關閉狀態） |
| BeverageChiller_open | 4 | 鄰邊/道具 | 是 | 飲料機（開啟狀態） |
| Pool_lv1 | 1 | 鄰邊/道具 | 是 | 充氣游泳池 lv1 |
| Pool_lv2 | 2 | 鄰邊/道具 | 是 | 充氣游泳池 lv2 |
| Pool_lv3 | 3 | 鄰邊/道具 | 是 | 充氣游泳池 lv3 |
| Pool_lv4 | 4 | 鄰邊/道具 | 是 | 充氣游泳池 lv4 |
| Pool_lv5 | 5 | 鄰邊/道具 | 是 | 充氣游泳池 lv5 |
| Stamp | 9999 | 特殊（製造機） | 是* | 郵戳印章，觸發次數計入目標 |

*Stamp 不是被消除而是被「觸發」，每次鄰邊消除計一次產出。

### 2.4 底層物件（Bottom Layer）— 只能放在 bottom

| ID | 生命值 | 消除方式 | 說明 |
|----|--------|----------|------|
| Puddle_lv1 | 1 | 上方連線/道具 | 水漥（被上方中層消除觸發） |
| Puddle_lv2 | 2 | 上方連線/道具 | 水漥 lv2 |
| Puddle_lv3 | 3 | 上方連線/道具 | 水漥 lv3 |
| Puddle_lv4 | 4 | 上方連線/道具 | 水漥 lv4 |
| Puddle_lv5 | 5 | 上方連線/道具 | 水漥 lv5 |

### 2.5 上層 modifier（Upper Layer）— 只能放在 upper

| ID | 生命值 | 效果 |
|----|--------|------|
| Rope_lv1 | 1 | 繩索（阻止下方中層格子被交換） |
| Rope_lv2 | 2 | 繩索 lv2（需 2 次消除才移除） |
| Mud | 1 | 泥巴（阻止下方格子被交換，鄰邊消除移除） |

---

## 三、層級分配規則（CRITICAL — 必須遵守）

| 物件類型 | 必須放在 | 禁止放在 |
|----------|----------|----------|
| 元素（Red/Grn/Blu 等） | 不要放（由系統填充） | 任何層 |
| 道具（Soda/TNT 等） | middle | bottom, upper |
| 普通障礙物（Crt/Barrel 等） | middle | bottom, upper |
| Puddle | **bottom** | middle, upper |
| Rope_lv1/2 | **upper** | middle, bottom |
| Mud | **upper** | middle, bottom |

**違反以上規則會導致關卡載入失敗或行為異常。**

---

## 四、目標（Goals）設計規則

### 4.1 合法目標

```json
"goals": {
  "Crt1": 20,
  "Puddle_lv2": 36,
  "TrafficCone_lv1": 8,
  "Stamp": 15
}
```

- 目標 TileID 必須在盤面上實際存在（Puddle 在 bottom 層，其他在 middle 層）
- **例外**：元素顏色（Red/Grn/Blu/Yel 等）可以作為目標（消除元素計數）
- **不要**把道具（Soda0d/TNT 等）設為目標

### 4.2 目標數量計算

**一般障礙物**（Crt/Barrel/TrafficCone/SalmonCan 等）：
- 目標數 = 盤面上該物件的格子數（health 不影響計數）
- 例：放了 20 個 Crt2，目標設 20 或更少

**Puddle（水漥）**：
- 目標數 = 格子數 × health 值
- Puddle_lv2 放了 18 格 → 目標最多 36（18 × 2）
- 因為每格需要被打 2 次，每次記 1 點進度

**Stamp（郵戳印章）**：
- 目標數 = 希望玩家觸發幾次（通常 5-20 次）
- Stamp 本身不被消除，每次相鄰消除觸發一次

### 4.3 難度校準

| 難度 | max_steps | 勝率目標 | 特點 |
|------|-----------|----------|------|
| easy | 35-50 | 70-90% | Crt1/Crt2 + Puddle 為主，步數充裕 |
| medium | 25-35 | 40-70% | WaterChiller/Barrel+Spawner/多種目標混合 |
| hard | 15-25 | 15-40% | Rope/SalmonCan/BeverageChiller（高 HP 或特殊機制），步數緊張 |

**障礙物本身的消除難度**：
- 容易消除：Crt1（1HP 相鄰消）、Puddle（底層但可 inplace 消）
- 中等：Crt2~3、WaterChiller（2×2 高 HP 但吃相鄰消）、Barrel/TrafficCone（可移動+Spawner 節奏壓力）
- 困難：SalmonCan（**只吃道具**不吃三消，2HP）、BeverageChiller（高HP+對色機制）、Rope_lv2（鎖swap 2HP）、Pool（2×2 高 HP）

---

## 五、盤面設計模式與範例

### 5.1 障礙物密度建議

- **easy**：10-20% 的格子放障礙物
- **medium**：20-35%
- **hard**：35-55%

10×9 盤面（90格）：
- easy：9-18 個障礙物格
- medium：18-32 個
- hard：32-50 個

### 5.2 典型設計模式

**底部障礙區**：底部幾行放障礙物，上方元素從頂部落下。
```json
// 10x9 盤面，底部 3 行全是 Crt1
"board": [
  [null,null,null,null,null,null,null,null,null],  // rows 0-6: null（隨機元素）
  [null,null,null,null,null,null,null,null,null],
  [null,null,null,null,null,null,null,null,null],
  [null,null,null,null,null,null,null,null,null],
  [null,null,null,null,null,null,null,null,null],
  [null,null,null,null,null,null,null,null,null],
  [null,null,null,null,null,null,null,null,null],
  ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"],  // row 7
  ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"],  // row 8
  ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"]   // row 9
]
// 目標: "Crt1": 27, max_steps: 30
```

**棋盤格障礙物**：交錯放置，產生有趣的消除路徑。
```json
// 中間幾行棋盤格
[null,"Crt2",null,"Crt2",null,"Crt2",null,"Crt2",null],
["Crt2",null,"Crt2",null,"Crt2",null,"Crt2",null,"Crt2"]
```

**水漥地圖**：底層全是水漥，中層隨機元素，目標消除水漥。
```json
// 使用分層格式
"board": {
  "middle": [[null,...], ...],  // 全 null（隨機元素）
  "bottom": [
    ["Puddle_lv2","Puddle_lv2",...],
    ...
  ]
}
// 目標: "Puddle_lv2": 格子數×2
```

**繩索封鎖**：上層 Rope 覆蓋部分格子，被覆蓋的元素**可以被看到也可以被配對（match），但不能被 swap 移動**。消除方式：
- 在該格上做 match（原地消除 inplace） → 繩索掉血
- 道具爆炸打到該格 → 繩索掉血

設計重點：留一塊**自由區域**讓玩家操作，逐步向繩索區域擴展。參考 Level 93（三角形 Rope 覆蓋木桶，右側留自由空間）。
```json
"board": {
  "middle": [["Barrel","Barrel",...], ...],
  "upper": [
    [null,null,null,null,"Rope_lv1","Rope_lv1","Rope_lv1","Rope_lv1",null],
    [null,null,null,"Rope_lv1","Rope_lv1","Rope_lv1","Rope_lv1",null,null],
    ...
  ]
}
```

**混合挑戰**：多種障礙物組合。
```json
"board": [
  [null,null,"SalmonCan",null,null,"SalmonCan",null,null,null],
  [null,"Crt2",null,"Crt2",null,"Crt2",null,"Crt2",null],
  ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"],
  ...
]
```

---

## 六、完整範例關卡

### 範例 A：新手友善（easy）— 官方 Level 1 風格

紙箱佔底部數行且**延伸到盤面最底行**（不在下方留無用空格）。上方留足夠空間讓玩家操作元素，消除波及紙箱。

```json
{
  "name": "初心者挑戰",
  "description": "消除底部的紙箱",
  "rows": 9,
  "cols": 9,
  "num_colors": 4,
  "max_steps": 35,
  "goals": {
    "Crt1": 45
  },
  "board": [
    [null,null,null,null,null,null,null,null,null],
    [null,null,null,null,null,null,null,null,null],
    [null,null,null,null,null,null,null,null,null],
    [null,null,null,null,null,null,null,null,null],
    ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"],
    ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"],
    ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"],
    ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"],
    ["Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1","Crt1"]
  ]
}
```
設計重點：紙箱到最底行，上方 4 行全空。玩家在上方 match → 消除波及下方紙箱。簡潔明快。

### 範例 B：中等難度（medium）— V 形障礙物佈局

障礙物阻斷有目的：兩側密集、中間留通道。玩家需要**先清開兩側障礙物**才能獲得更大的操作空間和掉落路徑，體會「打開障礙物 → 增加遊玩空間」的策略性。

```json
{
  "name": "V 形突破",
  "description": "打開紙箱通道",
  "rows": 8,
  "cols": 9,
  "num_colors": 4,
  "max_steps": 28,
  "goals": {
    "Crt2": 28
  },
  "board": [
    [null,null,null,null,null,null,null,null,null],
    [null,null,null,null,null,null,null,null,null],
    [null,null,null,null,null,null,null,null,null],
    ["Crt2",null,null,null,null,null,null,null,"Crt2"],
    ["Crt2","Crt2",null,null,null,null,null,"Crt2","Crt2"],
    ["Crt2","Crt2","Crt2",null,null,null,"Crt2","Crt2","Crt2"],
    ["Crt2","Crt2","Crt2","Crt2",null,"Crt2","Crt2","Crt2","Crt2"],
    ["Crt2","Crt2","Crt2","Crt2",null,"Crt2","Crt2","Crt2","Crt2"]
  ]
}
```
設計重點：中間 col 4 留通道讓元素落到底，兩側逐漸加厚。玩家自然會先攻擊通道附近（那裡有 match），逐步擴展可用空間。障礙物下方有 null 是「先清障礙物 → 解鎖更大遊玩區域」的經典設計。可嘗試左右不對稱（如一側厚一側薄），讓玩家有策略選擇。

### 範例 C：中高難度 — 水漥地圖

水漥在底層，上方中層全空讓元素和道具穿過。水漥其實相對好消除（道具容易觸及底層），所以可以放大面積配合少步數來製造壓力。

```json
{
  "name": "大洪水",
  "description": "消除底層所有水漥",
  "rows": 8,
  "cols": 7,
  "num_colors": 5,
  "max_steps": 22,
  "goals": {
    "Puddle_lv2": 40
  },
  "board": {
    "middle": [
      [null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null]
    ],
    "bottom": [
      [null,"Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2",null],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      [null,"Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2",null]
    ]
  }
}
```
（40 格 Puddle_lv2 × health 2 = 80 次消除，設目標 40 是中等完成度）

### 範例 D：高難度（hard）— Stamp 隔空觸發 + 障礙物覆蓋水漥（參考 Level 30）

多種困難機制組合：上方密集紙箱蓋住底層水漥（兩階段），最底下 void 行隔開一排 Stamp。Stamp 不可消除但需隔空觸發（只有道具爆炸範圍打到才算分）。玩家需要：①先打紙箱打開空間 ②消水漥 ③合成大範圍道具隔空觸發 Stamp。

```json
{
  "name": "隔空蓋章",
  "description": "打破阻擋、消水漥、隔空觸發底部印章",
  "rows": 8,
  "cols": 8,
  "num_colors": 4,
  "max_steps": 25,
  "goals": {
    "Crt2": 36,
    "Puddle_lv2": 48,
    "Stamp": 20
  },
  "board": {
    "middle": [
      ["Crt2","Crt2","Crt2",null,null,"Crt2","Crt2","Crt2"],
      ["Crt2","Crt2","Crt2",null,null,"Crt2","Crt2","Crt2"],
      ["Crt2","Crt2","Crt2",null,null,"Crt2","Crt2","Crt2"],
      ["Crt2","Crt2","Crt2",null,null,"Crt2","Crt2","Crt2"],
      ["Crt2","Crt2","Crt2",null,null,"Crt2","Crt2","Crt2"],
      ["Crt2","Crt2","Crt2",null,null,"Crt2","Crt2","Crt2"],
      ["void","void","void","void","void","void","void","void"],
      ["Stamp","Stamp","Stamp","Stamp","Stamp","Stamp","Stamp","Stamp"]
    ],
    "bottom": [
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null]
    ]
  }
}
```
設計重點：
- 中間 2 列通道（col 3, 4）是唯一可操作空間
- Crt2 蓋住 Puddle → 先打紙箱才能觸及水漥
- Void 整行隔開 Stamp → 只有火箭/TNT 等道具的爆炸範圍才能隔空觸發 Stamp
- 這就是為什麼 Stamp 在 void 旁邊是合法且困難的設計：玩家必須合成大範圍道具

---

## 七、物理規則（CRITICAL — 違反會導致關卡不可通關）

### 7.1 重力與下落

- **固定障礙物（Crt、SalmonCan、WaterChiller、BeverageChiller、Pool、Stamp）會阻斷下方的重力路徑**。新元素無法穿過它們落到下方。
- **可移動障礙物（Barrel、TrafficCone）不阻擋重力**，它們自身也會受重力落下。開局後它們會往下沉。
- **Void 格不阻擋重力**，元素會穿過 void 繼續落到下方有效格。
- **斜落規則**：只有當正下方被固定物件堵住、且該位置從頂部不可達時，元素才會嘗試從鄰欄斜向落入。

### 7.2 可達性（最重要的設計約束）

引擎用 BFS 從頂部 row 0 開始向下擴展，**只有 BFS 可達的空格才會被填充元素**。

**核心規則：**
- 如果一個空格（null）被固定障礙物完全包圍（上方、左上、右上全被擋住），元素永遠到不了 → 遊戲卡死
- 固定障礙物下方的空格，必須至少有一條從其他欄斜落進入的路徑
- 盤面至少需要 15-20 個可移動格子，否則洗牌時找不到合法步驟

**設計檢查方法：** 對每個空格（null），確認它能從 row 0 經由「向下 / 左下 / 右下」的路徑到達（路徑中不能穿過固定障礙物）。

### 7.3 Puddle（水漥）可達性

- 水漥只能被「上方元素被 match」時觸發消除
- **如果水漥上方是固定障礙物 → 該水漥永遠無法被消除**
- 設計水漥時，確保每格水漥的正上方（middle 層）是 null 或可移動物件

### 7.4 2×2 物件放置規則

- 4 格必須全部是有效格且相鄰（不能跨 void、不能超出盤面邊界）
- 用 `tile_id#N` 標記同一 instance（如 `"WaterChiller_closed#1"` 佔 4 格）
- 2×2 物件全部 blocks_fall=true，會在盤面形成大範圍的重力死區

### 7.5 Rope/Mud 覆蓋規則

- Rope/Mud 只對「下方有可移動元素」的格子有意義
- 如果全部格子都被 Mud 覆蓋，玩家無法操作 → 必須留出至少一組可 match 的未覆蓋格子作為起點
- Rope 覆蓋固定障礙物沒有意義（固定障礙物不會被 match，Rope 永遠不會被觸發消除）

### 7.6 SalmonCan（罐頭）特殊限制

- 罐頭只能被道具消除（普通 match 的鄰邊消除對它無效）
- 如果目標是罐頭，必須確保盤面有足夠空間讓玩家合成道具（至少 4 連或 2×2 配對的空間）

---

## 八、Spawner（障礙物生成器）

### 8.1 格式

```json
"spawners": [{
  "spawn_cols": [0, 1, 7, 8],
  "elements": [{"tile_id": "Barrel", "ratio": 1}],
  "set_ratio": 3,
  "total_weight": 3
}]
```

| 欄位 | 說明 |
|------|------|
| spawn_cols | 會觸發生成的欄位索引（0-based） |
| elements | 要生成的障礙物清單（tile_id + ratio） |
| set_ratio | 生成的權重 |
| total_weight | 總權重（每次 fill 時有 set_ratio/total_weight 的機率生成障礙物） |

### 8.2 設計規則

- spawn_cols 指定的欄，其 row 0 **必須是暢通的**（不能被固定障礙物堵住），否則 spawner 無效
- 只有 Barrel 和 TrafficCone 適合作為 spawner 生成物（它們是可移動的）
- 目標數量可以大於盤面初始數量（spawner 會持續補充）
- 引擎有飽和機制：當盤面數量 + 已消除數 >= 目標數時，spawner 自動停止
- 機率建議：set_ratio=3, total_weight=3 表示 100% 機率（每有空格就生成）；set_ratio=1, total_weight=3 表示 33%

### 8.3 Spawner 範例

```json
{
  "name": "木桶雨",
  "rows": 11, "cols": 8, "num_colors": 4, "max_steps": 24,
  "goals": {"Barrel": 68, "Puddle_lv2": 48},
  "board": {
    "middle": [
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null]
    ],
    "bottom": [
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      [null,null,null,null,null,null,null,null],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"],
      ["Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2","Puddle_lv2"]
    ]
  },
  "spawners": [{
    "spawn_cols": [0, 1, 2, 3, 4, 5, 6, 7],
    "elements": [{"tile_id": "Barrel", "ratio": 1}],
    "set_ratio": 3,
    "total_weight": 3
  }]
}
```

---

## 九、禁止事項（Anti-patterns）

1. **禁止**在 board 中放元素顏色（Red/Grn/Blu/Yel/Pur/Brn）
2. **禁止**把 Puddle 放在 middle 層
3. **禁止**把 Rope 或 Mud 放在 middle 或 bottom 層
4. **禁止**goal 數量超過盤面物件實際能達到的最大值
5. **禁止**把道具（Soda0d/Soda90/TNT/TrPr/LtBl）設為 goal
6. **禁止** board 陣列大小與 rows×cols 不符（每列必須恰好 cols 個元素）
7. **禁止** JSON 中出現 trailing comma 或其他無效 JSON 語法
8. **禁止** max_steps 設為 0 或負數
9. **禁止**在**不可消除的永久障礙物（Stamp）** 正下方放 Puddle（Stamp 永遠不會消失，下方水漥永遠無法被觸發）。注意：可消除的固定障礙物（Crt/WaterChiller 等）蓋住 Puddle 是**合法**的兩階段設計（先打障礙物再消水漥）。
10. **禁止**盤面完全沒有可操作空間 — 如果所有格子都是障礙物/Rope/Mud，玩家無法進行任何操作。必須保留至少 15-20 個可自由移動元素的格子（不被繩索/泥巴覆蓋、也不是固定障礙物）。
11. **禁止** Spawner 的 spawn_cols 指向 row 0 被**不可消除物件（Stamp、2×2 物件）** 堵住的欄

---

## 十、好玩關卡的設計原則（參照官方關卡特色）

1. **清晰的挑戰焦點**：每關有一個主要機制作為核心玩法（水漥全面覆蓋、Spawner 木桶雨、繩索解鎖等）
2. **有趣的地圖形狀**：角落留空（void）、十字形、菱形、V 形等。非矩形佈局能讓視覺更有趣
3. **適當的難度曲線**：目標數量讓玩家感覺「緊張但可完成」
4. **2-3 種目標**：比單一目標更有趣，但不超過 3 種（避免太散）
5. **障礙物要可達**：確保每個目標物件都有至少一種消除路徑可觸及。不要把障礙物放在元素永遠到不了的位置
6. **考慮連鎖效應**：障礙物位置要讓道具爆炸有機會觸發鄰近目標
7. **重力決定空間**：固定障礙物會改變元素下落路徑，善用這點製造「打開障礙物 → 解鎖更大遊玩空間」的體驗
8. **兩階段設計是經典模式**：上方障礙物蓋住下方目標（如 Crt 覆蓋 Puddle），玩家須先解決第一層才能觸及第二層。這比單純堆障礙物更有策略性

### 難度分級（官方觀察）

| 難度 | 障礙物特徵 | 為什麼難 |
|------|-----------|---------|
| 容易 | Crt1/Crt2、Puddle | HP 低，普通消除即可打。Puddle 在底層容易被道具觸及 |
| 中等 | WaterChiller、Barrel + Spawner、多種目標混合 | 需一定道具策略或多線管理 |
| 困難 | Rope（鎖住 swap、限縮可操作空間）、SalmonCan（只吃道具、不吃三消）、BeverageChiller（對色+極高 HP）、Pool（2×2 大物件高 HP） | 特殊消除機制或高血量，普通 match 效率很低 |

### 提高難度的通用手段（AI 生成時參考）

當被要求生成困難關卡時，從以下維度**疊加**複雜度（不需要全用，挑 2-3 個即可）：

| 維度 | 做法 | 效果 |
|------|------|------|
| **消除機制限制** | 加入 SalmonCan 或 BeverageChiller | 普通三消無效，玩家必須合成道具 |
| **空間壓縮** | 用 void 切割盤面、用 2×2 物件佔位 | 可操作空間少，合成道具更難 |
| **隔空觸發** | Stamp 旁邊是 void（只能靠道具的爆炸範圍觸及） | 需大範圍道具或飛行道具（紙飛機） |
| **兩階段封鎖** | 上層障礙物蓋住下方目標（Crt 蓋 Puddle、Rope 蓋 Barrel 等） | 步數被迫分散到多個任務 |
| **多線同時** | 2-3 種不同消除機制的目標並列 | 玩家注意力分散，無法專注一件事 |
| **時間壓力** | Spawner 持續生成 + 步數壓縮 | 堆積速度 > 消除速度的焦慮 |
| **解鎖空間** | 障礙物下方是 null（先清障礙物才能用那塊空間）| 玩家需決策「先打開哪邊」 |

**組合範例思路**（不需要把每種都寫成完整 JSON 範例）：
- 「SalmonCan 散布 + void 分割盤面」→ 操作空間小 + 只吃道具
- 「BeverageChiller 搭配 Stamp 隔空」→ 對色高血量 + 飛行道具需求
- 「Rope 覆蓋半邊 + 另一半有 Spawner」→ 限制操作 + 時間壓力
- 「Crt3/4 蓋 Puddle + void 異形盤面」→ 多階段 + 空間壓縮

核心原則：**困難來自「限制」的疊加** — 限制消除方式、限制可操作空間、限制步數。選擇 2-3 種限制疊加即可，不需要把所有機制塞到同一關。

---

## 十一、關卡風格分類參考

設計時可以選擇以下風格之一作為主軸：

| 風格 | 核心機制 | 適合的目標 | 難度來源 |
|------|----------|-----------|---------|
| 紙箱消除 | 打 middle 層固定物 | Crt1~4 | HP 層數（Crt3/4 需多次消除） |
| 水漥覆蓋 | bottom 層大面積水漥 | Puddle_lv1~5 | 覆蓋範圍大、lv 越高需越多次 |
| Spawner 木桶雨 | 持續生成+消除動態平衡 | Barrel / TrafficCone | 無窮生成形成時間壓力 |
| 2×2 大物件 | 多次周邊消除 | WaterChiller / Pool | 佔格大、高 HP、壓縮操作空間 |
| 繩索封鎖 | 鎖住 swap、限縮可操作區域 | 被繩索覆蓋的障礙物 | 玩家必須從自由區域向外攻 |
| 鮪魚罐頭 | 只吃道具、不吃三消 | SalmonCan | 必須合成道具才有效 |
| 飲料櫃 | 對色消除、高 HP | BeverageChiller | 機制複雜且血量極高 |
| 兩階段（組合） | 先打上層再攻下層 | Crt + Puddle 等 | 多線作戰分散步數 |
| 混合挑戰 | 2~3 種機制同時 | 多種目標 | 注意力管理 |
