"""
比對所有關卡的 `goals` 和盤面上實際的可消障礙物數量,
找出 goal 跟盤面對不起來的關卡。

也順便驗證:每個 Puddle / Mud / Rope 位置(bottom/upper)
是不是有 Crt 之類 blocking 障礙物在 middle 蓋著。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


GODOT_LEVELS_DIR = Path('godot_demo/levels')
OFFICIAL_DIR = Path('關卡格式資料')


def _family_of(tile_id: str) -> str | None:
    """tile_id → family prefix (對齊 official_format.py)。"""
    base = tile_id.split('#')[0]
    families = (
        'Crt', 'Puddle', 'Barrel', 'TrafficCone', 'SalmonCan',
        'WaterChiller', 'BeverageChiller', 'Pool', 'Stamp',
        'Mud', 'Rope', 'Roadblock', 'Postmark',
    )
    for f in families:
        if base.startswith(f):
            return f
    return None


def count_board_obstacles(level: dict) -> Counter:
    """數盤面上每個 family 的物件數(多格 instance 合一個)。"""
    counts: Counter[str] = Counter()
    seen_instances: set[str] = set()
    for layer_name in ('middle', 'upper', 'bottom'):
        layer = level.get('board', {}).get(layer_name, [])
        for row in layer:
            for cell in row:
                if not cell:
                    continue
                base = cell.split('#')[0] if '#' in cell else cell
                if '#' in cell:
                    if cell in seen_instances:
                        continue
                    seen_instances.add(cell)
                fam = _family_of(base)
                if fam:
                    counts[fam] += 1
    return counts


def main() -> None:
    levels = sorted(GODOT_LEVELS_DIR.glob('Level_*.json'))
    mismatches: list[str] = []
    print(f'掃描 {len(levels)} 個關卡...\n')
    print(f'{"關卡":<6}{"family":<22}{"goal":>5}{"actual":>8}{"diff":>7}')
    print('-' * 50)

    for path in levels:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        goals: dict[str, int] = d.get('goals', {})
        counts = count_board_obstacles(d)

        level_num = int(path.stem.split('_')[1])
        for fam, target in goals.items():
            actual = counts.get(fam, 0)
            if actual != target:
                mismatches.append(path.name)
                diff = actual - target
                print(f'L{level_num:<5}{fam:<22}{target:>5}{actual:>8}{diff:>+7}')

    print()
    if mismatches:
        print(f'**{len(set(mismatches))} 個關卡的 goal 數量對不起來!**')
    else:
        print('✓ 所有關卡 goal 都和盤面物件數量一致')

    print('\n=== Puddle 上面有沒有 Crt 蓋著 (Level 26 範例) ===')
    sample = json.load(open(GODOT_LEVELS_DIR / 'Level_026.json', encoding='utf-8'))
    middle = sample['board']['middle']
    bottom = sample['board']['bottom']
    H = len(middle)
    W = len(middle[0]) if H else 0
    puddle_with_top = 0
    puddle_alone = 0
    for r in range(H):
        for c in range(W):
            b = bottom[r][c]
            m = middle[r][c]
            if b and b.startswith('Puddle'):
                if m:
                    puddle_with_top += 1
                else:
                    puddle_alone += 1
    print(f'L26: Puddle 上面被覆蓋: {puddle_with_top}, 露出: {puddle_alone}, 共 {puddle_with_top + puddle_alone}')


if __name__ == '__main__':
    main()
