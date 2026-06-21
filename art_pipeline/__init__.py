"""
Game Art AI Generation Pipeline — 用 Gemini 把遊戲美術整批換風格。

高階 API: art_pipeline.api
CLI 入口: scripts/ai_art_gen.py
"""

from .api import (
    BASIC_ELEMENTS,
    FAMILY_LABELS,
    ApplySummary,
    AssetResult,
    GenerationSummary,
    apply_run_to_game,
    asset_catalog,
    asset_label,
    format_verdict_scores,
    generate,
    generate_elements,
    has_credentials,
    list_asset_names,
    list_assets,
    list_basic_elements,
    list_families,
    list_runs,
    load_report,
    load_sprite_bytes,
    restore_original_art,
    run_dir,
    suggest_run_name,
)

__all__ = [
    'BASIC_ELEMENTS',
    'FAMILY_LABELS',
    'ApplySummary',
    'AssetResult',
    'GenerationSummary',
    'apply_run_to_game',
    'asset_catalog',
    'asset_label',
    'format_verdict_scores',
    'generate',
    'generate_elements',
    'has_credentials',
    'list_asset_names',
    'list_assets',
    'list_basic_elements',
    'list_families',
    'list_runs',
    'load_report',
    'load_sprite_bytes',
    'restore_original_art',
    'run_dir',
    'suggest_run_name',
]
