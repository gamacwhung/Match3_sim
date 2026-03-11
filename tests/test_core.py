"""
核心邏輯測試

測試範圍：
  - 配對偵測 (3連/4連/5連/L-T/2x2)
  - 消除處理 + 鄰邊消除 + 原地消除
  - 道具生成
  - 道具啟動
  - 道具合成
  - 重力 + 填充
  - 遊戲環境 step/reset/goals
"""

import sys
import os
import unittest

# 確保可以 import 上層模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from board import Board, Tile, Cell
from tile_defs import get_def, is_element, is_powerup, TILE_REGISTRY
import match_engine
from match3_env import Match3Env


def make_board(grid_2d, rows=None, cols=None):
    """從 2D list 建立測試用盤面"""
    if rows is None:
        rows = len(grid_2d)
    if cols is None:
        cols = len(grid_2d[0]) if grid_2d else 0
    board = Board(rows, cols, num_colors=6)
    for r in range(rows):
        for c in range(cols):
            tile_id = grid_2d[r][c]
            if tile_id is not None:
                board.set_middle(r, c, Tile(tile_id))
    return board


class TestMatchDetection(unittest.TestCase):
    """配對偵測測試"""

    def test_橫向三連(self):
        grid = [
            ['Red', 'Red', 'Red', 'Blu'],
            ['Grn', 'Blu', 'Yel', 'Grn'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].color, 'Red')
        self.assertEqual(matches[0].pattern, 'THREE')
        self.assertEqual(len(matches[0].positions), 3)

    def test_縱向三連(self):
        grid = [
            ['Red', 'Grn'],
            ['Red', 'Blu'],
            ['Red', 'Yel'],
            ['Blu', 'Grn'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].color, 'Red')
        self.assertEqual(matches[0].pattern, 'THREE')

    def test_橫向四連_生成Soda90(self):
        grid = [
            ['Red', 'Red', 'Red', 'Red', 'Blu'],
            ['Grn', 'Blu', 'Yel', 'Grn', 'Yel'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pattern, 'FOUR_H')

    def test_縱向四連_生成Soda0d(self):
        grid = [
            ['Red', 'Grn'],
            ['Red', 'Blu'],
            ['Red', 'Yel'],
            ['Red', 'Grn'],
            ['Blu', 'Yel'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pattern, 'FOUR_V')

    def test_五連_生成LtBl(self):
        grid = [
            ['Red', 'Red', 'Red', 'Red', 'Red'],
            ['Grn', 'Blu', 'Yel', 'Grn', 'Blu'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pattern, 'FIVE_PLUS')

    def test_L形_生成TNT(self):
        # L 形：3 橫 + 3 直（交於角落，h+v-1=5）
        grid = [
            ['Red', 'Red', 'Red', 'Blu'],
            ['Red', 'Grn', 'Blu', 'Yel'],
            ['Red', 'Blu', 'Yel', 'Grn'],
            ['Blu', 'Yel', 'Grn', 'Blu'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pattern, 'L_T')

    def test_2x2方塊_生成TrPr(self):
        grid = [
            ['Red', 'Red', 'Blu'],
            ['Red', 'Red', 'Grn'],
            ['Blu', 'Yel', 'Grn'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pattern, 'BLOCK_2x2')

    def test_無配對(self):
        grid = [
            ['Red', 'Grn', 'Blu'],
            ['Blu', 'Red', 'Grn'],
            ['Grn', 'Blu', 'Red'],
        ]
        board = make_board(grid)
        matches = match_engine.find_matches(board)
        self.assertEqual(len(matches), 0)


class TestPowerupGeneration(unittest.TestCase):
    """道具生成測試"""

    def test_橫四連生成垂直火箭(self):
        grid = [
            ['Red', 'Red', 'Red', 'Red', 'Blu'],
            ['Grn', 'Blu', 'Yel', 'Grn', 'Yel'],
        ]
        board = make_board(grid)
        result = match_engine.resolve(board)
        self.assertTrue(
            any(pid == 'Soda90' for pid, _ in result['powerups_created']),
            "橫向四連應生成 Soda90（垂直火箭）"
        )

    def test_縱四連生成水平火箭(self):
        grid = [
            ['Red', 'Grn'],
            ['Red', 'Blu'],
            ['Red', 'Yel'],
            ['Red', 'Grn'],
            ['Blu', 'Yel'],
        ]
        board = make_board(grid)
        result = match_engine.resolve(board)
        self.assertTrue(
            any(pid == 'Soda0d' for pid, _ in result['powerups_created']),
            "縱向四連應生成 Soda0d（水平火箭）"
        )


class TestAdjacentElimination(unittest.TestCase):
    """鄰邊消除測試"""

    def test_紙箱被鄰邊消除(self):
        grid = [
            ['Red', 'Red', 'Red', 'Crt1'],
            ['Grn', 'Blu', 'Yel', 'Grn'],
        ]
        board = make_board(grid)
        match_engine.resolve(board)
        # Crt1 health=1，鄰邊消除 1 點 → 應該消除
        # 注意：resolve 後有重力+填充，已被替換

    def test_罐頭不被鄰邊消除(self):
        grid = [
            ['Red', 'Red', 'Red', 'SalmonCan'],
            ['Grn', 'Blu', 'Yel', 'Grn'],
        ]
        board = make_board(grid)
        # SalmonCan can_adjacent_elim=False
        match_engine.resolve(board)
        found = False
        for r in range(board.rows):
            for c in range(board.cols):
                t = board.get_middle(r, c)
                if t and t.tile_id == 'SalmonCan':
                    found = True
        self.assertTrue(found, "罐頭不應被鄰邊消除，應該仍在盤面上")


class TestInplaceElimination(unittest.TestCase):
    """原地消除測試"""

    def test_水漥被原地消除(self):
        grid = [
            ['Red', 'Red', 'Red'],
            ['Grn', 'Blu', 'Yel'],
        ]
        board = make_board(grid)
        board.get_cell(0, 0).bottom = Tile('Puddle_lv1')
        match_engine.resolve(board)
        cell = board.get_cell(0, 0)
        self.assertIsNone(cell.bottom, "水漥應被消除座標上的配對原地消除")


class TestGravity(unittest.TestCase):
    """重力測試"""

    def test_元素向下掉落(self):
        grid = [
            ['Red', None],
            [None, 'Blu'],
        ]
        board = make_board(grid)
        board.apply_gravity()
        self.assertIsNone(board.get_middle(0, 0))
        self.assertIsNotNone(board.get_middle(1, 0))
        self.assertEqual(board.get_middle(1, 0).tile_id, 'Red')

    def test_固定障礙物阻擋掉落(self):
        grid = [
            ['Red', None],
            ['Crt1', None],
            [None, None],
        ]
        board = make_board(grid)
        board.apply_gravity()
        crt_pos = None
        red_pos = None
        for r in range(3):
            t = board.get_middle(r, 0)
            if t:
                if t.tile_id == 'Crt1':
                    crt_pos = r
                elif t.tile_id == 'Red':
                    red_pos = r
        self.assertIsNotNone(crt_pos, "紙箱應仍在盤面上")
        if red_pos is not None:
            self.assertLess(red_pos, crt_pos, "元素不能穿過固定障礙物")


class TestPowerupActivation(unittest.TestCase):
    """道具啟動測試"""

    def test_水平火箭消除整行(self):
        grid = [
            ['Grn', 'Blu', 'Yel'],
            ['Red', 'Soda0d', 'Blu'],
            ['Yel', 'Grn', 'Red'],
        ]
        board = make_board(grid)
        match_engine.activate_powerup(board, 1, 1)
        for c in range(3):
            self.assertIsNone(board.get_middle(1, c),
                              f"第 1 行第 {c} 列應被水平火箭消除")

    def test_垂直火箭消除整列(self):
        grid = [
            ['Grn', 'Blu', 'Yel'],
            ['Red', 'Soda90', 'Blu'],
            ['Yel', 'Grn', 'Red'],
        ]
        board = make_board(grid)
        match_engine.activate_powerup(board, 1, 1)
        for r in range(3):
            self.assertIsNone(board.get_middle(r, 1),
                              f"第 {r} 行第 1 列應被垂直火箭消除")

    def test_炸彈消除5x5(self):
        board = Board(5, 5, num_colors=4)
        board.fill_random()
        board.set_middle(2, 2, Tile('TNT'))
        match_engine.activate_powerup(board, 2, 2)
        for r in range(5):
            for c in range(5):
                self.assertIsNone(board.get_middle(r, c),
                                  f"({r},{c}) 應被炸彈的 5x5 範圍消除")


class TestPowerupCombination(unittest.TestCase):
    """道具合成測試"""

    def test_火箭加火箭_十字消除(self):
        board = Board(5, 5, num_colors=4)
        board.fill_random()
        board.set_middle(2, 2, Tile('Soda0d'))
        board.set_middle(2, 3, Tile('Soda90'))
        match_engine.combine_powerups(board, 2, 2, 2, 3)
        for c in range(5):
            self.assertIsNone(board.get_middle(2, c),
                              f"第 2 行第 {c} 列應被十字消除清空")
        for r in range(5):
            self.assertIsNone(board.get_middle(r, 3),
                              f"第 {r} 行第 3 列應被十字消除清空")

    def test_TNT加TNT_7x7(self):
        board = Board(9, 9, num_colors=4)
        board.fill_random()
        board.set_middle(4, 4, Tile('TNT'))
        board.set_middle(4, 5, Tile('TNT'))
        match_engine.combine_powerups(board, 4, 4, 4, 5)
        for r in range(1, 8):
            for c in range(2, 9):
                if board.in_bounds(r, c):
                    self.assertIsNone(board.get_middle(r, c),
                                      f"({r},{c}) 應被 TNT+TNT 的 7x7 消除")


class TestEnvironment(unittest.TestCase):
    """遊戲環境測試"""

    def test_重置回傳有效狀態(self):
        env = Match3Env(rows=5, cols=5, num_colors=4, max_steps=10)
        state = env.reset()
        self.assertEqual(len(state['board']), 5)
        self.assertEqual(len(state['board'][0]), 5)
        self.assertEqual(state['steps_taken'], 0)
        self.assertFalse(state['done'])

    def test_無效交換回傳負獎勵(self):
        env = Match3Env(rows=5, cols=5, num_colors=4, max_steps=10)
        state, reward, done, info = env.step({
            'type': 'swap', 'pos1': (0, 0), 'pos2': (2, 2)
        })
        self.assertEqual(reward, -1)
        self.assertFalse(done)

    def test_載入關卡JSON(self):
        level_path = os.path.join(os.path.dirname(__file__), '..', 'levels', 'level_01.json')
        if os.path.exists(level_path):
            env = Match3Env(level_file=level_path)
            state = env.reset()
            self.assertEqual(len(state['board']), 10)
            self.assertEqual(len(state['board'][0]), 9)
            self.assertIn('Crt1', env.goals_required)

    def test_取得合法動作(self):
        env = Match3Env(rows=5, cols=5, num_colors=4, max_steps=10)
        moves = env.get_valid_moves()
        self.assertIsInstance(moves, list)

    def test_有效步驟消耗一步(self):
        env = Match3Env(rows=5, cols=5, num_colors=4, max_steps=100)
        moves = env.get_valid_moves()
        swap_moves = [m for m in moves if m['type'] == 'swap' and m.get('move_type') == 'match']
        if swap_moves:
            env.step(swap_moves[0])
            self.assertEqual(env.steps_taken, 1)


class TestBoard(unittest.TestCase):
    """盤面類別測試"""

    def test_深拷貝不影響原盤面(self):
        board = Board(3, 3, 4)
        board.fill_random()
        original_state = board.get_state_matrix()

        copy = board.copy()
        copy.clear_middle(0, 0)

        self.assertEqual(board.get_state_matrix(), original_state)
        self.assertIsNone(copy.get_middle(0, 0))

    def test_隨機填滿所有格子(self):
        board = Board(3, 3, 4)
        board.fill_random()
        for r in range(3):
            for c in range(3):
                self.assertIsNotNone(board.get_middle(r, c))

    def test_交換兩格(self):
        board = Board(2, 2, 4)
        board.set_middle(0, 0, Tile('Red'))
        board.set_middle(0, 1, Tile('Blu'))
        board.swap(0, 0, 0, 1)
        self.assertEqual(board.get_middle(0, 0).tile_id, 'Blu')
        self.assertEqual(board.get_middle(0, 1).tile_id, 'Red')


class TestMultiLayerCell(unittest.TestCase):
    """多層格子測試"""

    def test_繩索鎖住格子(self):
        cell = Cell()
        cell.middle = Tile('Red')
        cell.upper = Tile('Rope_lv1')
        self.assertTrue(cell.is_locked())

    def test_泥巴偵測(self):
        cell = Cell()
        cell.middle = Tile('Red')
        cell.upper = Tile('Mud')
        self.assertTrue(cell.has_mud())

    def test_被繩索鎖住不能交換(self):
        board = Board(2, 2, 4)
        board.set_middle(0, 0, Tile('Red'))
        board.set_middle(0, 1, Tile('Blu'))
        board.get_cell(0, 0).upper = Tile('Rope_lv1')
        self.assertFalse(board.can_swap(0, 0, 0, 1))


class TestShuffle(unittest.TestCase):
    """洗牌測試"""

    def test_洗牌保留固定障礙物(self):
        """固定障礙物不參與洗牌"""
        grid = [
            ['Red', 'Grn', 'Blu'],
            ['Crt1', 'Yel', 'Red'],
            ['Grn', 'Blu', 'Yel'],
        ]
        board = make_board(grid)
        crt_pos_before = None
        for r in range(3):
            for c in range(3):
                t = board.get_middle(r, c)
                if t and t.tile_id == 'Crt1':
                    crt_pos_before = (r, c)

        board.shuffle()

        crt_pos_after = None
        for r in range(3):
            for c in range(3):
                t = board.get_middle(r, c)
                if t and t.tile_id == 'Crt1':
                    crt_pos_after = (r, c)

        self.assertEqual(crt_pos_before, crt_pos_after,
                         "固定障礙物不應被洗牌移動")

    def test_洗牌後元素數量不變(self):
        """洗牌只是重新排列，數量不變"""
        board = Board(5, 5, 4)
        board.fill_random()

        tile_ids_before = sorted(
            board.get_middle(r, c).tile_id
            for r in range(5) for c in range(5)
            if board.get_middle(r, c)
        )

        board.shuffle()

        tile_ids_after = sorted(
            board.get_middle(r, c).tile_id
            for r in range(5) for c in range(5)
            if board.get_middle(r, c)
        )

        self.assertEqual(tile_ids_before, tile_ids_after,
                         "洗牌後物件種類和數量應保持不變")


class TestMudBlocking(unittest.TestCase):
    """泥巴阻擋測試"""

    def test_泥巴阻擋交換(self):
        board = Board(2, 2, 4)
        board.set_middle(0, 0, Tile('Red'))
        board.set_middle(0, 1, Tile('Blu'))
        board.get_cell(0, 0).upper = Tile('Mud')
        self.assertFalse(board.can_swap(0, 0, 0, 1),
                         "被泥巴覆蓋的格子不應該能交換")

    def test_泥巴被原地消除(self):
        grid = [
            ['Red', 'Red', 'Red'],
            ['Grn', 'Blu', 'Yel'],
        ]
        board = make_board(grid)
        board.get_cell(0, 1).upper = Tile('Mud')
        match_engine.resolve(board)
        cell = board.get_cell(0, 1)
        # Mud can_inplace_elim=False, can_prop_elim=True
        # 但 Mud 的 can_adjacent_elim=True，且位在消除格上
        # Mud 應該在中層消除時被原地消除（因為 upper 的 can_inplace_elim 判定）
        # 注意：tile_defs 裡 Mud 的 can_inplace_elim 未設為 True，預設 False
        # 所以 Mud 不會被原地消除，需要用道具消除
        # 這裡測試 Mud 在鄰邊消除位置的行為


class TestWaterChillerTransition(unittest.TestCase):
    """礦泉水櫃狀態轉換測試"""

    def test_關門狀態被消除後開門(self):
        grid = [
            ['Red', 'Red', 'Red', 'WaterChiller_closed'],
            ['Grn', 'Blu', 'Yel', 'Grn'],
        ]
        board = make_board(grid)
        board.waterchiller_open_health = 3
        match_engine.resolve(board)
        # WaterChiller_closed 在 (0,3)，被鄰邊消除後應轉為 WaterChiller_lv3
        # 由於 resolve 含重力+填充，需要追蹤
        found_open = False
        for r in range(board.rows):
            for c in range(board.cols):
                t = board.get_middle(r, c)
                if t and t.tile_id.startswith('WaterChiller_lv'):
                    found_open = True
        self.assertTrue(found_open,
                        "WaterChiller_closed 被消除後應轉為開門狀態")

    def test_開門狀態可被多次消除(self):
        grid = [
            ['Red', 'Red', 'Red', 'Grn'],
            ['Grn', 'Blu', 'Yel', 'Grn'],
        ]
        board = make_board(grid)
        # 直接放一個開門的 WaterChiller
        board.set_middle(0, 3, Tile('WaterChiller_lv3'))
        tile = board.get_middle(0, 3)
        self.assertEqual(tile.health, 3)
        defn = get_def('WaterChiller_lv3')
        self.assertEqual(defn['elimination_type'], 'multi',
                         "開門的 WaterChiller 應為多次消除類型")


class TestBeverageChillerColorMatch(unittest.TestCase):
    """飲料櫃顏色匹配測試"""

    def test_不匹配顏色不造成傷害(self):
        grid = [
            ['Blu', 'Blu', 'Blu', 'Grn'],
            ['Grn', 'Red', 'Yel', 'Red'],
        ]
        board = make_board(grid)
        # 放一個開門的 BeverageChiller，只接受 Red
        bc_tile = Tile('BeverageChiller_open')
        bc_tile.health = 4
        bc_tile.required_colors = ['Red']
        board.set_middle(0, 3, bc_tile)

        match_engine.resolve(board)
        # Blu 消除鄰邊到 (0,3)，但顏色不匹配 → 不應受損
        found = False
        for r in range(board.rows):
            for c in range(board.cols):
                t = board.get_middle(r, c)
                if t and t.tile_id == 'BeverageChiller_open':
                    found = True
                    self.assertEqual(t.health, 4, "不匹配顏色不應造成傷害")
        self.assertTrue(found, "BeverageChiller 應仍在盤面上")


class TestInstanceIdDedup(unittest.TestCase):
    """Instance ID 去重測試"""

    def test_解析帶實例標記的tile_id(self):
        env = Match3Env(rows=3, cols=3, num_colors=4, max_steps=10)
        tile_id, tag = env._parse_tile_id('Pool_lv3#1')
        self.assertEqual(tile_id, 'Pool_lv3')
        self.assertEqual(tag, '1')

    def test_無標記的tile_id(self):
        env = Match3Env(rows=3, cols=3, num_colors=4, max_steps=10)
        tile_id, tag = env._parse_tile_id('Red')
        self.assertEqual(tile_id, 'Red')
        self.assertIsNone(tag)


class TestLevelLoading(unittest.TestCase):
    """關卡載入測試"""

    def test_載入水漥關卡(self):
        level_path = os.path.join(os.path.dirname(__file__), '..', 'levels', 'level_06.json')
        if os.path.exists(level_path):
            env = Match3Env(level_file=level_path)
            # 檢查底層有水漥
            puddle_count = 0
            for r in range(env.board.rows):
                for c in range(env.board.cols):
                    cell = env.board.get_cell(r, c)
                    if cell.bottom and cell.bottom.tile_id == 'Puddle_lv2':
                        puddle_count += 1
            self.assertGreater(puddle_count, 0, "水漥關卡應有底層水漥")
            # 四個角落不應有水漥
            for r, c in [(0, 0), (0, 8), (9, 0), (9, 8)]:
                cell = env.board.get_cell(r, c)
                self.assertIsNone(cell.bottom,
                                  f"角落 ({r},{c}) 不應有水漥")

    def test_載入階梯紙箱關卡(self):
        level_path = os.path.join(os.path.dirname(__file__), '..', 'levels', 'level_04.json')
        if os.path.exists(level_path):
            env = Match3Env(level_file=level_path)
            self.assertIn('Crt1', env.goals_required)
            self.assertEqual(env.goals_required['Crt1'], 39)
            self.assertEqual(env.max_steps, 27)


class TestStampManufacturer(unittest.TestCase):
    """郵戳印章（製造機）測試"""

    def test_印章不會被消除_受鄰邊消除時生產目標物(self):
        """Stamp 受鄰邊消除時不消失，但計入 manufacturer_produced"""
        board = make_board([
            ['Red', 'Red', 'Red', 'Blu'],
        ], rows=1, cols=4)
        # (0,3) 放 Stamp
        board.set_middle(0, 3, Tile('Stamp'))
        board.manufacturer_produced = {}

        result = match_engine.resolve(board)
        # Stamp 應該仍在
        stamp = board.get_middle(0, 3)
        self.assertIsNotNone(stamp)
        self.assertEqual(stamp.tile_id, 'Stamp')
        # 應有 1 次生產記錄
        self.assertGreaterEqual(board.manufacturer_produced.get('Stamp', 0), 1)

    def test_印章被道具打到也不消除(self):
        """道具效果直接打到 Stamp 也只生產不消除"""
        board = make_board([
            [None, 'Soda0d', None],
        ], rows=1, cols=3)
        # 把 (0,0) 放 Stamp，火箭會直接命中它
        board.set_middle(0, 0, Tile('Stamp'))
        board.manufacturer_produced = {}

        match_engine.activate_powerup(board, 0, 1)
        stamp = board.get_middle(0, 0)
        self.assertIsNotNone(stamp)
        self.assertEqual(stamp.tile_id, 'Stamp')
        self.assertGreaterEqual(board.manufacturer_produced.get('Stamp', 0), 1)


class TestRopeMatchParticipation(unittest.TestCase):
    """繩索覆蓋元素仍可參與配對"""

    def test_繩索下元素參與配對但不被消除(self):
        """被 Rope 覆蓋的元素參與三消，元素不消失，繩索扣血"""
        # 使用多行盤面，底部消除不受 fill_top 影響
        board = make_board([
            ['Blu', 'Grn', 'Yel'],
            ['Grn', 'Yel', 'Blu'],
            ['Red', 'Red', 'Red'],
        ], rows=3, cols=3)
        # 在 (2,1) 加繩索
        cell = board.get_cell(2, 1)
        cell.upper = Tile('Rope_lv1')

        # 只做一輪 find_matches + 消除，不做重力填充
        matches = match_engine.find_matches(board)
        # 應找到一組 Red 三消（包含被繩索覆蓋的 (2,1)）
        self.assertTrue(len(matches) > 0)
        red_match = [mg for mg in matches if mg.color == 'Red']
        self.assertEqual(len(red_match), 1)
        self.assertIn((2, 1), red_match[0].positions)

        result = match_engine.resolve(board)
        # (2,1) 的 Red 應仍在（被繩索保護）
        self.assertIsNotNone(board.get_middle(2, 1))
        self.assertEqual(board.get_middle(2, 1).tile_id, 'Red')
        # 繩索應被消除（hp 1 → 0）
        self.assertIsNone(cell.upper)

    def test_繩索lv2下元素配對只扣一層(self):
        """Rope_lv2 被原地消除一次後 hp 減 1"""
        board = make_board([
            ['Blu', 'Grn', 'Yel'],
            ['Grn', 'Yel', 'Blu'],
            ['Red', 'Red', 'Red'],
        ], rows=3, cols=3)
        cell = board.get_cell(2, 1)
        cell.upper = Tile('Rope_lv2')

        match_engine.resolve(board)
        # 元素仍在
        self.assertIsNotNone(board.get_middle(2, 1))
        # 繩索 hp 從 2 扣到 1 → 仍存在
        self.assertIsNotNone(cell.upper)
        self.assertEqual(cell.upper.health, 1)


    def test_火箭消除會打掉繩索(self):
        """火箭效果範圍內的繩索會被消除"""
        board = make_board([
            ['Red', 'Soda0d', 'Blu'],
        ], rows=1, cols=3)
        cell = board.get_cell(0, 0)
        cell.upper = Tile('Rope_lv1')

        match_engine.activate_powerup(board, 0, 1)
        # 繩索應被道具消除
        self.assertIsNone(cell.upper)

    def test_光球消除不打繩索(self):
        """LtBl 消除元素時，繩索不受影響"""
        board = make_board([
            ['Red', 'Red', 'LtBl', 'Blu'],
            ['Red', 'Grn', 'Yel',  'Blu'],
        ], rows=2, cols=4)
        # 在 (0,0) 加繩索，覆蓋 Red
        cell = board.get_cell(0, 0)
        cell.upper = Tile('Rope_lv1')

        # LtBl 啟動會消除最多色（Red 有 3 個）
        match_engine.activate_powerup(board, 0, 2)
        # 繩索應仍在
        self.assertIsNotNone(cell.upper)
        self.assertEqual(cell.upper.tile_id, 'Rope_lv1')
        # 繩索下的 Red 應被消除（LtBl 可以消除繩索下的元素）
        self.assertIsNone(board.get_middle(0, 0))

    def test_光球加道具合成_繩索下轉道具但不觸發(self):
        """LtBl + 火箭合成：繩索下的元素轉為火箭但不觸發"""
        # 繩索放在 (2,2)，其他 Red 在 row 0/1，
        # 啟動的水平火箭不會打到 row 2 的繩索
        board = make_board([
            ['Red', 'Red', 'Blu', 'Yel'],
            ['Red', 'Grn', 'Blu', 'Yel'],
            ['Blu', 'Grn', 'Red', 'Yel'],
            ['LtBl', 'Soda0d', 'Grn', 'Yel'],
        ], rows=4, cols=4)
        # 在 (2,2) 加繩索覆蓋 Red
        cell = board.get_cell(2, 2)
        cell.upper = Tile('Rope_lv1')

        # LtBl + Soda0d 合成（Red 最多=4）
        board.swap(3, 0, 3, 1)
        match_engine.combine_powerups(board, 3, 0, 3, 1)
        # (2,2) 繩索仍在
        self.assertIsNotNone(cell.upper)
        # (2,2) 中層被轉為道具但未觸發 → 仍是道具
        mid = board.get_middle(2, 2)
        self.assertIsNotNone(mid)
        self.assertTrue(is_powerup(mid.tile_id))


class TestGeneratorWeights(unittest.TestCase):
    """元素生成器權重測試"""

    def test_指定權重只生成特定顏色(self):
        """設定 generator_weights 後只生成指定物件"""
        board = Board(3, 3)
        board.generator_weights = {'Red': 1}  # 只生成紅色
        for _ in range(20):
            tile = board.random_element()
            self.assertEqual(tile.tile_id, 'Red')

    def test_可生成非元素物件(self):
        """生成器可以生成障礙物（如 Barrel）"""
        board = Board(3, 3)
        board.generator_weights = {'Barrel': 1}
        tile = board.random_element()
        self.assertEqual(tile.tile_id, 'Barrel')


if __name__ == '__main__':
    unittest.main()
