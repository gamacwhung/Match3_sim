"""
Family style planner — LLM expands a theme concept into per-family visual language.

Complements theme_planner (element object assignments) with run-level cohesion tokens
(shared_shape, material, ornament, accent, …) for each family in the batch.
"""

from __future__ import annotations

import json

from . import gemini_api
from .roles import get_family_meta, load_config


def should_plan_family_styles(
    theme_text: str | None,
    targets: list[dict],
) -> bool:
    if not theme_text:
        return False
    families = {a.get('family') or 'misc' for a in targets}
    if len(families) >= 2:
        return True
    if len(targets) >= 2:
        return True
    return False


def _family_templates(family_ids: list[str]) -> str:
    cfg = load_config()
    lines = []
    for fid in family_ids:
        meta = get_family_meta(fid, cfg)
        cohesion = meta.get('cohesion', [])
        note = meta.get('series_note', '')
        lines.append(f'- {fid}: {note}')
        for c in cohesion[:3]:
            lines.append(f'    cohesion hint: {c}')
    return '\n'.join(lines)


def expand_family_styles(
    theme_concept: str,
    style_text: str,
    family_ids: list[str],
    *,
    client=None,
    model: str = gemini_api.DEFAULT_CRITIC_MODEL,
) -> dict:
    """
    Return:
      {
        'concept': str,
        'style': str,
        'families': { family_id: { shared_shape, material, ornament, accent, ... } },
      }
    """
    from google.genai import types

    families_block = _family_templates(family_ids)
    example_entries = ',\n    '.join(
        f'"{fid}": {{"shared_shape": "...", "material": "...", "ornament": "...", "accent": "..."}}'
        for fid in family_ids
    )
    rubric = f"""You are a game art director for a match-3 game.

[Theme concept] {theme_concept}
[Target art style] {style_text}

Define a DISTINCT visual language for each sprite family below so that:
1. Assets WITHIN the same family feel cohesive (shared material, ornament, rendering).
2. Different families are visually DISTINCT (elements simpler than powerups; obstacles heavier).
3. Basic match elements keep unmistakable red/green/blue/yellow/purple color identity.

Families:
{families_block}

Return ONLY JSON (no markdown):
{{
  "families": {{
    {example_entries}
  }}
}}"""

    if client is None:
        client = gemini_api.get_client()

    def _call():
        return client.models.generate_content(
            model=model,
            contents=rubric,
            config=types.GenerateContentConfig(response_mime_type='application/json'),
        )

    resp = gemini_api._with_retries(_call, f'expand_family_styles({model})')
    try:
        data = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(f'Family style planner returned invalid JSON: {resp.text[:300]}') from e

    families = {k: dict(v) for k, v in (data.get('families') or {}).items() if k in family_ids}
    missing = [f for f in family_ids if f not in families]
    if missing:
        raise RuntimeError(f'Family style planner missing entries for: {missing}')

    return {
        'concept': theme_concept,
        'style': style_text,
        'families': families,
    }


def family_plan_entry_for_asset(
    asset: dict,
    family_style_plan: dict | None,
) -> dict | None:
    if not family_style_plan:
        return None
    fam = asset.get('family')
    if not fam:
        return None
    return family_style_plan.get('families', {}).get(fam)
