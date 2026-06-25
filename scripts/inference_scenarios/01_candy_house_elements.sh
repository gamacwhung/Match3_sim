#!/usr/bin/env bash
# 情境 1：主題換皮 — 概念型主題「糖果屋」，LLM 自動展開每色物件
# 輸出：generated_art/candy_house/sprites/{Red,Grn,Blu,Yel,Pur}.png

set -euo pipefail
cd "$(dirname "$0")/../.."

python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "2D Disney cartoon style" \
  --theme "糖果屋" \
  --run candy_house \
  --no-reference-image
