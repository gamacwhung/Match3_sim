"""
Style planner — refine a vague --style into a precise, consistent art-direction brief.

Runs once per generation batch; result is cached in report.json as style_plan.
All assets (generate + critic + downstream planners) use the resolved brief.
"""

from __future__ import annotations

import json

from . import gemini_api
from .roles import GenerationMode


def resolved_style_text(style_plan: dict | None, raw_style: str) -> str:
    """Text injected as [Target art style] in generation/critic prompts."""
    if not style_plan:
        return raw_style
    brief = (style_plan.get('style_brief') or '').strip()
    return brief or raw_style


def refine_style_prompt(
    raw_style: str,
    *,
    mode: GenerationMode = 'restyle',
    theme_text: str | None = None,
    target_families: list[str] | None = None,
    client=None,
    model: str = gemini_api.DEFAULT_CRITIC_MODEL,
) -> dict:
    """
    Turn a short/vague style phrase into a locked art-direction brief.

    Returns:
      {
        'input': raw user --style,
        'summary': one-line summary,
        'style_brief': full paragraph for prompts,
        'rendering', 'line_and_shape', 'color_and_lighting', 'material_finish', 'avoid',
      }
    """
    from google.genai import types

    mode_label = 'theme-swap (invent new themed objects)' if mode == 'theme_swap' else 'restyle (preserve sprite subject, change art style only)'
    theme_line = f'\n[Theme concept] {theme_text}' if theme_text else ''
    families_line = ''
    if target_families:
        families_line = '\n[Sprite families in this batch] ' + ', '.join(target_families)

    rubric = f"""You are a lead art director for a match-3 mobile game.

The user gave a SHORT or VAGUE art-style prompt. Expand it into a PRECISE, LOCKED art-direction brief so that EVERY sprite in the batch looks like it was painted by the same artist with the same rules.

[User style input] {raw_style}
[Generation mode] {mode_label}{theme_line}{families_line}

Requirements for style_brief:
- Write in English, 3-6 sentences, imperative tone ("Use…", "Keep…").
- Specify: rendering dimension (2D/3D/pixel), line weight, shading model, material finish, palette temperature, lighting, edge treatment.
- Emphasize CROSS-ASSET CONSISTENCY — all sprites must share the same rendering pipeline.
- For match-3: readable silhouettes at ~70px; no photoreal noise; no text/watermarks.
- Do NOT invent gameplay objects — only define HOW to render.

Return ONLY JSON (no markdown):
{{
  "summary": "one sentence art direction in English",
  "style_brief": "full locked art-direction paragraph for image generation prompts",
  "rendering": "e.g. soft 3D toon render, not flat vector",
  "line_and_shape": "outline weight, corner roundness, proportions",
  "color_and_lighting": "palette, saturation, highlight/shadow style",
  "material_finish": "matte/glossy/painterly texture language",
  "avoid": "what to never do in this style"
}}"""

    if client is None:
        client = gemini_api.get_client()

    def _call():
        return client.models.generate_content(
            model=model,
            contents=rubric,
            config=types.GenerateContentConfig(response_mime_type='application/json'),
        )

    resp = gemini_api._with_retries(_call, f'refine_style({model})')
    try:
        data = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(f'Style planner returned invalid JSON: {resp.text[:300]}') from e

    brief = str(data.get('style_brief', '')).strip()
    if not brief:
        raise RuntimeError('Style planner returned empty style_brief')

    return {
        'input': raw_style,
        'summary': str(data.get('summary', '')).strip(),
        'style_brief': brief,
        'rendering': str(data.get('rendering', '')).strip(),
        'line_and_shape': str(data.get('line_and_shape', '')).strip(),
        'color_and_lighting': str(data.get('color_and_lighting', '')).strip(),
        'material_finish': str(data.get('material_finish', '')).strip(),
        'avoid': str(data.get('avoid', '')).strip(),
    }


if __name__ == '__main__':
    assert resolved_style_text(None, 'pixel art') == 'pixel art'
    assert resolved_style_text({'style_brief': 'Locked toon render.'}, 'pixel') == 'Locked toon render.'
    print('style_planner self-check ok')
