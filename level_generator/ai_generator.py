"""
AI 關卡生成器 — 支援 Anthropic Claude 和 OpenAI GPT

根據選擇的模型自動路由到對應的 API：
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

_GUIDE_PATH = pathlib.Path(__file__).parent.parent / 'level_design_guide.md'

DEFAULT_MODEL = 'gpt-5.4-2026-03-05'

# 模型清單：(display_name, model_id, provider)
MODEL_LIST = [
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
    key_name = 'ANTHROPIC_API_KEY' if provider == 'anthropic' else 'OPENAI_API_KEY'
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


def extract_json_from_response(text: str) -> dict | None:
    """從 AI 回應中提取 JSON"""
    pattern = r'```json\s*([\s\S]*?)```'
    for m in re.findall(pattern, text, re.IGNORECASE):
        try:
            return json.loads(m.strip())
        except json.JSONDecodeError:
            continue
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


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
) -> tuple:
    """
    呼叫 AI API 生成關卡（自動根據 model 路由到 OpenAI 或 Anthropic）。

    Returns:
        (assistant_text: str, level_dict: dict | None)
    """
    provider = get_model_provider(model)
    system_prompt = _build_system_prompt(params)

    # 加入使用者訊息（純文字，圖片在呼叫時注入）
    chat_history.append({'role': 'user', 'content': user_message})

    if provider == 'anthropic':
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
