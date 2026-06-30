"""
Asset role taxonomy — loads art_pipeline/asset_roles.json.

Provides structured gameplay-function classes (match_element, obstacle_movable, …)
and per-asset definitions used by manifest + generation pipeline.

Modes:
  restyle     — preserve original sprite subject (Reference A = original PNG)
  theme_swap  — invent new themed objects from abstract role (no original PNG ref)
"""

from __future__ import annotations

import json
import pathlib
from typing import Literal

GenerationMode = Literal['restyle', 'theme_swap']

ROLES_PATH = pathlib.Path(__file__).parent / 'asset_roles.json'
_config_cache: dict | None = None
_role_table_cache: dict[str, dict] | None = None


def load_config(path: pathlib.Path = ROLES_PATH) -> dict:
    global _config_cache
    if _config_cache is None or path != ROLES_PATH:
        _config_cache = json.loads(path.read_text(encoding='utf-8'))
    return _config_cache


def clear_cache() -> None:
    global _config_cache, _role_table_cache
    _config_cache = None
    _role_table_cache = None


def get_role_class(role_class_id: str, config: dict | None = None) -> dict:
    cfg = config or load_config()
    roles = cfg['role_classes']
    if role_class_id not in roles:
        raise KeyError(f'Unknown role_class: {role_class_id}')
    return roles[role_class_id]


def get_family_meta(family_id: str | None, config: dict | None = None) -> dict:
    if not family_id:
        return {}
    cfg = config or load_config()
    return cfg.get('families', {}).get(family_id, {})


def get_category_visual(category_id: str | None, config: dict | None = None) -> dict:
    if not category_id:
        return {}
    cfg = config or load_config()
    return cfg.get('meta', {}).get('visual_categories', {}).get(category_id, {})


def _format_template(text: str, params: dict, meta: dict) -> str:
    merged = {**meta, **params}
    merged.setdefault('cell_display_px', meta.get('cell_display_px', 70))
    try:
        return text.format(**merged)
    except KeyError:
        return text


def _expand_group(group: dict, config: dict) -> dict[str, dict]:
    meta = config.get('meta', {})
    cell_px = meta.get('cell_display_px', 70)
    common = [
        c.replace('{cell_display_px}', str(cell_px))
        for c in meta.get('common_sprite_constraints', [])
    ]
    role_class_id = group['role_class']
    role_class = get_role_class(role_class_id, config)
    family = group.get('family')
    transparent = group.get('transparent', True)
    out: dict[str, dict] = {}

    for name in group['names']:
        params = dict(group.get('params', {}).get(name, {}))
        fmt_ctx = {**meta, **params, 'cell_display_px': cell_px}
        function = _format_template(group['function'], params, meta)
        function_theme_swap = _format_template(
            group.get('function_theme_swap', group['function']), params, meta)
        constraints = [_format_template(c, params, meta) for c in group.get('constraints', [])]
        if transparent:
            constraints = constraints + common

        out[name] = {
            'role_class': role_class_id,
            'role_label': role_class.get('label', role_class_id),
            'role_summary': role_class.get('summary', ''),
            'category': role_class.get('category', 'unknown'),
            'function': function,
            'function_theme_swap': function_theme_swap,
            'constraints': constraints,
            'family': family,
            'transparent': transparent,
        }
    return out


def build_role_table(config: dict | None = None) -> dict[str, dict]:
    global _role_table_cache
    if _role_table_cache is not None and config is None:
        return _role_table_cache

    cfg = config or load_config()
    table: dict[str, dict] = {}
    for group in cfg.get('asset_groups', []):
        table.update(_expand_group(group, cfg))

    if config is None:
        _role_table_cache = table
    return table


def role_mode_brief(asset: dict, mode: GenerationMode, config: dict | None = None) -> dict:
    """Return mode-specific creative brief for an asset."""
    cfg = config or load_config()
    role_class = get_role_class(asset['role_class'], cfg)
    return role_class.get(mode, role_class.get('restyle', {}))


def list_role_classes(config: dict | None = None) -> list[dict]:
    cfg = config or load_config()
    return [
        {'id': rid, **meta}
        for rid, meta in sorted(cfg['role_classes'].items())
    ]
