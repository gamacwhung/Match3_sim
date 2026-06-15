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
        contents.append(f'[Reference image: {label}]')
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


def critique_image(client, model: str, original_png: bytes, generated_png: bytes,
                   style_text: str, asset: dict,
                   style_image: bytes | None = None) -> dict:
    """
    用 Gemini vision 評審生成圖。回傳:
      {style_score, function_score, background_ok, issues, fix_instructions, verdict}
    """
    from google.genai import types

    constraints = '\n'.join(f'- {c}' for c in asset.get('constraints', []))
    rubric = f"""You are a game art QA reviewer. Evaluate the result of restyling a match-3 game asset.

[Asset function] {asset['name']}: {asset['function']}
[Visual constraints]
{constraints}
[Target art style] {style_text}

The first image is the original asset (the baseline for function and composition);
the last image is the AI-generated new version.
Score it against the criteria below and return ONLY JSON (no other text):
{{
  "style_score": 0-10,         // how well it matches the target art style
  "function_score": 0-10,      // judging from the image alone, can the original gameplay function be recognized
  "background_ok": true/false, // background cleanliness (transparent assets: no solid color / checkerboard; background images: low contrast)
  "issues": ["issue 1", ...],
  "fix_instructions": "one concise sentence of concrete fix instructions for the image generation model, in English",
  "verdict": "pass" or "retry"  // pass only if style>=7 AND function>=7 AND background_ok
}}"""

    contents: list = [
        '[Original asset]',
        types.Part.from_bytes(data=original_png, mime_type='image/png'),
    ]
    if style_image:
        contents += ['[Target style reference]',
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
    return verdict
