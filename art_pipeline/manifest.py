"""
Asset Manifest — 盤點遊戲美術資產:名稱、尺寸、功能、視覺約束。

角色定義來自 art_pipeline/asset_roles.json(見 roles.py)。
function / constraints 一律用英文撰寫,因為會直接注入 Gemini prompt。

用法:
    from art_pipeline.manifest import build_manifest
    manifest = build_manifest()          # list[dict]
    python -m art_pipeline.manifest      # 輸出 art_pipeline/asset_manifest.json
"""

from __future__ import annotations

import json
import pathlib

from .roles import ROLES_PATH, build_role_table, get_family_meta, load_config

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
SPRITES_DIR = PROJECT_ROOT / 'godot_demo' / 'resources' / 'sprites'
MANIFEST_PATH = pathlib.Path(__file__).parent / 'asset_manifest.json'

CELL_DISPLAY_PX = load_config().get('meta', {}).get('cell_display_px', 70)


def _role(category: str, function: str, constraints: list[str] | None = None,
          family: str | None = None, transparent: bool = True) -> dict:
    """Fallback for unregistered sprites."""
    from .roles import load_config as _load
    common = _load().get('meta', {}).get('common_sprite_constraints', [])
    cell_px = CELL_DISPLAY_PX
    common_fmt = [c.replace('{cell_display_px}', str(cell_px)) for c in common]
    return {
        'role_class': 'unknown',
        'role_label': 'Unknown',
        'category': category,
        'function': function,
        'constraints': (constraints or []) + (common_fmt if transparent else []),
        'family': family,
        'transparent': transparent,
    }


ROLE_TABLE = build_role_table()


def build_manifest(sprites_dir: pathlib.Path = SPRITES_DIR) -> list[dict]:
    """掃描 sprites 目錄,合併功能表,回傳完整 manifest。"""
    from PIL import Image

    role_table = build_role_table()
    manifest = []
    unknown = []
    for png in sorted(sprites_dir.glob('*.png')):
        stem = png.stem
        with Image.open(png) as im:
            width, height = im.size
            has_alpha = im.mode in ('RGBA', 'LA', 'PA')
        role = role_table.get(stem)
        if role is None:
            unknown.append(stem)
            role = _role('unknown', '(Unregistered asset — add to asset_roles.json before generating)')
        manifest.append({
            'name': stem,
            'file': png.name,
            'path': str(png.relative_to(PROJECT_ROOT)),
            'width': width,
            'height': height,
            'has_alpha': has_alpha,
            **role,
        })
    if unknown:
        print(f'[manifest] 警告: {len(unknown)} 個 asset 未登錄功能描述: {unknown}')
    return manifest


def save_manifest(path: pathlib.Path = MANIFEST_PATH) -> list[dict]:
    manifest = build_manifest()
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[manifest] 已輸出 {len(manifest)} 筆 asset 到 {path}')
    return manifest


def families(manifest: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for a in manifest:
        out.setdefault(a.get('family') or 'misc', []).append(a['name'])
    for names in out.values():
        names.sort()
    return out


def all_asset_names(sprites_dir: pathlib.Path = SPRITES_DIR) -> list[str]:
    """所有可生成的 asset 名稱(與 --assets 選項一致)。"""
    return [a['name'] for a in build_manifest(sprites_dir)]


def format_assets_help(manifest: list[dict] | None = None) -> str:
    """產生 --assets / list-assets 用的分組說明文字。"""
    grouped = families(manifest or build_manifest())
    lines = ['可用 asset 名稱(逗號分隔,大小寫需完全一致):']
    for fam in sorted(grouped):
        lines.append(f'  {fam}: {", ".join(grouped[fam])}')
    return '\n'.join(lines)


if __name__ == '__main__':
    save_manifest()
