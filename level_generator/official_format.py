"""
官方關卡格式 ↔ 我們的關卡格式 雙向轉換

官方格式（"關卡格式資料/Level_*.json"）:
  - Grid.Items[]:   ID 列表，順序 (0,0)->(W-1,0)->(0,1)... 即先 x 後 y
  - Grid.Cells[]:   per-cell modifier (Puddle/Mud/Rope/FillType...)
  - 座標 (0,0) 是「左下角」
  - 多格物件 (WaterChiller/BeverageChiller/Pool/Safe) 用 4 個 corner ID 占據 2x2

我們的格式（"levels/level_*.json"）:
  - rows×cols 二維 array，row=0 是頂部
  - board: {middle, upper, bottom}，多格物件用 `tile_id#N` instance tag

CLI:
  python -m level_generator.official_format import 關卡格式資料/ -o levels_imported/
  python -m level_generator.official_format export levels/level_01.json -o exported.json
  python -m level_generator.official_format report 關卡格式資料/   # 不寫檔，只報告哪些可以匯
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter
from typing import Optional


# ===========================================================================
# ID 對照表
# ===========================================================================

# 官方單格 ID → (我們的 tile_id, 放哪一層)
SINGLE_OFFICIAL_TO_TILE = {
    0:  (None,         None),         # None 空值（不放任何東西）
    1:  ('Blu',        'middle'),
    2:  ('Grn',        'middle'),
    3:  ('Red',        'middle'),
    4:  ('Yel',        'middle'),
    5:  ('Pur',        'middle'),
    6:  ('Brn',        'middle'),     # Orange→Brn (我們沒橘色)
    7:  ('Soda0d',     'middle'),
    8:  ('Soda90',     'middle'),
    9:  ('TNT',        'middle'),
    10: ('TrPr',       'middle'),
    11: ('LtBl',       'middle'),
    15: (None,         None),         # RandomMatch — 由 fill 機制處理
    16: (None,         None),         # Match1 — 同色同組（忽略,當隨機）
    17: (None,         None),
    18: (None,         None),
    21: ('Crt1',       'middle'),
    22: ('Crt2',       'middle'),
    23: ('Crt3',       'middle'),
    24: ('Crt4',       'middle'),
    25: ('Puddle_lv1', 'bottom'),
    26: ('Puddle_lv2', 'bottom'),
    31: ('Stamp',      'middle'),
    32: ('Barrel',     'middle'),
    58: ('SalmonCan',  'middle'),
    65: ('Mud',        'upper'),
    92: ('TrafficCone_lv1', 'middle'),
    93: ('TrafficCone_lv2', 'middle'),
    156: ('Rope_lv1',  'upper'),
    157: ('Rope_lv2',  'upper'),
}

# 反向：我們的 tile_id → 官方 ID
TILE_TO_SINGLE_OFFICIAL = {
    tile_id: off_id
    for off_id, (tile_id, _layer) in SINGLE_OFFICIAL_TO_TILE.items()
    if tile_id is not None
}

# 官方 2x2 corner 群組 (BL, BR, TL, TR) → (我們的 tile_id, color or None)
CORNER_GROUPS = {
    (27, 28, 29, 30): ('WaterChiller_closed',   None),
    (33, 34, 35, 36): ('BeverageChiller_closed', 'Blue'),
    (37, 38, 39, 40): ('BeverageChiller_closed', 'Green'),
    (41, 42, 43, 44): ('BeverageChiller_closed', 'Red'),
    (45, 46, 47, 48): ('BeverageChiller_closed', 'Yellow'),
    (49, 50, 51, 52): ('BeverageChiller_closed', 'Purple'),
    (53, 54, 55, 56): ('BeverageChiller_closed', 'Orange'),
    (61, 62, 63, 64): ('Pool_lv1',              None),
    # Safe 67-70 我們未實作
}

# 反向：(tile_id, color) → corner quad
TILE_COLOR_TO_QUAD = {
    ('WaterChiller_closed',  None):     (27, 28, 29, 30),
    ('BeverageChiller_closed', 'Blue'): (33, 34, 35, 36),
    ('BeverageChiller_closed', 'Green'):(37, 38, 39, 40),
    ('BeverageChiller_closed', 'Red'):  (41, 42, 43, 44),
    ('BeverageChiller_closed', 'Yellow'):(45,46, 47, 48),
    ('BeverageChiller_closed', 'Purple'):(49,50, 51, 52),
    ('BeverageChiller_closed', 'Orange'):(53,54, 55, 56),
}
# Pool 預設用 lv1 → quad
POOL_QUAD = (61, 62, 63, 64)

# 官方未實作 / 我們也沒 對應的 ID（會發 warning）
UNSUPPORTED_OFFICIAL_IDS = {
    20,           # Coin
    57,           # Roadblock
    67, 68, 69, 70,  # Safe BL/BR/TL/TR
    94,           # TrafficCone3 (官方標暫時無用)
    59, 60,       # SalmonCan2/3 (暫時無用)
    66,           # Mud2 (暫時無用)
}

# Match*：填充提示，不是物件，靜默忽略
# (Hole=12, BlockHole=13 不在這裡 — 它們會被處理成 void)
SILENT_OFFICIAL_IDS = {
    16, 17, 18,   # Match1/2/3（同色填充提示,我們無此機制）
}

# BeverageChiller corner ID → 顏色（短名,對齊元素 tile_id Red/Grn/Blu/Yel/Pur/Brn）
BEV_CHILLER_CORNER_COLOR = {
    33: 'Blu', 34: 'Blu', 35: 'Blu', 36: 'Blu',
    37: 'Grn', 38: 'Grn', 39: 'Grn', 40: 'Grn',
    41: 'Red', 42: 'Red', 43: 'Red', 44: 'Red',
    45: 'Yel', 46: 'Yel', 47: 'Yel', 48: 'Yel',
    49: 'Pur', 50: 'Pur', 51: 'Pur', 52: 'Pur',
    53: 'Brn', 54: 'Brn', 55: 'Brn', 56: 'Brn',  # Orange→Brn (我們沒橘色)
}
WATER_CHILLER_CORNERS = {27, 28, 29, 30}
POOL_CORNERS = {61, 62, 63, 64}


def _corner_kind_and_pos(item_id):
    """
    判斷 item_id 是哪種 2x2 物件的角，並回傳該角的位置（0=BL, 1=BR, 2=TL, 3=TR）
    回傳 (kind, pos)；非 corner 回傳 (None, None)。
    """
    if 27 <= item_id <= 30:
        return ('water', item_id - 27)
    if 33 <= item_id <= 56:
        return ('bev', (item_id - 33) % 4)
    if 61 <= item_id <= 64:
        return ('pool', item_id - 61)
    return (None, None)

# Goal ID 不等於 item ID — 經 100 關官方資料反推實際對應關係。
# 「target_count」的計法,在不同物件上不同:
#   - 一般物件(Crt, Puddle, Barrel, ...): count = 盤上 instance 數
#   - WaterChiller / BeverageChiller (多格 chiller): count = 整個 chiller 的 HP 總和
#       WaterChiller 是 10 HP per instance,BC 是 4 HP per instance
#   - Stamp: count = 用印次數,跟盤上 stamp 數沒固定倍率(疑似 stamp 可多次點)
# 不能精確推算的(Stamp 等),就用 family 標 hint,實際 count 仍用官方給的數字。
GOAL_ID_TO_FAMILY = {
    12: 'Crt',           # 紙箱 — count = 紙箱 instance 數
    13: 'Puddle',        # 水漥 — count = puddle cell 數
    14: 'WaterChiller',  # 礦泉水櫃 — count = HP 總和(10/instance)
    15: 'Stamp',         # 郵戳 — count 直接用官方數
    16: 'Barrel',        # 木桶
    17: 'BeverageChiller',  # 飲料櫃 — count = HP 總和(4/instance)
    19: 'SalmonCan',     # 鮭魚罐
    20: 'Pool',          # 充氣泳池
    21: 'Mud',           # 泥巴
    26: 'TrafficCone',   # 交通錐
}
# 舊名(保留 backward compat)
GOAL_HINT = GOAL_ID_TO_FAMILY


# ===========================================================================
# 座標轉換
# ===========================================================================

def idx_to_xy(idx: int, W: int) -> tuple[int, int]:
    """官方 idx → (x, y), x=col 從左, y=row 從底"""
    return idx % W, idx // W


def xy_to_idx(x: int, y: int, W: int) -> int:
    return y * W + x


def y_to_row(y: int, H: int) -> int:
    """官方 y(底=0) → 我們的 row(頂=0)"""
    return H - 1 - y


def row_to_y(row: int, H: int) -> int:
    return H - 1 - row


# ===========================================================================
# Import: 官方 → 我們
# ===========================================================================

def official_to_ours(official: dict) -> tuple[dict, list[str]]:
    """
    把官方關卡 JSON 轉成我們的格式。
    回傳 (our_dict, warnings_list)。
    """
    warnings: list[str] = []
    grid = official['Grid']
    W, H = grid['Width'], grid['Height']
    items = grid['Items']
    cells_off = grid['Cells']

    if len(items) != W * H:
        warnings.append(f'Items 長度 {len(items)} 與 Width*Height={W*H} 不符')
    if len(cells_off) != W * H:
        warnings.append(f'Cells 長度 {len(cells_off)} 與 Width*Height={W*H} 不符')

    middle = [[None] * W for _ in range(H)]
    upper = [[None] * W for _ in range(H)]
    bottom = [[None] * W for _ in range(H)]
    bottle_colors_layer = [[None] * W for _ in range(H)]   # 每格 BC 的瓶子顏色

    used = set()        # 已被 2x2 占用的 idx
    instance_id = 0
    beverage_colors: set[str] = set()

    # 1) 先掃 2x2 corner groups（4 個角必須是同類別,且位置正確 BL/BR/TL/TR）
    for y in range(H - 1):
        for x in range(W - 1):
            i_bl = xy_to_idx(x, y, W)
            i_br = xy_to_idx(x + 1, y, W)
            i_tl = xy_to_idx(x, y + 1, W)
            i_tr = xy_to_idx(x + 1, y + 1, W)
            if any(i in used for i in (i_bl, i_br, i_tl, i_tr)):
                continue
            kinds_pos = [_corner_kind_and_pos(items[i]) for i in (i_bl, i_br, i_tl, i_tr)]
            kinds = [kp[0] for kp in kinds_pos]
            poss = [kp[1] for kp in kinds_pos]
            if (None in kinds or len(set(kinds)) != 1
                    or tuple(poss) != (0, 1, 2, 3)):
                continue
            kind = kinds[0]
            if kind == 'water':
                tile_id = 'WaterChiller_closed'
            elif kind == 'pool':
                tile_id = 'Pool_lv1'
            elif kind == 'bev':
                tile_id = 'BeverageChiller_closed'
            else:
                continue
            instance_id += 1
            tagged = f'{tile_id}#{instance_id}'
            # 4 角 (xx, yy, idx) 對應 (BL=0, BR=1, TL=2, TR=3)
            corner_positions = [
                (x, y, i_bl), (x + 1, y, i_br),
                (x, y + 1, i_tl), (x + 1, y + 1, i_tr),
            ]
            for xx, yy, idx in corner_positions:
                r = y_to_row(yy, H)
                middle[r][xx] = tagged
                used.add(xy_to_idx(xx, yy, W))
                # per-cell 瓶色（只對 BC）— 視覺左右 mirror,對齊官方畫面
                if kind == 'bev':
                    color = BEV_CHILLER_CORNER_COLOR.get(items[idx])
                    if color:
                        mirror_xx = (x + 1) if xx == x else x
                        bottle_colors_layer[r][mirror_xx] = color
                        beverage_colors.add(color)

    # 2) 單格 items
    hole_count = 0
    for idx, item_id in enumerate(items):
        if idx in used:
            continue
        if item_id == 0:
            continue
        if item_id in (12, 13):
            # Hole / BlockHole → 我們的 void（不存在的格）
            x, y = idx_to_xy(idx, W)
            r, c = y_to_row(y, H), x
            middle[r][c] = 'void'
            hole_count += 1
            continue
        if item_id in SILENT_OFFICIAL_IDS:
            continue
        if item_id in UNSUPPORTED_OFFICIAL_IDS:
            x, y = idx_to_xy(idx, W)
            warnings.append(
                f'item id {item_id} at (x={x},y={y}) — 我們未實作（{_official_name(item_id)}）,跳過'
            )
            continue
        # 散落的 chiller / pool corner（不在 2x2 內）→ 警告但不放
        if item_id in WATER_CHILLER_CORNERS or item_id in BEV_CHILLER_CORNER_COLOR or item_id in POOL_CORNERS:
            x, y = idx_to_xy(idx, W)
            warnings.append(
                f'item id {item_id} at (x={x},y={y}) — 落單的 chiller/pool 角,'
                f'非完整 2x2,跳過'
            )
            continue

        if item_id not in SINGLE_OFFICIAL_TO_TILE:
            x, y = idx_to_xy(idx, W)
            warnings.append(f'未知 item id {item_id} at (x={x},y={y}), 跳過')
            continue
        tile_id, layer = SINGLE_OFFICIAL_TO_TILE[item_id]
        if tile_id is None:
            continue   # RandomMatch — 由 fill 機制處理
        x, y = idx_to_xy(idx, W)
        r, c = y_to_row(y, H), x
        if layer == 'middle':
            middle[r][c] = tile_id
        elif layer == 'upper':
            upper[r][c] = tile_id
        elif layer == 'bottom':
            bottom[r][c] = tile_id

    # Hole/BlockHole 已正確標為 void,不發 warning（純資訊型）

    # 3) Cells modifier (Puddle/Mud/Rope) — 比 items 優先（如果衝突發 warning）
    for idx, cell in enumerate(cells_off):
        x, y = idx_to_xy(idx, W)
        r, c = y_to_row(y, H), x
        if cell.get('Puddle'):
            lv = int(cell['Puddle'])
            if bottom[r][c] is None:
                bottom[r][c] = f'Puddle_lv{min(2, lv)}'
        if cell.get('Mud'):
            if upper[r][c] is None:
                upper[r][c] = 'Mud'
        if cell.get('Rope'):
            if upper[r][c] is None:
                upper[r][c] = f'Rope_lv{int(cell["Rope"])}'

    # 4) Goals — Goal ID 不等於 item ID,要用 family 對應表轉。
    # 我們把 goal 用 family prefix 表示(例: "Crt", "Puddle") 不再拆成 Crt1/Crt2,
    # 顯示時就是「紙箱 0/94」一條線(不會出現兩條同名 "紙箱"),
    # game_manager 端會用 tile_id prefix 比對 → 任何 Crt 被清都會 +1。
    goals: dict[str, int] = {}
    obs_counts = _count_clearable(middle, upper, bottom)
    for g in official.get('Goals', []):
        family = GOAL_ID_TO_FAMILY.get(g['Goal'])
        target = int(g['Count'])
        if family:
            # 直接用 family 名作為 tile_id key(_resolve_obstacle_type 會匹配前綴)
            goals[family] = goals.get(family, 0) + target
        else:
            # 完全沒對到 → fallback heuristic(以前的行為)
            inferred = _infer_goal(g['Goal'], target, obs_counts, warnings)
            for tid, n in inferred.items():
                goals[tid] = goals.get(tid, 0) + n
            if not inferred:
                warnings.append(f'Goal id {g["Goal"]} Count={target} — 沒對應 family,跳過')

    # 5) Limits → max_steps
    max_steps = 30
    for lim in official.get('Limits', []):
        lim_kind = lim.get('Limit', 0)
        if lim_kind == 0:
            max_steps = lim.get('Count', 30)
            break
        warnings.append(f'Limit kind={lim_kind} 不支援,沿用預設 max_steps')

    # 6) Colors
    colors = official.get('Colors', [1, 2, 3, 4])
    num_colors = len(colors)

    out = {
        'name': official.get('Name', f'Imported_Level_{official.get("Number", "X")}'),
        'description': f'匯入自官方關卡 #{official.get("Number", "")}',
        'rows': H,
        'cols': W,
        'num_colors': num_colors,
        'max_steps': max_steps,
        'goals': goals,
        'board': {
            'middle': middle,
            'upper': upper,
            'bottom': bottom,
        },
    }
    if any(any(c) for c in bottle_colors_layer):
        out['board']['bottle_colors'] = bottle_colors_layer
    if beverage_colors:
        out['beverage_colors'] = sorted(beverage_colors)

    # 7) Spawners — Sets 中含障礙 ID (>=21) 的 Set，配合 FillType=1 的 spawn points
    spawners = _parse_spawners(official, W, H)
    if spawners:
        out['spawners'] = spawners

    return out, warnings


def _is_clearable_obstacle(tile_id: str) -> bool:
    """是否為「可消除的障礙物」"""
    obstacle_prefixes = (
        'Crt', 'Barrel', 'TrafficCone', 'SalmonCan',
        'WaterChiller', 'BeverageChiller', 'Pool', 'Stamp',
        'Puddle', 'Mud', 'Rope',
    )
    return tile_id.startswith(obstacle_prefixes)


def _parse_spawners(official: dict, W: int, H: int) -> list[dict]:
    """
    解析官方 Sets，產出 spawner 列表。
    每個 spawner = {
      "spawn_cols": [col indices where this set can spawn],
      "elements": [{"tile_id": "Barrel", "ratio": 1}, ...],
      "set_ratio": int
    }
    只回傳含有障礙物 (Id >= 21) 的 Set。
    """
    sets = official.get('Sets', [])
    grid = official.get('Grid', {})
    cells_off = grid.get('Cells', [])

    # 找出 FillType == 1 的 cell idx → (col, row) in our format
    fill_cells = set()
    for idx, cell in enumerate(cells_off):
        if cell.get('FillType') == 1:
            fill_cells.add(idx)

    spawners = []
    # 計算每個 TargetFills 區域內的總 CreateRatio（含普通糖果 Set）
    # 用來做機率競爭
    for s in sets:
        elements = s.get('Elements', [])
        has_obstacle = any(e.get('Id', 0) >= 21 for e in elements)
        if not has_obstacle:
            continue

        target_fills = s.get('TargetFills', [])
        spawn_cols = set()
        for idx in target_fills:
            if idx in fill_cells and idx < W * H:
                x, y = idx_to_xy(idx, W)
                spawn_cols.add(x)

        if not spawn_cols:
            continue

        # 找同 TargetFills 的所有 Set 的 CreateRatio 加總
        total_weight = 0
        for other_s in sets:
            if other_s.get('TargetFills', []) == target_fills:
                total_weight += other_s.get('CreateRatio', 1)

        elems_out = []
        for e in elements:
            eid = e.get('Id', 0)
            ratio = e.get('CreateRatio', 1)
            tile_info = SINGLE_OFFICIAL_TO_TILE.get(eid)
            if tile_info and tile_info[0]:
                elems_out.append({
                    'tile_id': tile_info[0],
                    'ratio': ratio,
                })

        if not elems_out:
            continue

        spawners.append({
            'spawn_cols': sorted(spawn_cols),
            'elements': elems_out,
            'set_ratio': s.get('CreateRatio', 1),
            'total_weight': total_weight,
        })

    return spawners


def _count_clearable(
    middle: list[list[Optional[str]]],
    upper: list[list[Optional[str]]],
    bottom: list[list[Optional[str]]],
) -> Counter:
    """
    數盤上每種可消障礙物的「物件數」。
    多格 instance（chiller/pool）按 1 個算,不重複計每一格。
    """
    counts: Counter[str] = Counter()
    seen_instances: set[str] = set()
    for layer in (middle, upper, bottom):
        for row in layer:
            for t in row:
                if not t:
                    continue
                if '#' in t:
                    if t in seen_instances:
                        continue
                    seen_instances.add(t)
                    base = t.split('#')[0]
                else:
                    base = t
                if _is_clearable_obstacle(base):
                    counts[base] += 1
    return counts


def _infer_goal(
    gid: int,
    target_count: int,
    obs_counts: Counter,
    warnings: list[str],
) -> dict[str, int]:
    """
    Goal ID 不等於 item ID,且 enum 沒明確定義。
    策略:
    1. 若盤上有 hint family（如 Goal 12 暗示 Carton）且總數等於 target,使用該 family
    2. 若有單一 obstacle 數量恰好 = target,直接用該 tile
    3. 否則按比例分配
    """
    hint = GOAL_HINT.get(gid)
    if hint:
        family_counts = {
            tid: cnt for tid, cnt in obs_counts.items() if tid.startswith(hint)
        }
        family_total = sum(family_counts.values())
        if family_total == target_count and family_counts:
            return dict(family_counts)

    exact = [tid for tid, cnt in obs_counts.items() if cnt == target_count]
    if exact:
        return {exact[0]: target_count}

    total = sum(obs_counts.values())
    if total == 0:
        warnings.append(
            f'Goal id {gid} Count={target_count} — 盤上沒障礙物,無法推算,略過'
        )
        return {}

    # 盤上 obstacles 總和正好等於目標 → 直接複製整盤,無警告
    if total == target_count:
        return dict(obs_counts)

    result: dict[str, int] = {}
    remaining = target_count
    items_sorted = obs_counts.most_common()
    for i, (tid, cnt) in enumerate(items_sorted):
        if i == len(items_sorted) - 1:
            result[tid] = max(0, remaining)
        else:
            n = round(target_count * cnt / total)
            result[tid] = n
            remaining -= n
    warnings.append(
        f'Goal id {gid} Count={target_count} — 盤上有 {dict(obs_counts)},'
        f'按比例推算成 {result}'
    )
    return result


def _official_name(off_id: int) -> str:
    """除錯用：官方 ID 的可讀名稱"""
    names = {
        12: 'Hole', 13: 'BlockHole', 20: 'Coin', 57: 'Roadblock',
        67: 'SafeBL', 68: 'SafeBR', 69: 'SafeTL', 70: 'SafeTR',
        59: 'SalmonCan2', 60: 'SalmonCan3', 66: 'Mud2', 94: 'TrafficCone3',
    }
    return names.get(off_id, f'id={off_id}')


# ===========================================================================
# Export: 我們 → 官方
# ===========================================================================

def ours_to_official(ours: dict) -> tuple[dict, list[str]]:
    """
    把我們的關卡 JSON 轉成官方格式。
    回傳 (official_dict, warnings_list)。
    """
    warnings: list[str] = []
    H = int(ours['rows'])
    W = int(ours['cols'])

    items = [0] * (H * W)
    cells_off = [
        {'FillType': 0, 'Puddle': 0, 'Mud': 0, 'Curtain': 0,
         'PurpleGrass': 0, 'Rope': 0}
        for _ in range(H * W)
    ]

    board = ours.get('board') or {}
    if isinstance(board, list):
        middle = board
        upper = None
        bottom = None
    else:
        middle = board.get('middle')
        upper = board.get('upper')
        bottom = board.get('bottom')

    # 1) 處理 instance 群組（2x2）
    used_idx: set[int] = set()
    instances: dict[tuple[str, str], list[tuple[int, int]]] = {}
    if middle:
        for r in range(min(H, len(middle))):
            for c in range(min(W, len(middle[r]))):
                t = middle[r][c]
                if isinstance(t, str) and '#' in t:
                    base, tag = t.rsplit('#', 1)
                    instances.setdefault((base, tag), []).append((r, c))

    beverage_color = None
    bc = ours.get('beverage_colors')
    if bc:
        beverage_color = bc[0] if isinstance(bc, list) else str(bc)

    for (base, tag), positions in instances.items():
        quad = _quad_for(base, beverage_color)
        if quad is None or len(positions) != 4:
            warnings.append(
                f'instance {base}#{tag} 有 {len(positions)} 格 — '
                f'無法輸出成 2x2,改用單格'
            )
            continue
        rs = sorted(set(r for r, _ in positions))
        cs = sorted(set(c for _, c in positions))
        if len(rs) != 2 or rs[1] - rs[0] != 1 or len(cs) != 2 or cs[1] - cs[0] != 1:
            warnings.append(
                f'instance {base}#{tag} 不是相鄰 2x2,改用單格'
            )
            continue
        r_top, r_bot = rs
        c_left, c_right = cs
        # 官方: BL=(c_left, y_low), TR=(c_right, y_high)
        y_low = row_to_y(r_bot, H)
        y_high = row_to_y(r_top, H)
        i_bl = xy_to_idx(c_left, y_low, W)
        i_br = xy_to_idx(c_right, y_low, W)
        i_tl = xy_to_idx(c_left, y_high, W)
        i_tr = xy_to_idx(c_right, y_high, W)
        items[i_bl], items[i_br], items[i_tl], items[i_tr] = quad
        for r, c in positions:
            used_idx.add(xy_to_idx(c, row_to_y(r, H), W))

    # 2) 單格物件
    for r in range(H):
        for c in range(W):
            x = c
            y = row_to_y(r, H)
            idx = xy_to_idx(x, y, W)
            if idx in used_idx:
                continue

            # middle
            mid_val = (
                middle[r][c]
                if middle and r < len(middle) and c < len(middle[r]) and middle[r][c]
                else None
            )
            if mid_val == 'void':
                items[idx] = 12  # Hole
                continue
            if mid_val:
                base = mid_val.split('#')[0] if '#' in mid_val else mid_val
                off = TILE_TO_SINGLE_OFFICIAL.get(base)
                if off is None:
                    warnings.append(f'tile {base} at row={r},col={c} 沒對應官方 ID,留空')
                else:
                    items[idx] = off
            else:
                # 中層空 → RandomMatch（讓官方遊戲填隨機元素）
                items[idx] = 15

            # upper
            if upper and r < len(upper) and c < len(upper[r]) and upper[r][c]:
                t = upper[r][c]
                if t == 'Mud':
                    cells_off[idx]['Mud'] = 1
                elif t.startswith('Rope_lv'):
                    try:
                        cells_off[idx]['Rope'] = int(t.split('lv')[-1])
                    except ValueError:
                        pass

            # bottom
            if bottom and r < len(bottom) and c < len(bottom[r]) and bottom[r][c]:
                t = bottom[r][c]
                if t.startswith('Puddle_lv'):
                    try:
                        lv = int(t.split('lv')[-1])
                        cells_off[idx]['Puddle'] = min(2, lv)
                        if lv > 2:
                            warnings.append(
                                f'Puddle_lv{lv} at row={r},col={c} 被截斷成 lv2 (官方只支援 lv1/2)'
                            )
                    except ValueError:
                        pass

    # 3) FillType: 頂排空格設為 1，且填入 RandomMatch(15)
    target_fills: list[int] = []
    for x in range(W):
        idx = xy_to_idx(x, H - 1, W)
        if items[idx] in (0, 15):
            cells_off[idx]['FillType'] = 1
            items[idx] = 15
            target_fills.append(idx)

    # 4) Goals — 我們的 tile_id → 官方 Goal ID
    # 多格物件（WaterChiller / BeverageChiller / Pool）沒單格 item ID,
    # 用最相近的 hint：Pool->20, Carton family->12, Barrel->16, etc.
    tile_to_goal_id = {
        'Crt1': 21, 'Crt2': 22, 'Crt3': 23, 'Crt4': 24,
        'Puddle_lv1': 25, 'Puddle_lv2': 26,
        'Stamp': 31, 'Barrel': 32, 'SalmonCan': 58,
        'TrafficCone_lv1': 92, 'TrafficCone_lv2': 93,
        'Mud': 65,
        # 多格物件 → 用 Goal hint 中最近的代表 ID
        'Pool_lv1': 20, 'Pool_lv2': 20, 'Pool_lv3': 20,
        'Pool_lv4': 20, 'Pool_lv5': 20,
        'WaterChiller_closed': 27,
        'BeverageChiller_closed': 33,
    }
    goal_off_list = []
    for tid, count in (ours.get('goals') or {}).items():
        off = tile_to_goal_id.get(tid)
        if off is None:
            warnings.append(f'Goal tile {tid} ×{count} 沒對應官方 Goal ID,略過')
            continue
        goal_off_list.append({
            'BoardId': 0,
            'Goal': off,
            'Count': int(count),
            'IsFromSettings': False,
        })

    # 5) Sets — 用我們的 num_colors 推一個預設集
    num_colors = int(ours.get('num_colors', 4))
    color_ids = list(range(1, num_colors + 1))   # 1=Blue, 2=Green, 3=Red, 4=Yellow, 5=Purple, 6=Orange
    sets = [{
        'Name': 'Set1',
        'Elements': [
            {'Id': cid, 'CreateRatio': 1, 'Count': 0}
            for cid in color_ids
        ],
        'CanFall': True,
        'CreateRatio': 1,
        'TargetFills': target_fills,
        'MaxItemCounts': [],
    }]

    out = {
        'Number': int(ours.get('number', 0)),
        'Name': ours.get('name', 'Exported_Level'),
        'Colors': color_ids,
        'Limits': [{
            'BoardId': 0,
            'Limit': 0,
            'Count': int(ours.get('max_steps', 30)),
        }],
        'Goals': goal_off_list,
        'Counts': [],
        'Sets': sets,
        'Predefined': [],
        'Grid': {
            'Items': items,
            'Cells': cells_off,
            'Width': W,
            'Height': H,
        },
        'Paths': [],
        'Collected': [],
        'Groups': [],
        'Drills': [],
        'LightbulbColorOrder': [],
        'PouchConfig': None,
    }
    return out, warnings


def _quad_for(base_tile: str, beverage_color: Optional[str]) -> Optional[tuple[int, int, int, int]]:
    """根據 base tile + 飲料櫃顏色,回傳 4 個 corner ID"""
    if base_tile.startswith('Pool'):
        return POOL_QUAD
    if base_tile == 'WaterChiller_closed':
        return TILE_COLOR_TO_QUAD[('WaterChiller_closed', None)]
    if base_tile == 'BeverageChiller_closed':
        color = beverage_color or 'Blue'
        return TILE_COLOR_TO_QUAD.get(
            ('BeverageChiller_closed', color),
            TILE_COLOR_TO_QUAD[('BeverageChiller_closed', 'Blue')]
        )
    return None


# ===========================================================================
# CLI
# ===========================================================================

def _import_dir(src: pathlib.Path, dst: pathlib.Path) -> None:
    """批次匯入：src 內所有 *.json → dst 內。"""
    files = sorted(src.glob('*.json'))
    if not files:
        print(f'[ERROR] {src} 內沒有 *.json')
        return
    dst.mkdir(parents=True, exist_ok=True)

    ok = 0
    warn = 0
    fail = 0
    summary_lines = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                official = json.load(fh)
            our, warnings = official_to_ours(official)
            # 輸出檔名：Level_046.json（三位數零填充，大寫 L）
            num_match = re.search(r'(\d+)', f.stem)
            if num_match:
                out_name = f'Level_{int(num_match.group(1)):03d}.json'
            else:
                out_name = f.name
            out_path = dst / out_name
            with open(out_path, 'w', encoding='utf-8') as fh:
                json.dump(our, fh, ensure_ascii=False, indent=2)
            if warnings:
                warn += 1
                summary_lines.append(f'⚠️  {f.name} ({len(warnings)} warnings)')
                for w in warnings:
                    summary_lines.append(f'    - {w}')
            else:
                ok += 1
        except Exception as e:
            fail += 1
            summary_lines.append(f'❌ {f.name}: {e}')

    print('\n'.join(summary_lines))
    print(f'\n=== 匯入完成 ===')
    print(f'  ✅ 完美 {ok} 關 / ⚠️  有警告 {warn} 關 / ❌ 失敗 {fail} 關')
    print(f'  輸出資料夾: {dst}')


def _export_file(src: pathlib.Path, dst: pathlib.Path) -> None:
    with open(src, 'r', encoding='utf-8') as fh:
        ours = json.load(fh)
    official, warnings = ours_to_official(ours)
    with open(dst, 'w', encoding='utf-8') as fh:
        json.dump(official, fh, ensure_ascii=False, indent=2)
    print(f'✅ 已輸出: {dst}')
    for w in warnings:
        print(f'  ⚠️  {w}')


def _report_dir(src: pathlib.Path) -> None:
    """只跑一遍轉換，不寫檔，列出哪些有警告/失敗。"""
    files = sorted(src.glob('*.json'))
    cats: dict[str, list[str]] = {'ok': [], 'warn': [], 'fail': []}
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                official = json.load(fh)
            _, warnings = official_to_ours(official)
            if warnings:
                cats['warn'].append((f.name, warnings))
            else:
                cats['ok'].append(f.name)
        except Exception as e:
            cats['fail'].append((f.name, str(e)))

    print(f'\n=== 報告 ({len(files)} 關) ===')
    print(f'✅ 完美匯入: {len(cats["ok"])} 關')
    print(f'⚠️  有警告: {len(cats["warn"])} 關')
    print(f'❌ 失敗: {len(cats["fail"])} 關')

    print('\n--- 警告分類（前 20）---')
    warn_counter: Counter[str] = Counter()
    for _, ws in cats['warn']:
        for w in ws:
            # 只取 warning 類型（字首到第一個底線/數字之前）
            key = w.split(',')[0][:80]
            warn_counter[key] += 1
    for w, n in warn_counter.most_common(20):
        print(f'  {n:>3}× {w}')

    if cats['fail']:
        print('\n--- 失敗 ---')
        for name, err in cats['fail']:
            print(f'  ❌ {name}: {err}')


def main():
    p = argparse.ArgumentParser(description='官方 ↔ 我們的關卡格式轉換')
    sub = p.add_subparsers(dest='cmd', required=True)

    imp = sub.add_parser('import', help='官方 → 我們（單檔或整個資料夾）')
    imp.add_argument('src', type=pathlib.Path)
    imp.add_argument('-o', '--output', type=pathlib.Path, required=True)

    exp = sub.add_parser('export', help='我們 → 官方（單檔）')
    exp.add_argument('src', type=pathlib.Path)
    exp.add_argument('-o', '--output', type=pathlib.Path, required=True)

    rep = sub.add_parser('report', help='跑一遍報告（不寫檔）')
    rep.add_argument('src', type=pathlib.Path)

    args = p.parse_args()
    if args.cmd == 'import':
        if args.src.is_dir():
            _import_dir(args.src, args.output)
        else:
            with open(args.src, 'r', encoding='utf-8') as fh:
                official = json.load(fh)
            our, warnings = official_to_ours(official)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, 'w', encoding='utf-8') as fh:
                json.dump(our, fh, ensure_ascii=False, indent=2)
            print(f'✅ 已輸出: {args.output}')
            for w in warnings:
                print(f'  ⚠️  {w}')
    elif args.cmd == 'export':
        _export_file(args.src, args.output)
    elif args.cmd == 'report':
        _report_dir(args.src)


if __name__ == '__main__':
    main()
