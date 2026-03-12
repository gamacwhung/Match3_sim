"""
AI 模擬測試器

對關卡跑多場遊戲，統計勝率和步數分布。
使用 ThreadPoolExecutor 並行執行，各遊戲互相獨立。
"""

import sys
import os
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from match3_env import Match3Env
from basic_agent import BasicAgent
from run_sim import run_one_game


@dataclass
class SimulationResults:
    n_games: int
    wins: int
    losses: int
    win_rate: float
    avg_steps: float
    min_steps: int
    max_steps_seen: int
    step_histogram: dict = field(default_factory=dict)  # {步數: 次數}

    def difficulty_label(self) -> str:
        if self.win_rate >= 0.8:
            return '太簡單（考慮減少 max_steps 或增加目標難度）'
        elif self.win_rate >= 0.5:
            return '適中偏易'
        elif self.win_rate >= 0.25:
            return '適中（平衡）'
        elif self.win_rate >= 0.1:
            return '挑戰性強'
        else:
            return '太難（考慮增加 max_steps 或減少目標）'


def _run_single_game(level_file_path: str) -> dict:
    """
    單場遊戲，建立獨立的 Env + Agent（thread-safe）。
    level_file_path 由呼叫者寫好並共用，無需每次建立 tempfile。
    """
    env = Match3Env(level_file=level_file_path)
    agent = BasicAgent()
    win, steps, progress = run_one_game(env, agent, verbose=False)
    return {'win': win, 'steps': steps, 'goals_progress': progress}


def run_simulation_batch(
    level_dict: dict,
    n_games: int = 100,
    steps_multiplier: float = 3.0,
    max_workers: int = 4,
    progress_callback=None,
) -> SimulationResults:
    """
    批次執行 n_games 場遊戲。

    Args:
        level_dict: 關卡 dict
        n_games: 場數
        steps_multiplier: max_steps 倍率（讓 AI 有足夠步數完成）
        max_workers: 並行 thread 數
        progress_callback: callable(current: int, total: int) 進度回調
    """
    original_steps = level_dict.get('max_steps', 30)
    elevated_steps = max(int(original_steps * steps_multiplier), original_steps + 50)

    # 寫一次 tempfile，所有 thread 共用（避免 100 次 I/O 開銷）
    tmp_path = None
    try:
        level_dict_copy = dict(level_dict)
        level_dict_copy['max_steps'] = elevated_steps
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            tmp_path = f.name
            json.dump(level_dict_copy, f, ensure_ascii=False)

        results_raw = []
        futures = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for _ in range(n_games):
                futures.append(executor.submit(_run_single_game, tmp_path))

            for i, future in enumerate(as_completed(futures)):
                try:
                    results_raw.append(future.result())
                except Exception:
                    results_raw.append({'win': False, 'steps': elevated_steps, 'goals_progress': {}})
                if progress_callback:
                    progress_callback(i + 1, n_games)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # 統計
    wins = sum(1 for r in results_raw if r['win'])
    all_steps = [r['steps'] for r in results_raw]

    # 步數分布（每 5 步一個 bucket）
    histogram = {}
    for s in all_steps:
        bucket = (s // 5) * 5
        histogram[bucket] = histogram.get(bucket, 0) + 1

    return SimulationResults(
        n_games=n_games,
        wins=wins,
        losses=n_games - wins,
        win_rate=wins / n_games,
        avg_steps=sum(all_steps) / len(all_steps) if all_steps else 0,
        min_steps=min(all_steps) if all_steps else 0,
        max_steps_seen=max(all_steps) if all_steps else 0,
        step_histogram=dict(sorted(histogram.items())),
    )
