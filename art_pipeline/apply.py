"""
套用 / 還原生成美術。

- apply 前自動把原版 sprites 備份到 godot_demo/resources/sprites_original_backup/
  (只備份一次,之後 apply 都不會覆寫備份,確保永遠能回到最初的原版)
- apply 只覆蓋「生成結果中存在」的同名檔,Godot 的 .import 設定不動,
  下次用 Godot Editor 開啟/Export 時會自動 re-import
- restore 把備份完整複製回去
"""

from __future__ import annotations

import pathlib
import shutil

from .manifest import SPRITES_DIR
from .pipeline import GENERATED_ROOT

BACKUP_DIR = SPRITES_DIR.parent / 'sprites_original_backup'


def ensure_backup() -> None:
    if BACKUP_DIR.exists():
        return
    BACKUP_DIR.mkdir(parents=True)
    n = 0
    for png in SPRITES_DIR.glob('*.png'):
        shutil.copy2(png, BACKUP_DIR / png.name)
        n += 1
    print(f'[backup] 已備份 {n} 張原版 sprite 到 {BACKUP_DIR}')


def apply_run(run_name: str) -> None:
    run_sprites = GENERATED_ROOT / run_name / 'sprites'
    if not run_sprites.is_dir():
        raise SystemExit(f'找不到生成結果目錄: {run_sprites}')
    pngs = sorted(run_sprites.glob('*.png'))
    if not pngs:
        raise SystemExit(f'{run_sprites} 內沒有 PNG')

    ensure_backup()
    applied = []
    skipped = []
    for png in pngs:
        target = SPRITES_DIR / png.name
        if not target.exists():
            skipped.append(png.name)
            continue
        shutil.copy2(png, target)
        applied.append(png.name)
    print(f'[apply] 已套用 {len(applied)} 張到 {SPRITES_DIR}')
    if skipped:
        print(f'[apply] 跳過 {len(skipped)} 張(原目錄沒有同名檔): {skipped}')
    print('[apply] 注意: Godot Web build 需重新 Export 才會看到新美術。')


def restore() -> None:
    if not BACKUP_DIR.is_dir():
        raise SystemExit(f'沒有備份可還原({BACKUP_DIR} 不存在)')
    n = 0
    for png in BACKUP_DIR.glob('*.png'):
        shutil.copy2(png, SPRITES_DIR / png.name)
        n += 1
    print(f'[restore] 已從備份還原 {n} 張原版 sprite')
