"""
Match3 AI Player — 對齊 ../match3_AI/match3_ai.py 的完整策略

決策流程（同原版）：
  1. 普通消除 (Match-3)：掃描所有可 swap → 模擬 swap 後算消除分
  2. 道具組合：偵測相鄰道具對，計算精確 combo 爆炸效益
  3. 戰術移動：將道具移到更好位置再引爆（扣移動成本）
  4. 單點道具：直接點擊引爆（殘局/斬殺免成本）

共用設定：讀取 ai_weights.json（Python 和 GDScript 共用同一份）

主要介面：
  find_best_action(env) -> action_dict | None
"""

from __future__ import annotations
import json
import sys
import pathlib
import random
from typing import Optional

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import match_engine
from tile_defs import is_powerup, is_obstacle, is_movable

# === 載入共用權重 ===
_WEIGHTS_PATH = _PROJECT_ROOT / 'ai_weights.json'
if _WEIGHTS_PATH.exists():
    with open(_WEIGHTS_PATH, encoding='utf-8') as _f:
        _W = json.load(_f)
else:
    _W = {}

WEIGHT_ELEMENT = _W.get('weight_element', 1)
WEIGHT_OBSTACLE = _W.get('weight_obstacle', 5)
WEIGHT_GOAL_OBSTACLE = _W.get('weight_goal_obstacle', 20)
BONUS_LTBL = _W.get('bonus_ltbl', 15)
BONUS_TNT = _W.get('bonus_tnt', 8)
BONUS_SODA = _W.get('bonus_soda', 5)
BONUS_TRPR = _W.get('bonus_trpr', 6)
COST_NORMAL_PROP = _W.get('cost_normal_prop', 2)
COST_RAINBOW = _W.get('cost_rainbow', 10)
ENDGAME_OBSTACLE_THRESHOLD = _W.get('endgame_obstacle_threshold', 10)
_COMBO = _W.get('combo_scores', {})


# ===========================================================================
# Public API
# ===========================================================================

def _reason_for(action: dict, board) -> str:
    """推論一個動作的「決策類別」(給報表/解說用,不影響選擇)。"""
    if action.get('type') == 'activate':
        return '啟動道具'
    p1 = action.get('pos1'); p2 = action.get('pos2')
    t1 = board.get_middle(*p1) if p1 else None
    t2 = board.get_middle(*p2) if p2 else None
    id1 = t1.tile_id if t1 else ''
    id2 = t2.tile_id if t2 else ''
    if is_powerup(id1) and is_powerup(id2):
        return '道具合成'
    if id1 == 'LtBl' or id2 == 'LtBl':
        return '紙風車炸色'
    if is_powerup(id1) or is_powerup(id2):
        return '戰術佈局'
    return '消除得分'


def find_best_action(env, *, rng: Optional[random.Random] = None, explain: bool = False):
    """選最佳動作。explain=False(預設)回傳 action dict(或 None);
    explain=True 回傳 (action, score, reason) 供報表/解說使用。"""
    if rng is None:
        rng = random

    board = env.board
    goals_required = env.goals_required or {}
    rows, cols = board.rows, board.cols

    total_goal_obstacles = _count_goal_obstacles_on_board(board, goals_required)
    is_endgame = total_goal_obstacles <= ENDGAME_OBSTACLE_THRESHOLD

    candidates: list[tuple[float, dict]] = []

    # ---- 1. 窮舉所有 swap 並評分 ----
    for r in range(rows):
        for c in range(cols):
            for dr, dc in [(0, 1), (1, 0)]:
                nr, nc = r + dr, c + dc
                if nr >= rows or nc >= cols:
                    continue
                if not _can_swap_safe(board, r, c, nr, nc):
                    continue

                t1 = board.get_middle(r, c)
                t2 = board.get_middle(nr, nc)

                # --- 2. 道具組合 (精確 combo) ---
                if t1 and t2 and is_powerup(t1.tile_id) and is_powerup(t2.tile_id):
                    score = _evaluate_powerup_combo(
                        board, r, c, nr, nc, t1.tile_id, t2.tile_id,
                        goals_required, is_endgame, total_goal_obstacles,
                    )
                    if score > 0:
                        candidates.append((score, {'type': 'swap', 'pos1': (r, c), 'pos2': (nr, nc)}))
                    continue

                # LtBl + element
                if t1 and t2:
                    if t1.tile_id == 'LtBl' and not is_powerup(t2.tile_id):
                        score = _evaluate_ltbl_element(board, r, c, t2, goals_required, is_endgame)
                        if score > 0:
                            candidates.append((score, {'type': 'swap', 'pos1': (r, c), 'pos2': (nr, nc)}))
                        continue
                    if t2.tile_id == 'LtBl' and not is_powerup(t1.tile_id):
                        score = _evaluate_ltbl_element(board, nr, nc, t1, goals_required, is_endgame)
                        if score > 0:
                            candidates.append((score, {'type': 'swap', 'pos1': (r, c), 'pos2': (nr, nc)}))
                        continue

                # --- 3. 戰術移動（道具 + 非道具 swap）---
                if t1 and is_powerup(t1.tile_id) and t1.tile_id != 'LtBl' and t2 and not is_powerup(t2.tile_id):
                    tac_score = _evaluate_tactical_move(
                        board, r, c, nr, nc, t1.tile_id,
                        goals_required, is_endgame, total_goal_obstacles,
                    )
                    if tac_score > 0:
                        candidates.append((tac_score, {'type': 'swap', 'pos1': (r, c), 'pos2': (nr, nc)}))
                    # 即使戰術移動有分，也繼續看 match 分

                if t2 and is_powerup(t2.tile_id) and t2.tile_id != 'LtBl' and t1 and not is_powerup(t1.tile_id):
                    tac_score = _evaluate_tactical_move(
                        board, nr, nc, r, c, t2.tile_id,
                        goals_required, is_endgame, total_goal_obstacles,
                    )
                    if tac_score > 0:
                        candidates.append((tac_score, {'type': 'swap', 'pos1': (r, c), 'pos2': (nr, nc)}))

                # --- 普通 match 評分 ---
                score = _evaluate_swap(board, r, c, nr, nc, goals_required)
                if score > 0:
                    candidates.append((score, {'type': 'swap', 'pos1': (r, c), 'pos2': (nr, nc)}))

    # ---- 4. 道具直接啟動 ----
    for r in range(rows):
        for c in range(cols):
            tile = board.get_middle(r, c)
            if tile is None or not is_powerup(tile.tile_id):
                continue
            score = _evaluate_powerup_activate(
                board, r, c, goals_required, is_endgame, total_goal_obstacles,
            )
            if score > 0:
                candidates.append((score, {'type': 'activate', 'pos': (r, c)}))

    if not candidates:
        return (None, 0.0, '') if explain else None

    # 取最高分（同分隨機）
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_score = candidates[0][0]
    top = [c for c in candidates if c[0] == top_score]
    chosen = rng.choice(top)
    if explain:
        return chosen[1], chosen[0], _reason_for(chosen[1], board)
    return chosen[1]


# ===========================================================================
# Swap 評分（普通 match）
# ===========================================================================

def _evaluate_swap(board, r1, c1, r2, c2, goals_required) -> float:
    board.swap(r1, c1, r2, c2)
    try:
        matches = match_engine.find_matches(board)
        if not matches:
            return -1.0
        return _score_matches(matches, board, goals_required)
    finally:
        board.swap(r1, c1, r2, c2)


def _score_matches(matches, board, goals_required) -> float:
    score = 0.0
    rows, cols = board.rows, board.cols

    for mg in matches:
        score += len(mg.positions) * WEIGHT_ELEMENT

        for (r, c) in mg.positions:
            cell = board.get_cell(r, c)
            if cell.bottom is not None:
                tid = cell.bottom.tile_id
                score += WEIGHT_GOAL_OBSTACLE if _is_goal_tile(tid, goals_required) else WEIGHT_OBSTACLE
            # upper layer (Rope/Mud inplace)
            if cell.upper is not None:
                tid = cell.upper.tile_id
                score += WEIGHT_GOAL_OBSTACLE if _is_goal_tile(tid, goals_required) else WEIGHT_OBSTACLE
            # 4-neighbor obstacles
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                ncell = board.get_cell(nr, nc)
                if ncell.middle is not None and is_obstacle(ncell.middle.tile_id):
                    tid = ncell.middle.tile_id
                    score += WEIGHT_GOAL_OBSTACLE if _is_goal_tile(tid, goals_required) else WEIGHT_OBSTACLE
                if ncell.upper is not None:
                    tid = ncell.upper.tile_id
                    score += WEIGHT_GOAL_OBSTACLE if _is_goal_tile(tid, goals_required) else WEIGHT_OBSTACLE

        # 道具合成獎勵
        pattern = getattr(mg, 'pattern', None)
        if pattern == 'FIVE_PLUS':
            score += BONUS_LTBL
        elif pattern == 'L_T':
            score += BONUS_TNT
        elif pattern in ('FOUR_H', 'FOUR_V'):
            score += BONUS_SODA
        elif pattern == 'BLOCK_2x2':
            score += BONUS_TRPR

    return score


# ===========================================================================
# 道具 Combo 精確評分（對齊 match3_AI）
# ===========================================================================

def _get_powerup_type(tile_id: str) -> Optional[str]:
    if tile_id == 'LtBl':
        return 'RAINBOW'
    if tile_id == 'TNT':
        return 'BOMB'
    if tile_id in ('Soda0d', 'Soda90'):
        return 'ROCKET'
    if tile_id == 'TrPr':
        return 'PROPELLER'
    return None


def _evaluate_powerup_combo(
    board, r1, c1, r2, c2, pid1, pid2,
    goals_required, is_endgame, total_goal_obstacles,
) -> float:
    t1 = _get_powerup_type(pid1)
    t2 = _get_powerup_type(pid2)
    if not t1 or not t2:
        return 0

    # Rainbow + 任何道具 = 999（全屏清除級）
    if t1 == 'RAINBOW' or t2 == 'RAINBOW':
        other = t2 if t1 == 'RAINBOW' else t1
        if other in ('BOMB', 'ROCKET', 'PROPELLER', 'RAINBOW'):
            return _COMBO.get('rainbow_rainbow', 999)

    # 標的中心（combo 爆炸中心）
    center_r, center_c = r2, c2
    rows, cols = board.rows, board.cols
    types = sorted([t1, t2])

    if types == ['BOMB', 'BOMB']:
        area = _get_area_cells(center_r, center_c, '7x7', rows, cols)
    elif types == ['BOMB', 'ROCKET']:
        area = _get_area_cells(center_r, center_c, 'cross_3', rows, cols)
    elif types == ['ROCKET', 'ROCKET']:
        area = _get_area_cells(center_r, center_c, 'cross_1', rows, cols)
    elif 'PROPELLER' in types:
        other = types[0] if types[1] == 'PROPELLER' else types[1]
        base_area = _get_area_cells(center_r, center_c, '1x1_cross', rows, cols)
        base_score = _count_obstacles_in_cells(board, base_area, goals_required)
        if other == 'PROPELLER':
            return base_score + _COMBO.get('propeller_propeller_bonus', 3)
        elif other == 'BOMB':
            best = _scan_best_impact(board, '5x5', goals_required)
            return base_score + best
        elif other == 'ROCKET':
            best = _scan_best_impact(board, 'line', goals_required)
            return base_score + best
        return base_score
    else:
        return 35  # fallback

    score = _count_obstacles_in_cells(board, area, goals_required)

    # 斬殺：如果這一步能清完所有目標障礙物，免成本
    is_lethal = score >= total_goal_obstacles
    penalty = 0 if (is_endgame or is_lethal) else COST_NORMAL_PROP * 2
    return max(0, score - penalty)


def _evaluate_tactical_move(
    board, prop_r, prop_c, dest_r, dest_c, prop_id,
    goals_required, is_endgame, total_goal_obstacles,
) -> float:
    """道具移到新位置後的引爆效益 - 移動成本"""
    # 模擬 swap 後，道具在 (dest_r, dest_c)
    impact = _estimate_powerup_impact_at(board, dest_r, dest_c, prop_id, goals_required)

    # 也算原本位置的 match 分（交換後另一邊可能產生 match）
    board.swap(prop_r, prop_c, dest_r, dest_c)
    try:
        matches = match_engine.find_matches(board)
        match_score = _score_matches(matches, board, goals_required) if matches else 0
    finally:
        board.swap(prop_r, prop_c, dest_r, dest_c)

    best_val = max(impact, match_score)
    is_lethal = best_val >= total_goal_obstacles
    penalty = 0 if (is_endgame or is_lethal) else COST_NORMAL_PROP
    return max(0, best_val - penalty)


# ===========================================================================
# 道具啟動評分
# ===========================================================================

def _evaluate_powerup_activate(board, r, c, goals_required, is_endgame, total_goal_obstacles) -> float:
    tile = board.get_middle(r, c)
    if tile is None:
        return -1
    pid = tile.tile_id

    raw_score = _estimate_powerup_impact_at(board, r, c, pid, goals_required)

    is_lethal = raw_score >= total_goal_obstacles
    penalty = 0 if (is_endgame or is_lethal) else (
        COST_RAINBOW if pid == 'LtBl' else COST_NORMAL_PROP
    )
    return max(0, raw_score - penalty)


def _estimate_powerup_impact_at(board, r, c, pid, goals_required) -> float:
    rows, cols = board.rows, board.cols

    if pid == 'Soda0d':
        cells = [(r, cc) for cc in range(cols)]
    elif pid == 'Soda90':
        cells = [(rr, c) for rr in range(rows)]
    elif pid == 'TNT':
        cells = [(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)]
    elif pid == 'TrPr':
        cells = [(r + dr, c + dc) for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (0, 0)]]
    elif pid == 'LtBl':
        color_counts: dict = {}
        for rr in range(rows):
            for cc in range(cols):
                cell = board.get_cell(rr, cc)
                if cell.middle and cell.middle.color is not None:
                    color_counts[cell.middle.color] = color_counts.get(cell.middle.color, 0) + 1
        if not color_counts:
            return 0
        best_color = max(color_counts, key=color_counts.get)
        cells = []
        for rr in range(rows):
            for cc in range(cols):
                cell = board.get_cell(rr, cc)
                if cell.middle and cell.middle.color == best_color:
                    cells.append((rr, cc))
    else:
        return 0

    return _count_obstacles_in_cells(board, cells, goals_required)


def _evaluate_ltbl_element(board, ltbl_r, ltbl_c, element_tile, goals_required, is_endgame) -> float:
    color = element_tile.color
    if color is None:
        return 0
    rows, cols = board.rows, board.cols
    cells = []
    for r in range(rows):
        for c in range(cols):
            cell = board.get_cell(r, c)
            if cell.middle and cell.middle.color == color:
                cells.append((r, c))
    score = _count_obstacles_in_cells(board, cells, goals_required)
    # 清色本身也有基礎分
    score += len(cells) * WEIGHT_ELEMENT
    penalty = 0 if is_endgame else COST_RAINBOW
    return max(0, score - penalty)


# ===========================================================================
# Area / Impact helpers
# ===========================================================================

def _get_area_cells(center_r, center_c, area_type, rows, cols) -> list[tuple[int, int]]:
    cells = []
    if area_type == '7x7':
        for r in range(max(0, center_r - 3), min(rows, center_r + 4)):
            for c in range(max(0, center_c - 3), min(cols, center_c + 4)):
                cells.append((r, c))
    elif area_type == 'cross_3':
        for r in range(max(0, center_r - 1), min(rows, center_r + 2)):
            for c in range(cols):
                cells.append((r, c))
        for c in range(max(0, center_c - 1), min(cols, center_c + 2)):
            for r in range(rows):
                if (r, c) not in cells:
                    cells.append((r, c))
    elif area_type == 'cross_1':
        for c in range(cols):
            cells.append((center_r, c))
        for r in range(rows):
            if (r, center_c) not in cells:
                cells.append((r, center_c))
    elif area_type == '5x5':
        for r in range(max(0, center_r - 2), min(rows, center_r + 3)):
            for c in range(max(0, center_c - 2), min(cols, center_c + 3)):
                cells.append((r, c))
    elif area_type == '1x1_cross':
        cells.append((center_r, center_c))
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = center_r + dr, center_c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                cells.append((nr, nc))
    return cells


def _count_obstacles_in_cells(board, cells, goals_required) -> float:
    rows, cols = board.rows, board.cols
    score = 0.0
    counted = set()
    for (r, c) in cells:
        if not (0 <= r < rows and 0 <= c < cols):
            continue
        cell = board.get_cell(r, c)
        if cell.middle and is_obstacle(cell.middle.tile_id):
            key = (r, c, 'mid')
            if key not in counted:
                counted.add(key)
                tid = cell.middle.tile_id
                score += WEIGHT_GOAL_OBSTACLE if _is_goal_tile(tid, goals_required) else WEIGHT_OBSTACLE
        if cell.bottom:
            key = (r, c, 'bot')
            if key not in counted:
                counted.add(key)
                tid = cell.bottom.tile_id
                score += WEIGHT_GOAL_OBSTACLE if _is_goal_tile(tid, goals_required) else WEIGHT_OBSTACLE
        if cell.upper:
            key = (r, c, 'up')
            if key not in counted:
                counted.add(key)
                tid = cell.upper.tile_id
                score += WEIGHT_GOAL_OBSTACLE if _is_goal_tile(tid, goals_required) else WEIGHT_OBSTACLE
    return score


def _scan_best_impact(board, impact_type, goals_required) -> float:
    rows, cols = board.rows, board.cols
    max_score = 0.0
    if impact_type == '5x5':
        for r in range(rows):
            for c in range(cols):
                cells = _get_area_cells(r, c, '5x5', rows, cols)
                s = _count_obstacles_in_cells(board, cells, goals_required)
                if s > max_score:
                    max_score = s
    elif impact_type == 'line':
        for r in range(rows):
            cells = [(r, c) for c in range(cols)]
            s = _count_obstacles_in_cells(board, cells, goals_required)
            if s > max_score:
                max_score = s
        for c in range(cols):
            cells = [(r, c) for r in range(rows)]
            s = _count_obstacles_in_cells(board, cells, goals_required)
            if s > max_score:
                max_score = s
    return max_score


# ===========================================================================
# Helpers
# ===========================================================================

def _can_swap_safe(board, r1, c1, r2, c2) -> bool:
    try:
        return board.can_swap(r1, c1, r2, c2)
    except Exception:
        return False


def _is_goal_tile(tile_id: str, goals_required: dict) -> bool:
    if not goals_required:
        return False
    if tile_id in goals_required:
        return True
    for goal_id in goals_required:
        base_goal = goal_id.split('_lv')[0].rstrip('0123456789')
        base_tile = tile_id.split('_lv')[0].rstrip('0123456789')
        if base_goal == base_tile:
            return True
    return False


def _count_goal_obstacles_on_board(board, goals_required) -> int:
    if not goals_required:
        return 0
    count = 0
    for r in range(board.rows):
        for c in range(board.cols):
            cell = board.get_cell(r, c)
            for layer in (cell.upper, cell.middle, cell.bottom):
                if layer is not None and _is_goal_tile(layer.tile_id, goals_required):
                    count += 1
    return count
