# 物件索引（精簡）

完整欄位定義見根目錄 `tile_defs.py` 的 `TILE_REGISTRY`。  
欄位：`adj` = 相鄰消、`prop` = 道具消、`inpl` = 原地消、`mov` = 可移動、`blk` = 擋下落。

## 元素 & 道具

| ID | 類別 | adj | prop | 備註 |
|----|------|:---:|:---:|------|
| Red…Brn | element | — | ✓ | 不在 board 手填 |
| Soda0d / Soda90 | powerup | — | — | 火箭 |
| TNT | powerup | — | — | 炸彈 |
| TrPr | powerup | — | — | 紙飛機 |
| LtBl | powerup | — | — | 光球 |

## 障礙物

| ID 前綴 | HP | adj | prop | inpl | mov | 備註 |
|---------|---:|:---:|:---:|:---:|:---:|------|
| Crt1–4 | 1–4 | ✓ | ✓ | — | — | 紙箱 |
| Puddle_lv* | 1–5 | — | ✓ | ✓ | — | 底層水漥 |
| Barrel | 1 | ✓ | ✓ | — | **✓** | 木桶，可 swap/落下 |
| TrafficCone_lv* | 1–2 | ✓ | ✓ | — | **✓** | 交通錐，可 swap/落下 |
| SalmonCan | **2** | — | ✓ | — | — | 僅道具；sealed→open→破 |
| WaterChiller_* | 11 | ✓ | ✓ | — | — | 礦泉水；開門後道具每格 -1 |
| BeverageChiller_* | 5 | ✓ | ✓ | — | — | 飲料櫃；相鄰對色殺瓶；match 去重 |
| Rope_lv* | 1–2 | — | ✓ | ✓ | — | 上層；蓋住元素仍可配對 |
| Mud | 1 | ✓ | ✓ | — | — | 上層 |
| Pool_lv* | 1–5 | ✓ | ✓ | — | — | 充氣泳池 |
| **Stamp** | ∞ | ✓ | ✓ | — | — | **製造機**：相鄰 → GOAL+1，不滅 |

## Godot 對應

| 官方/JSON | Godot obstacle.type |
|-----------|---------------------|
| Stamp | `manufacturer` |
| Chiller 系列 | `chiller` + HP 狀態 |
| 其餘 | 與 tile_id 前綴對應 sprite |

素材：`godot_demo/resources/sprites/`（來源 `M8/`，本機 gitignore）。

## 目標（goals）語意

| goal_kind | 顯示 | 計數 |
|-----------|------|------|
| hits（預設） | 次數 | 每受傷 +1 |
| instances | 台數 2×2 | 整台消除 +1 |
| manufacturer | 明信片 | 郵戳相鄰 match +1 |

關卡來源：`godot_demo/levels/Level_*.json`（`level_generator/official_format.py` 轉換）。
