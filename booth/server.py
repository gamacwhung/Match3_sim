"""
攤位關卡生成器 — FastAPI 後端（脫離 Streamlit）。

為什麼有這支：Streamlit 每次互動都整頁 rerun + 重畫，會把瀏覽器主執行緒吃光、
把同頁嵌入的 Godot 遊戲 iframe 主迴圈餓死 → 生成後遊戲凍住（standalone 不會）。
這支用「靜態前端 + 純 API」取代：
  - 前端是一個靜態頁，直接 <iframe> 嵌 Godot 遊戲（無 rerun，永遠不被拖累）
  - 生成只是一次非同步 fetch → 後端呼 Gemini → 回 JSON → 前端 postMessage 推進遊戲

跑法：
    pip install fastapi uvicorn
    set GOOGLE_API_KEY=...        # 或放 config.py / 環境變數
    python booth/server.py        # → http://localhost:8800
"""
from __future__ import annotations

import os
import sys
import json
import pathlib

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from level_generator.ai_generator import generate_level
from level_generator.validator import validate_level
from level_generator.sim_runner import run_simulation_batch

_STATIC = pathlib.Path(__file__).resolve().parent / "static"
_THEMES_JSON = _REPO / "godot_demo" / "web" / "live_sprites" / "themes.json"

# 攤位用 Flash 求速度；要更高品質改環境變數 BOOTH_MODEL=gemini-2.5-pro
BOOTH_MODEL = os.environ.get("BOOTH_MODEL", "gemini-3.5-flash")
# 遊戲網址：預設 GitHub Pages；本機測試可設 BOOTH_GODOT_URL=http://localhost:8765/
GAME_URL = os.environ.get("BOOTH_GODOT_URL", "https://gamacwhung.github.io/Match3_sim/")
MAX_ATTEMPTS = 2

# ── 攤位關卡指示（從 streamlit_app.py 原樣搬過來，維持生成品質一致）──────────────
BOOTH_LEVEL_HINT = (
    "\n\n（這是攤位快速體驗版：請設計小盤面、目標單純（1~2 種），"
    "難度要「中等、有一點挑戰」——不要太簡單到隨便點就過。"
    "步數要「抓緊、剛好夠用」：先估算最佳解所需步數，max_steps 大約只給最佳解的 1.2~1.4 倍，"
    "絕對不要給一大堆步數讓人亂點也能過。"
    "障礙物不要多到把盤面塞爆（要留得下操作空間），"
    "讓人 1~2 分鐘內玩完、需要稍微動點腦、過關有成就感的短關卡，重點是好玩、有挑戰但不卡死。）"
)
BOOTH_LEVEL_HINT_SHAPE = (
    "\n\n（這是攤位快速體驗版的「形狀關」：盤面可以大一點（把指定形狀做粗、做明顯），"
    "但目標仍要單純（1~2 種）、難度中等有點挑戰、步數抓緊（max_steps 約最佳解的 1.2~1.4 倍），"
    "形狀筆畫至少 2~3 格寬、每個障礙物旁邊都要有空地能湊出三消，務必留足夠操作空間、不要卡死。）"
)


def _shape_directive(name: str) -> str:
    return (
        f"（請把「可遊玩盤面範圍」做成「{name}」形狀：用 void 把該形狀以外挖空。"
        "形狀的每一段筆畫務必「至少 2~3 格寬」，絕對不要出現 1 格寬的細線"
        "（1 格寬玩家湊不出相鄰消除、變成又難又怪的死關）；"
        "盤面放大到約 12×12（最大就是 12×12）來容納夠粗的筆畫，形狀做大一點比較好認。"
        "內部正常放元素、只放少量障礙物，務必留足夠空地能消除。）"
    )


# 形狀 label → 指示句；非「矩形/空」的形狀會把盤面放大到 12×12（big_board）。
SHAPE_DIRECTIVES: dict[str, str] = {
    "矩形": "（請把盤面做成普通矩形，不要挖 void、不要做特殊形狀，正常放元素與少量障礙物即可。）",
    "十字": _shape_directive("十字"),
    "菱形": _shape_directive("菱形"),
    "愛心": _shape_directive("愛心"),
    "Google G": (
        "（請把「可遊玩盤面範圍」做成大寫「G」形狀：用 void 把 G 以外挖空。"
        "G 的長相＝像一個「C」（上、左、下三邊各一條粗邊框，整體右邊是開口）"
        "＋右下角有一條往內、往上的短橫筆（G 的小尾巴/橫槓）。"
        "所以「右上角必須是缺口（開口）」、右下角才有那段短橫筆，千萬不要把右邊整條封起來變成「O/方框」。"
        "G 的每一段筆畫務必「至少 2~3 格寬」，絕對不要 1 格寬的細線；"
        "盤面放大到約 12×12（最大 12×12）來容納夠粗的筆畫、G 做大一點比較好認。"
        "筆畫內部正常放元素、只放少量障礙物，務必留足夠空地能消除。）"
    ),
}
_BIG_BOARD_SHAPES = {"十字", "菱形", "愛心", "Google G"}

DIFFICULTY_DIRECTIVES: dict[str, str] = {
    "簡單": "（請把這關做成「簡單」難度：步數寬鬆、障礙少、目標單純，新手也能輕鬆過關。）",
    "普通": "（請把這關做成「普通」難度：需要稍微動點腦、有一點挑戰，但不會卡死。）",
    "困難": "（請把這關做成「困難」難度：步數抓緊、需要規劃，但仍保證有解、一定過得了。）",
}


app = FastAPI(title="Match3 Booth Generator")


class GenReq(BaseModel):
    prompt: str
    shape: str | None = None
    difficulty: str | None = None


@app.get("/api/config")
def api_config():
    return {"game_url": GAME_URL, "model": BOOTH_MODEL}


@app.get("/api/themes")
def api_themes():
    try:
        return json.loads(_THEMES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []


@app.post("/api/generate")
def api_generate(req: GenReq):
    user_msg = (req.prompt or "").strip()
    if not user_msg:
        return JSONResponse({"ok": False, "error": "請先描述你想要的關卡"}, status_code=400)

    shape = (req.shape or "").strip()
    big_board = shape in _BIG_BOARD_SHAPES
    extra = ""
    if shape in SHAPE_DIRECTIVES:
        extra += SHAPE_DIRECTIVES[shape]
    if (req.difficulty or "").strip() in DIFFICULTY_DIRECTIVES:
        extra += DIFFICULTY_DIRECTIVES[req.difficulty.strip()]

    rc = 12 if big_board else 8
    params = {
        "rows": rc, "cols": rc, "difficulty": "medium",
        "num_colors": 4, "obstacle_types": [], "goal_types": [],
    }
    hint = BOOTH_LEVEL_HINT_SHAPE if big_board else BOOTH_LEVEL_HINT

    full_prompt = user_msg + extra + hint
    feedback = ""
    level = None
    validation = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            # 攤位是單次生成，每次都用獨立空歷史（不累積對話）
            _text, level = generate_level(
                user_message=full_prompt + feedback,
                chat_history=[],
                params=params,
                model=BOOTH_MODEL,
            )
        except Exception as e:  # API/網路錯誤
            return JSONResponse({"ok": False, "error": f"生成失敗：{e}"}, status_code=500)

        if not level:
            feedback = (
                "\n\n【系統提醒】你上一次沒有輸出可解析的 JSON。請「只」輸出一個完整的 "
                "```json ... ``` 區塊；JSON 後面不要再加任何說明或文字。"
            )
            continue

        validation = validate_level(level)
        if validation.valid:
            break
        feedback = (
            "\n\n【系統提醒】你上一次產生的關卡有以下格式問題，請務必修正後重新輸出完整 JSON：\n- "
            + "\n- ".join(validation.errors[:8])
        )

    if not level:
        return JSONResponse(
            {"ok": False, "error": "連續沒生出有效關卡，請換句話再試一次"}, status_code=502
        )

    return {
        "ok": True,
        "level": level,
        "valid": bool(validation and validation.valid),
        "errors": list(validation.errors) if validation else [],
        "rows": level.get("rows"),
        "cols": level.get("cols"),
        "max_steps": level.get("max_steps"),
        "goals": level.get("goals", {}),
        "full_prompt": full_prompt,
    }


class SimReq(BaseModel):
    level: dict
    n_games: int = 60


@app.post("/api/simulate")
def api_simulate(req: SimReq):
    """AI 試玩 N 場 → 回勝率（難度指標）。前端的『AI 勝率』卡按了才跑。"""
    try:
        res = run_simulation_batch(req.level, n_games=max(10, min(req.n_games, 200)), max_workers=4)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"模擬失敗：{e}"}, status_code=500)
    wr = float(res.win_rate)
    if wr >= 0.8:
        badge, color, emoji = "輕鬆", "#34A853", "😄"
    elif wr >= 0.5:
        badge, color, emoji = "適中", "#4285F4", "🙂"
    elif wr >= 0.25:
        badge, color, emoji = "有挑戰", "#F9AB00", "😤"
    else:
        badge, color, emoji = "極難", "#EA4335", "🔥"
    return {"ok": True, "win_rate": wr, "badge": badge, "color": color, "emoji": emoji}


# 靜態前端掛在最後（API route 先比對，剩下的才交給靜態檔；html=True → / 回 index.html）
app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BOOTH_PORT", "8800"))
    print(f"[booth] 生成器後端啟動 → http://localhost:{port}  (遊戲: {GAME_URL})")
    uvicorn.run(app, host="0.0.0.0", port=port)
