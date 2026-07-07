// 攤位生成器前端 — 純靜態，單頁觸控友善。
// 遊戲嵌在頁面 iframe，但關卡用「網址 level_lz」帶進去（不是 postMessage）—— 經測試
// postMessage 推關會卡，網址帶關不會卡。所以每次生成 = reload iframe 到帶新關卡的網址。

const $ = (id) => document.getElementById(id);

// 目標/物件 ID → 中文名（觀眾看得懂）。key 會先去掉 HP/lv 後綴再查。
const TILE_ZH = {
  Crt: "紙箱", Barrel: "木桶", Puddle: "水漥", TrafficCone: "三角錐",
  SalmonCan: "鮭魚罐頭", WaterChiller: "礦泉水櫃", BeverageChiller: "飲料櫃",
  Rope: "繩子", Mud: "泥巴", Pool: "充氣泳池", Stamp: "郵戳機",
  Red: "紅色", Grn: "綠色", Blu: "藍色", Yel: "黃色", Pur: "紫色", Brn: "咖啡色",
  Soda0d: "火箭", Soda90: "火箭", TNT: "炸彈", TrPr: "紙飛機", LtBl: "光球",
};
// 把 "Crt2" / "Puddle_lv2" / "TrafficCone_lv1" 之類正規化成家族字首再查中文。
function tileZh(key) {
  if (TILE_ZH[key]) return TILE_ZH[key];
  let base = String(key).replace(/_lv\d+$/i, "").replace(/\d+$/, "");
  if (TILE_ZH[base]) return TILE_ZH[base];
  // 去掉 _xxx 後綴再試一次（如 WaterChiller_closed）
  base = base.replace(/_.*$/, "");
  return TILE_ZH[base] || key; // 查不到就原樣顯示（保底）
}
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
  buildArtWall(currentTheme); // 標題跑馬燈用當前(預設)主題的 sprite
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
      // 預設主題(themes.json 標 default:true 的那個)→ 開機就套用
      const def = themes.find((t) => t.default) || themes[0];
      currentTheme = def.name || "";
      sel.value = currentTheme;
    }
  } catch (e) {}
}

// ── 標題後方滾動美術牆（跑馬燈）───────────────────────────────────
// 挑好看、辨識度高的 sprite（避開泥巴/水漥/繩子這類偏暗的障礙）。
const WALL_SPRITES = ["Red", "Yel", "Grn", "Blu", "Pur", "LtBl", "Soda0d", "Soda90", "TrPr", "TNT", "SalmonCan", "Barrel", "Crt2"];
function spriteBase(theme) {
  // 具名主題 → live_sprites/themes/<name>/；預設 candy（空字串）→ flat live_sprites/
  return GAME_URL + "live_sprites/" + (theme ? "themes/" + theme + "/" : "");
}
const WALL_ITEM_W = 42 + 14; // img 寬 + gap，估算用
const WALL_SPEED = 20;       // px/s（原本約 12，稍微快一點）
function buildArtWall(theme) {
  const wall = $("art-wall");
  if (!wall) return;
  const base = spriteBase(theme);
  // 重複填滿：讓「單一 strip」就比視窗還寬 → 兩份並排時整條永遠填滿、不會捲到空白
  const reps = Math.max(2, Math.ceil((window.innerWidth * 1.3) / (WALL_SPRITES.length * WALL_ITEM_W)));
  let names = [];
  for (let i = 0; i < reps; i++) names = names.concat(WALL_SPRITES);
  const strip = names.map((n) => `<img src="${base}${n}.png" alt="" loading="lazy">`).join("");
  // 依 strip 總寬換算秒數 → 不管重複幾次，捲動速度都固定
  const secs = Math.round((names.length * WALL_ITEM_W) / WALL_SPEED);
  wall.style.setProperty("--art-wall-secs", secs + "s");
  // 兩份相同 strip 並排 → translateX 0→-50% 無縫循環
  wall.innerHTML = `<div class="art-wall-track"><div class="art-wall-strip">${strip}</div><div class="art-wall-strip" aria-hidden="true">${strip}</div></div>`;
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
  buildArtWall(currentTheme); // 跑馬燈跟著換主題
  reloadGame();
});

// 回待機畫面（換下一位訪客）：直接整頁重載，等同按 F5 →
// 對話框文字、目標、形狀/難度選取、數據、遊戲全部乾淨歸零,不會漏掉任何一項。
$("idle-btn").addEventListener("click", () => {
  location.reload();
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
// 進/出全螢幕時強制遊戲重新量測 canvas → 用全螢幕的解析度重繪(否則是放大糊的)。
// 同源 /game/ 才能 dispatch;多丟幾次確保 Godot 抓到新尺寸。
document.addEventListener("fullscreenchange", () => {
  [100, 400, 800].forEach((t) => setTimeout(() => {
    try { gameFrame.contentWindow.dispatchEvent(new Event("resize")); } catch (e) {}
  }, t));
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

// ── 生成（SSE 串流：邊生成邊顯示 AI 思考）─────────────────────────
async function generate() {
  const prompt = promptEl.value.trim();
  if (!prompt) return;

  setLoading(true);
  setStatus("work", '<span class="spinner"></span>AI 生成關卡中…');
  const tBox = $("thinking"), tText = $("thinking-text"), tLabel = $("thinking-label");
  tText.textContent = "";
  tLabel.innerHTML = icon("sparkles") + " AI 生成關卡中…";
  tBox.hidden = false;

  let acc = "";
  let fullOut = ""; // 不截斷的完整輸出（含 JSON + 設計說明）→ 給左邊「查看完整輸出」
  const appendThink = (s) => {
    acc += s;
    if (acc.length > 1600) acc = acc.slice(-1600); // 只留末段,避免太長
    tText.textContent = acc;
    tText.scrollTop = tText.scrollHeight;
  };

  let finished = false;
  try {
    const resp = await fetch("/api/generate_stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, shape: selShape || null, difficulty: selDiff || null }),
    });
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const p of parts) {
        const m = p.match(/^data: ([\s\S]*)$/);
        if (!m) continue;
        let evt;
        try { evt = JSON.parse(m[1]); } catch (e) { continue; }
        if (evt.type === "phase") { tLabel.innerHTML = icon("sparkles") + " " + evt.data; }
        else if (evt.type === "thought") { appendThink(evt.data); }
        else if (evt.type === "text") { tLabel.innerHTML = icon("pencil-line") + " 正在產出關卡…"; fullOut += evt.data; appendThink(evt.data); }
        else if (evt.type === "error") { setStatus("err", icon("circle-x") + " " + (evt.error || "生成失敗")); }
        else if (evt.type === "done") { onGenerated(evt, prompt, fullOut); finished = true; }
      }
    }
  } catch (e) {
    setStatus("err", icon("circle-x") + " 連線後端失敗：" + e.message);
  } finally {
    setLoading(false);
    setTimeout(() => { tBox.hidden = true; }, finished ? 1200 : 0);
  }
}

function onGenerated(data, prompt, rawOutput) {
  currentLevel = data.level;
  reloadGame(); // reload iframe → 帶新關卡網址（level_lz）
  $("full-prompt").textContent = data.full_prompt || prompt;
  $("system-prompt").textContent = data.system_prompt || "（無）";
  $("prompt-detail").hidden = false;
  // AI 這關的完整輸出（串流時接住的文字；接不到就退而顯示格式化 JSON）
  const out = (rawOutput || "").trim() || (data.level ? JSON.stringify(data.level, null, 2) : "（無）");
  $("model-output").textContent = out;
  $("output-detail").hidden = false;
  renderLevelMeta(data.level);
  renderStats(data);
  // 數量問題後端已自動校正 → 幾乎都會通過驗證。極少數殘留結構性問題只丟 console 給操作者(F12)。
  setStatus("ok", data.valid ? icon("circle-check") + " 關卡已生成，通過驗證" : icon("circle-check") + " 關卡已生成");
  if (!data.valid && (data.errors || []).length) console.warn("[booth] 關卡仍有結構性問題（不對觀眾顯示）:", data.errors);
  runSimulation(); // 生成完自動跑 AI 試玩 → 直接出勝率報表
}

// 關卡名稱 + 設計理念（模型回傳 JSON 裡的 name / description）
function renderLevelMeta(level) {
  const box = $("level-meta");
  const name = (level && level.name || "").trim();
  const desc = (level && level.description || "").trim();
  $("level-name").textContent = name;
  $("level-desc").textContent = desc;
  $("level-name").hidden = !name;
  $("level-desc").hidden = !desc;
  box.hidden = !(name || desc);
}

function setLoading(on) {
  genBtn.disabled = on || promptEl.value.trim().length === 0;
  genBtn.classList.toggle("loading", on);
  genBtn.innerHTML = on ? icon("loader-circle", "spin") + " 生成中…" : icon("sparkles") + " 用 AI 生成關卡";
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
    el.title = k; // 原始 ID 留給操作者除錯
    el.innerHTML = `${tileZh(k)} <b>×${goals[k]}</b>`;
    chips.appendChild(el);
  });
  $("goals-line").hidden = goalKeys.length === 0;

  // 數量問題後端已自動校正 → 幾乎都通過驗證,顯示原本的「通過驗證」資訊。
  // 罕見殘留的結構性問題不對觀眾顯示(觸控看不到 hover),只丟 console 給操作者(F12)。
  const b = $("banner");
  b.title = "";
  if (data.valid) {
    b.className = "banner ok";
    b.innerHTML = icon("check") + " 通過驗證，可以玩";
    b.hidden = false;
  } else {
    b.hidden = true;
    if ((data.errors || []).length) console.warn("[booth] 驗證未過（不對觀眾顯示）:", data.errors);
  }
}

// ── AI 勝率 + 步數報表：生成後自動跑、也可點卡片重跑 ──────────────
let simRunning = false;
async function runSimulation() {
  if (!currentLevel || simRunning) return;
  simRunning = true;
  const cell = $("st-winrate");
  cell.textContent = "測試中…";
  cell.style.color = "";
  try {
    const r = await fetch("/api/simulate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level: currentLevel, n_games: 100 }),
    }).then((x) => x.json());
    if (r.ok) {
      cell.textContent = Math.round(r.win_rate * 100) + "%";
      cell.style.color = r.color;
      cell.title = r.badge;
      renderSimReport(r);
    } else cell.textContent = "失敗";
  } catch (e) { cell.textContent = "失敗"; }
  finally { simRunning = false; }
}
$("st-winrate-card").addEventListener("click", runSimulation);

function renderSimReport(r) {
  const box = $("sim-report");
  if (!box) return;
  let html = `<div class="card">`;
  html += `<div class="row"><span class="k">AI 試玩 ${r.n_games || 100} 場</span>` +
          `<span style="color:${r.color}">勝率 ${Math.round(r.win_rate * 100)}% ${icon(r.icon)} ${r.badge}</span></div>`;
  if (r.wins != null) html += `<div class="row"><span class="k">勝 / 敗</span><span>${r.wins} / ${r.losses}</span></div>`;
  if (r.avg_steps) html += `<div class="row"><span class="k">平均過關步數</span><span>${r.avg_steps}</span></div>`;
  if (r.min_steps != null && r.max_steps_seen != null)
    html += `<div class="row"><span class="k">最快 / 最慢</span><span>${r.min_steps} / ${r.max_steps_seen} 步</span></div>`;

  const hist = r.step_histogram || {};
  const keys = Object.keys(hist);
  if (keys.length) {
    const mx = Math.max(...keys.map((k) => hist[k]));
    html += `<div class="hist-title">勝場過關步數分佈</div><div class="hist">`;
    keys.forEach((k) => {
      const w = Math.max(4, Math.round((hist[k] / mx) * 100));
      const lo = parseInt(k, 10);
      html += `<div class="hist-row"><span class="hist-k">${lo}–${lo + 4}</span>` +
              `<span class="hist-bar" style="width:${w}%"></span><span class="hist-n">${hist[k]}</span></div>`;
    });
    html += `</div>`;
  }
  html += `</div>`;
  box.innerHTML = html;
  box.hidden = false;
}

boot();
