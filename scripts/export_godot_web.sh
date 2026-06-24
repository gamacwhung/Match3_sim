#!/usr/bin/env bash
# =====================================================================
# Godot Web Export — 備份舊 build 後重新匯出（含 ArtTheme）
# =====================================================================
#
# 用法:
#   ./scripts/export_godot_web.sh              # 備份 + export
#   ./scripts/export_godot_web.sh --skip-backup  # 直接覆寫 web/
#   ./scripts/export_godot_web.sh --backup-only  # 只備份,不 export
#
# 環境變數:
#   GODOT  — Godot 執行檔路徑（必填,若不在 PATH）
#            macOS 例: /Applications/Godot.app/Contents/MacOS/Godot
#            Linux 例: ~/Godot/Godot_v4.6-stable_linux.x86_64
#
# 備份位置: godot_web_original/  （舊版完整 web build,只備份一次）
# 匯出位置: godot_demo/web/            （run.sh 與 GitHub Pages 使用）
# live_sprites/ 不會被刪除（AI 美術熱更新目錄）
# =====================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GODOT_DIR="$REPO_ROOT/godot_demo"
WEB_DIR="$GODOT_DIR/web"
BACKUP_DIR="$GODOT_DIR/../godot_web_original"
LIVE_DIR="$WEB_DIR/live_sprites"
SKIP_BACKUP=0
BACKUP_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-backup) SKIP_BACKUP=1 ;;
    --backup-only) BACKUP_ONLY=1 ;;
    -h|--help)
      sed -n '3,20p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

find_godot() {
  if [[ -n "${GODOT:-}" && -x "$GODOT" ]]; then
    echo "$GODOT"
    return
  fi
  if command -v godot >/dev/null 2>&1; then
    command -v godot
    return
  fi
  # macOS .app bundle
  for app in /Applications/Godot.app /Applications/Godot_4.app; do
    local bin="$app/Contents/MacOS/Godot"
    if [[ -x "$bin" ]]; then
      echo "$bin"
      return
    fi
  done
  return 1
}

backup_web() {
  if [[ -d "$BACKUP_DIR/index.pck" || -f "$BACKUP_DIR/index.pck" ]]; then
    echo "[backup] godot_web_original/ 已存在,跳過（刪除該目錄可強制再備份）"
    return
  fi
  if [[ ! -f "$WEB_DIR/index.pck" ]]; then
    echo "[backup] web/index.pck 不存在,無可備份"
    return
  fi
  echo "[backup] 複製 $WEB_DIR → $BACKUP_DIR （保留舊版 build）"
  mkdir -p "$BACKUP_DIR"
  # rsync 保留 live_sprites 在 web/;備份不含 live_sprites（執行期產物）
  rsync -a --exclude 'live_sprites' "$WEB_DIR/" "$BACKUP_DIR/"
  echo "[backup] 完成: $(du -sh "$BACKUP_DIR" | cut -f1)"
}

# Godot 預設 shell 在引擎啟動後立刻收掉進度條,但 ArtTheme 還在背景抓 live 美術。
# 這裡 patch web build:ArtTheme 等待、iframe 清晰度、HiDPI 修正(reexport 後仍需重打)。
patch_web_js_iframe() {
  local js="$WEB_DIR/index.js"
  [[ -f "$js" ]] || return 0
  if grep -q 'window.self===window.top),getPixelRatio' "$js"; then
    echo "[export] index.js 已含 iframe hidpi 修正,略過"
    return 0
  fi
  if ! grep -q 'hidpi:true,getPixelRatio' "$js"; then
    echo "[export] ⚠ index.js 找不到 hidpi 片段,iframe 清晰度 patch 略過"
    return 0
  fi
  sed -i.bak 's/hidpi:true,getPixelRatio/hidpi:(window.self===window.top),getPixelRatio/' "$js"
  rm -f "$js.bak"
  echo "[export] ✓ index.js: iframe 內停用 DPI 縮放"
}

patch_index_html() {
  local html="$WEB_DIR/index.html"
  [[ -f "$html" ]] || return 0
  python3 - "$html" <<'PY'
import sys

path = sys.argv[1]
src = open(path, encoding='utf-8').read()
changed = False

# --- iframe: mark body only (adaptive canvas + hidpi fix in index.js) ---
if 'IN_IFRAME' not in src:
    src = src.replace(
        '\t\t<script>\nconst GODOT_CONFIG = ',
        '\t\t<script>\n'
        'const IN_IFRAME = window.self !== window.top;\n'
        'if (IN_IFRAME) {\n\tdocument.body.classList.add(\'in-iframe\');\n}\n'
        'const GODOT_CONFIG = ',
        1,
    )
    changed = True

# --- ArtTheme splash 等待 ---
if '_artThemeReady' not in src:
    needle = "\t\t}).then(() => {\n\t\t\tsetStatusMode('hidden');\n\t\t}, displayFailureNotice);"
    repl = (
        "\t\t}).then(() => {\n"
        "\t\t\t// 等 ArtTheme 就緒(僅 ?live=1 時會抓 live 美術;否則立即就緒)\n"
        "\t\t\tconst artStart = Date.now();\n"
        "\t\t\tconst pollArt = () => {\n"
        "\t\t\t\tif (window._artThemeReady || Date.now() - artStart > 20000) {\n"
        "\t\t\t\t\tsetStatusMode('hidden');\n"
        "\t\t\t\t\treturn;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tconst p = window._artThemeProgress;\n"
        "\t\t\t\tif (p && p.total > 0) {\n"
        "\t\t\t\t\tstatusProgress.value = p.current;\n"
        "\t\t\t\t\tstatusProgress.max = p.total;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tsetTimeout(pollArt, 100);\n"
        "\t\t\t};\n"
        "\t\t\tpollArt();\n"
        "\t\t}, displayFailureNotice);"
    )
    if needle not in src:
        print('[export] ⚠ 找不到預設 splash 收尾片段,index.html patch 失敗(Godot 版本可能改了 shell)')
        sys.exit(0)
    src = src.replace(needle, repl, 1)
    changed = True

if changed:
    open(path, 'w', encoding='utf-8').write(src)
    print('[export] ✓ index.html 已 patch(iframe body class + ArtTheme 等待)')
elif '_artThemeReady' in src:
    print('[export] index.html 已含所有 patch,略過')
PY
}

sync_default_packed_art() {
  local py="$REPO_ROOT/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    py="$(command -v python3 || true)"
  fi
  if [[ -z "$py" ]]; then
    echo "[!] 找不到 python,無法同步預設打包美術" >&2
    exit 1
  fi
  echo "[export] 同步預設打包美術 → resources/sprites/ …"
  (
    cd "$REPO_ROOT"
    "$py" -c "from art_pipeline.apply import apply_default_packed_art; apply_default_packed_art()"
  )
}

export_web() {
  sync_default_packed_art

  local godot_bin
  godot_bin="$(find_godot)" || {
    echo "[!] 找不到 Godot。請安裝 Godot 4.6 並設定:" >&2
    echo "    export GODOT=/path/to/Godot" >&2
    echo "    或見 godot_demo/README_DEMO.md" >&2
    exit 1
  }

  echo "[export] 使用: $godot_bin"
  echo "[export] 腳本檢查…"
  (
    cd "$GODOT_DIR"
    "$godot_bin" --headless --quit-after 2 2>&1 | tee /tmp/godot_script_check.log || true
  )
  if grep -qE 'Failed to load script|Parse Error:|SCRIPT ERROR:' /tmp/godot_script_check.log 2>/dev/null; then
    echo "[!] Godot 腳本有錯誤,請先修復" >&2
    exit 1
  fi

  mkdir -p "$WEB_DIR"
  echo "[export] 匯出 Web → $WEB_DIR/index.html"
  (
    cd "$GODOT_DIR"
    "$godot_bin" --headless --path . --export-release "Web" "web/index.html"
  )

  if [[ ! -f "$WEB_DIR/index.pck" ]]; then
    echo "[!] export 失敗: 找不到 index.pck" >&2
    exit 1
  fi

  # 確認 ArtTheme 已進 pck
  if strings "$WEB_DIR/index.pck" | grep -qE 'art_theme|ArtTheme'; then
    echo "[export] ✓ index.pck 含 ArtTheme"
  else
    echo "[export] ⚠ index.pck 未偵測到 art_theme（可能仍為舊邏輯）"
  fi

  patch_web_js_iframe
  patch_index_html

  mkdir -p "$LIVE_DIR"
  local pck_mb
  pck_mb="$(du -m "$WEB_DIR/index.pck" | cut -f1)"
  echo "[export] 完成 index.pck ≈ ${pck_mb}MB"
  echo "[export] 本機測試: ./run.sh --godot-only → http://localhost:8765/"
}

[[ "$SKIP_BACKUP" -eq 0 ]] && backup_web
[[ "$BACKUP_ONLY" -eq 1 ]] && exit 0
export_web
