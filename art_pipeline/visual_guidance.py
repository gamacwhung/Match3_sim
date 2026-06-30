"""
Family / category visual guidance — shared prompt and critic blocks.

Used by pipeline (generation) and gemini_api (critique) for:
  - intra-family cohesion
  - cross-category visual distinction
  - family anchor reference notes
"""

from __future__ import annotations

from .roles import get_category_visual, get_family_meta, load_config

FAMILY_ANCHOR_REF_LABEL = (
    'Reference — family cohesion anchor. '
    'Match rendering style, material, line weight, ornament language and shading model. '
    'Change subject, color and gameplay-specific shape as required by this asset\'s role. '
    'Do NOT copy the anchor\'s silhouette if the gameplay role differs.')

FAMILY_ANCHOR_PROMPT_NOTE = (
    '[Family anchor] An attached image shows the established visual language for this family. '
    'Align with its rendering style and material — not necessarily its silhouette.')


def get_family_anchor_asset(family_id: str | None, config: dict | None = None) -> str | None:
    if not family_id:
        return None
    meta = get_family_meta(family_id, config)
    return meta.get('anchor_asset')


def order_targets_for_family_anchors(targets: list[dict], config: dict | None = None) -> list[dict]:
    """Group by family; anchor_asset first within each group; stable family order."""
    cfg = config or load_config()
    if not targets:
        return []

    family_order: list[str] = []
    by_family: dict[str, list[dict]] = {}
    for asset in targets:
        fam = asset.get('family') or 'misc'
        if fam not in by_family:
            family_order.append(fam)
            by_family[fam] = []
        by_family[fam].append(asset)

    ordered: list[dict] = []
    for fam in family_order:
        group = by_family[fam]
        anchor_name = get_family_anchor_asset(fam, cfg)
        if anchor_name and len(group) > 1:
            anchor = [a for a in group if a['name'] == anchor_name]
            rest = [a for a in group if a['name'] != anchor_name]
            ordered.extend(anchor + rest)
        else:
            ordered.extend(group)
    return ordered


def _distinct_from_lines(asset: dict, config: dict | None = None) -> list[str]:
    cfg = config or load_config()
    family_id = asset.get('family')
    family_meta = get_family_meta(family_id, cfg)
    lines: list[str] = []

    category = asset.get('category', 'unknown')
    cat_visual = get_category_visual(category, cfg)
    if cat_visual.get('distinct_from'):
        lines.append(cat_visual['distinct_from'])

    for other_cat in family_meta.get('distinct_from_categories', []):
        other = get_category_visual(other_cat, cfg)
        if other.get('label') and other.get('distinct_from'):
            lines.append(f"vs {other['label']}: {other['distinct_from']}")

    return lines


def format_family_visual_block(
    asset: dict,
    family_names: list[str] | None = None,
    *,
    family_plan_entry: dict | None = None,
    has_family_anchor: bool = False,
    config: dict | None = None,
) -> str:
    """Build [Family visual language] + distinction block for prompts / critic."""
    cfg = config or load_config()
    family_id = asset.get('family')
    if not family_id:
        return ''

    family_meta = get_family_meta(family_id, cfg)
    category = asset.get('category', 'unknown')
    cat_visual = get_category_visual(category, cfg)

    lines: list[str] = []

    if family_meta.get('series_note'):
        lines.append(f'[Series consistency] {family_meta["series_note"]}')

    cohesion = list(family_meta.get('cohesion', []))
    if cat_visual.get('cohesion'):
        cohesion = cohesion + [c for c in cat_visual['cohesion'] if c not in cohesion]
    if cohesion:
        lines.append('[Within-family cohesion — MUST follow]')
        lines.extend(f'- {c}' for c in cohesion)

    if family_plan_entry:
        plan_bits = [f'{k}: {v}' for k, v in family_plan_entry.items() if v]
        if plan_bits:
            lines.append('[Theme-specific family visual language] ' + '; '.join(plan_bits))

    distinct = _distinct_from_lines(asset, cfg)
    if distinct:
        lines.append('[Visual distinction from other sprite categories]')
        lines.extend(f'- {d}' for d in distinct)

    if family_names and len(family_names) > 1:
        lines.append(
            f'[Family members] {", ".join(family_names)} — keep a unified design language '
            f'across this "{family_id}" set.')

    if has_family_anchor:
        lines.append(FAMILY_ANCHOR_PROMPT_NOTE)

    return '\n' + '\n'.join(lines) if lines else ''


def format_critic_visual_block(
    asset: dict,
    *,
    family_plan_entry: dict | None = None,
    has_family_anchor: bool = False,
    multi_category_run: bool = False,
    config: dict | None = None,
) -> str:
    """Shorter visual guidance block for critic rubrics."""
    block = format_family_visual_block(
        asset, family_plan_entry=family_plan_entry,
        has_family_anchor=has_family_anchor, config=config)
    if not block and not multi_category_run:
        return ''
    extra = ''
    if asset.get('category') == 'element':
        extra = (
            '\n[Color clarity rule] For match elements: high cohesion is good, but if dominant '
            'colors are confused between red/green/blue/yellow/purple, function_score must be low '
            'and verdict must be retry.')
    return block + extra


def cohesion_critic_rubric(*, has_family_anchor: bool, multi_category_run: bool) -> str:
    parts: list[str] = []
    if has_family_anchor:
        parts.append(
            '\n  "cohesion_score": 0-10, // how well it matches the family anchor rendering '
            'style, material and ornament language (not necessarily the same silhouette)')
    if multi_category_run:
        parts.append(
            '\n  "distinction_score": 0-10, // how visually distinct this is from other '
            'sprite categories (elements vs powerups vs obstacles) per the guidance above')
    return ''.join(parts)


def cohesion_verdict_rules(*, has_family_anchor: bool, multi_category_run: bool) -> str:
    rules = []
    if has_family_anchor:
        rules.append('cohesion_score>=7')
    if multi_category_run:
        rules.append('distinction_score>=6')
    if not rules:
        return ''
    return ' AND '.join(rules) + ' AND '


if __name__ == '__main__':
    from art_pipeline.manifest import build_manifest
    from art_pipeline.roles import clear_cache

    clear_cache()
    m = build_manifest()
    by_name = {a['name']: a for a in m}
    ordered = order_targets_for_family_anchors([by_name['Grn'], by_name['Red']])
    assert ordered[0]['name'] == 'Red'
    block = format_family_visual_block(by_name['Red'], ['Red', 'Grn'])
    assert 'Within-family cohesion' in block
    print('visual_guidance self-check ok')
