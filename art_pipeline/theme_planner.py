"""
Theme planner — 用 LLM 把主題概念(例如「糖果屋」)展開成每個 element 的物件指派。

輸出格式與 THEME_PRESETS 相同:
  Red=red gingerbread roof tile, Grn=green candy cane, ...
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


def format_assignments(assignments: dict[str, str]) -> str:
    parts = []
    for name in ELEMENT_COLOR_HINTS:
        if name in assignments and assignments[name].strip():
            parts.append(f'{name}={assignments[name].strip()}')
    return ', '.join(parts)


def expand_theme_for_elements(
    theme_concept: str,
    style_text: str,
    element_names: list[str] | None = None,
    *,
    client=None,
    model: str = gemini_api.DEFAULT_CRITIC_MODEL,
) -> dict:
    """
    用 LLM 展開主題概念 → 每個 element 的物件描述。

    回傳:
      {
        'concept': str,
        'style': str,
        'summary': str,           # 一句話主題說明
        'assignments': {Red: ..., ...},
        'theme_direction': str,   # Red=..., Grn=..., 可直接餵 pipeline
      }
    """
    from google.genai import types

    names = element_names or list(ELEMENT_COLOR_HINTS.keys())
    color_lines = '\n'.join(
        f'- {n}: dominant color must be unmistakably {ELEMENT_COLOR_HINTS.get(n, n)}'
        for n in names
    )
    rubric = f"""You are a game art director for a match-3 game (theme-swap mode).

[Theme concept] {theme_concept}
[Target art style] {style_text}

Assign ONE distinct themed object to each match element below.
Objects should fit the theme concept and art style, and feel like they belong in the same set.
Each object must keep its gameplay color identity.

Elements:
{color_lines}

Return ONLY JSON (no markdown):
{{
  "summary": "one sentence describing the unified theme set in English",
  "assignments": {{
    "Red": "themed object description for red element",
    "Grn": "...",
    "Blu": "...",
    "Yel": "...",
    "Pur": "..."
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

    resp = gemini_api._with_retries(_call, f'expand_theme({model})')
    try:
        data = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(f'Theme planner returned invalid JSON: {resp.text[:300]}') from e

    assignments = {k: str(v) for k, v in (data.get('assignments') or {}).items() if k in names}
    missing = [n for n in names if n not in assignments]
    if missing:
        raise RuntimeError(f'Theme planner missing assignments for: {missing}')

    theme_direction = format_assignments(assignments)
    return {
        'concept': theme_concept,
        'style': style_text,
        'summary': str(data.get('summary', '')),
        'assignments': assignments,
        'theme_direction': theme_direction,
    }


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

    # 優先使用 planner 的 per-asset 指派
    if theme_plan and asset_name in theme_plan.get('assignments', {}):
        obj = theme_plan['assignments'][asset_name]
        lines.append(f'[This element\'s themed object] {obj}')
        return '\n' + '\n'.join(lines)

    if theme_text:
        # 手動 Red=..., Grn=... 格式 → 抽出此 asset 那一項
        for part in re.split(r'[,;]\s*', theme_text):
            part = part.strip()
            if '=' in part:
                key, val = part.split('=', 1)
                if key.strip() == asset_name:
                    lines.append(f'[This element\'s themed object] {val.strip()}')
                    return '\n' + '\n'.join(lines)
        lines.append(f'[Theme direction] {theme_text}')

    return '\n' + '\n'.join(lines) if lines else ''
