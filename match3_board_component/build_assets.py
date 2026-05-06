"""
從 M8/ 複製美術 PNG 到 frontend/assets/，並產出 Soda90.png（旋轉 90 度的火箭）。

執行：
    python match3_board_component/build_assets.py
"""

import os
import pathlib
import shutil
import sys

_HERE = pathlib.Path(__file__).parent
_ROOT = _HERE.parent
_M8 = _ROOT / 'M8'
_DEST = _HERE / 'frontend' / 'assets'

sys.path.insert(0, str(_HERE))
from asset_map import ASSET_SOURCES  # noqa: E402


def main():
    if not _M8.is_dir():
        print(f'[ERROR] 找不到 M8/ 目錄：{_M8}', file=sys.stderr)
        sys.exit(1)

    _DEST.mkdir(parents=True, exist_ok=True)

    copied = 0
    missing = []
    for asset_key, rel in ASSET_SOURCES.items():
        src = _M8 / rel
        if not src.is_file():
            missing.append((asset_key, rel))
            continue
        dst = _DEST / f'{asset_key}.png'
        shutil.copy2(src, dst)
        copied += 1

    print(f'已複製 {copied} 張圖片到 {_DEST}')
    if missing:
        print(f'\n[警告] 找不到 {len(missing)} 張原始圖：')
        for k, r in missing:
            print(f'  - {k}: {r}')

    # 產生 Soda90 = Soda0d 旋轉 90 度（垂直火箭）
    soda0 = _DEST / 'Soda0d.png'
    soda90 = _DEST / 'Soda90.png'
    if soda0.is_file():
        try:
            from PIL import Image
            img = Image.open(soda0)
            rotated = img.rotate(90, expand=True)
            rotated.save(soda90)
            print(f'已產生 {soda90.name}（{soda0.name} 旋轉 90 度）')
        except ImportError:
            shutil.copy2(soda0, soda90)
            print(f'PIL 不可用，{soda90.name} 直接複製自 {soda0.name}'
                  '（前端會用 CSS rotate）')


if __name__ == '__main__':
    main()
