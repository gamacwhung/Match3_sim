"""
High-level API for the game art generation pipeline.

Use from Streamlit pages, scripts, or tests — hides CLI / file-path details.

Example:
    from art_pipeline import api

    api.generate_elements("pixel art", run_name="lab_pixel")
    api.apply_run_to_game("lab_pixel")
"""

from __future__ import annotations

import json
import pathlib
import time
from dataclasses import dataclass, field
from typing import Callable

from . import gemini_api, pipeline
from .apply import (
    DEFAULT_PACKED_ART_RUN,
    ApplyProgressCallback,
    apply_run_batch,
    apply_default_packed_art,
    restore,
)
from .manifest import PROJECT_ROOT, build_manifest, families
from .pipeline import GENERATED_ROOT, resolve_expand_theme
from .theme_planner import expand_theme_for_elements

BASIC_ELEMENTS: tuple[str, ...] = ('Red', 'Grn', 'Blu', 'Yel', 'Pur')

FAMILY_LABELS: dict[str, str] = {
    'elements': '基本元素',
    'powerups': '道具',
    'crate': '紙箱',
    'movable': '可移動障礙',
    'salmon_can': '鮭魚罐頭',
    'puddle': '水漥',
    'rope': '繩索',
    'mud': '泥巴',
    'postmark': '郵戳',
    'pool': '游泳池',
    'water_chiller': '礦泉水櫃',
    'beverage_chiller': '飲料櫃',
    'background': '背景',
    'misc': '其他',
}


@dataclass
class AssetResult:
    name: str
    status: str
    iters: int
    image: bytes | None = None
    verdict: dict | None = None
    chosen_iter: int | None = None


@dataclass
class GenerationSummary:
    run_name: str
    run_dir: pathlib.Path
    style: str
    results: dict[str, AssetResult] = field(default_factory=dict)
    generation_mode: str = 'restyle'
    theme_text: str | None = None
    theme_plan: dict | None = None
    theme_expanded: str | None = None
    reference_run: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results.values() if r.status == 'pass')

    @property
    def needs_review(self) -> int:
        return sum(1 for r in self.results.values() if r.status == 'needs_review')

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results.values() if r.status == 'failed')


@dataclass
class ApplySummary:
    run_name: str
    applied: list[str] = field(default_factory=list)        # godot_demo/resources/sprites
    live_applied: list[str] = field(default_factory=list)   # godot_demo/web/live_sprites
    component_applied: list[str] = field(default_factory=list)  # playable board component
    skipped: list[str] = field(default_factory=list)

    @property
    def total_applied(self) -> int:
        return len(set(self.applied) | set(self.live_applied) | set(self.component_applied))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def has_credentials() -> bool:
    """Return True if Google / Vertex credentials are configured."""
    try:
        gemini_api.get_client()
        return True
    except ValueError:
        return False


def list_assets(*, family: str | None = None) -> list[dict]:
    manifest = build_manifest()
    if family:
        manifest = [a for a in manifest if a.get('family') == family]
    return manifest


def list_basic_elements() -> list[dict]:
    wanted = set(BASIC_ELEMENTS)
    return [a for a in build_manifest() if a['name'] in wanted]


def list_asset_names(*, family: str | None = None) -> list[str]:
    """All generatable asset names from godot_demo/resources/sprites/."""
    return [a['name'] for a in list_assets(family=family)]


def asset_label(name: str, asset: dict | None = None) -> str:
    """Human-readable label for multiselect, e.g. '[基本元素] Red'."""
    if asset is None:
        matches = [a for a in build_manifest() if a['name'] == name]
        asset = matches[0] if matches else {}
    fam = asset.get('family') or 'misc'
    fam_label = FAMILY_LABELS.get(fam, fam)
    return f'[{fam_label}] {name}'


def asset_catalog() -> tuple[list[str], dict[str, str]]:
    """Sorted asset names and name → display label map."""
    assets = list_assets()
    labels = {a['name']: asset_label(a['name'], a) for a in assets}
    names = sorted(labels.keys(), key=lambda n: labels[n].lower())
    return names, labels


def asset_image_map() -> dict[str, str]:
    """name → absolute sprite png path (for UI thumbnails)."""
    return {a['name']: str(PROJECT_ROOT / a['path']) for a in list_assets()}


def asset_thumbnail_map(reference_run: str | None = None) -> dict[str, str]:
    """Thumbnails for UI; when reference_run is set, use that run's sprites only."""
    if not reference_run:
        return asset_image_map()
    sprites_dir = run_dir(reference_run) / 'sprites'
    out: dict[str, str] = {}
    for name in asset_image_map():
        ref_path = sprites_dir / f'{name}.png'
        if ref_path.is_file():
            out[name] = str(ref_path)
    return out


def format_verdict_scores(verdict: dict | None) -> str:
    """Compact score line for UI: style / func / ref (when present)."""
    if not verdict:
        return ''
    parts = [
        f"style {verdict.get('style_score', '?')}",
        f"func {verdict.get('function_score', '?')}",
    ]
    if 'reference_element_score' in verdict:
        parts.append(f"ref {verdict['reference_element_score']}")
    return ' · '.join(parts)


def list_families() -> dict[str, list[str]]:
    return families(build_manifest())


def list_runs() -> list[str]:
    if not GENERATED_ROOT.is_dir():
        return []
    return sorted(
        p.name for p in GENERATED_ROOT.iterdir()
        if p.is_dir() and (p / 'sprites').is_dir()
    )


def list_reference_runs() -> list[str]:
    """Runs with sprites/ usable as Reference A for restyle."""
    return sorted(
        name for name in list_runs()
        if any((run_dir(name) / 'sprites').glob('*.png'))
    )


def run_dir(run_name: str) -> pathlib.Path:
    return GENERATED_ROOT / run_name


def load_report(run_name: str) -> dict:
    path = run_dir(run_name) / 'report.json'
    if not path.is_file():
        raise FileNotFoundError(f'No report for run {run_name!r}: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def load_sprite_bytes(run_name: str, asset_name: str) -> bytes | None:
    path = run_dir(run_name) / 'sprites' / f'{asset_name}.png'
    return path.read_bytes() if path.is_file() else None


def default_style_image() -> pathlib.Path | None:
    """預設元素參考圖路徑(若存在),供 UI 預覽/生成時 fallback。"""
    path = pipeline.DEFAULT_STYLE_IMAGE
    return path if path.is_file() else None


def suggest_run_name(style_text: str) -> str:
    slug = ''.join(ch if ch.isalnum() else '_' for ch in style_text.lower()).strip('_')
    slug = '_'.join(filter(None, slug.split('_')))[:24] or 'style'
    return f'lab_{slug}_{int(time.time())}'


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _raw_to_asset_result(raw: dict) -> AssetResult:
    return AssetResult(
        name=raw['name'],
        status=raw.get('status', 'failed'),
        iters=raw.get('iters', 0),
        image=raw.get('image'),
        verdict=raw.get('verdict'),
        chosen_iter=raw.get('chosen_iter'),
    )


def _load_generation_summary(
    run_name: str,
    *,
    style_text: str,
    mode: str,
    theme_text: str | None,
    reference_run: str | None,
    asset_names: list[str] | None = None,
) -> GenerationSummary:
    report = load_report(run_name)
    names = asset_names or report.get('target_assets') or list(report.get('results', {}))
    if asset_names and report.get('target_assets'):
        names = [n for n in asset_names if n in report['target_assets']]
    results: dict[str, AssetResult] = {}
    for name in names:
        raw = report.get('results', {}).get(name, {})
        image = raw.get('image') or load_sprite_bytes(run_name, name)
        results[name] = AssetResult(
            name=name,
            status=raw.get('status', 'failed'),
            iters=raw.get('iters', 0),
            image=image,
            verdict=raw.get('verdict'),
            chosen_iter=raw.get('chosen_iter'),
        )
    return GenerationSummary(
        run_name=run_name,
        run_dir=run_dir(run_name),
        style=style_text,
        results=results,
        generation_mode=mode,
        theme_text=theme_text,
        theme_plan=report.get('theme_plan'),
        theme_expanded=report.get('theme_expanded'),
        reference_run=reference_run,
    )


def generate(
    style_text: str,
    run_name: str,
    *,
    asset_names: list[str] | None = None,
    family: str | None = None,
    style_image_path: str | pathlib.Path | None = None,
    reference_image: bool = True,
    mode: str = 'restyle',
    theme_text: str | None = None,
    expand_theme: bool = False,
    reference_run: str | None = None,
    image_model: str | None = None,
    critic_model: str | None = None,
    max_iters: int = 3,
    force: bool = False,
    on_progress: Callable[[int, int, str, AssetResult | None], None] | None = None,
) -> GenerationSummary:
    """
    Generate art for the selected assets.

    on_progress(current_index, total, asset_name, result_or_none)
      is called before each asset (result=None) and after completion.

    Delegates to pipeline.run so Web and CLI share the same generation path.
    """
    progress_adapter = None
    if on_progress:
        def progress_adapter(cur: int, total: int, name: str, raw: dict | None) -> None:
            if raw is None:
                on_progress(cur, total, name, None)
            else:
                on_progress(cur, total, name, _raw_to_asset_result(raw))

    pipeline.run(
        style_text=style_text,
        run_name=run_name,
        style_image_path=style_image_path,
        asset_names=asset_names,
        family=family,
        image_model=image_model or gemini_api.DEFAULT_IMAGE_MODEL,
        critic_model=critic_model or gemini_api.DEFAULT_CRITIC_MODEL,
        max_iters=max_iters,
        force=force,
        mode=mode,
        theme_text=theme_text,
        reference_image=reference_image,
        expand_theme=expand_theme,
        reference_run=reference_run,
        on_progress=progress_adapter,
    )
    return _load_generation_summary(
        run_name,
        style_text=style_text,
        mode=mode,
        theme_text=theme_text,
        reference_run=reference_run,
        asset_names=asset_names,
    )


def preview_theme_plan(
    theme_concept: str,
    style_text: str,
    asset_names: list[str] | None = None,
    *,
    critic_model: str | None = None,
) -> dict:
    """LLM-expand a theme concept into per-asset object assignments (no image generation)."""
    names = asset_names or list(BASIC_ELEMENTS)
    client = gemini_api.get_client()
    return expand_theme_for_elements(
        theme_concept, style_text, names,
        client=client, model=critic_model or gemini_api.DEFAULT_CRITIC_MODEL,
    )


def generate_elements(
    style_text: str,
    run_name: str | None = None,
    **kwargs,
) -> GenerationSummary:
    """Convenience wrapper — generate only the five basic match elements."""
    return generate(
        style_text,
        run_name or suggest_run_name(style_text),
        asset_names=list(BASIC_ELEMENTS),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Apply / restore
# ---------------------------------------------------------------------------

def apply_run_to_game(
    run_name: str,
    *,
    to_component: bool = True,
    to_live: bool = True,
    to_project: bool = False,
    asset_names: list[str] | None = None,
    on_progress: ApplyProgressCallback | None = None,
) -> ApplySummary:
    """
    Apply a completed run to the game.

    - to_component: copy into the Streamlit playable board component
      (reflected instantly in the web UI — the only path that works locally
      without a Godot re-export). Default on.
    - to_live: copy into godot_demo/web/live_sprites/ (Godot runtime override;
      requires the web build to be re-exported once with the ArtTheme autoload,
      which currently happens in CI).
    - to_project: copy into godot_demo/resources/sprites/ (persistent source art,
      backs up originals; picked up on the next Godot export).
    - on_progress: optional callback(current_index, total, asset_name) per file.
    """
    names = asset_names
    if names is None:
        report = load_report(run_name)
        names = [
            n for n in report.get('results', {})
            if (run_dir(run_name) / 'sprites' / f'{n}.png').is_file()
        ]

    if to_component or to_live or to_project:
        comp, live, proj, skipped = apply_run_batch(
            run_name,
            names,
            to_component=to_component,
            to_live=to_live,
            to_project=to_project,
            on_progress=on_progress,
        )
        return ApplySummary(
            run_name=run_name,
            applied=proj,
            live_applied=live,
            component_applied=comp,
            skipped=skipped,
        )

    return ApplySummary(run_name=run_name)


def default_packed_art_run() -> str:
    """Run name whose sprites are baked into the Godot web pck by default."""
    return DEFAULT_PACKED_ART_RUN


def restore_original_art() -> None:
    """Restore game default packed art and clear live overrides."""
    restore()
