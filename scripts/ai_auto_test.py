"""
AI 自動測試 — 用 ai_player 跑 N 場關卡,出統計報告

用途:
  - QA / 平衡測試:同一關卡跑多次,看勝率、平均剩餘步數、卡關率
  - 批次驗證:一次跑 100 關官方關卡,看 AI 通關率
  - Demo 賣點:「AI 在 30 秒內幫你跑完 50 次,告訴你這關設計合不合理」

CLI 用法:
  python scripts/ai_auto_test.py LEVEL_JSON [--runs N] [--seed S]
    例:python scripts/ai_auto_test.py levels/level_01.json --runs 50

  python scripts/ai_auto_test.py --batch LEVELS_DIR [--runs N]
    例:python scripts/ai_auto_test.py --batch 關卡格式資料 --runs 10

程式介面(給 Streamlit / Notebook 用):
  run_one_game(level_file, seed=None, max_steps=None) -> GameResult
  run_batch(level_file, n_runs=50, seed=None, progress_callback=None) -> BatchReport
  run_levels(level_files, n_runs=10, ...) -> Dict[level_id, BatchReport]
"""

from __future__ import annotations
import sys
import pathlib
import argparse
import random
import time
import json
from dataclasses import dataclass, asdict, field
from typing import Optional, Callable

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from match3_env import Match3Env
from scripts.ai_player import find_best_action


# ===========================================================================
# Result dataclasses
# ===========================================================================

@dataclass
class GameResult:
    """單一場遊戲的結果。"""
    won: bool
    moves_used: int
    max_moves: int
    moves_left: int
    goals_required: dict
    goals_current: dict
    obstacles_left: int           # 結束時場上還剩多少目標障礙物
    no_action_count: int          # AI 找不到動作的次數
    elapsed_ms: float
    seed: int


@dataclass
class BatchReport:
    """N 場批次測試的彙總報告。"""
    level_name: str
    n_runs: int
    n_wins: int
    win_rate: float
    avg_moves_used: float
    avg_moves_left: float
    avg_obstacles_left: float
    avg_elapsed_ms: float
    moves_distribution: list      # [moves_used per run]
    results: list = field(default_factory=list)

    @property
    def loss_rate(self) -> float:
        return 1.0 - self.win_rate


# ===========================================================================
# 核心 runner
# ===========================================================================

def run_one_game(
    level_file: str,
    seed: Optional[int] = None,
    max_safety_steps: int = 200,
) -> GameResult:
    """
    跑一場遊戲到結束(贏 / 步數用盡 / AI 找不到動作)。
    
    Args:
        level_file: 關卡 JSON 路徑
        seed: 隨機種子(影響 AI 在多個同分動作中的選擇,以及盤面 shuffle)
        max_safety_steps: 安全閘 — 避免某 bug 讓 AI 無限循環
    """
    rng = random.Random(seed) if seed is not None else random.Random()
    # 也設定 Python 全域 random,因為 match_engine / board 可能用到
    if seed is not None:
        random.seed(seed)
    
    env = Match3Env(level_file=level_file)
    t0 = time.perf_counter()
    no_action_count = 0
    safety = 0
    
    while not env.done and safety < max_safety_steps:
        safety += 1
        action = find_best_action(env, rng=rng)
        if action is None:
            no_action_count += 1
            # 沒動作 → reset?或結束?demo 設計:結束(算輸)
            env.done = True
            break
        state, reward, done, info = env.step(action)
        # 若 step 回 invalid swap / no match — AI 給的動作不可行,計一次 no_action
        if isinstance(info, dict) and info.get('msg') in ('no match', 'invalid swap', 'not a powerup'):
            no_action_count += 1
            # 連續太多次 → break
            if no_action_count > 5:
                env.done = True
                break
    
    elapsed_ms = (time.perf_counter() - t0) * 1000
    obstacles_left = _count_remaining_obstacles(env)
    
    return GameResult(
        won=env.win,
        moves_used=env.steps_taken,
        max_moves=env.max_steps,
        moves_left=max(0, env.max_steps - env.steps_taken),
        goals_required=dict(env.goals_required),
        goals_current=dict(env.goals_current),
        obstacles_left=obstacles_left,
        no_action_count=no_action_count,
        elapsed_ms=elapsed_ms,
        seed=seed if seed is not None else -1,
    )


def run_batch(
    level_file: str,
    n_runs: int = 50,
    base_seed: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, GameResult], None]] = None,
) -> BatchReport:
    """
    對同一關卡跑 N 場,彙總統計。
    
    Args:
        progress_callback: fn(current_idx, total, last_result) — 進度回報
                           給 Streamlit progress bar / CLI tqdm 用
    """
    results: list[GameResult] = []
    for i in range(n_runs):
        seed = (base_seed + i) if base_seed is not None else random.randint(0, 1 << 30)
        result = run_one_game(level_file, seed=seed)
        results.append(result)
        if progress_callback:
            progress_callback(i + 1, n_runs, result)
    
    n_wins = sum(1 for r in results if r.won)
    return BatchReport(
        level_name=pathlib.Path(level_file).stem,
        n_runs=n_runs,
        n_wins=n_wins,
        win_rate=n_wins / n_runs if n_runs > 0 else 0.0,
        avg_moves_used=_avg([r.moves_used for r in results]),
        avg_moves_left=_avg([r.moves_left for r in results]),
        avg_obstacles_left=_avg([r.obstacles_left for r in results]),
        avg_elapsed_ms=_avg([r.elapsed_ms for r in results]),
        moves_distribution=[r.moves_used for r in results],
        results=results,
    )


def run_levels(
    level_files: list[str],
    n_runs_per_level: int = 10,
    base_seed: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, str, BatchReport], None]] = None,
) -> dict:
    """
    跑多個關卡 → {level_name: BatchReport}
    """
    out = {}
    for i, lf in enumerate(level_files):
        report = run_batch(lf, n_runs=n_runs_per_level, base_seed=base_seed)
        out[pathlib.Path(lf).stem] = report
        if progress_callback:
            progress_callback(i + 1, len(level_files), lf, report)
    return out


# ===========================================================================
# Helpers
# ===========================================================================

def _avg(lst):
    return sum(lst) / len(lst) if lst else 0.0


def _count_remaining_obstacles(env) -> int:
    """數場上還剩多少目標障礙物。"""
    if not env.goals_required:
        return 0
    remaining = 0
    for tile_id, required in env.goals_required.items():
        achieved = env.goals_current.get(tile_id, 0)
        remaining += max(0, required - achieved)
    return remaining


# ===========================================================================
# CLI
# ===========================================================================

def _cli():
    parser = argparse.ArgumentParser(description='Match3 AI 自動測試')
    parser.add_argument('level', nargs='?', help='關卡 JSON 路徑(單關)')
    parser.add_argument('--runs', type=int, default=50, help='每關跑幾次(default 50)')
    parser.add_argument('--seed', type=int, default=None, help='base seed')
    parser.add_argument('--batch', help='批次測試目錄(每關各跑 --runs 次)')
    parser.add_argument('--out', help='輸出 JSON 報告路徑')
    args = parser.parse_args()
    
    if args.batch:
        level_files = sorted(pathlib.Path(args.batch).glob('*.json'))
        if not level_files:
            print(f'No .json found in {args.batch}')
            return
        print(f'Batch testing {len(level_files)} levels × {args.runs} runs each')
        reports = run_levels(
            [str(lf) for lf in level_files],
            n_runs_per_level=args.runs,
            base_seed=args.seed,
            progress_callback=lambda i, n, lf, r: print(
                f'  [{i}/{n}] {pathlib.Path(lf).stem}: '
                f'win={r.win_rate*100:.1f}% avg_moves={r.avg_moves_used:.1f}'
            ),
        )
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                json.dump({k: asdict(v) for k, v in reports.items()}, f,
                          ensure_ascii=False, indent=2, default=str)
            print(f'Saved to {args.out}')
    elif args.level:
        print(f'Testing {args.level} × {args.runs} runs')
        report = run_batch(args.level, n_runs=args.runs, base_seed=args.seed,
                           progress_callback=lambda i, n, r: print(
                               f'  [{i}/{n}] {"WIN" if r.won else "LOSS"} '
                               f'moves={r.moves_used} obs_left={r.obstacles_left}'
                           ))
        print('\n=== Report ===')
        print(f'  Level:           {report.level_name}')
        print(f'  Win rate:        {report.win_rate*100:.1f}% ({report.n_wins}/{report.n_runs})')
        print(f'  Avg moves used:  {report.avg_moves_used:.1f} / {report.results[0].max_moves}')
        print(f'  Avg moves left:  {report.avg_moves_left:.1f}')
        print(f'  Avg obs left:    {report.avg_obstacles_left:.1f}')
        print(f'  Avg time:        {report.avg_elapsed_ms:.0f} ms')
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                json.dump(asdict(report), f, ensure_ascii=False, indent=2, default=str)
            print(f'Saved to {args.out}')
    else:
        parser.print_help()


if __name__ == '__main__':
    _cli()
