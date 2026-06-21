#!/usr/bin/env bash
# AI art generation shortcuts
#
# 列出所有 --assets / --family 選項:
#   .venv/bin/python scripts/ai_art_gen.py list-assets
#
# --family 選項(整組生成):
#   elements          Red, Grn, Blu, Yel, Pur
#   powerups          Soda0d, Soda90, TNT, LtBl, TrPr
#   crate             Crt1, Crt2, Crt3, Crt4
#   movable           Barrel, TrafficCone_lv1, TrafficCone_lv2
#   salmon_can        SalmonCan, SalmonCan_body, SalmonCan_top1, SalmonCan_top2
#   puddle            Puddle_lv1, Puddle_lv2
#   rope              Rope_lv1, Rope_lv2
#   mud               Mud
#   postmark          Stamp, Postmark_01, Postmark_02, Postmark_card, Postmark_bundle, Postmark_goal
#   pool              Pool_lv1 .. Pool_lv5
#   water_chiller     WaterChiller_closed, WaterChiller_door, WaterChiller_lv1 .. lv11
#   beverage_chiller  BeverageChiller_closed, body, door, bottle_*, lv1 .. lv5
#   background        board_bg
#
# --assets 範例(逗號分隔,大小寫需完全一致):
#   Red,Grn,Blu,Yel,Pur
#   Soda0d,Soda90,TNT,LtBl,TrPr
#   Crt1,Crt2,Crt3,Crt4

.venv/bin/python scripts/ai_art_gen.py generate --style "pixel art" --run test_pixel_art --assets Red,Blu
