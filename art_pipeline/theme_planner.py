"""
Theme planner — 用 LLM 把主題概念(例如「水果」)展開成每個 asset 的物件指派。

輸出格式:
  Red=red apple, Soda0d=horizontal watermelon slice rocket, ...
"""

from __future__ import annotations

import json
import re

from . import gemini_api

ELEMENT_COLOR_HINTS = {
    'Red': 'red',
    'Grn': 'green',
    'Blu': 'blue',
    'Yel': 'yellow',
    'Pur': 'purple',
}


def _asset_brief_line(asset: dict) -> str:
    name = asset['name']
    role = asset.get('role_label', asset.get('role_class', 'unknown'))
    func = asset.get('function_theme_swap') or asset.get('function', '')
    fam = asset.get('family') or 'misc'
    color = ELEMENT_COLOR_HINTS.get(name)
    color_note = f' Dominant color must stay unmistakably {color}.' if color else ''
    return f'- {name} [{fam}] ({role}): {func}{color_note}'


def format_assignments(assignments: dict[str, str],
                       names: list[str] | None = None) -> str:
    order = names or sorted(assignments.keys())
    parts = []
    for name in order:
        val = assignments.get(name, '').strip()
        if val:
            parts.append(f'{name}={val}')
    return ', '.join(parts)


def _assignment_order(preferred: list[str], assignments: dict[str, str]) -> list[str]:
    ordered = [n for n in preferred if n in assignments]
    for name in sorted(assignments):
        if name not in ordered:
            ordered.append(name)
    return ordered


def _parse_assignments(data: dict, names: list[str]) -> dict[str, str]:
    """Map LLM assignment keys onto exact asset names (case-insensitive fallback)."""
    raw = data.get('assignments') or {}
    if not isinstance(raw, dict):
        return {}
    by_lower = {n.lower(): n for n in names}
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if key in by_lower.values():
            val = str(v).strip()
            if val:
                out[key] = val
        elif key.lower() in by_lower:
            val = str(v).strip()
            if val:
                out[by_lower[key.lower()]] = val
    return out


def _theme_rubric(theme_concept: str, style_text: str, targets: list[dict],
                  existing: dict[str, str], *, only_names: list[str] | None = None) -> str:
    show = [a for a in targets if not only_names or a['name'] in only_names]
    asset_lines = '\n'.join(_asset_brief_line(a) for a in show)
    required_keys = ',\n    '.join(f'"{a["name"]}": "..."' for a in show)
    existing_block = ''
    if existing:
        lines = '\n'.join(f'  {k}: {v}' for k, v in sorted(existing.items()))
        existing_block = (
            '\n[Already assigned — new objects must feel like the same themed set]\n'
            f'{lines}\n')
    must_list = ', '.join(a['name'] for a in show)
    return f"""You are a game art director for a match-3 game (theme-swap mode).

[Theme concept] {theme_concept}
[Target art style] {style_text}

The target art style MUST shape every assignment: rendering dimension, material finish, silhouette simplicity, palette, and mood. Each description should say WHAT the object is AND HOW it should look in this style.

Assign ONE distinct themed object per asset below. Objects must fit the theme concept, match the art style, and read clearly as game sprites at ~70px.
Respect each asset's gameplay role (powerup direction, obstacle HP stages, color identity, etc.).
Keep powerups and props SIMPLE — iconic silhouettes, not ornate jewelry or busy filigree.
Powerups must read purely from the OBJECT'S SHAPE. NEVER describe glow, trail, whoosh, sparkle, aura, sparks, energy beams, exhaust flames or motion effects — these break background removal. Express direction/explosiveness/power through the object form and its own surface colors only.
{existing_block}
Assets:
{asset_lines}

You MUST include an assignment for every asset listed above. Use the exact asset name as the JSON key.
Required keys: {must_list}

Return ONLY JSON (no markdown):
{{
  "summary": "one sentence describing the unified themed set in English",
  "assignments": {{
    {required_keys}
  }}
}}"""


def expand_theme_for_targets(
    theme_concept: str,
    style_text: str,
    targets: list[dict],
    *,
    existing_assignments: dict[str, str] | None = None,
    client=None,
    model: str = gemini_api.DEFAULT_CRITIC_MODEL,
) -> dict:
    """
    用 LLM 展開主題概念 → 每個 target asset 的物件描述。

    style_text 應為 refine 後的畫風 brief（與生成 prompt 一致）。
    existing_assignments: 已指派過的 asset（分批生成時保持同一套主題）。
    """
    from google.genai import types

    if not targets:
        raise ValueError('expand_theme_for_targets: empty targets')

    names = [a['name'] for a in targets]
    existing = existing_assignments or {}

    if client is None:
        client = gemini_api.get_client()

    assignments: dict[str, str] = {}
    summary = ''
    pending = list(names)

    for _ in range(3):
        if not pending:
            break
        rubric = _theme_rubric(
            theme_concept, style_text, targets, {**existing, **assignments},
            only_names=pending,
        )

        def _call(rubric=rubric):
            return client.models.generate_content(
                model=model,
                contents=rubric,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    http_options=gemini_api._http_options(),
                ),
            )

        resp = gemini_api._with_retries(_call, f'expand_theme({model})')
        try:
            data = json.loads(resp.text)
        except (json.JSONDecodeError, TypeError) as e:
            raise RuntimeError(f'Theme planner returned invalid JSON: {resp.text[:300]}') from e

        if not summary:
            summary = str(data.get('summary', ''))
        assignments.update(_parse_assignments(data, pending))
        pending = [n for n in names if n not in assignments]

    missing = [n for n in names if n not in assignments]
    if missing:
        raise RuntimeError(f'Theme planner missing assignments for: {missing}')

    return {
        'concept': theme_concept,
        'style': style_text,
        'summary': summary,
        'assignments': assignments,
    }


def expand_theme_for_elements(
    theme_concept: str,
    style_text: str,
    element_names: list[str] | None = None,
    *,
    client=None,
    model: str = gemini_api.DEFAULT_CRITIC_MODEL,
) -> dict:
    """Backward-compat: expand by asset name list (loads manifest entries)."""
    from .manifest import build_manifest

    names = element_names or list(ELEMENT_COLOR_HINTS.keys())
    by_name = {a['name']: a for a in build_manifest()}
    targets = [by_name[n] for n in names if n in by_name]
    missing = [n for n in names if n not in by_name]
    if missing:
        raise ValueError(f'Unknown assets: {missing}')
    plan = expand_theme_for_targets(
        theme_concept, style_text, targets,
        client=client, model=model,
    )
    order = _assignment_order(names, plan['assignments'])
    plan['theme_direction'] = format_assignments(plan['assignments'], order)
    return plan


def theme_plan_complete_for_targets(theme_plan: dict | None,
                                    theme_text: str | None,
                                    style_text: str | None,
                                    target_names: list[str]) -> bool:
    if not theme_plan or not theme_text or not style_text:
        return False
    if theme_plan.get('concept') != theme_text or theme_plan.get('style') != style_text:
        return False
    assignments = theme_plan.get('assignments', {})
    return all(n in assignments for n in target_names)


def theme_note_for_asset(asset_name: str, theme_text: str | None,
                         theme_plan: dict | None = None) -> str:
    """組出單一 asset 用的 theme prompt 片段。"""
    if not theme_text and not theme_plan:
        return ''

    lines: list[str] = []
    if theme_plan:
        summary = theme_plan.get('summary', '').strip()
        concept = theme_plan.get('concept', '').strip()
        if concept:
            lines.append(f'[Overall theme concept] {concept}')
        if summary:
            lines.append(f'[Theme set summary] {summary}')

    if theme_plan and asset_name in theme_plan.get('assignments', {}):
        obj = theme_plan['assignments'][asset_name]
        lines.append(f"[This asset's themed object] {obj}")
        return '\n' + '\n'.join(lines)

    if theme_text:
        for part in re.split(r'[,;]\s*', theme_text):
            part = part.strip()
            if '=' in part:
                key, val = part.split('=', 1)
                if key.strip() == asset_name:
                    lines.append(f"[This asset's themed object] {val.strip()}")
                    return '\n' + '\n'.join(lines)
        lines.append(f'[Theme direction] {theme_text}')

    return '\n' + '\n'.join(lines) if lines else ''


if __name__ == '__main__':
    assert 'Red' in _asset_brief_line({
        'name': 'Red', 'family': 'elements', 'role_label': 'Match Element',
        'function': 'Basic red match element.',
    })
    assert format_assignments({'Red': 'apple', 'TNT': 'bomb'}, ['Red', 'TNT']) == (
        'Red=apple, TNT=bomb')
    got = _parse_assignments({'assignments': {'red': 'apple', 'Blu': 'berry'}}, ['Red', 'Blu'])
    assert got == {'Red': 'apple', 'Blu': 'berry'}
    print('theme_planner self-check ok')
