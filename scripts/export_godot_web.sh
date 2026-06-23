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
# 這裡 patch index.html,讓進度條等到 window._artThemeReady 才隱藏(reexport 後仍需重打)。
patch_index_html() {
  local html="$WEB_DIR/index.html"
  [[ -f "$html" ]] || return 0
  if grep -q '_artThemeReady' "$html"; then
    echo "[export] index.html 已含 ArtTheme 等待邏輯,略過 patch"
    return 0
  fi
  python3 - "$html" <<'PY'
import sys
path = sys.argv[1]
src = open(path, encoding='utf-8').read()
needle = "\t\t}).then(() => {\n\t\t\tsetStatusMode('hidden');\n\t\t}, displayFailureNotice);"
repl = (
    "\t\t}).then(() => {\n"
    "\t\t\t// 等 ArtTheme 抓完 live 美術(或逾時)再收掉 splash 進度條\n"
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
    print('[export] \u26a0 找不到預設 splash 收尾片段,index.html patch 失敗(Godot 版本可能改了 shell)')
    sys.exit(0)
open(path, 'w', encoding='utf-8').write(src.replace(needle, repl, 1))
print('[export] \u2713 index.html 已 patch:進度條會等 ArtTheme 載完')
PY
}

export_web() {
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
