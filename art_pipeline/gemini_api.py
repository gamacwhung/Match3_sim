"""
Gemini API 封裝 — 生圖(nano banana)+ vision 評審。

Key 解析重用 level_generator.ai_generator 的邏輯:
config.py / Streamlit secrets / 環境變數 GOOGLE_API_KEY,或 Vertex AI(GCP_PROJECT_ID)。
"""

from __future__ import annotations

import json
import time

# 預設模型 — 可在 CLI 用 --image-model / --critic-model 覆寫
DEFAULT_IMAGE_MODEL = 'gemini-3.1-flash-image'   # nano banana(GA、便宜),可換 gemini-3.1-flash-image
DEFAULT_CRITIC_MODEL = 'gemini-2.5-flash'

_MAX_API_RETRIES = 3
_RETRY_BACKOFF_SEC = 5.0

# 全域規則:素材不可有臉部五官(眼睛/嘴巴/表情)— 評審發現時須列為 issue 並判定 retry。
NO_FACE_REVIEW_NOTE = (
    '\n[Hard rule] The asset MUST NOT have any facial features (eyes, mouth, face, expression) '
    'or anthropomorphic traits. If you see any, list it under "issues" and set "verdict" to '
    '"retry" regardless of the other scores.')


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
        return genai.Client(vertexai=True, project=project_id, location=location)
    if api_key:
        return genai.Client(api_key=api_key)
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
            transient = any(t in msg for t in ('429', '500', '503', 'RESOURCE_EXHAUSTED',
                                               'UNAVAILABLE', 'DeadlineExceeded', 'timeout'))
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
            config=types.GenerateContentConfig(response_modalities=['TEXT', 'IMAGE']),
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
                   *, mode: str = 'restyle') -> dict:
    """
    用 Gemini vision 評審生成圖。回傳:
      {style_score, function_score, background_ok, issues, fix_instructions, verdict}

    mode:
      restyle     — 與原圖比對,function + 構圖保留
      theme_swap  — 僅依 abstract gameplay role 評審,不比對原圖
    """
    if mode == 'theme_swap':
        return _critique_theme_swap(client, model, generated_png, style_text, asset, style_image)
    return _critique_restyle(client, model, original_png, generated_png, style_text, asset, style_image)


def _critique_restyle(client, model: str, original_png: bytes, generated_png: bytes,
                      style_text: str, asset: dict,
                      style_image: bytes | None = None) -> dict:
    from google.genai import types

    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))

    if style_image:
        ref_line = ('\nThere is also a design-element reference image (Reference B): a source of '
                    'distinctive visual elements — motifs/totems, logos/emblems, ornamental '
                    'patterns, special shapes — plus its art style, color palette and mood, that '
                    'should be woven into the new version.')
        ref_score_line = ('\n  "reference_element_score": 0-10, // how well it incorporates the '
                          'design elements from the reference image (Reference B): motifs/totems, '
                          'logos, special shapes, ornamental patterns, plus its palette and style')
        verdict_rule = ('// pass only if style_score>=7 AND reference_element_score>=7 AND '
                        'function_score>=7 AND background_ok')
    else:
        ref_line = ''
        ref_score_line = ''
        verdict_rule = '// pass only if style_score>=7 AND function_score>=7 AND background_ok'

    rubric = f"""You are a game art QA reviewer. Evaluate the result of restyling a match-3 game asset.

[Asset function] {asset['name']}: {asset['function']}
[Visual constraints]
{constraints}
[Target art style (text)] {style_text}{NO_FACE_REVIEW_NOTE}

The first image is the original asset (the baseline for function and composition);
the last image is the AI-generated new version.{ref_line}
Score it against the criteria below and return ONLY JSON (no other text):
{{
  "style_score": 0-10,         // how well it matches the target art style described in text{ref_score_line}
  "function_score": 0-10,      // judging from the image alone, can the original gameplay function be recognized
  "background_ok": true/false, // background cleanliness (transparent assets: no solid color / checkerboard; background images: low contrast)
  "issues": ["issue 1", ...],
  "fix_instructions": "one concise sentence of concrete fix instructions for the image generation model, in English",
  "verdict": "pass" or "retry"  {verdict_rule}
}}"""

    contents: list = [
        '[Original asset]',
        types.Part.from_bytes(data=original_png, mime_type='image/png'),
    ]
    if style_image:
        contents += ['[Design-element reference (Reference B)]',
                     types.Part.from_bytes(data=style_image, mime_type='image/png')]
    contents += ['[AI-generated new version]',
                 types.Part.from_bytes(data=generated_png, mime_type='image/png'), rubric]

    def _call():
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type='application/json'),
        )

    resp = _with_retries(_call, f'critique({model})')
    try:
        verdict = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return {'style_score': 0, 'function_score': 0, 'background_ok': False,
                'issues': ['critic returned non-JSON output'], 'fix_instructions': '',
                'verdict': 'retry'}
    # 防衛性補欄位
    verdict.setdefault('style_score', 0)
    verdict.setdefault('function_score', 0)
    verdict.setdefault('background_ok', False)
    verdict.setdefault('issues', [])
    verdict.setdefault('fix_instructions', '')
    verdict.setdefault('verdict', 'retry')
    if style_image:
        verdict.setdefault('reference_element_score', 0)
    return verdict


def _critique_theme_swap(client, model: str, generated_png: bytes,
                         style_text: str, asset: dict,
                         style_image: bytes | None = None) -> dict:
    from google.genai import types
    from .roles import get_family_meta, role_mode_brief

    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))
    brief = role_mode_brief(asset, 'theme_swap')
    preserve = ', '.join(brief.get('preserve', []))
    family_meta = get_family_meta(asset.get('family'))
    family_line = ''
    if family_meta.get('series_note'):
        family_line = f'\n[Series consistency] {family_meta["series_note"]}'

    if style_image:
        ref_line = ('\nThere is also a theme reference image: use it as the visual theme source '
                    '(motifs, palette, mood) — the object subject is NOT constrained by any '
                    'original sprite.')
        ref_score_line = ('\n  "reference_element_score": 0-10, // how well it incorporates the '
                          'theme reference image motifs, palette and style')
        verdict_rule = ('// pass only if style_score>=7 AND reference_element_score>=7 AND '
                        'function_score>=7 AND background_ok')
    else:
        ref_line = ''
        ref_score_line = ''
        verdict_rule = '// pass only if style_score>=7 AND function_score>=7 AND background_ok'

    rubric = f"""You are a game art QA reviewer. Evaluate a NEW themed match-3 game asset created from an abstract gameplay role (theme-swap mode — there is NO original sprite to compare against).

[Asset name] {asset['name']}
[Gameplay role] {asset.get('role_label', asset.get('role_class', ''))}: {asset.get('function_theme_swap', asset['function'])}
[Creative brief] {brief.get('creative_brief', '')}
[Must preserve (gameplay readability)] {preserve}
[Visual constraints]
{constraints}
[Target art style (text)] {style_text}{family_line}{ref_line}{NO_FACE_REVIEW_NOTE}

The image is the AI-generated new version. Judge ONLY whether it fulfills the gameplay role and constraints — do NOT penalize for looking different from any legacy sprite.
Score it and return ONLY JSON (no other text):
{{
  "style_score": 0-10,         // how well it matches the target art style / theme{ref_score_line}
  "function_score": 0-10,      // from the image alone, can the gameplay function be recognized
  "background_ok": true/false,
  "issues": ["issue 1", ...],
  "fix_instructions": "one concise sentence of concrete fix instructions for the image generation model, in English",
  "verdict": "pass" or "retry"  {verdict_rule}
}}"""

    contents: list = []
    if style_image:
        contents += ['[Theme reference image]',
                     types.Part.from_bytes(data=style_image, mime_type='image/png')]
    contents += ['[AI-generated new version]',
                 types.Part.from_bytes(data=generated_png, mime_type='image/png'), rubric]

    def _call():
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type='application/json'),
        )

    resp = _with_retries(_call, f'critique_theme_swap({model})')
    try:
        verdict = json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return {'style_score': 0, 'function_score': 0, 'background_ok': False,
                'issues': ['critic returned non-JSON output'], 'fix_instructions': '',
                'verdict': 'retry'}
    verdict.setdefault('style_score', 0)
    verdict.setdefault('function_score', 0)
    verdict.setdefault('background_ok', False)
    verdict.setdefault('issues', [])
    verdict.setdefault('fix_instructions', '')
    verdict.setdefault('verdict', 'retry')
    if style_image:
        verdict.setdefault('reference_element_score', 0)
    return verdict
