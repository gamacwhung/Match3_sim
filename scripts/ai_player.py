"""
Match3 AI Player — Score-based 啟發式 AI(仿 ../match3_AI 的策略)

設計目標:
  - 用 Match3_sim 自己的 board / match_engine API,**不依賴** ../match3_AI 的 YOLO
    模組跟它特有的縮寫 tile_id(BRC_RYBE@5 那種)。
  - 仿照 match3_AI 的核心思路:
      1. 窮舉所有可 swap 的相鄰格 → 模擬 swap → 算消除分
      2. 額外掃描所有 powerup → 算直接活化分
      3. 套用 endgame / lethal 規則調整道具使用成本
      4. 取最高分動作回傳

評分權重表(可調):
  WEIGHT_ELEMENT       1     普通元素消除
  WEIGHT_OBSTACLE      5     消除一般障礙物
  WEIGHT_GOAL_OBSTACLE 20    消除目標障礙物(關卡 goals 內的)
  BONUS_LTBL          15     生成 5+ 連光球
  BONUS_TNT            8     生成 L/T 炸彈
  BONUS_SODA           5     生成 4 連火箭
  BONUS_TRPR           6     生成 2x2 紙飛機
  COST_NORMAL_PROP     2     非殘局 / 非斬殺 下,使用普通道具的成本
  COST_RAINBOW        10     非殘局 / 非斬殺 下,使用光球的成本

主要介面:
  find_best_action(env) -> action_dict | None
      回傳 {'type': 'swap', 'pos1': ..., 'pos2': ...} 或
            {'type': 'activate', 'pos': ...} 或 None(無可行動作)
"""

from __future__ import annotations
import sys
import pathlib
import random
from typing import Optional

# 把專案根目錄加到 sys.path,讓 scripts/ 內可以 import match_engine 等
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import match_engine
from tile_defs import is_powerup, is_obstacle, is_movable


# === 評分權重 ===
WEIGHT_ELEMENT = 1
WEIGHT_OBSTACLE = 5
WEIGHT_GOAL_OBSTACLE = 20

BONUS_LTBL = 15
BONUS_TNT = 8
BONUS_SODA = 5
BONUS_TRPR = 6

COST_NORMAL_PROP = 2
COST_RAINBOW = 10

# 殘局判定:場上總目標障礙物 ≤ 此值 → 道具不扣成本
ENDGAME_OBSTACLE_THRESHOLD = 10


# ===========================================================================
# Public API
# ===========================================================================

def find_best_action(env, *, rng: Optional[random.Random] = None) -> Optional[dict]:
    """
    對當前 env.board 狀態算最佳動作。
    
    Args:
        env: Match3Env 實例
        rng: 隨機數產生器(可選),用來在多個同分動作中隨機選
    
    Returns:
        action dict 給 env.step(),沒任何可行動作則 None
    """
    if rng is None:
        rng = random
    
    board = env.board
    goals_required = env.goals_required or {}
    
    # 計算殘局 / 斬殺判定基準
    total_goal_obstacles = _count_goal_obstacles_on_board(board, goals_required)
    is_endgame = total_goal_obstacles <= ENDGAME_OBSTACLE_THRESHOLD
    
    # ---- 1. 窮舉所有 swap 並評分 ----
    candidates: list[tuple[float, dict]] = []
    rows, cols = board.rows, board.cols
    for r in range(rows):
        for c in range(cols):
            for dr, dc in [(0, 1), (1, 0)]:  # 只往右/下,避免重複
                nr, nc = r + dr, c + dc
                if nr >= rows or nc >= cols:
                    continue
                if not _can_swap_safe(board, r, c, nr, nc):
                    continue
                score = _evaluate_swap(
                    board, r, c, nr, nc,
                    goals_required, is_endgame,
                )
                if score > 0:
                    candidates.append(
                        (score, {'type': 'swap', 'pos1': (r, c), 'pos2': (nr, nc)})
                    )
    
    # ---- 2. 道具直接啟動評分 ----
    for r in range(rows):
        for c in range(cols):
            tile = board.get_middle(r, c)
            if tile is None or not is_powerup(tile.tile_id):
                continue
            score = _evaluate_powerup_activate(
                board, r, c, goals_required, is_endgame,
            )
            if score > 0:
                candidates.append(
                    (score, {'type': 'activate', 'pos': (r, c)})
                )
    
    if not candidates:
        return None
    
    # ---- 3. 取最高分(同分隨機) ----
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_score = candidates[0][0]
    top = [c for c in candidates if c[0] == top_score]
    return rng.choice(top)[1]


# ===========================================================================
# Swap 評分
# ===========================================================================

def _evaluate_swap(board, r1, c1, r2, c2, goals_required, is_endgame) -> float:
    """
    模擬 swap → find_matches → 算消除分。不跑完整 resolve(避免 side effect)。
    
    為了效能:在 board 上暫時 swap,find_matches 後 swap back。
    """
    t1 = board.get_middle(r1, c1)
    t2 = board.get_middle(r2, c2)
    
    # 道具合成 — 視為高分動作(暫時不模擬具體效果,給固定加成)
    if t1 and t2 and is_powerup(t1.tile_id) and is_powerup(t2.tile_id):
        return _evaluate_powerup_combo(t1.tile_id, t2.tile_id, board, goals_required, is_endgame)
    
    # 道具 + 元素 swap(LtBl + Element 是特殊組合)
    if t1 and t2:
        if t1.tile_id == 'LtBl' and not is_powerup(t2.tile_id):
            return _evaluate_ltbl_element(board, r1, c1, t2, goals_required, is_endgame)
        if t2.tile_id == 'LtBl' and not is_powerup(t1.tile_id):
            return _evaluate_ltbl_element(board, r2, c2, t1, goals_required, is_endgame)
    
    # 暫時 swap → find_matches → 算分 → swap back
    board.swap(r1, c1, r2, c2)
    try:
        matches = match_engine.find_matches(board)
        if not matches:
            return -1.0  # 沒消除,白費一步
        score = _score_matches(matches, board, goals_required)
        # 若把道具 swap 出去 — 等同立即啟動它,額外加分(扣成本)
        # (但這比較複雜,簡化先省略,demo 用基本版)
        return score
    finally:
        board.swap(r1, c1, r2, c2)


def _score_matches(matches, board, goals_required) -> float:
    """對一個 match list 算總分。"""
    score = 0.0
    rows, cols = board.rows, board.cols
    
    for mg in matches:
        # 基本:消除元素分
        score += len(mg.positions) * WEIGHT_ELEMENT
        
        # 鄰邊障礙物 / 下層(Puddle)分數
        for (r, c) in mg.positions:
            # 該格 bottom layer(Puddle)— 原地消除
            cell = board.get_cell(r, c)
            if cell.bottom is not None:
                tid = cell.bottom.tile_id
                if _is_goal_tile(tid, goals_required):
                    score += WEIGHT_GOAL_OBSTACLE
                else:
                    score += WEIGHT_OBSTACLE
            # 4 鄰 obstacle
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                ncell = board.get_cell(nr, nc)
                if ncell.middle is not None and is_obstacle(ncell.middle.tile_id):
                    tid = ncell.middle.tile_id
                    if _is_goal_tile(tid, goals_required):
                        score += WEIGHT_GOAL_OBSTACLE
                    else:
                        score += WEIGHT_OBSTACLE
                if ncell.upper is not None:
                    # 上層 Mud 等被相鄰消除
                    tid = ncell.upper.tile_id
                    if _is_goal_tile(tid, goals_required):
                        score += WEIGHT_GOAL_OBSTACLE
                    else:
                        score += WEIGHT_OBSTACLE
        
        # 道具合成獎勵(根據 match pattern)
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
# Powerup 評分
# ===========================================================================

def _evaluate_powerup_activate(board, r, c, goals_required, is_endgame) -> float:
    """評估直接點擊位於 (r, c) 的道具。"""
    tile = board.get_middle(r, c)
    if tile is None:
        return -1
    pid = tile.tile_id
    
    # 估計這個道具能打到多少目標
    raw_score = _estimate_powerup_impact(board, r, c, pid, goals_required)
    
    # 扣成本(殘局 / 斬殺時免成本)
    penalty = 0 if is_endgame else (
        COST_RAINBOW if pid == 'LtBl' else COST_NORMAL_PROP
    )
    return raw_score - penalty


def _estimate_powerup_impact(board, r, c, pid, goals_required) -> float:
    """估計道具引爆能打到的目標障礙物數量 * weight。"""
    rows, cols = board.rows, board.cols
    affected_cells = set()
    
    if pid == 'Soda0d':  # 水平火箭 — 整行
        for cc in range(cols):
            affected_cells.add((r, cc))
    elif pid == 'Soda90':  # 垂直火箭 — 整列
        for rr in range(rows):
            affected_cells.add((rr, c))
    elif pid == 'TNT':  # 3x3
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                affected_cells.add((r + dr, c + dc))
    elif pid == 'TrPr':  # 十字 4 格
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            affected_cells.add((r + dr, c + dc))
    elif pid == 'LtBl':  # 隨機選一色,清光該色
        # 取場上最多色 → 預估打中那麼多 cell
        color_counts: dict = {}
        for rr in range(rows):
            for cc in range(cols):
                cell = board.get_cell(rr, cc)
                if cell.middle and cell.middle.color is not None:
                    color_counts[cell.middle.color] = color_counts.get(cell.middle.color, 0) + 1
        if color_counts:
            best_color = max(color_counts, key=color_counts.get)
            for rr in range(rows):
                for cc in range(cols):
                    cell = board.get_cell(rr, cc)
                    if cell.middle and cell.middle.color == best_color:
                        affected_cells.add((rr, cc))
    
    # 算這些 cell 內(含 4 鄰)的目標障礙物
    score = 0.0
    counted = set()
    for (r, c) in affected_cells:
        if not (0 <= r < rows and 0 <= c < cols):
            continue
        cell = board.get_cell(r, c)
        if cell.middle and is_obstacle(cell.middle.tile_id):
            tid = cell.middle.tile_id
            key = (r, c, 'mid')
            if key not in counted:
                counted.add(key)
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


def _evaluate_powerup_combo(pid1: str, pid2: str, board, goals_required, is_endgame) -> float:
    """估算兩個道具 swap 合成的爆炸效益。"""
    # 用粗略的固定加分;真實效果取決於盤面,但 demo 用足夠
    if pid1 == 'LtBl' or pid2 == 'LtBl':
        return 60 - (0 if is_endgame else COST_RAINBOW)
    return 35 - (0 if is_endgame else COST_NORMAL_PROP * 2)


def _evaluate_ltbl_element(board, ltbl_r, ltbl_c, element_tile, goals_required, is_endgame) -> float:
    """LtBl + 元素 → 清光該色。"""
    color = element_tile.color
    if color is None:
        return 0
    rows, cols = board.rows, board.cols
    affected = 0
    for r in range(rows):
        for c in range(cols):
            cell = board.get_cell(r, c)
            if cell.middle and cell.middle.color == color:
                affected += 1
    score = affected * WEIGHT_ELEMENT
    # 大概率順便打到旁邊障礙
    score += affected * 0.5 * WEIGHT_OBSTACLE
    return score - (0 if is_endgame else COST_RAINBOW)


# ===========================================================================
# Helpers
# ===========================================================================

def _can_swap_safe(board, r1, c1, r2, c2) -> bool:
    """安全地問 board.can_swap,有些版本可能不接受越界。"""
    try:
        return board.can_swap(r1, c1, r2, c2)
    except Exception:
        return False


def _is_goal_tile(tile_id: str, goals_required: dict) -> bool:
    """判斷 tile_id 是不是當前關卡 goals 內的目標。"""
    if not goals_required:
        return False
    # 直接命中
    if tile_id in goals_required:
        return True
    # 前綴命中(處理 Puddle_lv1 vs Puddle_lv2 都算 Puddle 目標的情況)
    for goal_id in goals_required:
        # goal_id 可能是 'Puddle' 也可能是 'Puddle_lv2',兩端各自前綴比對
        base_goal = goal_id.split('_lv')[0]
        base_tile = tile_id.split('_lv')[0]
        if base_goal == base_tile:
            return True
    return False


def _count_goal_obstacles_on_board(board, goals_required) -> int:
    """數場上還剩多少目標障礙物 — 殘局判定用。"""
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
