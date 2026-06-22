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
import time
from typing import Callable

from .manifest import SPRITES_DIR
from .pipeline import GENERATED_ROOT

ApplyProgressCallback = Callable[[int, int, str], None]

BACKUP_DIR = SPRITES_DIR.parent / 'sprites_original_backup'
LIVE_SPRITES_DIR = SPRITES_DIR.parent.parent / 'web' / 'live_sprites'
# board_bg 全螢幕用,web 端不需 2048 — 套用時縮到 1024 避免 WASM OOM
LIVE_BOARD_BG_MAX_DIM = 1024
# Streamlit playable board component assets — overwriting these is reflected instantly
# (no Godot re-export needed). PROJECT_ROOT = repo root.
PROJECT_ROOT = SPRITES_DIR.parent.parent.parent
COMPONENT_ASSETS_DIR = PROJECT_ROOT / 'match3_board_component' / 'frontend' / 'assets'
COMPONENT_BACKUP_DIR = PROJECT_ROOT / 'match3_board_component' / 'frontend' / 'assets_original_backup'


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
        raise FileNotFoundError(f'找不到生成結果目錄: {run_sprites}')
    pngs = sorted(run_sprites.glob('*.png'))
    if not pngs:
        raise FileNotFoundError(f'{run_sprites} 內沒有 PNG')

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
        raise FileNotFoundError(f'沒有備份可還原({BACKUP_DIR} 不存在)')
    n = 0
    for png in BACKUP_DIR.glob('*.png'):
        shutil.copy2(png, SPRITES_DIR / png.name)
        n += 1
    print(f'[restore] 已從備份還原 {n} 張原版 sprite')
    clear_live_sprites()
    restore_component()


def _resolve_run_pngs(run_name: str, asset_names: list[str] | None = None) -> list[pathlib.Path]:
    run_sprites = GENERATED_ROOT / run_name / 'sprites'
    if not run_sprites.is_dir():
        raise FileNotFoundError(f'找不到生成結果目錄: {run_sprites}')
    pngs = sorted(run_sprites.glob('*.png'))
    if not pngs:
        raise FileNotFoundError(f'{run_sprites} 內沒有 PNG')
    if asset_names:
        wanted = {f'{n}.png' for n in asset_names}
        pngs = [p for p in pngs if p.name in wanted]
    if not pngs:
        raise FileNotFoundError(f'{run_sprites} 內沒有符合條件的 PNG')
    return pngs


def _copy_png_to_live(png: pathlib.Path, target: pathlib.Path) -> None:
    if png.stem == 'board_bg':
        from PIL import Image

        im = Image.open(png)
        w, h = im.size
        longest = max(w, h)
        if longest > LIVE_BOARD_BG_MAX_DIM:
            scale = LIVE_BOARD_BG_MAX_DIM / longest
            im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        im.save(target, format='PNG')
        return
    shutil.copy2(png, target)


def apply_run_batch(
    run_name: str,
    asset_names: list[str] | None = None,
    *,
    to_component: bool = False,
    to_live: bool = False,
    to_project: bool = False,
    on_progress: ApplyProgressCallback | None = None,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Copy generated sprites to one or more destinations in a single pass.

    on_progress(current, total, asset_stem) is called before each file.
    Returns (component_applied, live_applied, project_applied, skipped).
    """
    pngs = _resolve_run_pngs(run_name, asset_names)
    total = len(pngs)

    if to_project:
        ensure_backup()
    if to_component:
        _ensure_component_backup()
    if to_live:
        LIVE_SPRITES_DIR.mkdir(parents=True, exist_ok=True)

    component_applied: list[str] = []
    live_applied: list[str] = []
    project_applied: list[str] = []
    skipped: list[str] = []

    for idx, png in enumerate(pngs, 1):
        if on_progress:
            on_progress(idx, total, png.stem)

        if to_component:
            target = COMPONENT_ASSETS_DIR / png.name
            if not COMPONENT_ASSETS_DIR.is_dir():
                raise FileNotFoundError(f'找不到元件 assets 目錄: {COMPONENT_ASSETS_DIR}')
            if target.exists():
                shutil.copy2(png, target)
                component_applied.append(png.stem)
            elif png.stem not in skipped:
                skipped.append(png.stem)

        if to_live:
            _copy_png_to_live(png, LIVE_SPRITES_DIR / png.name)
            live_applied.append(png.stem)

        if to_project:
            target = SPRITES_DIR / png.name
            if target.exists():
                shutil.copy2(png, target)
                project_applied.append(png.stem)
            elif png.stem not in skipped:
                skipped.append(png.stem)

    if to_live and live_applied:
        (LIVE_SPRITES_DIR / 'revision.txt').write_text(str(time.time()), encoding='utf-8')

    if component_applied:
        print(f'[component] 已套用 {len(component_applied)} 張到 {COMPONENT_ASSETS_DIR}')
    if live_applied:
        print(f'[live] 已套用 {len(live_applied)} 張到 {LIVE_SPRITES_DIR}')
    if project_applied:
        print(f'[apply] 已套用 {len(project_applied)} 張到 {SPRITES_DIR}')

    return component_applied, live_applied, project_applied, skipped


def apply_run_to_live(run_name: str, asset_names: list[str] | None = None) -> tuple[list[str], list[str]]:
    """
    Copy generated sprites into godot_demo/web/live_sprites/ for runtime override.

    Godot web build loads these over the packed defaults — no re-export needed.
  Returns (applied, skipped).
    """
    run_sprites = GENERATED_ROOT / run_name / 'sprites'
    if not run_sprites.is_dir():
        raise FileNotFoundError(f'找不到生成結果目錄: {run_sprites}')

    LIVE_SPRITES_DIR.mkdir(parents=True, exist_ok=True)
    applied: list[str] = []
    skipped: list[str] = []

    pngs = sorted(run_sprites.glob('*.png'))
    if asset_names:
        wanted = {f'{n}.png' for n in asset_names}
        pngs = [p for p in pngs if p.name in wanted]

    for png in pngs:
        target = LIVE_SPRITES_DIR / png.name
        _copy_png_to_live(png, target)
        applied.append(png.stem)

    # Touch revision file so clients can detect updates without parsing mtimes.
    (LIVE_SPRITES_DIR / 'revision.txt').write_text(str(time.time()), encoding='utf-8')
    print(f'[live] 已套用 {len(applied)} 張到 {LIVE_SPRITES_DIR}')
    return applied, skipped


def _ensure_component_backup() -> None:
    if COMPONENT_BACKUP_DIR.exists():
        return
    if not COMPONENT_ASSETS_DIR.is_dir():
        return
    COMPONENT_BACKUP_DIR.mkdir(parents=True)
    n = 0
    for png in COMPONENT_ASSETS_DIR.glob('*.png'):
        shutil.copy2(png, COMPONENT_BACKUP_DIR / png.name)
        n += 1
    print(f'[component] 已備份 {n} 張原版 sprite 到 {COMPONENT_BACKUP_DIR}')


def apply_run_to_component(run_name: str, asset_names: list[str] | None = None) -> tuple[list[str], list[str]]:
    """
    Copy generated sprites into the Streamlit board component assets.

    The playable board reflects these immediately (with a cache-buster) — no Godot
    re-export required. Returns (applied, skipped).
    """
    run_sprites = GENERATED_ROOT / run_name / 'sprites'
    if not run_sprites.is_dir():
        raise FileNotFoundError(f'找不到生成結果目錄: {run_sprites}')
    if not COMPONENT_ASSETS_DIR.is_dir():
        raise FileNotFoundError(f'找不到元件 assets 目錄: {COMPONENT_ASSETS_DIR}')

    _ensure_component_backup()
    applied: list[str] = []
    skipped: list[str] = []

    pngs = sorted(run_sprites.glob('*.png'))
    if asset_names:
        wanted = {f'{n}.png' for n in asset_names}
        pngs = [p for p in pngs if p.name in wanted]

    for png in pngs:
        target = COMPONENT_ASSETS_DIR / png.name
        if not target.exists():
            skipped.append(png.stem)
            continue
        shutil.copy2(png, target)
        applied.append(png.stem)
    print(f'[component] 已套用 {len(applied)} 張到 {COMPONENT_ASSETS_DIR}')
    return applied, skipped


def restore_component() -> None:
    if not COMPONENT_BACKUP_DIR.is_dir():
        return
    n = 0
    for png in COMPONENT_BACKUP_DIR.glob('*.png'):
        shutil.copy2(png, COMPONENT_ASSETS_DIR / png.name)
        n += 1
    print(f'[component] 已從備份還原 {n} 張原版 sprite')


def clear_live_sprites() -> None:
    """Remove runtime overrides (game falls back to packed sprites)."""
    if not LIVE_SPRITES_DIR.is_dir():
        return
    for png in LIVE_SPRITES_DIR.glob('*.png'):
        png.unlink()
    rev = LIVE_SPRITES_DIR / 'revision.txt'
    if rev.is_file():
        rev.unlink()
    print(f'[live] 已清除 {LIVE_SPRITES_DIR}')
