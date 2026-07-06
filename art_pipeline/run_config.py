"""Snapshot generation invocation (CLI / Web) for report.json."""

from __future__ import annotations

import shlex
from datetime import datetime, timezone
from typing import Any


def build_run_config(
    *,
    source: str = 'cli',
    run_name: str,
    style_text: str,
    mode: str,
    theme_text: str | None = None,
    family: str | None = None,
    asset_names: list[str] | None = None,
    style_image_path: str | None = None,
    reference_run: str | None = None,
    image_model: str,
    critic_model: str,
    max_iters: int,
    dry_run: bool = False,
    force: bool = False,
    reference_image: bool = True,
    expand_theme: bool = False,
    refine_style: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict:
    """Flat dict of invocation parameters + reproduce_command shell snippet."""
    mode_cli = 'theme-swap' if mode == 'theme_swap' else 'restyle'
    cfg: dict[str, Any] = {
        'source': source,
        'invoked_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'command': 'generate',
        'run': run_name,
        'mode': mode_cli,
        'style': style_text,
        'theme': theme_text,
        'family': family,
        'assets': asset_names,
        'style_image': style_image_path,
        'reference_run': reference_run,
        'image_model': image_model,
        'critic_model': critic_model,
        'max_iters': max_iters,
        'dry_run': dry_run,
        'force': force,
        'reference_image': reference_image,
        'expand_theme': expand_theme,
        'refine_style': refine_style,
    }
    if extra:
        cfg.update(extra)
    cfg['reproduce_command'] = format_reproduce_command(cfg)
    return cfg


def format_reproduce_command(cfg: dict) -> str:
    """Multi-line shell command equivalent to the invocation."""
    lines = ['python scripts/ai_art_gen.py generate \\']
    if cfg.get('mode') == 'theme-swap':
        lines.append('  --mode theme-swap \\')
    lines.append(f'  --style {shlex.quote(cfg["style"])} \\')
    if cfg.get('theme'):
        lines.append(f'  --theme {shlex.quote(cfg["theme"])} \\')
    lines.append(f'  --run {shlex.quote(cfg["run"])} \\')
    if cfg.get('assets'):
        assets = ','.join(cfg['assets'])
        lines.append(f'  --assets {shlex.quote(assets)} \\')
    elif cfg.get('family'):
        lines.append(f'  --family {shlex.quote(cfg["family"])} \\')
    if cfg.get('reference_run'):
        lines.append(f'  --reference-run {shlex.quote(cfg["reference_run"])} \\')
    if cfg.get('style_image'):
        lines.append(f'  --style-image {shlex.quote(cfg["style_image"])} \\')
    if not cfg.get('reference_image', True):
        lines.append('  --no-reference-image \\')
    if cfg.get('expand_theme') is False and cfg.get('mode') == 'theme-swap' and cfg.get('theme'):
        lines.append('  --no-expand-theme \\')
    elif cfg.get('expand_theme'):
        lines.append('  --expand-theme \\')
    if not cfg.get('refine_style', True):
        lines.append('  --no-refine-style \\')
    if cfg.get('dry_run'):
        lines.append('  --dry-run \\')
    if cfg.get('force'):
        lines.append('  --force \\')
    if cfg.get('max_iters', 3) != 3:
        lines.append(f'  --max-iters {cfg["max_iters"]} \\')
    default_image = 'gemini-3.1-flash-image'
    default_critic = 'gemini-3.5-flash'
    if cfg.get('image_model') and cfg['image_model'] != default_image:
        lines.append(f'  --image-model {shlex.quote(cfg["image_model"])} \\')
    if cfg.get('critic_model') and cfg['critic_model'] != default_critic:
        lines.append(f'  --critic-model {shlex.quote(cfg["critic_model"])} \\')
    if lines[-1].endswith(' \\'):
        lines[-1] = lines[-1][:-2]
    return '\n'.join(lines)


if __name__ == '__main__':
    cmd = build_run_config(
        run_name='fruit_3dCartoon',
        style_text='3D Disney Cartoon Style, Simple design, high gloss color',
        mode='theme_swap',
        theme_text='水果',
        family='elements',
        image_model='gemini-3.1-flash-image',
        critic_model='gemini-3.5-flash',
        max_iters=3,
        dry_run=True,
        reference_image=False,
        expand_theme=True,
        refine_style=True,
    )
    assert 'fruit_3dCartoon' in cmd['reproduce_command']
    assert '--no-reference-image' in cmd['reproduce_command']
    print('run_config self-check ok')
