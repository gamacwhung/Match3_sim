#!/usr/bin/env bash
# 情境 4：主題換皮 — 蒸汽龐克工坊，只生成道具 family（TNT、汽水、彩虹球等）
# 輸出：generated_art/steampunk_powerups/sprites/

set -euo pipefail
cd "$(dirname "$0")/../.."

python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "steampunk brass pixel art, rivets, gauges, copper pipes" \
  --theme "蒸汽工坊，齒輪與壓力閥造型的消除道具" \
  --run steampunk_theme \
  --no-reference-image
