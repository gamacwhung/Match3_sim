#!/usr/bin/env bash
# 情境 3：換畫風（restyle）— 保留原物件形狀，改成 16-bit 像素風
# 預設會參考官方 sprite；輸出：generated_art/pixel_restyle/sprites/

set -euo pipefail
cd "$(dirname "$0")/../.."

python scripts/ai_art_gen.py generate \
  --mode restyle \
  --style "16-bit pixel art, crisp outlines, limited palette, retro game sprite" \
  --run pixel_restyle \
