"""
模擬執行入口

用法:
  python run_sim.py                          # 隨機盤面，預設參數
  python run_sim.py --level levels/level_01.json
  python run_sim.py --level levels/level_01.json --games 100 --verbose
"""

import argparse
import sys

from match3_env import Match3Env
from basic_agent import BasicAgent


def run_one_game(env, agent, verbose=False):
    """執行一局遊戲，回傳 (win, steps, goals_progress)"""
    state = env.reset()
    if verbose:
        env.render()

    while not env.done:
        action = agent.choose_action(env)
        if action is None:
            # 無合法動作 → 觸發洗牌
            env.board.shuffle()
            if verbose:
                print('  ⟳ 無合法步驟，觸發洗牌')
                env.render()
            continue

        state, reward, done, info = env.step(action)
        if verbose:
            action_str = _format_action(action)
            print(f'動作: {action_str}  獎勵: {reward}')
            if info.get('shuffled'):
                print('  ⟳ 步驟後無合法步驟，觸發洗牌')
            msg = info.get('msg')
            if msg:
                msg_zh = {'win': '勝利！', 'out of steps': '步數用完',
                          'no match': '無消除', 'invalid swap': '無效交換',
                          'not a powerup': '非道具', 'game already over': '遊戲已結束'
                          }.get(msg, msg)
                print(f'  → {msg_zh}')
            env.render()

    return env.win, env.steps_taken, env.get_goals_progress()


def _format_action(action):
    """格式化動作為可讀字串"""
    if action['type'] == 'swap':
        r1, c1 = action['pos1']
        r2, c2 = action['pos2']
        mt = action.get('move_type', '?')
        mt_zh = {'match': '消除', 'combo': '合成', 'ltbl_elem': '紙風車+元素'}.get(mt, mt)
        return f'交換 ({r1},{c1})<->({r2},{c2}) [{mt_zh}]'
    elif action['type'] == 'activate':
        r, c = action['pos']
        return f'啟動道具 ({r},{c})'
    return str(action)


def main():
    parser = argparse.ArgumentParser(description='三消遊戲模擬器')
    parser.add_argument('--level', type=str, default=None,
                        help='關卡 JSON 檔案路徑')
    parser.add_argument('--rows', type=int, default=10)
    parser.add_argument('--cols', type=int, default=9)
    parser.add_argument('--colors', type=int, default=4)
    parser.add_argument('--max-steps', type=int, default=30)
    parser.add_argument('--games', type=int, default=1,
                        help='模擬局數')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='每步都印出盤面')
    args = parser.parse_args()

    env = Match3Env(
        rows=args.rows,
        cols=args.cols,
        num_colors=args.colors,
        max_steps=args.max_steps,
        level_file=args.level,
    )
    agent = BasicAgent()

    wins = 0
    total_steps = 0

    for game_idx in range(args.games):
        if args.games > 1 and not args.verbose:
            print(f'\r第 {game_idx + 1}/{args.games} 局...', end='', flush=True)

        win, steps, progress = run_one_game(env, agent, verbose=args.verbose)
        if win:
            wins += 1
        total_steps += steps

        if args.verbose and args.games > 1:
            result = '勝利' if win else '失敗'
            print(f'--- 第 {game_idx + 1} 局: {result}，{steps} 步 ---\n')

    # 統計結果
    if args.games > 1:
        print()
    print(f'=== 模擬結果：{args.games} 局 ===')
    print(f'勝率: {wins}/{args.games} ({wins/args.games*100:.1f}%)')
    print(f'平均步數: {total_steps/args.games:.1f}')


if __name__ == '__main__':
    main()
