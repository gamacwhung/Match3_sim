"""把所有官方關卡(關卡格式資料/Level_*.json)批次轉成我們的格式,
輸出到 godot_demo/levels/。

用法:
    python scripts/import_official_to_godot.py

執行後 godot_demo/levels/ 會被清空再重建,output filename 是
Level_001.json ~ Level_100.json(三位數補零方便排序)。

我們原本手寫的 levels/level_01.json ~ level_06.json 不會動,
godot_demo 端會優先用官方 import 出來的 Level_*.json。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from level_generator.official_format import official_to_ours  # noqa: E402

OFFICIAL_DIR = ROOT / '關卡格式資料'
GODOT_LEVELS_DIR = ROOT / 'godot_demo' / 'levels'


def main() -> None:
    if not OFFICIAL_DIR.exists():
        print(f'[ERR] 找不到官方關卡目錄:{OFFICIAL_DIR}')
        sys.exit(1)
    GODOT_LEVELS_DIR.mkdir(parents=True, exist_ok=True)

    # 清掉先前匯入產物(只清 Level_*.json,我們自製的 level_*.json 不動)
    for f in GODOT_LEVELS_DIR.glob('Level_*.json'):
        f.unlink()

    converted = 0
    skipped: list[tuple[int, str]] = []

    official_files = sorted(
        OFFICIAL_DIR.glob('Level_*.json'),
        key=lambda p: int(p.stem.split('_')[1]),
    )

    for src in official_files:
        try:
            num = int(src.stem.split('_')[1])
        except (IndexError, ValueError):
            continue
        try:
            with src.open('r', encoding='utf-8') as fh:
                data = json.load(fh)
            our, warnings = official_to_ours(data)
        except Exception as exc:
            skipped.append((num, f'parse fail: {exc}'))
            continue

        out_path = GODOT_LEVELS_DIR / f'Level_{num:03d}.json'
        with out_path.open('w', encoding='utf-8') as fh:
            json.dump(our, fh, ensure_ascii=False, indent=2)
        converted += 1
        if warnings:
            tail = '; '.join(warnings[:3])
            print(f'  Level_{num:03d}: warnings -> {tail}')

    print('-' * 60)
    print(f'[OK] 轉換完成 {converted} 關 → {GODOT_LEVELS_DIR}')
    if skipped:
        print(f'[WARN] 跳過 {len(skipped)} 關:')
        for num, reason in skipped:
            print(f'  Level_{num}: {reason}')


if __name__ == '__main__':
    main()
