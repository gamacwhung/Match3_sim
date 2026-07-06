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
import asyncio
import threading
import queue as _queue
import mimetypes
import pathlib

# .wasm 要正確 MIME 才能讓 Godot 的 WebAssembly.instantiateStreaming 吃（否則退回慢路徑）
mimetypes.add_type("application/wasm", ".wasm")

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from level_generator.ai_generator import generate_level, build_system_prompt
from level_generator.validator import validate_level, _tile_family, _count_tiles_on_board
from tile_defs import get_def, is_element
from level_generator.sim_runner import run_simulation_batch


def _merge_same_family_goals(level: dict) -> None:
    """同一家族障礙物若被拆成多個目標(Crt1+Crt2)→ 合併成一個家族目標(Crt:總和)。
    讓目標欄乾淨只一格,且遊戲端會把所有變體一起算(_normalize_goal_key)。就地修改 level。"""
    goals = level.get("goals")
    if not isinstance(goals, dict) or len(goals) < 2:
        return
    by_fam: dict = {}
    for tile, cnt in goals.items():
        fam = _tile_family(tile)
        by_fam.setdefault(fam, {"tiles": [], "total": 0})
        by_fam[fam]["tiles"].append(tile)
        by_fam[fam]["total"] += cnt
    new_goals: dict = {}
    for fam, info in by_fam.items():
        if len(info["tiles"]) > 1:
            new_goals[fam] = info["total"]            # 多變體 → 合併成家族目標
        else:
            new_goals[info["tiles"][0]] = info["total"]  # 單一 → 保留原 key
    level["goals"] = new_goals


def _snap_obstacle_goals_to_board(level: dict) -> None:
    """把障礙物目標數「校正成盤面實際可消總數」→ 目標一定跟盤面對得上,免得靠 AI 精準數對。
    勝利條件本來就是「清光盤上的 X」,所以目標 = 盤面該障礙可消數永遠正確。就地修改 level。
    不動的:元素(動態無限補充)、有 spawner 持續生成的家族、觸發型(Stamp/Postmark,無限觸發)。"""
    goals = level.get("goals")
    if not isinstance(goals, dict) or not goals:
        return
    # 各家族盤面可消總數:single(紙箱/木桶…)= 物件數;multi(冰箱…)= HP 累計;Stamp = 無限
    fam_cap: dict = {}
    for tid, n in _count_tiles_on_board(level).items():
        fam = _tile_family(tid)
        defn = get_def(tid) or {}
        hp = defn.get("health", 1)
        if hp >= 9999:
            fam_cap[fam] = float("inf")
        else:
            contrib = hp if defn.get("elimination_type", "single") == "multi" else 1
            fam_cap[fam] = fam_cap.get(fam, 0) + n * contrib
    # 有 spawner 持續生成的家族 → 不校正(無限補充,目標可大於盤面現有數)
    spawner_fams = set()
    for sp in (level.get("spawners") or []):
        if isinstance(sp, dict):
            for e in sp.get("elements", []):
                if isinstance(e, dict):
                    spawner_fams.add(_tile_family(e.get("tile_id", "")))
    new_goals: dict = {}
    for tile, cnt in goals.items():
        if is_element(tile) or _tile_family(tile) in spawner_fams:
            new_goals[tile] = cnt            # 元素 / spawner 補充 → 保留原數
            continue
        cap = fam_cap.get(_tile_family(tile), 0)
        if cap == 0 or cap == float("inf"):
            new_goals[tile] = cnt            # 盤面沒有(交給驗證擋)或觸發型 → 不動
        else:
            new_goals[tile] = int(cap)       # 校正成盤面實際可消總數
    level["goals"] = new_goals

_STATIC = pathlib.Path(__file__).resolve().parent / "static"
_THEMES_JSON = _REPO / "godot_demo" / "web" / "live_sprites" / "themes.json"

# 攤位用 Flash 求速度；要更高品質改環境變數 BOOTH_MODEL=gemini-2.5-pro
BOOTH_MODEL = os.environ.get("BOOTH_MODEL", "gemini-3.5-flash")
# 遊戲網址：預設「同源 /game/」—— 後端自己 serve 遊戲，iframe 就同源、不會被瀏覽器跨域節流凍住。
# 要改回 GitHub Pages 或本機別 port：設 BOOTH_GODOT_URL=https://...
GAME_URL = os.environ.get("BOOTH_GODOT_URL", "/game/")
_GODOT_WEB = _REPO / "godot_demo" / "web"
MAX_ATTEMPTS = 3  # 驗證失敗會帶著錯誤重生,多給幾次讓「目標數/頂部通道」這類問題自動修掉

# ── 攤位關卡指示（從 streamlit_app.py 原樣搬過來，維持生成品質一致）──────────────
BOOTH_LEVEL_HINT = (
    "\n\n（這是攤位快速體驗版：請設計小盤面、目標單純（1~2 種），"
    "難度要「中等、有一點挑戰」——不要太簡單到隨便點就過。"
    "步數要「抓緊、剛好夠用」：先估算最佳解所需步數，max_steps 大約只給最佳解的 1.2~1.4 倍，"
    "絕對不要給一大堆步數讓人亂點也能過。"
    "障礙物不要多到把盤面塞爆（要留得下操作空間），"
    "讓人 1~2 分鐘內玩完、需要稍微動點腦、過關有成就感的短關卡，重點是好玩、有挑戰但不卡死。"
    "\n⚠️ 目標種類：同一種障礙物只用『一個』目標 —— 不要同時要求 Crt1 又 Crt2（紙箱就只挑一種 HP，例如只用 Crt2）；"
    "若要兩個目標，請用『不同家族』的障礙物（例如 Crt + Barrel），這樣目標欄才乾淨、不會出現重複格子。"
    "\n⚠️ 目標數量鐵則：紙箱(Crt)/木桶(Barrel)/水漥(Puddle)/三角錐這類障礙「打爆一個算一個」，"
    "請『先決定盤面要放幾個，再把目標設成等於那個數量』，讓玩家清完所有障礙物剛好達標、乾淨過關。"
    "絕對不要『目標比盤面多』（一定過不了），也不要『盤面放一堆卻只要求清一部分』"
    "（例：放 25 個卻只要清 15 個 → 贏了還剩一堆障礙物、玩家覺得很怪）。"
    "唯一例外是有 spawner 會持續生成的物件（如障礙雨的木桶）才可設比盤面初始多。"
    "\n⚠️ 頂部留通道：障礙物千萬不要把盤面「頂部（最上面幾排）」整片塞滿，"
    "大部分欄的最上面要留開放格，可玩的開放區域要從頂部往下連通，"
    "讓元素能一直從上面掉下來補充；否則清完現有元素就沒有新元素可用、變成卡死的死關。）"
)
BOOTH_LEVEL_HINT_SHAPE = (
    "\n\n（這是攤位快速體驗版的「形狀關」：盤面可以大一點（把指定形狀做粗、做明顯），"
    "但目標仍要單純（1~2 種）、難度中等有點挑戰、步數抓緊（max_steps 約最佳解的 1.2~1.4 倍），"
    "形狀筆畫至少 2~3 格寬、每個障礙物旁邊都要有空地能湊出三消，務必留足夠操作空間、不要卡死。"
    "\n⚠️ 目標數量鐵則：紙箱/木桶/水漥這類障礙『打爆一個算一個』，目標數量要『等於盤面實際放的該物件數量』"
    "（清完剛好過關；除非有 spawner 持續生成）。不要『目標比盤面多』(過不了)、也不要『放一堆只清一部分』(贏了還剩很多很怪)。"
    "\n⚠️ 頂部留通道：形狀的「最上面那幾排」不要整片塞滿障礙物，要留開放格讓元素能從上面掉下來補充，"
    "否則清完就沒新元素、變死關（例如 G 形狀的上橫不要全部塞紙箱）。）"
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
        "（請把「可遊玩盤面範圍」做成大寫「G」形狀，其餘用 void 挖空。盤面 10×10～12×12 都可以，"
        "大小、粗細、比例、開口大小、鉤子長短你都可以自己變化，讓每次生成的 G 長得不太一樣（要有變化、不要每次一模一樣），"
        "但務必保留下面三個『讓它是 G 而不是 C 或 O』的必備特徵，缺一不可：\n"
        "① 外圈像 C：上邊、左邊、下邊是連續的粗筆畫（每段至少 2～3 格寬）。\n"
        "② 右上角必須是明顯開口：右上那一段一定要挖空(void)，千萬不要把右邊整條封起來變成 O／方框。\n"
        "③ 中間偏右有一條『往盤面內部伸出的短橫槓』(G 的關鍵鉤子)：從右側中段往內畫一小段水平筆畫、下面再接一小段右邊直筆。"
        "這條橫槓就是 G 跟 C 的唯一差別，一定要畫出來、而且要看得出來。\n"
        "下面只是『幫助理解特徵』的示意（# = 可玩格、. = void），請「不要照抄」，自己變化出不同的 G：\n"
        "  .#####.\n"
        "  ######\n"
        "  ##....\n"
        "  ##.###   ← 右上開口 + 中段往內的短橫槓\n"
        "  ##...#\n"
        "  ######\n"
        "  .#####\n"
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


@app.middleware("http")
async def _cache_live_sprites(request, call_next):
    """具名主題貼圖/manifest 網址已穩定(art_theme 對具名主題不再帶 ?v)→ 給長快取。
    攤位早上把各主題載過一次後,之後同台瀏覽器 F5 直接吃快取、不再逐檔重新驗證。"""
    resp = await call_next(request)
    p = request.url.path
    if "/live_sprites/" in p and (p.endswith(".png") or p.endswith(".json")):
        resp.headers["Cache-Control"] = "public, max-age=86400"  # 1 天;要更新主題就 hard-refresh
    return resp


class GenReq(BaseModel):
    prompt: str
    shape: str | None = None
    difficulty: str | None = None


@app.get("/api/config")
def api_config():
    return {"game_url": GAME_URL, "model": BOOTH_MODEL}


# 暫時隱藏的主題:pixar_cartoon 美術成品跟糖果風幾乎一樣(同事確認),先不給訪客選。
# 不動 themes.json(同事美術資產),只在 API 層過濾。
_HIDDEN_THEMES = {"pixar_cartoon"}


@app.get("/api/themes")
def api_themes():
    try:
        themes = json.loads(_THEMES_JSON.read_text(encoding="utf-8"))
        return [t for t in themes if t.get("name") not in _HIDDEN_THEMES]
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

        # 先自動修正可修的(合併同家族目標、目標數校正成盤面數)→ 只有結構性錯誤才觸發重生
        _merge_same_family_goals(level)
        _snap_obstacle_goals_to_board(level)
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

    validation = validate_level(level)

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
        "system_prompt": build_system_prompt(params),
    }


def _build_inputs(req: "GenReq"):
    """從請求組出 (full_prompt, params)。給 /generate 與 /generate_stream 共用。"""
    user_msg = (req.prompt or "").strip()
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
    return user_msg + extra + hint, params


@app.post("/api/generate_stream")
async def api_generate_stream(req: GenReq):
    """串流版生成:邊生成邊把 AI 的『思考』+『JSON』推給前端(SSE),做即時打字效果。"""
    if not (req.prompt or "").strip():
        return JSONResponse({"ok": False, "error": "請先描述你想要的關卡"}, status_code=400)
    full_prompt, params = _build_inputs(req)

    q: _queue.Queue = _queue.Queue()

    def worker():
        feedback = ""
        level = None
        validation = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            q.put({"type": "phase", "data": "AI 生成關卡中…" if attempt == 1 else f"自動修正、重新生成（第 {attempt} 次）…"})

            def cb(piece, is_thought=False):
                q.put({"type": "thought" if is_thought else "text", "data": piece})

            try:
                _text, level = generate_level(
                    user_message=full_prompt + feedback, chat_history=[],
                    params=params, model=BOOTH_MODEL, stream_callback=cb,
                    thinking="off",  # 關閉思考(較快);串流仍會即時顯示 JSON 產出打字效果
                )
            except Exception as e:
                q.put({"type": "error", "error": f"生成失敗：{e}"})
                return
            if not level:
                feedback = "\n\n【系統提醒】請「只」輸出一個完整的 ```json ... ``` 區塊。"
                continue
            # 先自動修正可修的(合併同家族目標、目標數校正成盤面數)→ 只有結構性錯誤才觸發重生
            _merge_same_family_goals(level)
            _snap_obstacle_goals_to_board(level)
            validation = validate_level(level)
            if validation.valid:
                break
            feedback = "\n\n【系統提醒】上次格式問題，請修正後重新輸出完整 JSON：\n- " + "\n- ".join(validation.errors[:8])

        if not level:
            q.put({"type": "error", "error": "連續沒生出有效關卡，請換句話再試一次"})
            return
        validation = validate_level(level)
        q.put({
            "type": "done", "level": level,
            "valid": bool(validation and validation.valid),
            "errors": list(validation.errors) if validation else [],
            "rows": level.get("rows"), "cols": level.get("cols"),
            "max_steps": level.get("max_steps"), "goals": level.get("goals", {}),
            "full_prompt": full_prompt, "system_prompt": build_system_prompt(params),
        })

    threading.Thread(target=worker, daemon=True).start()

    async def event_gen():
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, q.get)
            yield "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
            if item.get("type") in ("done", "error"):
                break

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


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
        badge, color, icon = "輕鬆", "#34A853", "smile"
    elif wr >= 0.5:
        badge, color, icon = "適中", "#4285F4", "meh"
    elif wr >= 0.25:
        badge, color, icon = "有挑戰", "#F9AB00", "angry"
    else:
        badge, color, icon = "極難", "#EA4335", "flame"
    return {
        "ok": True, "win_rate": wr, "badge": badge, "color": color, "icon": icon,
        "n_games": res.n_games, "wins": res.wins, "losses": res.losses,
        "avg_steps": round(res.avg_steps_won or res.avg_steps, 1),
        "min_steps": res.min_steps, "max_steps_seen": res.max_steps_seen,
        # 步數分布(只算勝場):{步數: 場數} → 前端畫長條圖
        "step_histogram": {str(k): v for k, v in sorted(res.step_histogram.items())},
    }


# Godot 遊戲：同源 serve（/game/）→ iframe 同源、不被跨域節流凍住（這就是脫離 iframe 卡頓的關鍵）
if _GODOT_WEB.exists():
    app.mount("/game", StaticFiles(directory=str(_GODOT_WEB), html=True), name="game")

# 靜態前端掛在最後（API route 先比對，剩下的才交給靜態檔；html=True → / 回 index.html）
app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BOOTH_PORT", "8800"))
    print(f"[booth] 生成器後端啟動 → http://localhost:{port}  (遊戲: {GAME_URL})")
    uvicorn.run(app, host="0.0.0.0", port=port)
