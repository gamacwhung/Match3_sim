"""
Stage planner — LLM expands a multi-stage family (Crt1-4, Pool_lv1-5, …) into a
per-stage visual spec plus a reference chain, so that each stage is *visibly
distinct* from its neighbour while staying in the same design.

Complements:
  theme_planner        — per-element themed object assignment
  family_style_planner — per-family cohesion tokens (material/ornament/…)

This planner is stage-level: for one family it produces
  {
    'family': 'crate',
    'anchor': 'Crt4',                 # pristine end, locks the base design
    'order': ['Crt4', 'Crt3', 'Crt2', 'Crt1'],   # generation order (anchor first)
    'stages': {
      'Crt4': {'visual': 'intact crate, all slats whole', 'ref_from': None},
      'Crt3': {'visual': 'one slat cracked, corner dented', 'ref_from': 'Crt4'},
      ...
    },
  }

Each stage's ``ref_from`` names the previous stage; the pipeline feeds BOTH the
family anchor (locks style) and that previous stage (locks progression) to the
image model — dual reference, which keeps drift bounded while making the step
between adjacent stages unmistakable at ~70px.
"""

from __future__ import annotations

import json

from . import gemini_api
from .roles import get_family_meta, load_config
from .visual_guidance import get_family_anchor_asset


def _lv(asset: dict) -> int | None:
    """Stage level, from asset['lv'] or asset['params']['lv'] (manifest stores it in params)."""
    lv = asset.get('lv', asset.get('params', {}).get('lv'))
    return lv if isinstance(lv, int) else None


def _state(asset: dict) -> str | None:
    return asset.get('state', asset.get('params', {}).get('state'))


def stage_assets_for_family(targets: list[dict], family_id: str) -> list[dict]:
    """Assets in ``targets`` belonging to ``family_id`` that carry a numeric stage ``lv``."""
    out = [a for a in targets
           if a.get('family') == family_id and _lv(a) is not None]
    return sorted(out, key=_lv)


def is_stage_family(family_id: str | None, config: dict | None = None) -> bool:
    """True when this family opts into stage-progression planning (asset_roles.json)."""
    if not family_id:
        return False
    return bool(get_family_meta(family_id, config).get('stage_progression'))


def stage_order(family_id: str, targets: list[dict],
                config: dict | None = None) -> list[str]:
    """Generation order: anchor (usually the pristine/full end) first, then descending lv."""
    cfg = config or load_config()
    assets = stage_assets_for_family(targets, family_id)
    if not assets:
        return []
    anchor = get_family_anchor_asset(family_id, cfg)
    # Chain runs from the anchor outward. Anchor is typically the highest-HP
    # (pristine/full) stage, so walk lv high -> low from it.
    names = [a['name'] for a in assets]
    if anchor in names:
        names.remove(anchor)
        names_desc = sorted(names, key=lambda n: -_lv_of(n, assets))
        return [anchor] + names_desc
    return sorted((a['name'] for a in assets), key=lambda n: -_lv_of(n, assets))


def _lv_of(name: str, assets: list[dict]) -> int:
    for a in assets:
        if a['name'] == name:
            return _lv(a) or 0
    return 0


def ref_from_for(order: list[str]) -> dict[str, str | None]:
    """Chain each stage to the previous one in generation order (first has none)."""
    chain: dict[str, str | None] = {}
    prev: str | None = None
    for name in order:
        chain[name] = prev
        prev = name
    return chain


def expand_stage_progression(
    family_id: str,
    targets: list[dict],
    style_text: str,
    *,
    theme_text: str | None = None,
    client=None,
    model: str = gemini_api.DEFAULT_CRITIC_MODEL,
    config: dict | None = None,
) -> dict | None:
    """LLM-expand a multi-stage family into discrete, mutually-distinct per-stage visuals.

    Returns None when the family has fewer than 2 numbered stages (nothing to chain).
    """
    from google.genai import types

    cfg = config or load_config()
    assets = stage_assets_for_family(targets, family_id)
    if len(assets) < 2:
        return None

    order = stage_order(family_id, targets, cfg)
    ref_from = ref_from_for(order)
    max_lv = max(_lv(a) or 0 for a in assets)
    meta = get_family_meta(family_id, cfg)
    series_note = meta.get('series_note', '')

    # Feed the model the gameplay meaning of each stage (HP level + any authored state).
    stage_lines = []
    for a in sorted(assets, key=lambda x: -(_lv(x) or 0)):
        authored = _state(a)
        note = f' (authored hint: {authored})' if authored else ''
        stage_lines.append(f'- {a["name"]}: HP {_lv(a)}/{max_lv}{note}')
    stages_block = '\n'.join(stage_lines)
    theme_line = f'\n[Theme concept] {theme_text}' if theme_text else ''

    rubric = f"""You are a game art director for a match-3 game.

[Family] {family_id}
[Series meaning] {series_note}
[Target art style] {style_text}{theme_line}

This family is the SAME object shown at {len(assets)} progressive HP/depletion stages.
HP {max_lv} = fully intact/full; HP 1 = about to be destroyed.

Write a SHORT, CONCRETE visual spec for each stage so that:
1. All stages are clearly the SAME object and design (identical base shape, material, palette).
2. Each stage is UNMISTAKABLY different from its neighbours when viewed small (~70px):
   use DISCRETE, chunky, readable damage/depletion steps — not subtle gradients.
   (e.g. missing whole chunks, big cracks, water level in clear quarters — not faint scratches.)
3. The change is MONOTONIC as HP drops (damage only ever increases toward HP 1).

Stages (highest HP first):
{stages_block}

Return ONLY JSON (no markdown):
{{
  "stages": {{
    {', '.join(f'"{a["name"]}": "concrete visual for this stage"' for a in sorted(assets, key=lambda x: -(_lv(x) or 0)))}
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

    resp = gemini_api._with_retries(_call, f'expand_stage_progression({family_id})')
    try:
        data = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(
            f'Stage planner returned invalid JSON: {resp.text[:300]}') from e

    raw = data.get('stages') or {}
    names = {a['name'] for a in assets}
    stages: dict[str, dict] = {}
    for name in names:
        visual = str(raw.get(name, '')).strip()
        if not visual:
            raise RuntimeError(f'Stage planner missing visual for {name}')
        stages[name] = {'visual': visual, 'ref_from': ref_from.get(name)}

    return {
        'family': family_id,
        'concept': theme_text,
        'style': style_text,
        'anchor': order[0] if order else None,
        'order': order,
        'stages': stages,
    }


def stage_note_for_asset(asset_name: str, stage_plan: dict | None) -> str:
    """Prompt fragment describing THIS stage's target look + the required visible step."""
    if not stage_plan:
        return ''
    entry = stage_plan.get('stages', {}).get(asset_name)
    if not entry:
        return ''
    lines = [f'[This stage\'s target look] {entry["visual"]}']
    ref = entry.get('ref_from')
    if ref:
        ref_visual = stage_plan.get('stages', {}).get(ref, {}).get('visual', '')
        lines.append(
            f'[Progression — MUST be obvious] The attached previous-stage reference is '
            f'"{ref}" ({ref_visual}). This stage has LESS HP: show clearly MORE '
            f'damage/depletion than it, in a discrete step a player notices instantly at ~70px. '
            f'Keep the same base object and style; change ONLY the damage/depletion.')
    return '\n' + '\n'.join(lines)


if __name__ == '__main__':
    # self-check: order + ref chain wiring, no network needed
    fake_targets = [
        {'name': 'Crt1', 'family': 'crate', 'lv': 1, 'state': 'almost destroyed'},
        {'name': 'Crt2', 'family': 'crate', 'lv': 2, 'state': 'visibly damaged'},
        {'name': 'Crt3', 'family': 'crate', 'lv': 3, 'state': 'slightly damaged'},
        {'name': 'Crt4', 'family': 'crate', 'lv': 4, 'state': 'intact'},
    ]
    cfg = {'families': {'crate': {'anchor_asset': 'Crt4', 'stage_progression': True,
                                  'series_note': 'same crate, progressive damage'}}}
    assert is_stage_family('crate', cfg)
    assert not is_stage_family('elements', cfg)
    order = stage_order('crate', fake_targets, cfg)
    assert order == ['Crt4', 'Crt3', 'Crt2', 'Crt1'], order
    chain = ref_from_for(order)
    assert chain == {'Crt4': None, 'Crt3': 'Crt4', 'Crt2': 'Crt3', 'Crt1': 'Crt2'}, chain
    plan = {'stages': {
        'Crt4': {'visual': 'intact crate', 'ref_from': None},
        'Crt3': {'visual': 'one slat cracked', 'ref_from': 'Crt4'},
    }}
    note = stage_note_for_asset('Crt3', plan)
    assert 'MUST be obvious' in note and 'Crt4' in note, note
    assert stage_note_for_asset('Crt4', plan).find('Progression') == -1
    print('stage_planner self-check ok')
