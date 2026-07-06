"""
Gemini API 封裝 — 生圖(nano banana)+ vision 評審。

Key 解析重用 level_generator.ai_generator 的邏輯:
config.py / Streamlit secrets / 環境變數 GOOGLE_API_KEY,或 Vertex AI(GCP_PROJECT_ID)。
"""

from __future__ import annotations

import json
import time

# 預設模型 — 可在 CLI 用 --image-model / --critic-model 覆寫
DEFAULT_IMAGE_MODEL = 'gemini-3.1-flash-image'   # nano banana(GA);高品質可換 gemini-3-pro-image。無 3.5 image 版
DEFAULT_CRITIC_MODEL = 'gemini-3.5-flash'

_MAX_API_RETRIES = 3
_RETRY_BACKOFF_SEC = 5.0
# ponytail: ms timeouts on HttpOptions; image gen needs headroom vs text/vision critic
_API_TIMEOUT_MS = 120_000
_IMAGE_TIMEOUT_MS = 180_000

# Critic pass thresholds (also referenced by pipeline + visual_guidance)
PASS_STYLE = 8
PASS_FUNCTION = 8
PASS_ELEMENT = 8
PASS_COHESION = 8
PASS_REASONABLENESS = 8
PASS_PROGRESSION = 7

PROGRESSION_RUBRIC = (
    '\n  "progression_score": 0-10, // stage progression readability: this asset is one HP '
    'stage of a multi-stage object and an image of the PREVIOUS (less-damaged) stage is '
    'attached. Score HIGH only if (a) it is clearly the SAME base object/material/palette as '
    'the previous stage AND (b) it shows clearly MORE damage/depletion than it, in a discrete '
    'step a player notices instantly at ~70px. Score LOW if it looks nearly identical to the '
    'previous stage, or if it drifted into a different object/style'
)

REASONABLENESS_RUBRIC = (
    '\n  "reasonableness_score": 0-10, // overall visual plausibility: natural proportions '
    'and silhouette for the intended object, believable design with no bizarre warping '
    '(e.g. extremely elongated/narrow, lopsided or melted shapes), reads as one coherent '
    'game sprite at ~70px'
)

CUTOUT_RUBRIC = (
    '\n  "cutout_ok": true/false,     // BACKGROUND-REMOVAL integrity. This asset is shown '
    'composited on a magenta/white CHECKERBOARD that reveals every transparent pixel. Set '
    'FALSE if the checkerboard shows THROUGH the object anywhere — transparent holes/gaps '
    'punched INTO the subject, missing chunks bitten out of it, ragged/eaten/incomplete '
    'edges, or leftover colored fringe/halo. The checkerboard must appear ONLY around the '
    'object\'s outer silhouette, NEVER inside the solid object. Set TRUE only for a clean, '
    'complete, hole-free cutout'
)


def critic_pass_rules(*, style_image: bool, cohesion_rules: str,
                       transparent: bool = True, has_prev_stage: bool = False) -> str:
    """Verdict comment line for critic JSON rubric."""
    parts = [
        f'style_score>={PASS_STYLE}',
        f'function_score>={PASS_FUNCTION}',
        f'reasonableness_score>={PASS_REASONABLENESS}',
        'background_ok',
    ]
    if style_image:
        parts.insert(2, f'reference_element_score>={PASS_ELEMENT}')
    if transparent:
        parts.append('cutout_ok')
    if has_prev_stage:
        parts.append(f'progression_score>={PASS_PROGRESSION}')
    return f'{cohesion_rules}{" AND ".join(parts)}'


def _http_options(timeout_ms: int = _API_TIMEOUT_MS):
    from google.genai import types
    return types.HttpOptions(timeout=timeout_ms)

# 全域規則:素材不可有臉部五官(眼睛/嘴巴/表情)— 評審發現時須列為 issue 並判定 retry。
NO_FACE_REVIEW_NOTE = (
    '\n[Hard rule] The asset MUST NOT have any facial features (eyes, mouth, face, expression) '
    'or anthropomorphic traits. If you see any, list it under "issues" and set "verdict" to '
    '"retry" regardless of the other scores.')

NO_OUTLINE_REVIEW_NOTE = (
    '\n[Hard rule] The asset MUST NOT have any outline, stroke, ink border, or contour line '
    '(black, white, or colored). If you see any, list it under "issues" and set "verdict" to '
    '"retry" regardless of the other scores.')

FILL_FRAME_REVIEW_NOTE = (
    '\n[Hard rule] The subject must FILL most of the canvas (large, centered, only a thin '
    'margin) and must NOT be a thin, spindly, sliver-like or overly elongated shape. If it '
    'leaves large empty areas or looks thin/elongated, list it under "issues", lower '
    'reasonableness_score, and set "verdict" to "retry".')


def get_client():
    """建立 google-genai client(Vertex AI 優先,否則 API Key)。"""
    from google import genai
    from level_generator.ai_generator import _get_key

    project_id = _get_key('gcp_project')
    api_key = _get_key('google')

    if project_id:
        import os
        cred_file = _get_key('gcp_credentials')
        if cred_file:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = cred_file
        location = _get_key('gcp_location') or 'us-central1'
        return genai.Client(
            vertexai=True, project=project_id, location=location,
            http_options=_http_options(),
        )
    if api_key:
        return genai.Client(api_key=api_key, http_options=_http_options())
    raise ValueError(
        '找不到 Google API 設定。請設定其中一種:\n'
        '  A) GOOGLE_API_KEY(AI Studio,https://aistudio.google.com/apikey)\n'
        '  B) GCP_PROJECT_ID + GCP_CREDENTIALS_FILE(Vertex AI)\n'
        '可放在 config.py、.streamlit/secrets.toml 或環境變數。'
    )


def _with_retries(fn, what: str):
    last_err = None
    for attempt in range(1, _MAX_API_RETRIES + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — API 層各種 transient error 統一重試
            last_err = e
            msg = str(e)
            transient = (
                isinstance(e, TimeoutError)
                or any(t in msg for t in ('429', '500', '503', 'RESOURCE_EXHAUSTED',
                                          'UNAVAILABLE', 'DeadlineExceeded', 'timeout',
                                          'Timeout', 'timed out'))
            )
            if attempt == _MAX_API_RETRIES or not transient:
                raise
            wait = _RETRY_BACKOFF_SEC * attempt
            print(f'  [api] {what} 失敗(第 {attempt} 次,{type(e).__name__}),{wait:.0f}s 後重試…')
            time.sleep(wait)
    raise last_err


def generate_image(client, model: str, prompt: str,
                   ref_images: list[tuple[bytes, str]] | None = None) -> bytes:
    """
    呼叫 Gemini 圖像生成。ref_images: [(png_bytes, 用途說明), ...]
    回傳生成圖的 bytes。沒生出圖會 raise RuntimeError。
    """
    from google.genai import types

    contents: list = []
    for img_bytes, label in (ref_images or []):
        contents.append(f'[{label}]')
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type='image/png'))
    contents.append(prompt)

    def _call():
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'],
                http_options=_http_options(_IMAGE_TIMEOUT_MS),
            ),
        )

    resp = _with_retries(_call, f'generate_image({model})')

    for cand in (resp.candidates or []):
        for part in (cand.content.parts or []):
            inline = getattr(part, 'inline_data', None)
            if inline and inline.data:
                return inline.data
    text = getattr(resp, 'text', '') or ''
    raise RuntimeError(f'模型沒有回傳圖像。文字回應: {text[:300]}')


def critique_image(client, model: str, original_png: bytes | None, generated_png: bytes,
                   style_text: str, asset: dict,
                   style_image: bytes | None = None,
                   *, mode: str = 'restyle',
                   family_anchor: bytes | None = None,
                   family_style_plan: dict | None = None,
                   prev_stage_image: bytes | None = None) -> dict:
    """
    用 Gemini vision 評審生成圖。回傳:
      {style_score, function_score, reasonableness_score, background_ok, cohesion_score?,
       progression_score?, issues, fix_instructions, verdict}

    mode:
      restyle     — 與原圖比對,function + 構圖保留
      theme_swap  — 僅依 abstract gameplay role 評審,不比對原圖
    """
    kwargs = dict(
        family_anchor=family_anchor, family_style_plan=family_style_plan,
        prev_stage_image=prev_stage_image)
    if mode == 'theme_swap':
        return _critique_theme_swap(
            client, model, generated_png, style_text, asset, style_image, **kwargs)
    return _critique_restyle(
        client, model, original_png, generated_png, style_text, asset, style_image, **kwargs)


def _normalize_verdict(verdict: dict, *, style_image: bool | None,
                       has_family_anchor: bool, has_prev_stage: bool = False) -> dict:
    verdict.setdefault('style_score', 0)
    verdict.setdefault('function_score', 0)
    verdict.setdefault('reasonableness_score', 0)
    verdict.setdefault('background_ok', False)
    verdict.setdefault('cutout_ok', False)
    verdict.setdefault('issues', [])
    verdict.setdefault('fix_instructions', '')
    verdict.setdefault('verdict', 'retry')
    if style_image:
        verdict.setdefault('reference_element_score', 0)
    if has_family_anchor:
        verdict.setdefault('cohesion_score', 0)
    if has_prev_stage:
        verdict.setdefault('progression_score', 0)
    return verdict


def _build_critique_visual_context(asset: dict, family_anchor: bytes | None) -> str:
    from .visual_guidance import format_critic_visual_block

    return format_critic_visual_block(
        asset, has_family_anchor=family_anchor is not None,
    )


def _critique_restyle(client, model: str, original_png: bytes, generated_png: bytes,
                      style_text: str, asset: dict,
                      style_image: bytes | None = None,
                      *, family_anchor: bytes | None = None,
                      family_style_plan: dict | None = None,
                      prev_stage_image: bytes | None = None) -> dict:
    from google.genai import types
    from .postprocess import preview_on_checkerboard
    from .visual_guidance import cohesion_critic_rubric, cohesion_verdict_rules

    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))
    visual_block = _build_critique_visual_context(asset, family_anchor)
    has_anchor = family_anchor is not None
    has_prev = prev_stage_image is not None
    transparent = asset.get('transparent', True)
    cohesion_extra = cohesion_critic_rubric(has_family_anchor=has_anchor)
    cohesion_rules = cohesion_verdict_rules(has_family_anchor=has_anchor)
    progression_extra = PROGRESSION_RUBRIC if has_prev else ''

    if style_image:
        ref_line = ('\nThere is also a design-element reference image (Reference B): a source of '
                    'distinctive visual elements — motifs/totems, logos/emblems, ornamental '
                    'patterns, special shapes — plus its art style, color palette and mood, that '
                    'should be woven into the new version.')
        ref_score_line = ('\n  "reference_element_score": 0-10, // how well it incorporates the '
                          'design elements from the reference image (Reference B): motifs/totems, '
                          'logos, special shapes, ornamental patterns, plus its palette and style')
    else:
        ref_line = ''
        ref_score_line = ''

    anchor_line = ''
    if has_anchor:
        anchor_line = ('\nThere is also a family cohesion anchor image: the new version should '
                       'match its rendering style and material, not necessarily its silhouette.')
    prev_line = ''
    if has_prev:
        prev_line = ('\nThere is also a PREVIOUS-STAGE image (one HP level higher / less damaged): '
                     'the new version must be the SAME object shown with clearly MORE damage.')

    verdict_rule = f'// pass only if {critic_pass_rules(style_image=bool(style_image), cohesion_rules=cohesion_rules, transparent=transparent, has_prev_stage=has_prev)}'
    cutout_rubric = CUTOUT_RUBRIC if transparent else ''
    gen_label = ('[AI-generated new version — shown composited on a magenta/white checkerboard '
                 'to reveal transparency]' if transparent else '[AI-generated new version]')
    critic_png = preview_on_checkerboard(generated_png) if transparent else generated_png

    rubric = f"""You are a game art QA reviewer. Evaluate the result of restyling a match-3 game asset.

[Asset function] {asset['name']}: {asset['function']}
[Visual constraints]
{constraints}
[Target art style (text)] {style_text}{visual_block}{NO_FACE_REVIEW_NOTE}{NO_OUTLINE_REVIEW_NOTE}{FILL_FRAME_REVIEW_NOTE}

The first image is the original asset (the baseline for function and composition);
the last image is the AI-generated new version.{ref_line}{anchor_line}{prev_line}
Score it against the criteria below and return ONLY JSON (no other text):
{{
  "style_score": 0-10,         // how well it matches the target art style described in text{ref_score_line}{cohesion_extra}{progression_extra}
  "function_score": 0-10,      // judging from the image alone, can the original gameplay function be recognized{REASONABLENESS_RUBRIC}
  "background_ok": true/false, // background cleanliness (transparent assets: no solid color; background images: low contrast){cutout_rubric}
  "issues": ["issue 1", ...],
  "fix_instructions": "one concise sentence of concrete fix instructions for the image generation model, in English",
  "verdict": "pass" or "retry"  {verdict_rule}
}}"""

    contents: list = [
        '[Original asset]',
        types.Part.from_bytes(data=original_png, mime_type='image/png'),
    ]
    if family_anchor:
        contents += ['[Family cohesion anchor]',
                     types.Part.from_bytes(data=family_anchor, mime_type='image/png')]
    if prev_stage_image:
        contents += ['[Previous stage (less damaged)]',
                     types.Part.from_bytes(data=prev_stage_image, mime_type='image/png')]
    if style_image:
        contents += ['[Design-element reference (Reference B)]',
                     types.Part.from_bytes(data=style_image, mime_type='image/png')]
    contents += [gen_label,
                 types.Part.from_bytes(data=critic_png, mime_type='image/png'), rubric]

    def _call():
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                http_options=_http_options(),
            ),
        )

    resp = _with_retries(_call, f'critique({model})')
    try:
        verdict = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return _normalize_verdict(
            {'style_score': 0, 'function_score': 0, 'reasonableness_score': 0,
             'background_ok': False,
             'issues': ['critic returned non-JSON output'], 'fix_instructions': '',
             'verdict': 'retry'},
            style_image=style_image, has_family_anchor=has_anchor, has_prev_stage=has_prev)
    return _normalize_verdict(
        verdict, style_image=style_image, has_family_anchor=has_anchor, has_prev_stage=has_prev)


def _critique_theme_swap(client, model: str, generated_png: bytes,
                         style_text: str, asset: dict,
                         style_image: bytes | None = None,
                         *, family_anchor: bytes | None = None,
                         family_style_plan: dict | None = None,
                         prev_stage_image: bytes | None = None) -> dict:
    from google.genai import types
    from .postprocess import preview_on_checkerboard
    from .roles import role_mode_brief
    from .visual_guidance import cohesion_critic_rubric, cohesion_verdict_rules

    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))
    brief = role_mode_brief(asset, 'theme_swap')
    preserve = ', '.join(brief.get('preserve', []))
    visual_block = _build_critique_visual_context(asset, family_anchor)
    has_anchor = family_anchor is not None
    has_prev = prev_stage_image is not None
    transparent = asset.get('transparent', True)
    cohesion_extra = cohesion_critic_rubric(has_family_anchor=has_anchor)
    cohesion_rules = cohesion_verdict_rules(has_family_anchor=has_anchor)
    progression_extra = PROGRESSION_RUBRIC if has_prev else ''

    if style_image:
        ref_line = ('\nThere is also a theme reference image: use it as the visual theme source '
                    '(motifs, palette, mood) — the object subject is NOT constrained by any '
                    'original sprite.')
        ref_score_line = ('\n  "reference_element_score": 0-10, // how well it incorporates the '
                          'theme reference image motifs, palette and style')
    else:
        ref_line = ''
        ref_score_line = ''

    anchor_line = ''
    if has_anchor:
        anchor_line = ('\nThere is also a family cohesion anchor image for this family: match '
                       'its rendering style and material, not necessarily its silhouette.')
    prev_line = ''
    if has_prev:
        prev_line = ('\nThere is also a PREVIOUS-STAGE image (one HP level higher / less damaged): '
                     'the new version must be the SAME object shown with clearly MORE damage.')

    verdict_rule = f'// pass only if {critic_pass_rules(style_image=bool(style_image), cohesion_rules=cohesion_rules, transparent=transparent, has_prev_stage=has_prev)}'
    cutout_rubric = CUTOUT_RUBRIC if transparent else ''
    gen_label = ('[AI-generated new version — shown composited on a magenta/white checkerboard '
                 'to reveal transparency]' if transparent else '[AI-generated new version]')
    critic_png = preview_on_checkerboard(generated_png) if transparent else generated_png

    rubric = f"""You are a game art QA reviewer. Evaluate a NEW themed match-3 game asset created from an abstract gameplay role (theme-swap mode — there is NO original sprite to compare against).

[Asset name] {asset['name']}
[Gameplay role] {asset.get('role_label', asset.get('role_class', ''))}: {asset.get('function_theme_swap', asset['function'])}
[Creative brief] {brief.get('creative_brief', '')}
[Must preserve (gameplay readability)] {preserve}
[Visual constraints]
{constraints}
[Target art style (text)] {style_text}{visual_block}{ref_line}{anchor_line}{prev_line}{NO_FACE_REVIEW_NOTE}{NO_OUTLINE_REVIEW_NOTE}{FILL_FRAME_REVIEW_NOTE}

The last image is the AI-generated new version. Judge ONLY whether it fulfills the gameplay role and constraints — do NOT penalize for looking different from any legacy sprite.
Score it and return ONLY JSON (no other text):
{{
  "style_score": 0-10,         // how well it matches the target art style / theme{ref_score_line}{cohesion_extra}{progression_extra}
  "function_score": 0-10,      // from the image alone, can the gameplay function be recognized{REASONABLENESS_RUBRIC}
  "background_ok": true/false,{cutout_rubric}
  "issues": ["issue 1", ...],
  "fix_instructions": "one concise sentence of concrete fix instructions for the image generation model, in English",
  "verdict": "pass" or "retry"  {verdict_rule}
}}"""

    contents: list = []
    if family_anchor:
        contents += ['[Family cohesion anchor]',
                     types.Part.from_bytes(data=family_anchor, mime_type='image/png')]
    if prev_stage_image:
        contents += ['[Previous stage (less damaged)]',
                     types.Part.from_bytes(data=prev_stage_image, mime_type='image/png')]
    if style_image:
        contents += ['[Theme reference image]',
                     types.Part.from_bytes(data=style_image, mime_type='image/png')]
    contents += [gen_label,
                 types.Part.from_bytes(data=critic_png, mime_type='image/png'), rubric]

    def _call():
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                http_options=_http_options(),
            ),
        )

    resp = _with_retries(_call, f'critique_theme_swap({model})')
    try:
        verdict = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return _normalize_verdict(
            {'style_score': 0, 'function_score': 0, 'reasonableness_score': 0,
             'background_ok': False,
             'issues': ['critic returned non-JSON output'], 'fix_instructions': '',
             'verdict': 'retry'},
            style_image=style_image, has_family_anchor=has_anchor, has_prev_stage=has_prev)
    return _normalize_verdict(
        verdict, style_image=style_image, has_family_anchor=has_anchor, has_prev_stage=has_prev)


if __name__ == '__main__':
    assert _http_options().timeout == _API_TIMEOUT_MS
    assert _http_options(_IMAGE_TIMEOUT_MS).timeout == _IMAGE_TIMEOUT_MS
    assert 'reasonableness_score>=' in critic_pass_rules(style_image=False, cohesion_rules='')
    assert 'cutout_ok' in critic_pass_rules(style_image=False, cohesion_rules='', transparent=True)
    assert 'cutout_ok' not in critic_pass_rules(style_image=False, cohesion_rules='', transparent=False)
    assert 'progression_score>=' in critic_pass_rules(
        style_image=False, cohesion_rules='', has_prev_stage=True)
    assert 'progression_score>=' not in critic_pass_rules(style_image=False, cohesion_rules='')
    print('gemini_api timeout ok')
