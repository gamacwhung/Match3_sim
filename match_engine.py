"""
消除引擎 — 配對偵測、消除處理、道具生成/啟動/合成/連鎖

主要流程:
  1. find_matches()      — 偵測所有三連以上的配對
  2. resolve()           — 主消除循環 (消除→鄰邊→道具→重力→填充→repeat)
  3. activate_powerup()  — 啟動單個道具效果
  4. combine_powerups()  — 兩道具合成效果

消除優先級 (依設計文檔):
  5+ 連線 → LtBl (紙風車)
  L/T 形  → TNT  (炸彈)
  2×2 方塊→ TrPr (紙飛機)
  4 連橫  → Soda90 (垂直火箭)
  4 連直  → Soda0d (水平火箭)
  3 連    → 純消除
"""

from collections import deque
from board import Board, Tile, Cell
from tile_defs import (
    get_def, is_element, is_powerup, is_movable, is_obstacle,
    can_adjacent_elim, can_prop_elim, can_inplace_elim,
    get_color, POWERUP_IDS, COLORS,
    TRPR_TARGET_WEIGHTS, TRPR_GOAL_BONUS, TRPR_LAST_HIT_BONUS,
)

# ---------------------------------------------------------------------------
# MatchGroup — 一組配對結果
# ---------------------------------------------------------------------------
class MatchGroup:
    __slots__ = ('positions', 'color', 'pattern', 'pivot')

    def __init__(self, positions, color, pattern, pivot):
        self.positions = frozenset(positions)  # set of (r, c)
        self.color = color
        self.pattern = pattern   # 'THREE', 'FOUR_H', 'FOUR_V', 'L_T', 'BLOCK_2x2', 'FIVE_PLUS'
        self.pivot = pivot       # (r, c) 消除點（道具生成位置）


# ===========================================================================
# 1. 配對偵測
# ===========================================================================

def _count_line_h(board: Board, r, c, color):
    """從 (r,c) 向兩側計算橫向同色連線長度"""
    if not board.in_bounds(r, c):
        return 0, []
    t = board.get_middle(r, c)
    if t is None or t.color != color:
        return 0, []
    positions = [(r, c)]
    # 向右
    cc = c + 1
    while cc < board.cols:
        tt = board.get_middle(r, cc)
        if tt and tt.color == color:
            positions.append((r, cc))
            cc += 1
        else:
            break
    # 向左
    cc = c - 1
    while cc >= 0:
        tt = board.get_middle(r, cc)
        if tt and tt.color == color:
            positions.append((r, cc))
            cc -= 1
        else:
            break
    return len(positions), positions


def _count_line_v(board: Board, r, c, color):
    """從 (r,c) 向兩側計算縱向同色連線長度"""
    if not board.in_bounds(r, c):
        return 0, []
    t = board.get_middle(r, c)
    if t is None or t.color != color:
        return 0, []
    positions = [(r, c)]
    rr = r + 1
    while rr < board.rows:
        tt = board.get_middle(rr, c)
        if tt and tt.color == color:
            positions.append((rr, c))
            rr += 1
        else:
            break
    rr = r - 1
    while rr >= 0:
        tt = board.get_middle(rr, c)
        if tt and tt.color == color:
            positions.append((rr, c))
            rr -= 1
        else:
            break
    return len(positions), positions


def _check_2x2(board: Board, r, c, color):
    """檢查以 (r,c) 為左上角的 2×2 方塊"""
    if r < 0 or r >= board.rows - 1 or c < 0 or c >= board.cols - 1:
        return False
    for dr in (0, 1):
        for dc in (0, 1):
            t = board.get_middle(r + dr, c + dc)
            if t is None or t.color != color:
                return False
    return True


def find_matches(board: Board) -> list:
    """
    掃描整個盤面，找出所有三連以上的配對。
    回傳 list[MatchGroup]，每個 MatchGroup 已標注 pattern 和 pivot。
    同一個座標不會出現在多個 MatchGroup 中。
    """
    rows, cols = board.rows, board.cols
    used = set()  # 已被分配到 MatchGroup 的座標
    results = []

    # 收集所有原始水平 / 垂直連線
    raw_h_lines = []  # (color, set_of_positions)
    raw_v_lines = []

    # 橫向（用 t.color 代替 is_element 加速）
    grid = board.grid
    for r in range(rows):
        row = grid[r]
        c = 0
        while c < cols:
            t = row[c].middle
            if t is None or t.color is None:
                c += 1
                continue
            color = t.color
            run = [(r, c)]
            cc = c + 1
            while cc < cols:
                tt = row[cc].middle
                if tt is not None and tt.color == color:
                    run.append((r, cc))
                    cc += 1
                else:
                    break
            if len(run) >= 3:
                raw_h_lines.append((color, set(run)))
            c = cc

    # 縱向
    for c in range(cols):
        r = 0
        while r < rows:
            t = grid[r][c].middle
            if t is None or t.color is None:
                r += 1
                continue
            color = t.color
            run = [(r, c)]
            rr = r + 1
            while rr < rows:
                tt = grid[rr][c].middle
                if tt is not None and tt.color == color:
                    run.append((rr, c))
                    rr += 1
                else:
                    break
            if len(run) >= 3:
                raw_v_lines.append((color, set(run)))
            r = rr

    # 2×2 方塊（不需要 3 連也能觸發）
    raw_blocks = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            t = grid[r][c].middle
            if t is None or t.color is None:
                continue
            color = t.color
            if _check_2x2(board, r, c, color):
                block = {(r, c), (r, c+1), (r+1, c), (r+1, c+1)}
                raw_blocks.append((color, block))

    # 合併有交叉的同色連線成為群組
    all_lines = raw_h_lines + raw_v_lines + raw_blocks
    # Union-Find 合併
    parent = list(range(len(all_lines)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pa] = pb

    for i in range(len(all_lines)):
        for j in range(i + 1, len(all_lines)):
            if all_lines[i][0] == all_lines[j][0]:  # 同色
                if all_lines[i][1] & all_lines[j][1]:  # 有交集
                    union(i, j)

    # 按群組收集
    groups = {}
    for i, (color, positions) in enumerate(all_lines):
        root = find(i)
        if root not in groups:
            groups[root] = (color, set())
        groups[root][1].update(positions)

    # 對每個群組判定 pattern
    for color, positions in groups.values():
        if positions & used:
            # 移除已用的座標
            positions -= used
        if len(positions) < 3:
            continue

        pattern, pivot = _classify_pattern(board, positions, color)
        mg = MatchGroup(positions, color, pattern, pivot)
        results.append(mg)
        used.update(positions)

    return results


def _classify_pattern(board, positions, color):
    """
    根據座標集合判定消除模式和消除點。

    優先級: FIVE_PLUS > L_T > BLOCK_2x2 > FOUR_H/FOUR_V > THREE
    """
    # 找出所有橫/縱連續段
    rows_in = {}
    cols_in = {}
    for r, c in positions:
        rows_in.setdefault(r, []).append(c)
        cols_in.setdefault(c, []).append(r)

    # 最長橫向段
    max_h_len = 0
    max_h_positions = []
    for r, cs in rows_in.items():
        cs_sorted = sorted(cs)
        segs = _find_consecutive_segments(cs_sorted)
        for seg in segs:
            if len(seg) > max_h_len:
                max_h_len = len(seg)
                max_h_positions = [(r, c) for c in seg]

    # 最長縱向段
    max_v_len = 0
    max_v_positions = []
    for c, rs in cols_in.items():
        rs_sorted = sorted(rs)
        segs = _find_consecutive_segments(rs_sorted)
        for seg in segs:
            if len(seg) > max_v_len:
                max_v_len = len(seg)
                max_v_positions = [(r, c) for r in seg]

    # --- 5+ 連線 → LtBl ---
    if max_h_len >= 5 or max_v_len >= 5:
        # pivot = 中間位置
        line = max_h_positions if max_h_len >= max_v_len else max_v_positions
        pivot = line[len(line) // 2]
        return 'FIVE_PLUS', pivot

    # --- L/T 形: h≥2, v≥2, h+v-1 ≥ 5 ---
    # 找交叉點
    for r, c in positions:
        h_count, _ = _count_line_h(board, r, c, color)
        v_count, _ = _count_line_v(board, r, c, color)
        if h_count >= 2 and v_count >= 2 and (h_count + v_count - 1) >= 5:
            return 'L_T', (r, c)

    # --- 2×2 方塊 → TrPr ---
    for r, c in positions:
        for dr in (0, -1):
            for dc in (0, -1):
                tr, tc = r + dr, c + dc
                if _check_2x2(board, tr, tc, color):
                    # pivot = 四格的其中一個（通常取消除點，這裡取中心偏左上）
                    return 'BLOCK_2x2', (tr, tc)

    # --- 4 連 ---
    if max_h_len == 4:
        # 橫向 4 消 → 生成垂直火箭 (Soda90)
        pivot = max_h_positions[1]  # 偏中間位置
        return 'FOUR_H', pivot
    if max_v_len == 4:
        # 縱向 4 消 → 生成水平火箭 (Soda0d)
        pivot = max_v_positions[1]
        return 'FOUR_V', pivot

    # --- 3 連 ---
    if max_h_len >= max_v_len:
        pivot = max_h_positions[len(max_h_positions) // 2]
    else:
        pivot = max_v_positions[len(max_v_positions) // 2]
    return 'THREE', pivot


def _find_consecutive_segments(sorted_vals):
    """將排序後的整數列表分成連續段"""
    if not sorted_vals:
        return []
    segments = []
    current = [sorted_vals[0]]
    for v in sorted_vals[1:]:
        if v == current[-1] + 1:
            current.append(v)
        else:
            segments.append(current)
            current = [v]
    segments.append(current)
    return segments


# ===========================================================================
# 2. 消除處理
# ===========================================================================

# 道具生成表
PATTERN_TO_POWERUP = {
    'FIVE_PLUS': 'LtBl',
    'L_T': 'TNT',
    'BLOCK_2x2': 'TrPr',
    'FOUR_H': 'Soda90',   # 橫向拼湊 → 垂直火箭
    'FOUR_V': 'Soda0d',   # 縱向拼湊 → 水平火箭
}


def resolve(board: Board, track_goals=True, goals_current=None, goals_required=None):
    """
    主消除循環: 消除 → 鄰邊消除 → 原地消除 → 道具觸發 → 重力 → 填充 → repeat

    Returns:
        dict: {
            'eliminated': dict of {tile_id: count},
            'powerups_created': list of (tile_id, (r,c)),
        }
    """
    total_eliminated = {}
    total_powerups = []

    while True:
        match_groups = find_matches(board)
        if not match_groups:
            break

        # 收集本輪所有要消除的座標和要生成的道具
        to_clear = set()          # 中層要清空的座標
        to_damage = {}            # {(r,c): damage_amount} 鄰邊消除
        to_damage_colors = {}     # {(r,c): set(color)} 鄰邊消除觸發顏色（BeverageChiller用）
        powerup_spawns = []       # [(powerup_id, (r,c))]
        triggered_powerups = []   # 消除範圍內被觸發的道具 [(r,c, tile_id)]
        damaged_single = set()    # 追蹤已在本輪受過單次消除的 instance_id

        for mg in match_groups:
            # 決定是否生成道具
            powerup_id = PATTERN_TO_POWERUP.get(mg.pattern)
            if powerup_id:
                powerup_spawns.append((powerup_id, mg.pivot))

            # 標記消除座標
            for r, c in mg.positions:
                tile = board.get_middle(r, c)
                if tile is None:
                    continue

                # 被繩索覆蓋的元素：參與配對但不被消除（繩索在下方原地消除段處理）
                cell = board.get_cell(r, c)
                if cell.upper and cell.upper.tile_id.startswith('Rope'):
                    continue

                # 如果是道具，加入觸發佇列
                if is_powerup(tile.tile_id):
                    triggered_powerups.append((r, c, tile.tile_id))
                    to_clear.add((r, c))
                    continue

                # 元素 / 可消除物件
                to_clear.add((r, c))

            # 鄰邊消除：每個消除格的上下左右鄰格
            for r, c in mg.positions:
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if not board.in_bounds(nr, nc):
                        continue
                    if (nr, nc) in mg.positions:
                        continue  # 已在消除範圍內
                    neighbor = board.get_middle(nr, nc)
                    if neighbor is None:
                        continue
                    if can_adjacent_elim(neighbor.tile_id):
                        to_damage[(nr, nc)] = to_damage.get((nr, nc), 0) + 1
                        # 記錄觸發消除的顏色（BeverageChiller 需要）
                        if mg.color:
                            to_damage_colors.setdefault((nr, nc), set()).add(mg.color)

            # 原地消除：消除座標同格的下層（水漥）
            for r, c in mg.positions:
                cell = board.get_cell(r, c)
                if cell.bottom and can_inplace_elim(cell.bottom.tile_id):
                    _damage_tile_at_layer(board, r, c, 'bottom', 1, damaged_single,
                                          track_goals, goals_current, goals_required,
                                          total_eliminated)

            # 原地消除：消除座標同格的上層（繩索）
            for r, c in mg.positions:
                cell = board.get_cell(r, c)
                if cell.upper and can_inplace_elim(cell.upper.tile_id):
                    _damage_tile_at_layer(board, r, c, 'upper', 1, damaged_single,
                                          track_goals, goals_current, goals_required,
                                          total_eliminated)

        # 執行鄰邊消除
        for (r, c), dmg in to_damage.items():
            if (r, c) in to_clear:
                continue  # 已經要被清除了
            tile = board.get_middle(r, c)
            if tile is None:
                continue
            defn = get_def(tile.tile_id)
            if defn is None:
                continue

            # BeverageChiller_open 只能被匹配的顏色消除
            if tile.tile_id == 'BeverageChiller_open' and tile.required_colors:
                colors_hitting = to_damage_colors.get((r, c), set())
                matching = colors_hitting & set(tile.required_colors)
                if not matching:
                    continue  # 沒有匹配的顏色，跳過

            actual_dmg = dmg
            if defn['elimination_type'] == 'single':
                # 單次消除：一次消除行為只扣 1
                key = tile.instance_id or (r, c)
                if key in damaged_single:
                    continue
                damaged_single.add(key)
                actual_dmg = 1

            _damage_middle(board, r, c, actual_dmg, to_clear,
                           track_goals, goals_current, goals_required, total_eliminated)

        # 清空被消除的格子（注意：道具生成在 pivot 位置）
        for r, c in to_clear:
            tile = board.get_middle(r, c)
            if tile:
                _count_elimination(tile.tile_id, total_eliminated)
                if track_goals and goals_current is not None and goals_required is not None:
                    if tile.tile_id in goals_required:
                        goals_current[tile.tile_id] = goals_current.get(tile.tile_id, 0) + 1
                    elif tile.color and tile.color in goals_required:
                        goals_current[tile.color] = goals_current.get(tile.color, 0) + 1
            board.clear_middle(r, c)

        # 在 pivot 位置生成道具（若 pivot 被繩索覆蓋，找已清空的位置）
        for powerup_id, (pr, pc) in powerup_spawns:
            if (pr, pc) not in to_clear:
                # pivot 被繩索保護，找 match group 中已清空的位置
                placed = False
                for mg in match_groups:
                    if (pr, pc) in mg.positions:
                        for pos in mg.positions:
                            if pos in to_clear and board.get_middle(*pos) is None:
                                board.set_middle(*pos, Tile(powerup_id))
                                total_powerups.append((powerup_id, pos))
                                placed = True
                                break
                        break
                if not placed:
                    # fallback: 放在 pivot（覆蓋元素）
                    board.set_middle(pr, pc, Tile(powerup_id))
                    total_powerups.append((powerup_id, (pr, pc)))
            else:
                board.set_middle(pr, pc, Tile(powerup_id))
                total_powerups.append((powerup_id, (pr, pc)))

        # 處理被觸發的道具（連鎖）
        _process_powerup_chain(board, triggered_powerups, to_clear,
                               track_goals, goals_current, goals_required,
                               total_eliminated)

        # 重力 + 填充
        board.apply_gravity()
        board.fill_top()

    return {
        'eliminated': total_eliminated,
        'powerups_created': total_powerups,
    }


def _damage_middle(board, r, c, damage, to_clear,
                   track_goals, goals_current, goals_required, total_eliminated):
    """對中層物件造成傷害，血量歸零時加入清除集合或觸發狀態轉換"""
    tile = board.get_middle(r, c)
    # 製造機（Stamp）：每次受消除生產一個目標物，不受傷害
    if tile and tile._cat == 'manufacturer':
        board.manufacturer_produced[tile.tile_id] = \
            board.manufacturer_produced.get(tile.tile_id, 0) + 1
        _count_elimination(tile.tile_id, total_eliminated)
        return
    if _apply_damage_to_middle(board, r, c, damage):
        to_clear.add((r, c))


def _damage_tile_at_layer(board, r, c, layer, damage, damaged_single,
                          track_goals, goals_current, goals_required, total_eliminated):
    """對指定層的物件造成傷害"""
    cell = board.get_cell(r, c)
    tile = getattr(cell, layer)
    if tile is None:
        return
    defn = get_def(tile.tile_id)
    if defn and defn['elimination_type'] == 'single':
        key = tile.instance_id or (r, c, layer)
        if key in damaged_single:
            return
        damaged_single.add(key)
        damage = 1
    tile.health -= damage
    if tile.health <= 0:
        _count_elimination(tile.tile_id, total_eliminated)
        if track_goals and goals_current is not None and goals_required is not None:
            if tile.tile_id in goals_required:
                goals_current[tile.tile_id] = goals_current.get(tile.tile_id, 0) + 1
        setattr(cell, layer, None)


def _count_elimination(tile_id, total_eliminated):
    """計數消除"""
    total_eliminated[tile_id] = total_eliminated.get(tile_id, 0) + 1


def _apply_damage_to_middle(board, r, c, damage):
    """
    對中層物件造成傷害，處理狀態轉換。
    回傳 True 表示物件被消除（應 clear_middle），False 表示仍存活或轉換。
    """
    tile = board.get_middle(r, c)
    if tile is None:
        return False

    # 製造機（Stamp）：不受傷害，不會被消除
    if tile._cat == 'manufacturer':
        return False

    tile.health -= damage
    if tile.health <= 0:
        # WaterChiller_closed → 開門
        if tile.tile_id == 'WaterChiller_closed':
            open_hp = getattr(board, 'waterchiller_open_health', 3)
            new_tile = Tile(f'WaterChiller_lv{open_hp}')
            board.set_middle(r, c, new_tile)
            return False
        # BeverageChiller_closed → 開門
        if tile.tile_id == 'BeverageChiller_closed':
            open_hp = getattr(board, 'beveragechiller_open_health', 4)
            new_tile = Tile('BeverageChiller_open')
            new_tile.health = open_hp
            new_tile.required_colors = tile.required_colors
            board.set_middle(r, c, new_tile)
            return False
        return True  # 正常消除
    return False  # 未消除


# ===========================================================================
# 3. 道具啟動與連鎖
# ===========================================================================

def get_powerup_targets(board: Board, r, c, powerup_id, goals_required=None):
    """
    計算道具效果的目標座標列表

    Returns:
        list[(r, c)]
    """
    rows, cols = board.rows, board.cols

    if powerup_id == 'Soda0d':
        # 水平火箭 → 整行
        return [(r, cc) for cc in range(cols)]

    elif powerup_id == 'Soda90':
        # 垂直火箭 → 整列
        return [(rr, c) for rr in range(rows)]

    elif powerup_id == 'TNT':
        # 炸彈 → 5×5
        targets = []
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                nr, nc = r + dr, c + dc
                if board.in_bounds(nr, nc):
                    targets.append((nr, nc))
        return targets

    elif powerup_id == 'TrPr':
        # 紙飛機 → 只回傳十字 4 格（飛行目標需要在掉落後才決定）
        targets = [(r, c)]
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if board.in_bounds(nr, nc):
                targets.append((nr, nc))
        return targets

    elif powerup_id == 'LtBl':
        # 紙風車 → 消除數量最多的同色元素 + 每個被消元素的鄰邊
        return _get_ltbl_targets(board)

    return []


def _find_trpr_target(board, src_r, src_c, goals_required=None):
    """找紙飛機的飛行目標（最高權重的障礙物）"""
    best_pos = None
    best_weight = -1

    for r in range(board.rows):
        for c in range(board.cols):
            if r == src_r and c == src_c:
                continue
            tile = board.get_middle(r, c)
            if tile is None:
                continue
            defn = get_def(tile.tile_id)
            if defn is None:
                continue

            weight = 0
            cat = defn['category']
            if cat == 'element':
                weight = TRPR_TARGET_WEIGHTS.get('element', 1)
            elif cat == 'powerup':
                weight = TRPR_TARGET_WEIGHTS.get('powerup', 0)
            elif cat == 'obstacle' or cat == 'manufacturer':
                # 嘗試用前綴匹配權重
                for prefix, w in TRPR_TARGET_WEIGHTS.items():
                    if tile.tile_id.startswith(prefix):
                        weight = w
                        break
                else:
                    weight = 10  # 預設障礙物權重

            # 通關目標加權
            if goals_required and tile.tile_id in goals_required:
                weight += TRPR_GOAL_BONUS
            # 血量=1 加權
            if tile.health == 1 and is_obstacle(tile.tile_id):
                weight += TRPR_LAST_HIT_BONUS

            # 上層物件也算
            cell = board.get_cell(r, c)
            if cell.upper:
                upper_def = get_def(cell.upper.tile_id)
                if upper_def:
                    for prefix, w in TRPR_TARGET_WEIGHTS.items():
                        if cell.upper.tile_id.startswith(prefix):
                            weight += w
                            break

            if weight > best_weight:
                best_weight = weight
                best_pos = (r, c)

    return best_pos


def _get_ltbl_targets(board):
    """紙風車：找數量最多的顏色，回傳所有該色元素的座標"""
    color_counts = {}
    color_cells = {}
    for r in range(board.rows):
        for c in range(board.cols):
            tile = board.get_middle(r, c)
            if tile and is_element(tile.tile_id) and tile.color:
                color_counts[tile.color] = color_counts.get(tile.color, 0) + 1
                color_cells.setdefault(tile.color, []).append((r, c))

    if not color_counts:
        return []

    max_color = max(color_counts, key=color_counts.get)
    return color_cells[max_color]


def activate_powerup(board: Board, r, c, goals_required=None,
                     track_goals=True, goals_current=None, goals_required_dict=None):
    """
    啟動一個道具。

    Args:
        board: 盤面
        r, c: 道具位置
        goals_required: 用於紙飛機目標選擇
    """
    tile = board.get_middle(r, c)
    if tile is None or not is_powerup(tile.tile_id):
        return

    powerup_id = tile.tile_id
    # 消除道具本身
    board.clear_middle(r, c)

    targets = get_powerup_targets(board, r, c, powerup_id, goals_required)
    triggered = []

    is_ltbl = (powerup_id == 'LtBl')
    target_set = set(targets)

    for tr, tc in targets:
        # 非 LtBl 道具：消除目標格的上層（繩索）和下層（水漥）
        if not is_ltbl:
            cell = board.get_cell(tr, tc)
            if cell.upper:
                ud = get_def(cell.upper.tile_id)
                if ud and ud.get('can_prop_elim', True):
                    cell.upper.health -= 1
                    if cell.upper.health <= 0:
                        cell.upper = None
            if cell.bottom:
                bd = get_def(cell.bottom.tile_id)
                if bd and bd.get('can_prop_elim', True):
                    cell.bottom.health -= 1
                    if cell.bottom.health <= 0:
                        cell.bottom = None

        t = board.get_middle(tr, tc)
        if t is None:
            continue
        if is_powerup(t.tile_id) and (tr, tc) != (r, c):
            triggered.append((tr, tc, t.tile_id))
            board.clear_middle(tr, tc)
        elif t._cat == 'manufacturer':
            board.manufacturer_produced[t.tile_id] = \
                board.manufacturer_produced.get(t.tile_id, 0) + 1
        elif is_element(t.tile_id) or is_obstacle(t.tile_id):
            defn = get_def(t.tile_id)
            if defn and defn.get('can_prop_elim', True):
                if _apply_damage_to_middle(board, tr, tc, 1):
                    board.clear_middle(tr, tc)
        # 鄰邊消除（道具效果也觸發鄰邊消除）
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = tr + dr, tc + dc
            if not board.in_bounds(nr, nc):
                continue
            if (nr, nc) in target_set:
                continue
            neighbor = board.get_middle(nr, nc)
            if neighbor is None:
                continue
            if neighbor._cat == 'manufacturer':
                board.manufacturer_produced[neighbor.tile_id] = \
                    board.manufacturer_produced.get(neighbor.tile_id, 0) + 1
            elif can_adjacent_elim(neighbor.tile_id):
                if _apply_damage_to_middle(board, nr, nc, 1):
                    board.clear_middle(nr, nc)

    # 連鎖觸發
    _process_powerup_chain(board, triggered, set(),
                           track_goals, goals_current, goals_required_dict, {})

    # 紙飛機的飛行階段：十字消除後 → 重力填充 → 再決定飛行目標
    if powerup_id == 'TrPr':
        board.apply_gravity()
        board.fill_top()
        _trpr_fly_phase(board, r, c, goals_required,
                        track_goals, goals_current, goals_required_dict)


def _trpr_fly_phase(board, src_r, src_c, goals_required,
                    track_goals, goals_current, goals_required_dict,
                    total_eliminated=None):
    """紙飛機飛行階段：在重力填充後找目標並打擊"""
    if total_eliminated is None:
        total_eliminated = {}
    fly_target = _find_trpr_target(board, src_r, src_c, goals_required)
    if not fly_target:
        return
    fr, fc = fly_target
    tile = board.get_middle(fr, fc)
    if tile is None:
        return
    if is_powerup(tile.tile_id):
        triggered = [(fr, fc, tile.tile_id)]
        board.clear_middle(fr, fc)
        _process_powerup_chain(board, triggered, set(),
                               track_goals, goals_current, goals_required_dict,
                               total_eliminated)
    elif tile._cat == 'manufacturer':
        board.manufacturer_produced[tile.tile_id] = \
            board.manufacturer_produced.get(tile.tile_id, 0) + 1
    else:
        if _apply_damage_to_middle(board, fr, fc, 1):
            _count_elimination(tile.tile_id, total_eliminated)
            if track_goals and goals_current is not None and goals_required_dict is not None:
                if tile.tile_id in goals_required_dict:
                    goals_current[tile.tile_id] = goals_current.get(tile.tile_id, 0) + 1
            board.clear_middle(fr, fc)
    # 飛行打擊的鄰邊消除
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = fr + dr, fc + dc
        if board.in_bounds(nr, nc):
            neighbor = board.get_middle(nr, nc)
            if neighbor is None:
                continue
            if neighbor._cat == 'manufacturer':
                board.manufacturer_produced[neighbor.tile_id] = \
                    board.manufacturer_produced.get(neighbor.tile_id, 0) + 1
            elif can_adjacent_elim(neighbor.tile_id):
                if _apply_damage_to_middle(board, nr, nc, 1):
                    board.clear_middle(nr, nc)


def _process_powerup_chain(board, triggered_list, already_cleared,
                           track_goals, goals_current, goals_required, total_eliminated):
    """BFS 處理道具連鎖"""
    queue = deque(triggered_list)
    processed = set()
    for r, c, _ in triggered_list:
        processed.add((r, c))

    trpr_pending = []  # 紙飛機飛行階段（需要重力填充後才執行）

    while queue:
        pr, pc, pid = queue.popleft()
        targets = get_powerup_targets(board, pr, pc, pid, goals_required)

        for tr, tc in targets:
            tile = board.get_middle(tr, tc)
            if tile is None:
                continue

            # 連鎖觸發其他道具（LtBl 不連鎖 LtBl）
            if is_powerup(tile.tile_id) and (tr, tc) not in processed:
                if not (pid == 'LtBl' and tile.tile_id == 'LtBl'):
                    processed.add((tr, tc))
                    queue.append((tr, tc, tile.tile_id))
                    board.clear_middle(tr, tc)
                    continue

            # 道具消除
            defn = get_def(tile.tile_id)
            if defn and defn.get('can_prop_elim', True):
                if _apply_damage_to_middle(board, tr, tc, 1):
                    _count_elimination(tile.tile_id, total_eliminated)
                    if track_goals and goals_current is not None and goals_required is not None:
                        if tile.tile_id in goals_required:
                            goals_current[tile.tile_id] = goals_current.get(tile.tile_id, 0) + 1
                    board.clear_middle(tr, tc)

            # 上層
            cell = board.get_cell(tr, tc)
            if cell.upper:
                ud = get_def(cell.upper.tile_id)
                if ud and ud.get('can_prop_elim', True):
                    cell.upper.health -= 1
                    if cell.upper.health <= 0:
                        _count_elimination(cell.upper.tile_id, total_eliminated)
                        cell.upper = None

            # 下層
            if cell.bottom:
                bd = get_def(cell.bottom.tile_id)
                if bd and bd.get('can_prop_elim', True):
                    cell.bottom.health -= 1
                    if cell.bottom.health <= 0:
                        _count_elimination(cell.bottom.tile_id, total_eliminated)
                        cell.bottom = None

        # 紙飛機：十字處理完，記錄待飛行
        if pid == 'TrPr':
            trpr_pending.append((pr, pc))

    # 所有連鎖處理完後，處理紙飛機的飛行階段（重力填充後才飛）
    if trpr_pending:
        board.apply_gravity()
        board.fill_top()
        for src_r, src_c in trpr_pending:
            _trpr_fly_phase(board, src_r, src_c, goals_required,
                            track_goals, goals_current, goals_required, total_eliminated)


# ===========================================================================
# 4. 道具合成
# ===========================================================================

def combine_powerups(board: Board, r1, c1, r2, c2,
                     goals_required=None, track_goals=True,
                     goals_current=None, goals_required_dict=None):
    """
    兩道具合成。先清除兩道具，然後執行合成效果。

    Returns:
        bool: 是否觸發了合成
    """
    t1 = board.get_middle(r1, c1)
    t2 = board.get_middle(r2, c2)
    if t1 is None or t2 is None:
        return False
    if not is_powerup(t1.tile_id) or not is_powerup(t2.tile_id):
        # 紙風車 + 元素
        if is_powerup(t1.tile_id) and t1.tile_id == 'LtBl' and is_element(t2.tile_id):
            return _combine_ltbl_element(board, r1, c1, r2, c2, t2.color,
                                         track_goals, goals_current, goals_required_dict)
        if is_powerup(t2.tile_id) and t2.tile_id == 'LtBl' and is_element(t1.tile_id):
            return _combine_ltbl_element(board, r2, c2, r1, c1, t1.color,
                                         track_goals, goals_current, goals_required_dict)
        return False

    pid1, pid2 = t1.tile_id, t2.tile_id
    # 清除兩道具
    board.clear_middle(r1, c1)
    board.clear_middle(r2, c2)

    # 合成位置（取 r2, c2 作為合成點）
    cr, cc = r2, c2

    # 分類
    def _cat(pid):
        if pid in ('Soda0d', 'Soda90'):
            return 'ROCKET'
        return pid  # TNT, TrPr, LtBl

    c1_cat, c2_cat = _cat(pid1), _cat(pid2)
    combo = frozenset([c1_cat, c2_cat])

    if combo == frozenset(['ROCKET', 'ROCKET']):
        # 十字消除 (整行+整列)
        targets = set()
        for cc2 in range(board.cols):
            targets.add((cr, cc2))
        for rr in range(board.rows):
            targets.add((rr, cc))
        _apply_combo_targets(board, targets, track_goals, goals_current, goals_required_dict)

    elif combo == frozenset(['ROCKET', 'TNT']):
        # 3 寬十字
        targets = set()
        for offset in range(-1, 2):
            for cc2 in range(board.cols):
                if board.in_bounds(cr + offset, cc2):
                    targets.add((cr + offset, cc2))
            for rr in range(board.rows):
                if board.in_bounds(rr, cc + offset):
                    targets.add((rr, cc + offset))
        _apply_combo_targets(board, targets, track_goals, goals_current, goals_required_dict)

    elif combo == frozenset(['TNT', 'TNT']):
        # 7×7
        targets = set()
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                if board.in_bounds(cr + dr, cc + dc):
                    targets.add((cr + dr, cc + dc))
        _apply_combo_targets(board, targets, track_goals, goals_current, goals_required_dict)

    elif combo == frozenset(['ROCKET', 'TrPr']):
        # 4 格消除 → 重力填充 → 飛到目標放火箭
        _apply_trpr_base(board, cr, cc, track_goals, goals_current, goals_required_dict)
        board.apply_gravity()
        board.fill_top()
        fly_target = _find_trpr_target(board, cr, cc, goals_required)
        if fly_target:
            fr, fc = fly_target
            rocket_id = pid1 if _cat(pid1) == 'ROCKET' else pid2
            targets = set(get_powerup_targets(board, fr, fc, rocket_id))
            _apply_combo_targets(board, targets, track_goals, goals_current, goals_required_dict)

    elif combo == frozenset(['TNT', 'TrPr']):
        # 4 格消除 → 重力填充 → 飛到目標放炸彈
        _apply_trpr_base(board, cr, cc, track_goals, goals_current, goals_required_dict)
        board.apply_gravity()
        board.fill_top()
        fly_target = _find_trpr_target(board, cr, cc, goals_required)
        if fly_target:
            fr, fc = fly_target
            targets = set(get_powerup_targets(board, fr, fc, 'TNT'))
            _apply_combo_targets(board, targets, track_goals, goals_current, goals_required_dict)

    elif combo == frozenset(['TrPr']):
        # TrPr + TrPr → 4 格消除 → 重力填充 → 起飛 3 台紙飛機
        _apply_trpr_base(board, cr, cc, track_goals, goals_current, goals_required_dict)
        board.apply_gravity()
        board.fill_top()
        for _ in range(3):
            fly_target = _find_trpr_target(board, cr, cc, goals_required)
            if fly_target:
                fr, fc = fly_target
                tile = board.get_middle(fr, fc)
                if tile:
                    if _apply_damage_to_middle(board, fr, fc, 1):
                        board.clear_middle(fr, fc)

    elif 'LtBl' in combo:
        other = c1_cat if c2_cat == 'LtBl' else c2_cat
        if other == 'LtBl':
            # LtBl + LtBl → 全盤面消除 1 層
            for r in range(board.rows):
                for c in range(board.cols):
                    cell = board.get_cell(r, c)
                    if cell.upper:
                        cell.upper.health -= 1
                        if cell.upper.health <= 0:
                            cell.upper = None
                    elif cell.middle:
                        cell.middle.health -= 1
                        if cell.middle.health <= 0:
                            board.clear_middle(r, c)
                    if cell.bottom:
                        cell.bottom.health -= 1
                        if cell.bottom.health <= 0:
                            cell.bottom = None
        else:
            # LtBl + 任意道具 → 最多色元素全轉為該道具後使用
            ltbl_targets = _get_ltbl_targets(board)
            powerup_to_create = pid1 if _cat(pid1) != 'LtBl' else pid2
            spawned_positions = []
            rope_positions = set()  # 被繩索覆蓋的位置
            for tr, tc in ltbl_targets:
                board.set_middle(tr, tc, Tile(powerup_to_create))
                cell = board.get_cell(tr, tc)
                if cell.upper and cell.upper.tile_id.startswith('Rope'):
                    rope_positions.add((tr, tc))
                spawned_positions.append((tr, tc))
            # 逐一啟動（繩索下的道具不觸發，繩索不消除）
            for tr, tc in spawned_positions:
                if (tr, tc) in rope_positions:
                    continue  # 繩索保護，不觸發
                t = board.get_middle(tr, tc)
                if t and is_powerup(t.tile_id):
                    activate_powerup(board, tr, tc, goals_required,
                                     track_goals, goals_current, goals_required_dict)

    return True


def _combine_ltbl_element(board, lr, lc, er, ec, element_color,
                          track_goals, goals_current, goals_required):
    """紙風車 + 元素 → 消除該色所有元素"""
    board.clear_middle(lr, lc)
    board.clear_middle(er, ec)

    for r in range(board.rows):
        for c in range(board.cols):
            tile = board.get_middle(r, c)
            if tile and is_element(tile.tile_id) and tile.color == element_color:
                board.clear_middle(r, c)
                # 鄰邊消除
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if board.in_bounds(nr, nc):
                        neighbor = board.get_middle(nr, nc)
                        if neighbor and can_adjacent_elim(neighbor.tile_id):
                            if _apply_damage_to_middle(board, nr, nc, 1):
                                board.clear_middle(nr, nc)
    return True


def _apply_combo_targets(board, targets, track_goals, goals_current, goals_required):
    """對合成效果的目標座標造成傷害"""
    triggered = []
    for r, c in targets:
        tile = board.get_middle(r, c)
        if tile is None:
            continue
        if is_powerup(tile.tile_id):
            triggered.append((r, c, tile.tile_id))
            board.clear_middle(r, c)
            continue
        if tile._cat == 'manufacturer':
            board.manufacturer_produced[tile.tile_id] = \
                board.manufacturer_produced.get(tile.tile_id, 0) + 1
            continue
        defn = get_def(tile.tile_id)
        if defn and defn.get('can_prop_elim', True):
            if _apply_damage_to_middle(board, r, c, 1):
                board.clear_middle(r, c)
        # 道具消除也影響上/下層
        cell = board.get_cell(r, c)
        if cell.upper:
            ud = get_def(cell.upper.tile_id)
            if ud and ud.get('can_prop_elim', True):
                cell.upper.health -= 1
                if cell.upper.health <= 0:
                    cell.upper = None
        if cell.bottom:
            bd = get_def(cell.bottom.tile_id)
            if bd and bd.get('can_prop_elim', True):
                cell.bottom.health -= 1
                if cell.bottom.health <= 0:
                    cell.bottom = None

    # 連鎖
    if triggered:
        _process_powerup_chain(board, triggered, set(),
                               track_goals, goals_current, goals_required, {})


def _apply_trpr_base(board, r, c, track_goals, goals_current, goals_required):
    """紙飛機的基礎效果（上下左右 4 格消除）"""
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = r + dr, c + dc
        if board.in_bounds(nr, nc):
            tile = board.get_middle(nr, nc)
            if tile:
                defn = get_def(tile.tile_id)
                if defn and defn.get('can_prop_elim', True):
                    if _apply_damage_to_middle(board, nr, nc, 1):
                        board.clear_middle(nr, nc)


# ===========================================================================
# 5. 有效移動偵測
# ===========================================================================

def _has_match_near(board, r1, c1, r2, c2):
    """
    交換 (r1,c1) ↔ (r2,c2) 後，只檢查兩個位置附近是否有消除。
    比 find_matches() 快很多（只看局部而非整個盤面）。
    """
    grid = board.grid
    rows, cols = board.rows, board.cols

    for r, c in ((r1, c1), (r2, c2)):
        t = grid[r][c].middle
        if t is None or t.color is None:
            continue
        color = t.color

        # 橫向連線
        count = 1
        cc = c - 1
        while cc >= 0 and (tt := grid[r][cc].middle) is not None and tt.color == color:
            count += 1
            cc -= 1
        cc = c + 1
        while cc < cols and (tt := grid[r][cc].middle) is not None and tt.color == color:
            count += 1
            cc += 1
        if count >= 3:
            return True

        # 縱向連線
        count = 1
        rr = r - 1
        while rr >= 0 and (tt := grid[rr][c].middle) is not None and tt.color == color:
            count += 1
            rr -= 1
        rr = r + 1
        while rr < rows and (tt := grid[rr][c].middle) is not None and tt.color == color:
            count += 1
            rr += 1
        if count >= 3:
            return True

        # 2×2 方塊
        for dr in (0, -1):
            for dc in (0, -1):
                tr, tc = r + dr, c + dc
                if 0 <= tr < rows - 1 and 0 <= tc < cols - 1:
                    if _check_2x2(board, tr, tc, color):
                        return True

    return False


def find_valid_moves(board: Board):
    """
    找出所有能產生消除的交換動作。

    Returns:
        list[dict]: 每個 dict 為 {'pos1': (r,c), 'pos2': (r,c), 'type': str}
            type: 'match' (普通消除), 'combo' (道具合成), 'ltbl_elem' (紙風車+元素),
                  'powerup_swap' (道具+非道具)
    """
    moves = []
    seen = set()
    grid = board.grid
    pid_set = POWERUP_IDS

    for r in range(board.rows):
        for c in range(board.cols):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if not board.in_bounds(r2, c2):
                    continue
                if not board.can_swap(r, c, r2, c2):
                    continue

                pair = ((r, c), (r2, c2))
                if pair in seen:
                    continue
                seen.add(pair)

                t1 = grid[r][c].middle
                t2 = grid[r2][c2].middle
                p1 = t1.tile_id in pid_set
                p2 = t2.tile_id in pid_set

                # 道具合成
                if p1 and p2:
                    moves.append({'pos1': (r, c), 'pos2': (r2, c2), 'type': 'combo'})
                    continue

                # 紙風車 + 元素
                if (t1.tile_id == 'LtBl' and t2.color is not None) or \
                   (t2.tile_id == 'LtBl' and t1.color is not None):
                    moves.append({'pos1': (r, c), 'pos2': (r2, c2), 'type': 'ltbl_elem'})
                    continue

                # 道具 + 非道具 → 道具在新位置啟動，永遠合法
                if p1 != p2:
                    moves.append({'pos1': (r, c), 'pos2': (r2, c2), 'type': 'powerup_swap'})
                    continue

                # 普通交換：局部檢查是否有消除（不掃描整個盤面）
                board.swap(r, c, r2, c2)
                has_match = _has_match_near(board, r, c, r2, c2)
                board.swap(r, c, r2, c2)  # 換回

                if has_match:
                    moves.append({'pos1': (r, c), 'pos2': (r2, c2), 'type': 'match'})

    return moves
