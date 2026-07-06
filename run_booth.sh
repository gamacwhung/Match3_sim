#!/usr/bin/env bash
# =====================================================================
# Booth 一鍵啟動 (macOS / Linux) — 自動帶好 Vertex AI 認證後啟動 booth server
# =====================================================================
#
#   ./run_booth.sh                    # 開發,預設 8800
#   ./run_booth.sh --port 8501        # 對外正式(公開連結)
#   ./run_booth.sh --port 8501 --model gemini-2.5-pro
#
# 認證:自動在專案根目錄找「service_account 類型的 *.json」,設定
#       GCP_PROJECT_ID + GCP_CREDENTIALS_FILE(Vertex AI)。
#       → 換電腦(同事備援)只要把那個 JSON 放進專案根目錄即可,不必手動設環境變數。
#
# 會先清掉「目前佔用該 Port 的舊 process」再啟動(所以這也是安全的『重啟』指令)。
# 第一次使用先給執行權限:  chmod +x run_booth.sh
# =====================================================================
set -euo pipefail

PORT=8800
MODEL="gemini-3.5-flash"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)  PORT="$2";  shift 2;;
    -m|--model) MODEL="$2"; shift 2;;
    -h|--help)  echo "用法: ./run_booth.sh [--port 8501] [--model gemini-2.5-pro]"; exit 0;;
    *) echo "未知參數: $1" >&2; exit 1;;
  esac
done

cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then echo "[!] 找不到 python3,請先安裝 Python 3" >&2; exit 1; fi

# 1) 找服務帳戶 JSON(type=service_account)並取 project_id
CRED="$("$PY" - <<'PYEOF'
import json, glob, os
for f in glob.glob("*.json"):
    try:
        d = json.load(open(f))
        if d.get("type") == "service_account" and d.get("project_id"):
            print(os.path.abspath(f)); break
    except Exception:
        pass
PYEOF
)"
if [[ -z "$CRED" ]]; then
  echo "[!] 找不到服務帳戶 JSON(type=service_account)。請把 Vertex AI 金鑰 JSON 放到專案根目錄:" >&2
  echo "    $(pwd)" >&2
  exit 1
fi
PROJECT_ID="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['project_id'])" "$CRED")"

export GCP_PROJECT_ID="$PROJECT_ID"
export GCP_CREDENTIALS_FILE="$CRED"
export BOOTH_PORT="$PORT"
export BOOTH_MODEL="$MODEL"

echo "=============================================================="
echo " Booth server"
echo "   project : $PROJECT_ID"
echo "   creds   : $(basename "$CRED")"
echo "   port    : $PORT    model: $MODEL"
echo "=============================================================="

# 2) 清掉佔用該 Port 的舊 process(安全重啟)
if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  if [[ -n "$PIDS" ]]; then
    echo "[i] 停掉舊 process ($PIDS) on port $PORT"
    kill -9 $PIDS 2>/dev/null || true
    sleep 1
  fi
fi

# 3) 啟動
exec "$PY" booth/server.py
