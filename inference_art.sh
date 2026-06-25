#!/usr/bin/env bash
# AI 美術生成 — 五種推論情境
# 用法：bash inference_art.sh [1-5|all]
# 或直接執行 scripts/inference_scenarios/ 下的個別腳本

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SCENARIOS=(
  "$ROOT/scripts/inference_scenarios/01_candy_house_elements.sh"
  "$ROOT/scripts/inference_scenarios/02_ocean_elements_manual.sh"
  "$ROOT/scripts/inference_scenarios/03_pixel_restyle_elements.sh"
  "$ROOT/scripts/inference_scenarios/04_steampunk_powerups.sh"
  "$ROOT/scripts/inference_scenarios/05_zen_garden_pool.sh"
)

run_one() {
  local n="$1"
  if [[ "$n" -lt 1 || "$n" -gt 5 ]]; then
    echo "用法: $0 [1-5|all]" >&2
    exit 1
  fi
  bash "${SCENARIOS[$((n - 1))]}"
}

ARG="${1:-}"

case "$ARG" in
  all)
    for i in 1 2 3 4 5; do
      echo "========== 情境 $i =========="
      run_one "$i"
    done
    ;;
  1|2|3|4|5)
    run_one "$ARG"
    ;;
  *)
    echo "用法: $0 [1-5|all]" >&2
    echo ""
    echo "情境一覽："
    echo "  1  糖果屋 elements（theme-swap + LLM 展開主題）"
    echo "  2  海底世界 elements（theme-swap + 手動每色物件）"
    echo "  3  像素風 elements（restyle 保留原物件）"
    echo "  4  蒸汽龐克 powerups（theme-swap 道具系列）"
    echo "  5  枯山水 pool（theme-swap 水池障礙物）"
    exit 1
    ;;
esac
