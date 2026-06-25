#!/usr/bin/env bash
# 情境 5：主題換皮 — 日式枯山水庭園，水池系列（Pool_lv1–lv5）
# 輸出：generated_art/zen_garden_pool/sprites/

set -euo pipefail
cd "$(dirname "$0")/../.."

python scripts/ai_art_gen.py generate \
  --mode theme-swap \
  --style "Japanese zen garden illustration, soft ink wash, moss and stone textures" \
  --theme "日式枯山水庭園，石池與苔石" \
  --run zen_garden_pool \
  --no-reference-image
