// 攤位生成器前端 — 純靜態，單頁觸控友善。
// 遊戲嵌在頁面 iframe，但關卡用「網址 level_lz」帶進去（不是 postMessage）—— 經測試
// postMessage 推關會卡，網址帶關不會卡。所以每次生成 = reload iframe 到帶新關卡的網址。

const $ = (id) => document.getElementById(id);
const gameFrame = $("game");
const promptEl = $("prompt");
const genBtn = $("gen-btn");
const clearBtn = $("clear-btn");
const statusEl = $("status");

let GAME_URL = "/game/";
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
  reloadGame(); // 一進頁面就載遊戲（待機畫面）
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

// ── 遊戲 iframe（關卡編進網址 level_lz，開機直接載）──────────────────
function gameSrc(level) {
  const qs = ["booth=1", "v=" + Date.now()];
  if (currentTheme) qs.push("theme=" + encodeURIComponent(currentTheme));
  if (level) qs.push("level_lz=" + btoa(encodeURIComponent(JSON.stringify(level))));
  return GAME_URL + "?" + qs.join("&");
}
function reloadGame() {
  gameFrame.src = gameSrc(currentLevel);
}

$("theme").addEventListener("change", (e) => {
  currentTheme = e.target.value || "";
  reloadGame();
});

// 全螢幕遊玩（怕觀眾覺得畫面太小）— 整個遊戲框進全螢幕，退出鈕才疊得上去
$("fs-btn").addEventListener("click", () => {
  const el = $("game-wrap");
  if (el.requestFullscreen) el.requestFullscreen();
  else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
});
$("fs-exit").addEventListener("click", () => {
  if (document.exitFullscreen) document.exitFullscreen();
  else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
});

// ── 範本 pill：填進輸入框 ─────────────────────────────────────────
$("presets").addEventListener("click", (e) => {
  const p = e.target.closest(".pill");
  if (!p) return;
  promptEl.value = p.dataset.prompt;
  promptEl.dispatchEvent(new Event("input"));
  promptEl.focus();
});

// ── 形狀 / 難度 pill：只「選取」，不自動重生（按生成才套用）─────────
function wirePills(containerId, setter) {
  $(containerId).addEventListener("click", (e) => {
    const p = e.target.closest(".pill");
    if (!p) return;
    [...$(containerId).children].forEach((c) => c.classList.remove("active"));
    p.classList.add("active");
    setter(p);
  });
}
wirePills("shapes", (p) => (selShape = p.dataset.shape || ""));
wirePills("diffs", (p) => (selDiff = p.dataset.diff || ""));

// ── 輸入 / 清除 ────────────────────────────────────────────────────
function refreshButtons() {
  const empty = promptEl.value.trim().length === 0;
  genBtn.disabled = empty;
  clearBtn.disabled = empty && !selShape && !selDiff;
}
promptEl.addEventListener("input", refreshButtons);
promptEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !genBtn.disabled) generate();
});

clearBtn.addEventListener("click", () => {
  promptEl.value = "";
  selShape = "";
  selDiff = "";
  // pill 回到「不指定」
  ["shapes", "diffs"].forEach((id) => {
    [...$(id).children].forEach((c, i) => c.classList.toggle("active", i === 0));
  });
  refreshButtons();
  promptEl.focus();
});

genBtn.addEventListener("click", generate);

// ── 生成 ──────────────────────────────────────────────────────────
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
    reloadGame(); // reload iframe → 帶新關卡網址（level_lz），遊戲開機直接載入
    $("game-hint").style.display = "none";

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
  genBtn.disabled = on || promptEl.value.trim().length === 0;
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
  $("sim-report").hidden = true; // 新關卡 → 清掉舊的試玩報表

  const chips = $("goals-chips");
  chips.innerHTML = "";
  goalKeys.forEach((k) => {
    const el = document.createElement("span");
    el.className = "goal-chip";
    el.innerHTML = `${k} <b>×${goals[k]}</b>`;
    chips.appendChild(el);
  });
  $("goals-line").hidden = goalKeys.length === 0;

  // 訪客只看乾淨訊息;原因放 hover(title) 給操作者除錯用
  const b = $("banner");
  if (data.valid) { b.className = "banner ok"; b.textContent = "✓ 通過驗證，可以玩"; b.title = ""; }
  else {
    b.className = "banner warn";
    b.textContent = "⚠️ 這關可能有點小瑕疵，建議再生成一次（滑鼠移上看原因）";
    b.title = (data.errors || []).join("\n") || "（無詳細原因）";
  }
  b.hidden = false;
}

// ── AI 勝率 + 步數報表：點卡片才跑模擬 ───────────────────────────
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
      renderSimReport(r);
    } else cell.textContent = "失敗";
  } catch (e) { cell.textContent = "失敗"; }
});

function renderSimReport(r) {
  const box = $("sim-report");
  if (!box) return;
  box.innerHTML =
    `<div class="card"><div class="row"><span class="k">AI 試玩 ${r.n_games || 60} 場勝率</span>` +
    `<span style="color:${r.color}">${Math.round(r.win_rate * 100)}% ${r.emoji} ${r.badge}</span></div>` +
    (r.avg_steps ? `<div class="row"><span class="k">平均過關步數</span><span>${r.avg_steps}</span></div>` : "") +
    `</div>`;
  box.hidden = false;
}

boot();
