"""
遊戲環境 — 對外 API (step / reset / goals / render)

Action 格式:
  {'type': 'swap', 'pos1': (r,c), 'pos2': (r,c)}
  {'type': 'activate', 'pos': (r,c)}       # 點擊道具
"""

import json
import pathlib
from board import Board, Tile
from tile_defs import (
    get_def, is_element, is_powerup, is_obstacle, TILE_REGISTRY,
)
import match_engine


class Match3Env:
    def __init__(self, rows=10, cols=9, num_colors=4,
                 max_steps=30, level_file=None):
        self.default_rows = rows
        self.default_cols = cols
        self.default_num_colors = num_colors
        self.default_max_steps = max_steps
        self.level_file = level_file

        # 目前狀態
        self.board: Board = None
        self.steps_taken = 0
        self.max_steps = max_steps
        self.goals_required = {}   # {tile_id: required_count}
        self.goals_current = {}    # {tile_id: current_count}
        self.done = False
        self.win = False

        if level_file:
            self.reset(level_file=level_file)
        else:
            self.reset()

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self, level_file=None):
        """
        重置遊戲狀態。

        Args:
            level_file: 關卡 JSON 路徑（可選）。
                        若不提供，則使用上次的 level_file 或隨機初始化。

        Returns:
            dict: 初始狀態
        """
        lf = level_file or self.level_file
        self.steps_taken = 0
        self.done = False
        self.win = False

        if lf:
            self._load_level(lf)
        else:
            self.board = Board(self.default_rows, self.default_cols,
                               self.default_num_colors)
            self.max_steps = self.default_max_steps
            self.goals_required = {}
            self.goals_current = {}
            self.board.fill_random()
            self.board.remove_initial_matches()

        return self._get_state()

    # ------------------------------------------------------------------
    # step
    # ------------------------------------------------------------------

    def step(self, action):
        """
        執行一步動作。

        Args:
            action: dict
              {'type': 'swap', 'pos1': (r,c), 'pos2': (r,c)}
              {'type': 'activate', 'pos': (r,c)}

        Returns:
            (state, reward, done, info)
        """
        if self.done:
            return self._get_state(), 0, True, {'msg': 'game already over'}

        reward = 0
        info = {}

        # 快照：記錄動作前的盤面狀態（用於目標追蹤）
        self.board.manufacturer_produced = {}  # 重置製造機計數
        snapshot_before = self._snapshot_goals()

        action_type = action.get('type', 'swap')

        if action_type == 'swap':
            r1, c1 = action['pos1']
            r2, c2 = action['pos2']

            if not self.board.can_swap(r1, c1, r2, c2):
                return self._get_state(), -1, False, {'msg': 'invalid swap'}

            t1 = self.board.get_middle(r1, c1)
            t2 = self.board.get_middle(r2, c2)

            # 道具合成
            if t1 and t2 and is_powerup(t1.tile_id) and is_powerup(t2.tile_id):
                self.board.swap(r1, c1, r2, c2)
                match_engine.combine_powerups(
                    self.board, r1, c1, r2, c2,
                    goals_required=self.goals_required,
                )
                self.board.apply_gravity()
                self.board.fill_top()
                match_engine.resolve(self.board)
                self.steps_taken += 1

            # 紙風車 + 元素
            elif t1 and t2 and (
                (t1.tile_id == 'LtBl' and is_element(t2.tile_id)) or
                (t2.tile_id == 'LtBl' and is_element(t1.tile_id))
            ):
                self.board.swap(r1, c1, r2, c2)
                match_engine.combine_powerups(
                    self.board, r1, c1, r2, c2,
                    goals_required=self.goals_required,
                )
                self.board.apply_gravity()
                self.board.fill_top()
                match_engine.resolve(self.board)
                self.steps_taken += 1

            # 道具 + 非道具：道具在新位置啟動
            elif t1 and t2 and (
                (is_powerup(t1.tile_id) and not is_powerup(t2.tile_id)) or
                (is_powerup(t2.tile_id) and not is_powerup(t1.tile_id))
            ):
                self.board.swap(r1, c1, r2, c2)
                # 道具移到新位置後啟動
                if is_powerup(t1.tile_id):
                    # t1 原在 (r1,c1), swap 後在 (r2,c2)
                    match_engine.activate_powerup(
                        self.board, r2, c2,
                        goals_required=self.goals_required,
                    )
                else:
                    # t2 原在 (r2,c2), swap 後在 (r1,c1)
                    match_engine.activate_powerup(
                        self.board, r1, c1,
                        goals_required=self.goals_required,
                    )
                self.board.apply_gravity()
                self.board.fill_top()
                match_engine.resolve(self.board)
                self.steps_taken += 1

            else:
                # 普通交換
                self.board.swap(r1, c1, r2, c2)
                matches = match_engine.find_matches(self.board)
                if not matches:
                    # 沒有消除 → 換回
                    self.board.swap(r1, c1, r2, c2)
                    return self._get_state(), -1, False, {'msg': 'no match'}

                match_engine.resolve(self.board)
                self.steps_taken += 1

        elif action_type == 'activate':
            r, c = action['pos']
            tile = self.board.get_middle(r, c)
            if tile is None or not is_powerup(tile.tile_id):
                return self._get_state(), -1, False, {'msg': 'not a powerup'}

            match_engine.activate_powerup(
                self.board, r, c,
                goals_required=self.goals_required,
            )
            self.board.apply_gravity()
            self.board.fill_top()
            match_engine.resolve(self.board)
            self.steps_taken += 1

        else:
            return self._get_state(), -1, False, {'msg': f'unknown action type: {action_type}'}

        # 用盤面快照差異來追蹤目標進度（比在引擎內部追蹤可靠）
        snapshot_after = self._snapshot_goals()
        eliminated = self._diff_snapshots(snapshot_before, snapshot_after)
        for tile_id, count in eliminated.items():
            if tile_id in self.goals_required:
                self.goals_current[tile_id] = self.goals_current.get(tile_id, 0) + count
        # 製造機生產的目標物（Stamp 不會從盤面消失，快照差異抓不到）
        for tile_id, count in self.board.manufacturer_produced.items():
            if tile_id in self.goals_required:
                self.goals_current[tile_id] = self.goals_current.get(tile_id, 0) + count
        reward = sum(count * (5 if is_obstacle(tid) else 1) for tid, count in eliminated.items())
        info['eliminated'] = eliminated

        # 檢查遊戲結束條件
        if self.goals_met():
            self.done = True
            self.win = True
            reward += 100
            info['msg'] = 'win'
        elif self.steps_taken >= self.max_steps:
            self.done = True
            self.win = False
            info['msg'] = 'out of steps'
        else:
            # 檢查是否需要洗牌（無合法步驟時自動 shuffle）
            if not self.get_valid_moves():
                self.board.shuffle()
                info['shuffled'] = True

        return self._get_state(), reward, self.done, info

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def goals_met(self) -> bool:
        """檢查是否所有目標都達成"""
        if not self.goals_required:
            return False
        for tile_id, required in self.goals_required.items():
            if self.goals_current.get(tile_id, 0) < required:
                return False
        return True

    def get_valid_moves(self):
        """回傳所有合法動作"""
        swap_moves = match_engine.find_valid_moves(self.board)
        actions = []
        for m in swap_moves:
            actions.append({
                'type': 'swap',
                'pos1': m['pos1'],
                'pos2': m['pos2'],
                'move_type': m['type'],
            })

        # 可直接點擊的道具
        for r in range(self.board.rows):
            for c in range(self.board.cols):
                tile = self.board.get_middle(r, c)
                if tile and is_powerup(tile.tile_id):
                    # 只有不被鎖住的道具可以點擊
                    cell = self.board.get_cell(r, c)
                    if not cell.is_locked():
                        actions.append({
                            'type': 'activate',
                            'pos': (r, c),
                        })

        return actions

    def get_goals_progress(self):
        """回傳目標進度"""
        progress = {}
        for tile_id, required in self.goals_required.items():
            current = self.goals_current.get(tile_id, 0)
            progress[tile_id] = {
                'current': current,
                'required': required,
                'met': current >= required,
            }
        return progress

    # ------------------------------------------------------------------
    # render
    # ------------------------------------------------------------------

    def render(self):
        """列印遊戲狀態"""
        print(f'=== 第 {self.steps_taken} 步 / 上限 {self.max_steps} 步 ===')

        # 目標
        if self.goals_required:
            print('目標:')
            for tile_id, required in self.goals_required.items():
                current = self.goals_current.get(tile_id, 0)
                status = '完成' if current >= required else f'{current}/{required}'
                print(f'  {tile_id}: {status}')

        # 盤面
        self.board.render()

        if self.done:
            print('結果:', '勝利！' if self.win else '失敗')
        print()

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _get_state(self):
        """回傳狀態 dict（供 agent 使用）"""
        return {
            'board': self.board.get_state_matrix(),
            'steps_taken': self.steps_taken,
            'max_steps': self.max_steps,
            'goals_required': dict(self.goals_required),
            'goals_current': dict(self.goals_current),
            'done': self.done,
            'win': self.win,
        }

    def _snapshot_goals(self):
        """快照盤面上所有目標相關物件的數量"""
        counts = {}
        for r in range(self.board.rows):
            for c in range(self.board.cols):
                # 中層
                tile = self.board.get_middle(r, c)
                if tile:
                    counts[tile.tile_id] = counts.get(tile.tile_id, 0) + 1
                # 上層
                cell = self.board.get_cell(r, c)
                if cell.upper:
                    counts[cell.upper.tile_id] = counts.get(cell.upper.tile_id, 0) + 1
                # 下層
                if cell.bottom:
                    counts[cell.bottom.tile_id] = counts.get(cell.bottom.tile_id, 0) + 1
        return counts

    def _diff_snapshots(self, before, after):
        """計算兩個快照之間的差異（被消除的物件）"""
        eliminated = {}
        all_ids = set(before.keys()) | set(after.keys())
        for tile_id in all_ids:
            diff = before.get(tile_id, 0) - after.get(tile_id, 0)
            if diff > 0:
                eliminated[tile_id] = diff
        return eliminated

    def _load_level(self, level_file):
        """載入關卡 JSON"""
        path = pathlib.Path(level_file)
        if not path.is_absolute():
            path = pathlib.Path(__file__).parent / path

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        rows = data['rows']
        cols = data['cols']
        num_colors = data.get('num_colors', self.default_num_colors)
        self.max_steps = data.get('max_steps', self.default_max_steps)
        self.goals_required = dict(data.get('goals', {}))
        self.goals_current = {}
        self.level_file = level_file

        self.board = Board(rows, cols, num_colors)
        # 關卡特殊設定
        self.board.waterchiller_open_health = data.get('waterchiller_open_health', 3)
        self.board.beveragechiller_open_health = data.get('beveragechiller_open_health', 4)

        # 元素生成器權重（可設定各色機率和非元素物件生成）
        gen_weights = data.get('generator_weights', None)
        if gen_weights:
            self.board.generator_weights = gen_weights

        board_data = data.get('board')
        if board_data is None:
            # 無盤面定義 → 隨機
            self.board.fill_random()
            self.board.remove_initial_matches()
            return

        # 飲料櫃顏色設定（全域，套用到所有 BeverageChiller）
        self._beverage_colors = data.get('beverage_colors', None)

        # 新格式: board 是 dict 包含 middle / upper / bottom
        if isinstance(board_data, dict):
            self._load_layered_board(board_data, rows, cols)
        else:
            # 舊格式: board 是 2D array → 視為 middle 層
            self._load_simple_board(board_data, rows, cols)

        # 對所有 BeverageChiller 設定 required_colors
        if self._beverage_colors:
            for r in range(rows):
                for c in range(cols):
                    tile = self.board.get_middle(r, c)
                    if tile and tile.tile_id.startswith('BeverageChiller'):
                        tile.required_colors = list(self._beverage_colors)

    def _parse_tile_id(self, raw_id):
        """解析 tile_id，處理 #N 實例標記（如 'Pool_lv3#1'）"""
        if '#' in raw_id:
            tile_id, instance_tag = raw_id.rsplit('#', 1)
            return tile_id, instance_tag
        return raw_id, None

    def _make_tile(self, raw_id, instance_map):
        """建立 Tile，處理 instance_id 共用"""
        tile_id, instance_tag = self._parse_tile_id(raw_id)
        if tile_id not in TILE_REGISTRY:
            defn = get_def(tile_id)
            if defn is None:
                return None
        tile = Tile(tile_id)
        if instance_tag is not None:
            key = (tile_id, instance_tag)
            if key not in instance_map:
                instance_map[key] = self.board.new_instance_id()
            tile.instance_id = instance_map[key]
        return tile

    def _load_simple_board(self, board_2d, rows, cols):
        """舊格式：2D array → middle 層（只載入非元素物件，元素隨機生成）"""
        instance_map = {}
        for r in range(min(rows, len(board_2d))):
            row_data = board_2d[r]
            for c in range(min(cols, len(row_data))):
                raw_id = row_data[c]
                if raw_id is None:
                    continue
                tile = self._make_tile(raw_id, instance_map)
                if tile and not is_element(tile.tile_id):
                    # 只放障礙物/道具，元素由隨機填充
                    self.board.set_middle(r, c, tile)

        # 隨機填充元素到空格
        for r in range(rows):
            for c in range(cols):
                if self.board.get_middle(r, c) is None:
                    self.board.set_middle(r, c, self.board.random_element())

        # 消除初始三連
        self.board.remove_initial_matches()

    def _load_layered_board(self, board_dict, rows, cols):
        """新格式：dict 包含 middle / upper / bottom（中層元素隨機生成）"""
        instance_map = {}

        # middle（只載入非元素物件）
        middle_data = board_dict.get('middle')
        if middle_data:
            for r in range(min(rows, len(middle_data))):
                for c in range(min(cols, len(middle_data[r]))):
                    raw_id = middle_data[r][c]
                    if raw_id:
                        tile = self._make_tile(raw_id, instance_map)
                        if tile and not is_element(tile.tile_id):
                            self.board.set_middle(r, c, tile)

        # upper
        upper_data = board_dict.get('upper')
        if upper_data:
            for r in range(min(rows, len(upper_data))):
                for c in range(min(cols, len(upper_data[r]))):
                    raw_id = upper_data[r][c]
                    if raw_id:
                        tile = self._make_tile(raw_id, instance_map)
                        if tile:
                            self.board.get_cell(r, c).upper = tile

        # bottom
        bottom_data = board_dict.get('bottom')
        if bottom_data:
            for r in range(min(rows, len(bottom_data))):
                for c in range(min(cols, len(bottom_data[r]))):
                    raw_id = bottom_data[r][c]
                    if raw_id:
                        tile = self._make_tile(raw_id, instance_map)
                        if tile:
                            self.board.get_cell(r, c).bottom = tile

        # 隨機填充元素到空格
        for r in range(rows):
            for c in range(cols):
                if self.board.get_middle(r, c) is None:
                    self.board.set_middle(r, c, self.board.random_element())

        # 消除初始三連
        self.board.remove_initial_matches()
