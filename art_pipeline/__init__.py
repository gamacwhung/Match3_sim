"""
Game Art AI Generation Pipeline — 用 Gemini 把遊戲美術整批換風格。

流程:
  1. manifest   — 盤點現有 asset(名稱/尺寸/功能/視覺約束)
  2. pipeline   — 逐張生成: Gemini 生圖 → 程式化驗證 → Gemini vision 評審 → 不過關帶修正指示重生成
  3. apply      — 備份原圖後把生成結果套進 godot_demo/resources/sprites/,可隨時 restore

CLI 入口: scripts/ai_art_gen.py
"""
