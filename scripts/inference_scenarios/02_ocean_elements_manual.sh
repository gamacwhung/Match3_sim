#!/usr/bin/env bash
# 情境 2：主題換皮 — 海底世界，手動指定每色物件（不經 LLM 展開）
# 輸出：generated_art/ocean_elements/sprites/{Red,Grn,Blu,Yel,Pur}.png

set -euo pipefail
cd "$(dirname "$0")/../.."

python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "ocean watercolor pixel art, soft bubbles, seafoam highlights" \
  --run ocean_theme \
  --no-reference-image \
