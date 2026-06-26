// 攤位生成器前端 — 純靜態，無框架、無 rerun。
// 生成 = 一次非同步 fetch（Gemini 在後端跑）→ postMessage 推進遊戲 iframe。
// 遊戲是獨立 cross-origin iframe，這頁怎麼忙都不會拖累它的主迴圈（這就是脫離 Streamlit 的重點）。

const $ = (id) => document.getElementById(id);
const gameFrame = $("game");
const promptEl = $("prompt");
const genBtn = $("gen-btn");
const regenBtn = $("regen-btn");
const statusEl = $("status");

let GAME_URL = "https://gamacwhung.github.io/Match3_sim/";
let currentTheme = "";
let currentLevel = null;
let selShape = "";
let selDiff = "";

// ── 啟動 ──────────────────────────────────────────────────────────
async function boot() {
  try {
    const cfg = await fetch("/api/config").then((r) => r.json());
    if (cfg.game_url) GAME_URL = cfg.game_url;
    if (cfg.model) $("model-tag").textContent = "模型：" + cfg.model;
  } catch (e) {}
  await loadThemes();
  reloadGame();
}

async function loadThemes() {
  try {
    const themes = await fetch("/api/themes").then((r) => r.json());
    if (Array.isArray(themes) && themes.length) {
      const sel = $("theme");
      sel.innerHTML = "";
      themes.forEach((t) => {
        const o = document.createElement("option");
        o.value = t.name || "";
        o.textContent = t.label || t.name || "預設";
        sel.appendChild(o);
      });
    }
  } catch (e) {}
}

// ── 遊戲 iframe ───────────────────────────────────────────────────
function gameSrc() {
  const qs = ["booth=1"];
  if (currentTheme) qs.push("theme=" + encodeURIComponent(currentTheme));
  qs.push("v=" + Date.now()); // 繞過 index.html 快取，每次拿最新 build
  return GAME_URL + "?" + qs.join("&");
}
function reloadGame() {
  gameFrame.src = gameSrc();
  if (currentLevel) pushLevel(currentLevel);
}
function pushLevel(level) {
  const payload = { type: "load_level", level_json: JSON.stringify(level) };
  const send = () => { try { gameFrame.contentWindow.postMessage(payload, "*"); } catch (e) {} };
  // 遊戲端對「同一關卡」去重，不會重啟 → 多推幾次無害，確保載入慢時也收得到。
  [0, 600, 1200, 2000, 3000, 4200, 6000].forEach((t) => setTimeout(send, t));
}

$("theme").addEventListener("change", (e) => { currentTheme = e.target.value || ""; reloadGame(); });

// ── 範本 pill：填進輸入框 ─────────────────────────────────────────
$("presets").addEventListener("click", (e) => {
  const p = e.target.closest(".pill");
  if (!p) return;
  promptEl.value = p.dataset.prompt;
  promptEl.dispatchEvent(new Event("input"));
  promptEl.focus();
});

// ── 形狀 / 難度 pill：單選；已有關卡 → 立刻用同句重生 ─────────────
function wirePills(containerId, setter) {
  $(containerId).addEventListener("click", (e) => {
    const p = e.target.closest(".pill");
    if (!p) return;
    [...$(containerId).children].forEach((c) => c.classList.remove("active"));
    p.classList.add("active");
    setter(p);
    if (currentLevel && promptEl.value.trim()) generate(); // 在這關基礎上重生
  });
}
wirePills("shapes", (p) => (selShape = p.dataset.shape || ""));
wirePills("diffs", (p) => (selDiff = p.dataset.diff || ""));

// ── 生成 ──────────────────────────────────────────────────────────
promptEl.addEventListener("input", () => {
  const empty = promptEl.value.trim().length === 0;
  genBtn.disabled = empty;
  regenBtn.disabled = empty;
});
promptEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !genBtn.disabled) generate();
});
genBtn.addEventListener("click", generate);
regenBtn.addEventListener("click", () => { if (!regenBtn.disabled) generate(); });

async function generate() {
  const prompt = promptEl.value.trim();
  if (!prompt) return;

  setLoading(true);
  setStatus("work", '<span class="spinner"></span>AI 生成關卡中…（約 5~15 秒）');

  try {
    const resp = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, shape: selShape || null, difficulty: selDiff || null }),
    });
    const data = await resp.json();
    if (!data.ok) { setStatus("err", "❌ " + (data.error || "生成失敗，請再試一次")); return; }

    currentLevel = data.level;
    pushLevel(data.level);
    $("game-hint").style.display = "none";

    // 上次送出 + 完整 prompt
    const ls = $("last-sent");
    ls.textContent = "上次送出：" + prompt;
    ls.hidden = false;
    $("full-prompt").textContent = data.full_prompt || prompt;
    $("prompt-detail").hidden = false;

    renderStats(data);
    setStatus("ok", data.valid ? "✅ 關卡已生成，右邊開始玩吧！" : "⚠️ 生成完成（小瑕疵，仍可玩）");
  } catch (e) {
    setStatus("err", "❌ 連線後端失敗：" + e.message);
  } finally {
    setLoading(false);
  }
}

function setLoading(on) {
  const empty = promptEl.value.trim().length === 0;
  genBtn.disabled = on || empty;
  regenBtn.disabled = on || empty;
  genBtn.classList.toggle("loading", on);
  genBtn.textContent = on ? "⏳ 生成中…" : "✨ 用 AI 生成關卡";
}
function setStatus(kind, html) { statusEl.innerHTML = `<span class="${kind}">${html}</span>`; }

// ── 數據條 / 目標 / banner ───────────────────────────────────────
function renderStats(data) {
  const goals = data.goals || {};
  const goalKeys = Object.keys(goals);
  $("st-board").textContent = data.rows && data.cols ? `${data.rows}×${data.cols}` : "—";
  $("st-steps").textContent = data.max_steps || "—";
  $("st-goals").textContent = goalKeys.length || "—";
  $("st-winrate").textContent = "點我測";
  $("st-winrate").style.color = "";

  const chips = $("goals-chips");
  chips.innerHTML = "";
  goalKeys.forEach((k) => {
    const el = document.createElement("span");
    el.className = "goal-chip";
    el.innerHTML = `${k} <b>×${goals[k]}</b>`;
    chips.appendChild(el);
  });
  $("goals-line").hidden = goalKeys.length === 0;

  const b = $("banner");
  if (data.valid) {
    b.className = "banner ok"; b.textContent = "✓ 通過驗證，可以玩";
  } else {
    b.className = "banner warn";
    b.textContent = "⚠️ " + (data.errors && data.errors.length ? data.errors.slice(0, 2).join("；") : "格式有小瑕疵，仍可玩");
  }
  b.hidden = false;
}

// ── AI 勝率：點卡片才跑模擬 ──────────────────────────────────────
$("st-winrate-card").addEventListener("click", async () => {
  if (!currentLevel) return;
  const cell = $("st-winrate");
  cell.textContent = "測試中…";
  try {
    const r = await fetch("/api/simulate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level: currentLevel, n_games: 60 }),
    }).then((x) => x.json());
    if (r.ok) {
      cell.textContent = Math.round(r.win_rate * 100) + "%";
      cell.style.color = r.color;
      cell.title = `${r.emoji} ${r.badge}`;
    } else {
      cell.textContent = "失敗";
    }
  } catch (e) { cell.textContent = "失敗"; }
});

boot();
