"""
AI 關卡生成器 — 支援 Google Gemini、Anthropic Claude、OpenAI GPT

根據選擇的模型自動路由到對應的 API：
- gemini-* 模型 → Google Gen AI SDK（需要 GOOGLE_API_KEY）
- claude-* 模型 → Anthropic API（需要 ANTHROPIC_API_KEY）
- gpt-* / o1-* / o3-* 模型 → OpenAI API（需要 OPENAI_API_KEY）
"""

import sys
import os
import re
import json
import base64
import pathlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_GUIDE_PATH = pathlib.Path(__file__).parent.parent / 'docs' / 'level_design_guide.md'

DEFAULT_MODEL = 'gemini-2.5-pro'

# 模型清單：(display_name, model_id, provider)
MODEL_LIST = [
    # Google Gemini（Google Cloud Day 預設）
    ('Gemini 2.5 Pro', 'gemini-2.5-pro', 'google'),
    ('Gemini 2.5 Flash', 'gemini-2.5-flash', 'google'),
    ('Gemini 3.1 Pro Preview', 'gemini-3.1-pro-preview', 'google'),
    ('Gemini 3.5 Flash', 'gemini-3.5-flash', 'google'),
    ('Gemini 2.0 Flash', 'gemini-2.0-flash-001', 'google'),
    # OpenAI
    ('GPT-5.4 (2026-03-05)', 'gpt-5.4-2026-03-05', 'openai'),
    ('GPT-5.3 chat latest', 'gpt-5.3-chat-latest', 'openai'),
    ('GPT-4o', 'gpt-4o', 'openai'),
    ('GPT-4o mini', 'gpt-4o-mini', 'openai'),
    ('o3-mini', 'o3-mini', 'openai'),
    # Anthropic
    ('Claude Sonnet 4.6', 'claude-sonnet-4-6', 'anthropic'),
    ('Claude Opus 4.6', 'claude-opus-4-6', 'anthropic'),
    ('Claude Haiku 4.5', 'claude-haiku-4-5-20251001', 'anthropic'),
]


def get_model_provider(model: str) -> str:
    """根據 model ID 判斷 provider"""
    for _, mid, provider in MODEL_LIST:
        if mid == model:
            return provider
    # fallback: 根據前綴猜測
    if model.startswith('gemini-'):
        return 'google'
    if model.startswith('claude-'):
        return 'anthropic'
    return 'openai'


def get_available_models() -> list[str]:
    """回傳所有模型的 display_name 清單（供 UI selectbox 用）"""
    return [name for name, _, _ in MODEL_LIST]


def model_id_from_display(display_name: str) -> str:
    """從 display_name 取得 model_id"""
    for name, mid, _ in MODEL_LIST:
        if name == display_name:
            return mid
    return display_name


def _get_key(provider: str) -> str | None:
    """
    取得 API key，優先順序：
    1. UI 輸入（session_state，給別人使用時填）
    2. config.py（本地開發用）
    3. Streamlit secrets（雲端部署用）
    4. 環境變數（fallback）
    """
    if provider == 'google':
        key_name = 'GOOGLE_API_KEY'
    elif provider == 'anthropic':
        key_name = 'ANTHROPIC_API_KEY'
    elif provider == 'gcp_project':
        key_name = 'GCP_PROJECT_ID'
    elif provider == 'gcp_location':
        key_name = 'GCP_LOCATION'
    elif provider == 'gcp_credentials':
        key_name = 'GCP_CREDENTIALS_FILE'
    else:
        key_name = 'OPENAI_API_KEY'
    ss_key = f'ui_{key_name}'  # session_state 的 key

    # 1. UI 輸入
    try:
        import streamlit as st
        val = st.session_state.get(ss_key, '')
        if val and val.strip():
            return val.strip()
    except Exception:
        pass

    # 2. config.py
    try:
        import importlib
        config = importlib.import_module('config')
        val = getattr(config, key_name, '')
        if val and val.strip():
            return val.strip()
    except (ImportError, ModuleNotFoundError):
        pass

    # 3. Streamlit secrets
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key_name in st.secrets:
            return st.secrets[key_name]
    except Exception:
        pass

    # 4. 環境變數
    return os.environ.get(key_name) or None


def _load_design_guide() -> str:
    try:
        return _GUIDE_PATH.read_text(encoding='utf-8')
    except Exception:
        return '（設計指南載入失敗，請依照 Match3 關卡 JSON 格式生成關卡）'


def _build_system_prompt(params: dict) -> str:
    guide = _load_design_guide()
    difficulty = params.get('difficulty', 'medium')
    rows = params.get('rows', 10)
    cols = params.get('cols', 9)
    num_colors = params.get('num_colors', 4)
    obstacles = params.get('obstacle_types', [])
    goal_types = params.get('goal_types', [])

    obstacles_str = '、'.join(obstacles) if obstacles else '（由 AI 自行決定）'
    goals_str = '、'.join(goal_types) if goal_types else '（由 AI 自行決定）'

    return f"""你是一個專業的 Match3（三消）遊戲關卡設計師。你的任務是根據以下設計規範，生成可玩、有趣的關卡 JSON。

{guide}

---

## 當前關卡參數

- 盤面大小：{rows} 行 × {cols} 列
- 難度：{difficulty}
- 顏色數：{num_colors}
- 指定障礙物類型：{obstacles_str}
- 指定目標類型：{goals_str}

---

## 輸出規範

1. 必須輸出**一個** ```json 代碼塊，包含完整的關卡 JSON
2. JSON 必須符合設計指南中的所有規範（特別是層級分配規則）
3. 不要在 JSON 中放置元素顏色（Red/Grn/Blu 等）
4. 確保 goal 數量合理（不超過盤面最大可達成數）
5. JSON 後面可以加 2-3 句中文設計說明

輸出格式：
```json
{{...完整的關卡 JSON...}}
```
設計說明：...
"""


def _balanced_brace_spans(text: str) -> list[str]:
    """掃出所有「括號平衡」的頂層 {...} 子字串（忽略字串內的大括號）。"""
    spans, depth, start, in_str, esc = [], 0, -1, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    spans.append(text[start:i + 1])
    return spans


def extract_json_from_response(text: str) -> dict | None:
    """從 AI 回應中提取 JSON（容錯：fenced 區塊 → 平衡括號候選 → 貪婪 fallback）。"""
    # 1) ```json fenced 區塊
    for m in re.findall(r'```json\s*([\s\S]*?)```', text, re.IGNORECASE):
        try:
            return json.loads(m.strip())
        except json.JSONDecodeError:
            continue
    # 2) 任意 ``` fenced 區塊（內容像 JSON）
    for m in re.findall(r'```\s*([\s\S]*?)```', text):
        s = m.strip()
        if s.startswith('{'):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                continue
    # 3) 平衡括號候選：挑最大、可解析的（避開後面的「設計說明」等雜訊）
    for s in sorted(_balanced_brace_spans(text), key=len, reverse=True):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            continue
    # 4) 貪婪 fallback
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# Google Gemini 呼叫
# ---------------------------------------------------------------------------

def _call_gemini(model: str, system_prompt: str, messages: list, image_bytes, image_media_type, stream_callback=None) -> str:
    from google import genai
    from google.genai import types

    # 優先使用 Vertex AI（有 PROJECT_ID 時）；否則用 API Key
    project_id = _get_key('gcp_project')
    api_key = _get_key('google')

    if project_id:
        # 設定 SA credentials（如果有的話）
        cred_file = _get_key('gcp_credentials')
        if cred_file:
            cred_path = pathlib.Path(__file__).resolve().parent.parent / cred_file
            if cred_path.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)
        # Vertex AI 模式
        location = _get_key('gcp_location') or 'us-central1'
        client = genai.Client(vertexai=True, project=project_id, location=location)
    elif api_key:
        # AI Studio 模式：用 API Key
        client = genai.Client(api_key=api_key)
    else:
        raise ValueError(
            '找不到 Google AI 認證。請擇一設定：\n'
            '  A) GOOGLE_API_KEY（AI Studio）\n'
            '  B) GCP_PROJECT_ID + GCP_CREDENTIALS_FILE（Vertex AI）\n'
            '取得 API Key：https://aistudio.google.com/apikey'
        )

    # 組裝 contents：把 chat history 轉成 Gemini 格式
    contents = []
    for msg in messages:
        role = 'user' if msg['role'] == 'user' else 'model'
        content = msg['content']
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get('type') == 'text' and block.get('text'):
                        parts.append(types.Part.from_text(text=block['text']))
                    elif block.get('type') == 'image':
                        src = block.get('source', {})
                        if src.get('type') == 'base64' and src.get('data'):
                            import base64 as b64mod
                            img_data = b64mod.b64decode(src['data'])
                            if img_data:
                                parts.append(types.Part.from_bytes(
                                    data=img_data, mime_type=src['media_type']
                                ))
            # 防呆：parts 全空時跳過此訊息，避免空 part 觸發 400 INVALID_ARGUMENT
            if parts:
                contents.append(types.Content(role=role, parts=parts))
        elif content:
            # 防呆：空/None 文字訊息不送（會造成空 part）
            contents.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=content)]
            ))

    # 最後一條 user 訊息加入圖片
    if image_bytes and contents and contents[-1].role == 'user':
        contents[-1].parts.append(
            types.Part.from_bytes(data=image_bytes, mime_type=image_media_type)
        )

    # 開啟「思考」並要求把思考過程一起回傳(include_thoughts)：
    # 思考歸思考、答案(JSON)歸答案 —— 既能即時顯示 AI 在想什麼(不再是空白長停頓)、
    # 思考也能提升盤面品質，又不會把碎念混進 JSON 害解析失敗。
    # thinking_config 在舊版 SDK / 不支援的模型上會失敗 → 自動 fallback。
    def _build_config(thinking_mode: str):
        kw = dict(
            system_instruction=system_prompt,
            max_output_tokens=8192,
            temperature=0.9,
        )
        if thinking_mode == 'off':
            # 攤位求快：thinking_budget=0 直接關閉思考，生成快很多（不再有思考停頓）
            kw['thinking_config'] = types.ThinkingConfig(thinking_budget=0)
        elif thinking_mode == 'show':
            kw['thinking_config'] = types.ThinkingConfig(include_thoughts=True)
        return types.GenerateContentConfig(**kw)

    # 先試「關閉思考」(最快)；舊 SDK/模型不支援 thinking_config 就退回模型預設。
    try:
        config = _build_config('off')
    except Exception:
        config = _build_config('none')

    # 逐字串流：有 callback 時用 stream API，邊收邊回報。
    # 把「思考」與「答案」分流：思考 → callback(text, is_thought=True) 只顯示不入庫；
    # 答案 → 累積回傳(供解析 JSON)。
    if stream_callback is not None:
        answer_parts = []
        thought_parts = []
        for chunk in client.models.generate_content_stream(
            model=model, contents=contents, config=config,
        ):
            cands = getattr(chunk, 'candidates', None) or []
            if not cands:
                continue
            content = getattr(cands[0], 'content', None)
            for part in (getattr(content, 'parts', None) or []):
                txt = getattr(part, 'text', None)
                if not txt:
                    continue
                is_thought = bool(getattr(part, 'thought', False))
                if is_thought:
                    thought_parts.append(txt)
                else:
                    answer_parts.append(txt)
                try:
                    stream_callback(txt, is_thought)
                except TypeError:
                    # 舊版 callback 只吃一個參數 → 思考不傳、只傳答案
                    if not is_thought:
                        try:
                            stream_callback(txt)
                        except Exception:
                            pass
                except Exception:
                    pass
        answer_text = ''.join(answer_parts)
        # 保險：萬一模型把 JSON 寫進「思考」而答案沒有 → 連思考一起回傳供解析，
        # 才不會明明吐了 JSON 卻被判定「沒有有效 JSON」。
        if '{' not in answer_text and thought_parts:
            answer_text = ''.join(thought_parts) + '\n' + answer_text
        return answer_text

    response = client.models.generate_content(
        model=model, contents=contents, config=config,
    )
    return response.text


# ---------------------------------------------------------------------------
# Anthropic 呼叫
# ---------------------------------------------------------------------------

def _call_anthropic(model: str, system_prompt: str, messages: list, image_bytes, image_media_type) -> str:
    api_key = _get_key('anthropic')
    if not api_key:
        raise ValueError(
            '找不到 ANTHROPIC_API_KEY。\n'
            '請設定環境變數 ANTHROPIC_API_KEY，或在 .streamlit/secrets.toml 加入。'
        )
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    # 最後一條 user 訊息加入圖片
    msgs = list(messages)
    if image_bytes and msgs and msgs[-1]['role'] == 'user':
        img_b64 = base64.standard_b64encode(image_bytes).decode('utf-8')
        text_content = msgs[-1]['content']
        if isinstance(text_content, str):
            text_content = text_content
        msgs[-1] = {
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {
                    'type': 'base64', 'media_type': image_media_type, 'data': img_b64,
                }},
                {'type': 'text', 'text': text_content if isinstance(text_content, str) else str(text_content)},
            ],
        }

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=msgs,
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# OpenAI 呼叫
# ---------------------------------------------------------------------------

def _call_openai(model: str, system_prompt: str, messages: list, image_bytes, image_media_type) -> str:
    api_key = _get_key('openai')
    if not api_key:
        raise ValueError(
            '找不到 OPENAI_API_KEY。\n'
            '請設定環境變數 OPENAI_API_KEY，或在 .streamlit/secrets.toml 加入。'
        )
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    # 轉換 messages 格式（OpenAI 用 content 字串或 content list）
    openai_msgs = [{'role': 'system', 'content': system_prompt}]
    for msg in messages:
        role = msg['role']
        content = msg['content']
        # 如果 content 是 Anthropic 的 list 格式（含圖片），轉換成 OpenAI 格式
        if isinstance(content, list):
            oai_content = []
            for block in content:
                if isinstance(block, dict):
                    if block.get('type') == 'text':
                        oai_content.append({'type': 'text', 'text': block['text']})
                    elif block.get('type') == 'image':
                        src = block.get('source', {})
                        if src.get('type') == 'base64':
                            data_url = f"data:{src['media_type']};base64,{src['data']}"
                            oai_content.append({'type': 'image_url', 'image_url': {'url': data_url}})
            openai_msgs.append({'role': role, 'content': oai_content})
        else:
            openai_msgs.append({'role': role, 'content': content})

    # 最後一條 user 訊息加入圖片（如果有）
    if image_bytes and openai_msgs and openai_msgs[-1]['role'] == 'user':
        img_b64 = base64.standard_b64encode(image_bytes).decode('utf-8')
        data_url = f'data:{image_media_type};base64,{img_b64}'
        last_content = openai_msgs[-1]['content']
        if isinstance(last_content, str):
            openai_msgs[-1]['content'] = [
                {'type': 'text', 'text': last_content},
                {'type': 'image_url', 'image_url': {'url': data_url}},
            ]
        elif isinstance(last_content, list):
            last_content.append({'type': 'image_url', 'image_url': {'url': data_url}})

    # o3-mini 不支援 system role，改成第一條 user message
    if model.startswith('o3') or model.startswith('o1'):
        sys_msg = openai_msgs.pop(0)
        if openai_msgs and openai_msgs[0]['role'] == 'user':
            first_content = openai_msgs[0]['content']
            prefix = sys_msg['content'] + '\n\n---\n\n'
            if isinstance(first_content, str):
                openai_msgs[0]['content'] = prefix + first_content
            elif isinstance(first_content, list):
                openai_msgs[0]['content'] = [{'type': 'text', 'text': prefix}] + first_content
        else:
            openai_msgs.insert(0, {'role': 'user', 'content': sys_msg['content']})

    response = client.chat.completions.create(
        model=model,
        messages=openai_msgs,
        max_completion_tokens=4096,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# 統一入口
# ---------------------------------------------------------------------------

def generate_level(
    user_message: str,
    chat_history: list,
    params: dict,
    image_bytes: bytes | None = None,
    image_media_type: str = 'image/png',
    model: str = DEFAULT_MODEL,
    stream_callback=None,
) -> tuple:
    """
    呼叫 AI API 生成關卡（自動根據 model 路由到 OpenAI 或 Anthropic）。

    stream_callback：傳入時，Gemini 會逐字串流，每收到一段文字就呼叫一次
                     callback(piece)（目前只有 Gemini 路徑支援）。

    Returns:
        (assistant_text: str, level_dict: dict | None)
    """
    provider = get_model_provider(model)
    system_prompt = _build_system_prompt(params)

    # 加入使用者訊息（純文字，圖片在呼叫時注入）
    chat_history.append({'role': 'user', 'content': user_message})

    if provider == 'google':
        assistant_text = _call_gemini(model, system_prompt, chat_history, image_bytes, image_media_type, stream_callback=stream_callback)
    elif provider == 'anthropic':
        assistant_text = _call_anthropic(model, system_prompt, chat_history, image_bytes, image_media_type)
    else:
        assistant_text = _call_openai(model, system_prompt, chat_history, image_bytes, image_media_type)

    chat_history.append({'role': 'assistant', 'content': assistant_text})

    level_dict = extract_json_from_response(assistant_text)
    return assistant_text, level_dict


def build_system_prompt(params: dict) -> str:
    """公開版 system prompt，供 UI 顯示用"""
    return _build_system_prompt(params)


def build_zero_input_message(params: dict) -> str:
    difficulty = params.get('difficulty', 'medium')
    rows = params.get('rows', 10)
    cols = params.get('cols', 9)
    num_colors = params.get('num_colors', 4)
    obstacles = params.get('obstacle_types', [])
    goal_types = params.get('goal_types', [])

    parts = [f'請生成一個 {difficulty} 難度的 {rows}×{cols} 關卡，使用 {num_colors} 種顏色元素。']
    if obstacles:
        parts.append(f'包含以下障礙物：{", ".join(obstacles)}。')
    if goal_types:
        parts.append(f'目標類型：{", ".join(goal_types)}。')
    parts.append('請設計一個有趣、有挑戰性但可完成的關卡佈局。')
    return ' '.join(parts)
