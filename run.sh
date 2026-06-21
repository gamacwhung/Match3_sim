#!/usr/bin/env bash
# =====================================================================
# Match3_sim — one-shot launcher (macOS / Linux)
# =====================================================================
#
# Usage:
#   ./run.sh                  # Streamlit (8501) + Godot web server (8765)
#   ./run.sh --streamlit-only # Streamlit only
#   ./run.sh --godot-only     # Godot web server only
#   ./run.sh --install        # create venv + pip install -r requirements.txt
#   ./run.sh --stop           # stop servers started by this script
#
# Prerequisites (one-time):
#   1. ./run.sh --install
#   2. (optional) Export Godot web: ./scripts/export_godot_web.sh
#      Godot 預設路徑: /Applications/Godot.app
#
# Demo URLs:
#   http://localhost:8501/                 Streamlit home
#   http://localhost:8501/AI_Auto_Test     AI auto-test report
#   http://localhost:8501/Demo             Demo mode
#   http://localhost:8501/AI_Art_Lab       AI art generation lab
#   http://localhost:8765/                 Godot visual (after web export)
# =====================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$REPO_ROOT/.demo_logs"
STREAMLIT_PORT=8501
GODOT_PORT=8765
STREAMLIT_ONLY=0
GODOT_ONLY=0
DO_STOP=0
DO_INSTALL=0

usage() {
  sed -n '5,22p' "$0" | sed 's/^# \?//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --streamlit-only) STREAMLIT_ONLY=1 ;;
    --godot-only) GODOT_ONLY=1 ;;
    --stop) DO_STOP=1 ;;
    --install) DO_INSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    --streamlit-port) STREAMLIT_PORT="${2:?missing port}"; shift ;;
    --godot-port) GODOT_PORT="${2:?missing port}"; shift ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ "$STREAMLIT_ONLY" -eq 1 && "$GODOT_ONLY" -eq 1 ]]; then
  echo "Use either --streamlit-only or --godot-only, not both." >&2
  exit 1
fi

pick_python() {
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    echo "$REPO_ROOT/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  echo "Python not found. Install Python 3.10+ or run: ./run.sh --install" >&2
  exit 1
}

PYTHON="$(pick_python)"

stop_server() {
  local name="$1"
  local pid_file="$LOG_DIR/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "  Stopped $name (PID $pid)"
  else
    echo "  $name not running"
  fi
  rm -f "$pid_file"
}

start_server() {
  local name="$1"
  shift
  local log_file="$LOG_DIR/$name.log"
  local pid_file="$LOG_DIR/$name.pid"

  stop_server "$name" >/dev/null 2>&1 || true

  echo "Starting $name..."
  (
    cd "$REPO_ROOT"
    exec "$@"
  ) >>"$log_file" 2>&1 &
  local pid=$!
  echo "$pid" >"$pid_file"
  echo "  $name PID = $pid, log = $log_file"
}

ensure_deps() {
  if ! "$PYTHON" -c "import streamlit" >/dev/null 2>&1; then
    echo "Missing Python dependencies."
    echo "Run: ./run.sh --install"
    exit 1
  fi
}

do_install() {
  if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
    echo "Creating virtualenv at .venv ..."
    python3 -m venv "$REPO_ROOT/.venv"
  fi
  PYTHON="$REPO_ROOT/.venv/bin/python"
  echo "Installing requirements with $PYTHON ..."
  "$PYTHON" -m pip install --upgrade pip
  "$PYTHON" -m pip install -r "$REPO_ROOT/requirements.txt"
  echo "Done. Start the demo with: ./run.sh"
}

mkdir -p "$LOG_DIR"

if [[ "$DO_INSTALL" -eq 1 ]]; then
  do_install
  exit 0
fi

if [[ "$DO_STOP" -eq 1 ]]; then
  echo "Stopping demo servers..."
  stop_server "streamlit"
  stop_server "godot-web"
  exit 0
fi

ensure_deps

if [[ "$GODOT_ONLY" -eq 0 ]]; then
  start_server "streamlit" \
    "$PYTHON" -m streamlit run streamlit_app.py \
    --server.port "$STREAMLIT_PORT" \
    --server.headless true
fi

GODOT_WEB_DIR="$REPO_ROOT/godot_demo/web"
if [[ "$STREAMLIT_ONLY" -eq 0 ]]; then
  if [[ -d "$GODOT_WEB_DIR" && -f "$GODOT_WEB_DIR/index.html" ]]; then
    start_server "godot-web" \
      "$PYTHON" scripts/serve_godot.py \
      --port "$GODOT_PORT" \
      --dir godot_demo/web
  else
    echo "[!] godot_demo/web/ not ready — skipping Godot web server"
    echo "    Export Godot → Web to godot_demo/web/ (see godot_demo/README_DEMO.md)"
    echo "    Or open godot_demo/ in Godot Editor and press F5"
  fi
fi

echo
echo "=============================================================="
echo " Match3_sim is running"
echo "=============================================================="
if [[ "$GODOT_ONLY" -eq 0 ]]; then
  echo "  Streamlit:      http://localhost:$STREAMLIT_PORT/"
    echo "  AI auto-test:   http://localhost:$STREAMLIT_PORT/AI_Auto_Test"
    echo "  Demo mode:      http://localhost:$STREAMLIT_PORT/Demo"
    echo "  AI Art Lab:     http://localhost:$STREAMLIT_PORT/AI_Art_Lab"
fi
if [[ "$STREAMLIT_ONLY" -eq 0 && -f "$GODOT_WEB_DIR/index.html" ]]; then
  echo "  Godot visual:   http://localhost:$GODOT_PORT/"
fi
echo
echo "  Stop:  ./run.sh --stop"
echo "  Logs:  $LOG_DIR"
echo "=============================================================="
