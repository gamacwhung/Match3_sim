"""
盤面類別 — 多層 Cell 結構、重力、填充

Cell 結構：
  upper  - 上層 (Rope/Mud)，覆蓋中層
  middle - 中層 (Element/Powerup/Obstacle/空)
  bottom - 下層 (Puddle)，被中層覆蓋
"""

import random
import copy
from tile_defs import (
    TILE_REGISTRY, COLORS, DEFAULT_NUM_COLORS, POWERUP_IDS,
    get_def, is_element, is_powerup, is_movable, blocks_fall, get_color,
)


# ---------------------------------------------------------------------------
# Tile 實例
# ---------------------------------------------------------------------------
class Tile:
    __slots__ = ('tile_id', 'health', 'instance_id', 'color',
                 'required_colors', '_defn', '_cat')

    def __init__(self, tile_id: str, health: int = None, instance_id=None):
        self.tile_id = tile_id
        defn = get_def(tile_id)
        self._defn = defn
        self._cat = defn['category'] if defn else None
        self.health = health if health is not None else (defn['health'] if defn else 1)
        self.instance_id = instance_id  # 多格物件去重
        self.color = get_color(tile_id) if defn else None
        self.required_colors = None  # 飲料櫃開門時需要的顏色

    def copy(self):
        t = Tile.__new__(Tile)
        t.tile_id = self.tile_id
        t.health = self.health
        t.instance_id = self.instance_id
        t.color = self.color
        t.required_colors = self.required_colors
        t._defn = self._defn
        t._cat = self._cat
        return t

    def __repr__(self):
        if self.health > 1:
            return f'{self.tile_id}({self.health})'
        return self.tile_id


# ---------------------------------------------------------------------------
# Cell — 盤面上的一格
# ---------------------------------------------------------------------------
class Cell:
    __slots__ = ('upper', 'middle', 'bottom')

    def __init__(self):
        self.upper = None   # Tile | None  (Rope, Mud)
        self.middle = None  # Tile | None  (Element, Powerup, Obstacle)
        self.bottom = None  # Tile | None  (Puddle)

    def is_empty(self):
        """中層為空（可以掉落新物件進來）"""
        return self.middle is None

    def is_locked(self):
        """被上層物件鎖住（繩索），不可交換"""
        if self.upper is None:
            return False
        return self.upper.tile_id.startswith('Rope')

    def has_mud(self):
        """被泥巴覆蓋"""
        return self.upper is not None and self.upper.tile_id == 'Mud'

    def get_display(self):
        """取得顯示用字串"""
        parts = []
        if self.upper:
            parts.append(f'[{self.upper}]')
        if self.middle:
            parts.append(str(self.middle))
        else:
            parts.append('____')
        if self.bottom:
            parts.append(f'({self.bottom})')
        return ''.join(parts)

    def copy(self):
        c = Cell()
        c.upper = self.upper.copy() if self.upper else None
        c.middle = self.middle.copy() if self.middle else None
        c.bottom = self.bottom.copy() if self.bottom else None
        return c


# ---------------------------------------------------------------------------
# Board — 盤面
# ---------------------------------------------------------------------------
class Board:
    def __init__(self, rows: int, cols: int, num_colors: int = DEFAULT_NUM_COLORS):
        self.rows = rows
        self.cols = cols
        self.num_colors = min(num_colors, len(COLORS))
        self.active_colors = COLORS[:self.num_colors]
        self.grid: list[list[Cell]] = [
            [Cell() for _ in range(cols)] for _ in range(rows)
        ]
        self._next_instance_id = 1
        # 關卡設定：WaterChiller 開門後的血量（預設 3）
        self.waterchiller_open_health = 3
        # 關卡設定：BeverageChiller 開門後的血量（預設 4）
        self.beveragechiller_open_health = 4
        # 製造機生產計數（每步開始前重置）
        self.manufacturer_produced = {}  # {tile_id: count}
        # 元素生成器參數
        self.generator_weights = None  # None=均等, 或 {tile_id: weight} 含顏色和非元素物件

    def new_instance_id(self) -> int:
        iid = self._next_instance_id
        self._next_instance_id += 1
        return iid

    def in_bounds(self, r, c) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def get_cell(self, r, c) -> Cell:
        return self.grid[r][c]

    def get_middle(self, r, c):
        """取得中層 Tile（最常用的操作）"""
        return self.grid[r][c].middle

    def set_middle(self, r, c, tile):
        self.grid[r][c].middle = tile

    def clear_middle(self, r, c):
        self.grid[r][c].middle = None

    # ----- 隨機元素 -----

    def random_element(self) -> Tile:
        """根據生成器權重產生物件（預設均等隨機元素）"""
        if self.generator_weights:
            items = list(self.generator_weights.keys())
            weights = list(self.generator_weights.values())
            tile_id = random.choices(items, weights=weights, k=1)[0]
            return Tile(tile_id)
        color = random.choice(self.active_colors)
        return Tile(color)

    # ----- 初始化（隨機填滿，無初始三連） -----

    def fill_random(self):
        """用隨機元素填滿所有空的中層格子"""
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c].middle is None:
                    self.grid[r][c].middle = self.random_element()

    def remove_initial_matches(self):
        """移除初始盤面的三連和 2x2 方塊（反覆替換直到沒有）"""
        max_iter = 100
        for _ in range(max_iter):
            changed = False
            for r in range(self.rows):
                for c in range(self.cols):
                    tile = self.get_middle(r, c)
                    if tile is None or not is_element(tile.tile_id):
                        continue
                    color = tile.color
                    # 檢查橫向三連
                    if (c >= 2
                            and self._mid_color(r, c-1) == color
                            and self._mid_color(r, c-2) == color):
                        self.set_middle(r, c, self._random_different(color))
                        changed = True
                        continue
                    # 檢查縱向三連
                    if (r >= 2
                            and self._mid_color(r-1, c) == color
                            and self._mid_color(r-2, c) == color):
                        self.set_middle(r, c, self._random_different(color))
                        changed = True
                        continue
                    # 檢查 2x2 方塊（以當前格為右下角）
                    if (r >= 1 and c >= 1
                            and self._mid_color(r-1, c) == color
                            and self._mid_color(r, c-1) == color
                            and self._mid_color(r-1, c-1) == color):
                        self.set_middle(r, c, self._random_different(color))
                        changed = True
            if not changed:
                break

    def _mid_color(self, r, c):
        t = self.get_middle(r, c)
        return t.color if t else None

    def _random_different(self, exclude_color) -> Tile:
        choices = [c for c in self.active_colors if c != exclude_color]
        return Tile(random.choice(choices))

    # ----- 重力 -----

    def _column_drop(self, c):
        """單列直落一輪（從下往上），回傳是否有移動。"""
        grid = self.grid
        rows = self.rows
        moved = False
        for r in range(rows - 2, -1, -1):
            tile = grid[r][c].middle
            if tile is None:
                continue
            defn = tile._defn
            if defn is None or defn['movement'] != 'movable':
                continue
            if grid[r + 1][c].middle is None:
                grid[r + 1][c].middle = tile
                grid[r][c].middle = None
                moved = True
        return moved

    def apply_gravity(self):
        """
        可移動物件掉落，三階段反覆直到穩定：
        Phase 1: 每列直落到底
        Phase 2: DFS 左斜落 — 落到 c-1 後立即直落 c-1，
                 再繼續掃描（左優先），直到所有左斜落完成
        Phase 3: 右斜落 — 同理
        有任何斜落就回到 Phase 1 重新開始。
        """
        rows, cols = self.rows, self.cols
        grid = self.grid

        overall_moved = True
        while overall_moved:
            overall_moved = False

            # Phase 1: 全列直落到底
            for c in range(cols):
                while self._column_drop(c):
                    overall_moved = True

            # Phase 2: 左斜落（DFS 左優先，重複直到無左斜可落）
            left_moved = True
            while left_moved:
                left_moved = False
                for r in range(rows - 2, -1, -1):
                    for c in range(cols):
                        tile = grid[r][c].middle
                        if tile is None:
                            continue
                        defn = tile._defn
                        if defn is None or defn['movement'] != 'movable':
                            continue
                        if grid[r + 1][c].middle is None:
                            continue
                        if c > 0 and grid[r + 1][c - 1].middle is None:
                            grid[r + 1][c - 1].middle = tile
                            grid[r][c].middle = None
                            # 落到 c-1 後立即直落該列
                            while self._column_drop(c - 1):
                                pass
                            left_moved = True
                            overall_moved = True

            # Phase 3: 右斜落（重複直到無右斜可落）
            right_moved = True
            while right_moved:
                right_moved = False
                for r in range(rows - 2, -1, -1):
                    for c in range(cols):
                        tile = grid[r][c].middle
                        if tile is None:
                            continue
                        defn = tile._defn
                        if defn is None or defn['movement'] != 'movable':
                            continue
                        if grid[r + 1][c].middle is None:
                            continue
                        if c < cols - 1 and grid[r + 1][c + 1].middle is None:
                            grid[r + 1][c + 1].middle = tile
                            grid[r][c].middle = None
                            while self._column_drop(c + 1):
                                pass
                            right_moved = True
                            overall_moved = True

    def fill_top(self):
        """填充頂部空格"""
        for c in range(self.cols):
            for r in range(self.rows):
                if self.grid[r][c].middle is None:
                    # 檢查這格是否被固定物件佔著（不該填充）
                    self.grid[r][c].middle = self.random_element()
                else:
                    break  # 遇到非空就停（空格只在頂部連續出現）

    # ----- 交換 -----

    def swap(self, r1, c1, r2, c2):
        """交換兩格的中層物件"""
        self.grid[r1][c1].middle, self.grid[r2][c2].middle = (
            self.grid[r2][c2].middle, self.grid[r1][c1].middle
        )

    def can_swap(self, r1, c1, r2, c2) -> bool:
        """檢查兩格是否可交換"""
        if not self.in_bounds(r1, c1) or not self.in_bounds(r2, c2):
            return False
        # 必須相鄰
        if abs(r1-r2) + abs(c1-c2) != 1:
            return False
        cell1, cell2 = self.grid[r1][c1], self.grid[r2][c2]
        # 被繩索鎖住或泥巴覆蓋不可交換
        if cell1.is_locked() or cell2.is_locked():
            return False
        if cell1.has_mud() or cell2.has_mud():
            return False
        t1, t2 = cell1.middle, cell2.middle
        if t1 is None or t2 is None:
            return False
        # 至少一個可移動
        m1 = is_movable(t1.tile_id) or is_element(t1.tile_id) or is_powerup(t1.tile_id)
        m2 = is_movable(t2.tile_id) or is_element(t2.tile_id) or is_powerup(t2.tile_id)
        if not (m1 and m2):
            return False
        # 兩個都是不可移動障礙物 → 不可交換
        # （可移動障礙物如 Barrel 可以和元素交換）
        return True

    # ----- Shuffle（洗牌） -----

    def shuffle(self):
        """
        洗牌：收集所有可移動的中層物件，隨機重新排列放回原位。
        固定障礙物、上層、下層都不動。
        洗牌後如果仍無合法步驟，會再洗一次（最多 100 次）。
        """
        # 收集可移動物件的座標和 tile
        movable_positions = []
        movable_tiles = []
        for r in range(self.rows):
            for c in range(self.cols):
                tile = self.grid[r][c].middle
                if tile is None:
                    continue
                if is_element(tile.tile_id) or is_powerup(tile.tile_id):
                    movable_positions.append((r, c))
                    movable_tiles.append(tile)
                elif is_movable(tile.tile_id):
                    # 可移動障礙物（Barrel, TrafficCone）也參與洗牌
                    movable_positions.append((r, c))
                    movable_tiles.append(tile)

        if len(movable_tiles) < 2:
            return

        for _ in range(100):
            random.shuffle(movable_tiles)
            for i, (r, c) in enumerate(movable_positions):
                self.grid[r][c].middle = movable_tiles[i]
            # 確保洗牌後沒有立即的三連（避免自動消除）
            # 且有合法步驟可走
            from match_engine import find_matches, find_valid_moves
            if not find_matches(self) and find_valid_moves(self):
                return
        # 100 次都找不到好的排列，就用最後一次的結果

    # ----- 深拷貝 -----

    def copy(self):
        b = Board.__new__(Board)
        b.rows = self.rows
        b.cols = self.cols
        b.num_colors = self.num_colors
        b.active_colors = self.active_colors[:]
        b.grid = [[cell.copy() for cell in row] for row in self.grid]
        b._next_instance_id = self._next_instance_id
        b.waterchiller_open_health = self.waterchiller_open_health
        b.beveragechiller_open_health = self.beveragechiller_open_health
        b.manufacturer_produced = dict(self.manufacturer_produced)
        b.generator_weights = self.generator_weights
        return b

    # ----- 狀態輸出 -----

    def get_state_matrix(self):
        """回傳 2D list[list[str|None]]，格式與 YOLO 輸出一致"""
        result = []
        for r in range(self.rows):
            row = []
            for c in range(self.cols):
                t = self.grid[r][c].middle
                row.append(t.tile_id if t else None)
            result.append(row)
        return result

    def render(self):
        """列印盤面"""
        # 欄位標頭
        header = '     ' + '  '.join(f'{c:^8}' for c in range(self.cols))
        print(header)
        print('     ' + '---------' * self.cols)
        for r in range(self.rows):
            row_str = f'[{r:>2}] '
            for c in range(self.cols):
                cell = self.grid[r][c]
                display = cell.get_display()
                row_str += f'{display:^10}'
            print(row_str)
