"""
基礎 AI Agent — 暴力搜索最佳移動

策略：
  1. 列舉所有合法動作
  2. 對每個動作模擬一次 step（深拷貝盤面）
  3. 選取得分最高的動作
"""

import match_engine
from board import Board
from tile_defs import is_element, is_powerup, is_obstacle


def evaluate_move(board: Board, action, goals_required=None):
    """
    模擬一次動作並回傳評分。

    Args:
        board: 原盤面（不會被修改）
        action: dict，合法動作
        goals_required: 目標 dict（用於紙飛機目標選擇等）

    Returns:
        float: 評分
    """
    sim_board = board.copy()
    goals_current = {}

    action_type = action.get('type', 'swap')

    if action_type == 'swap':
        r1, c1 = action['pos1']
        r2, c2 = action['pos2']
        move_type = action.get('move_type', 'match')

        sim_board.swap(r1, c1, r2, c2)

        if move_type == 'combo':
            match_engine.combine_powerups(
                sim_board, r1, c1, r2, c2,
                goals_required=goals_required,
                track_goals=True,
                goals_current=goals_current,
                goals_required_dict=goals_required,
            )
            sim_board.apply_gravity()
            sim_board.fill_top()

        elif move_type == 'ltbl_elem':
            match_engine.combine_powerups(
                sim_board, r1, c1, r2, c2,
                goals_required=goals_required,
                track_goals=True,
                goals_current=goals_current,
                goals_required_dict=goals_required,
            )
            sim_board.apply_gravity()
            sim_board.fill_top()

        elif move_type == 'powerup_swap':
            # 道具 + 非道具：道具在新位置啟動
            t1 = sim_board.get_middle(r1, c1)
            if t1 and is_powerup(t1.tile_id):
                match_engine.activate_powerup(
                    sim_board, r1, c1,
                    goals_required=goals_required,
                    track_goals=True,
                    goals_current=goals_current,
                    goals_required_dict=goals_required,
                )
            else:
                match_engine.activate_powerup(
                    sim_board, r2, c2,
                    goals_required=goals_required,
                    track_goals=True,
                    goals_current=goals_current,
                    goals_required_dict=goals_required,
                )
            sim_board.apply_gravity()
            sim_board.fill_top()

        result = match_engine.resolve(
            sim_board,
            track_goals=True,
            goals_current=goals_current,
            goals_required=goals_required,
        )

    elif action_type == 'activate':
        r, c = action['pos']
        match_engine.activate_powerup(
            sim_board, r, c,
            goals_required=goals_required,
            track_goals=True,
            goals_current=goals_current,
            goals_required_dict=goals_required,
        )
        sim_board.apply_gravity()
        sim_board.fill_top()
        result = match_engine.resolve(
            sim_board,
            track_goals=True,
            goals_current=goals_current,
            goals_required=goals_required,
        )
    else:
        return 0.0

    return _score_result(result, goals_current, goals_required)


def _score_result(result, goals_current, goals_required):
    """計算模擬結果的分數"""
    score = 0.0

    # 消除分數
    for tile_id, count in result.get('eliminated', {}).items():
        if is_element(tile_id):
            score += count
        elif is_obstacle(tile_id):
            score += count * 5

    # 道具生成分數
    score += len(result.get('powerups_created', [])) * 10

    # 目標進度分數
    if goals_required:
        for tile_id, required in goals_required.items():
            current = goals_current.get(tile_id, 0)
            score += min(current, required) * 20

    return score


class BasicAgent:
    """暴力搜索 Agent"""

    def choose_action(self, env):
        """
        從所有合法動作中選出最佳動作。

        Args:
            env: Match3Env 實例

        Returns:
            dict: 最佳動作，若無合法動作則回傳 None
        """
        moves = env.get_valid_moves()
        if not moves:
            return None

        best_action = None
        best_score = -float('inf')

        for action in moves:
            score = evaluate_move(
                env.board, action,
                goals_required=env.goals_required,
            )
            if score > best_score:
                best_score = score
                best_action = action

        return best_action
