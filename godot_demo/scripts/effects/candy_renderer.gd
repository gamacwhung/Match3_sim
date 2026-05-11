extends Node2D
##
## CandyRenderer
##
## 改造後:0-3 用我們的 M8 美術 sprite (Red/Grn/Blu/Yel),
## 4-5 fallback 回原 yuehpo 的向量畫法(以防有人用 6 色關卡)
##
## 特殊糖果:STRIPED_H/V → Soda0d/Soda90 火箭;WRAPPED → TNT;COLOR_BOMB → LtBl 光球
##

enum CandyColor { RED, GRN, BLU, YEL, EXTRA1, EXTRA2 }

# 主要的 4 色 sprite 對照(對齊我們的 levels JSON 的 0-3 索引)
const SPRITE_TEXTURES: Dictionary = {
	0: preload("res://resources/sprites/Red.png"),
	1: preload("res://resources/sprites/Grn.png"),
	2: preload("res://resources/sprites/Blu.png"),
	3: preload("res://resources/sprites/Yel.png"),
	4: preload("res://resources/sprites/Pur.png"),
}

# 特殊糖果用我們的盤內道具 sprite
const TEXTURE_STRIPED_H: Texture2D = preload("res://resources/sprites/Soda0d.png")  # 整列火箭(水平消除)
const TEXTURE_STRIPED_V: Texture2D = preload("res://resources/sprites/Soda90.png")  # 整欄火箭(垂直消除)
const TEXTURE_WRAPPED: Texture2D = preload("res://resources/sprites/TNT.png")        # 5x5 爆炸
const TEXTURE_COLOR_BOMB: Texture2D = preload("res://resources/sprites/LtBl.png")    # 光球(清最多色)
const TEXTURE_SPIRAL: Texture2D = preload("res://resources/sprites/TrPr.png")        # 紙飛機(2x2 合成、十字消除)

# 6 色 fallback 顏色(只在沒 sprite 時才用)
const COLOR_MAP = {
	CandyColor.RED: Color(0.95, 0.2, 0.2),
	CandyColor.GRN: Color(0.2, 0.85, 0.3),
	CandyColor.BLU: Color(0.2, 0.45, 0.95),
	CandyColor.YEL: Color(1.0, 0.9, 0.15),
	CandyColor.EXTRA1: Color(0.7, 0.25, 0.9),
	CandyColor.EXTRA2: Color(1.0, 0.55, 0.1),
}

const HIGHLIGHT_MAP = {
	CandyColor.RED: Color(1.0, 0.6, 0.6),
	CandyColor.GRN: Color(0.6, 1.0, 0.7),
	CandyColor.BLU: Color(0.6, 0.75, 1.0),
	CandyColor.YEL: Color(1.0, 1.0, 0.6),
	CandyColor.EXTRA1: Color(0.9, 0.6, 1.0),
	CandyColor.EXTRA2: Color(1.0, 0.8, 0.5),
}

const SHADOW_MAP = {
	CandyColor.RED: Color(0.55, 0.08, 0.08),
	CandyColor.GRN: Color(0.08, 0.5, 0.12),
	CandyColor.BLU: Color(0.08, 0.2, 0.55),
	CandyColor.YEL: Color(0.6, 0.55, 0.05),
	CandyColor.EXTRA1: Color(0.35, 0.1, 0.5),
	CandyColor.EXTRA2: Color(0.6, 0.3, 0.05),
}


# ===========================================================================
# Public draw entry — game_board / candy.gd 都從這裡呼叫
# ===========================================================================
static func draw_candy(canvas: CanvasItem, candy_color: int, sz: float, special_type: int = 0) -> void:
	if SPRITE_TEXTURES.has(candy_color):
		_draw_sprite_candy(canvas, SPRITE_TEXTURES[candy_color], sz, special_type)
	else:
		# 罕見情況 (6 色關卡) → 走原本的向量風格
		_draw_vector_candy(canvas, candy_color, sz, special_type)


static func draw_color_bomb(canvas: CanvasItem, sz: float) -> void:
	# 光球(LtBl)
	var size = sz * 0.92
	var rect = Rect2(-size * 0.5, -size * 0.5, size, size)
	canvas.draw_texture_rect(TEXTURE_COLOR_BOMB, rect, false)


# ---------------------------------------------------------------------------
# Sprite 渲染(主路徑)
# ---------------------------------------------------------------------------
static func _draw_sprite_candy(canvas: CanvasItem, tex: Texture2D, sz: float, special_type: int = 0) -> void:
	# 特殊糖果 → 直接用對應 sprite 取代基底糖
	if special_type > 0:
		var sp_tex = _get_special_texture(special_type)
		if sp_tex:
			var sp_size = sz * 0.95
			canvas.draw_texture_rect(sp_tex, Rect2(-sp_size * 0.5, -sp_size * 0.5, sp_size, sp_size), false)
			return

	# 一般糖果 — 等比例 sprite,稍微留邊好看
	var size = sz * 0.92
	var rect = Rect2(-size * 0.5, -size * 0.5, size, size)
	canvas.draw_texture_rect(tex, rect, false)


static func _get_special_texture(special_type: int) -> Texture2D:
	match special_type:
		1: return TEXTURE_STRIPED_H
		2: return TEXTURE_STRIPED_V
		3: return TEXTURE_WRAPPED
		4: return TEXTURE_COLOR_BOMB
		5: return TEXTURE_SPIRAL  # 紙飛機 TrPr (2x2 合成)
	return null


# ---------------------------------------------------------------------------
# Vector fallback(yuehpo 原風格,只在 candy_color > 4 時觸發)
# ---------------------------------------------------------------------------
static func _draw_vector_candy(canvas: CanvasItem, candy_color: int, sz: float, special_type: int = 0) -> void:
	if not COLOR_MAP.has(candy_color):
		return
	var base = COLOR_MAP[candy_color]
	var highlight = HIGHLIGHT_MAP[candy_color]
	var shadow = SHADOW_MAP[candy_color]
	var half = sz * 0.45

	# 簡化為圓形 fallback(原本的 6 種形狀太花俏,demo 用不到)
	canvas.draw_circle(Vector2(1, 2), half, shadow * Color(1, 1, 1, 0.4))
	canvas.draw_circle(Vector2.ZERO, half, base)
	canvas.draw_circle(Vector2.ZERO, half * 0.85, lerp(base, highlight, 0.3))
	canvas.draw_circle(Vector2(-half * 0.25, -half * 0.25), half * 0.35, Color(1, 1, 1, 0.45))

	if special_type > 0:
		_draw_special_overlay(canvas, special_type, half)


static func _draw_special_overlay(canvas: CanvasItem, special_type: int, r: float) -> void:
	# 特殊糖果不到位時的 fallback overlay(只是符號)
	match special_type:
		1: # Striped horizontal
			for i in 3:
				var y_off = (i - 1) * r * 0.35
				canvas.draw_line(Vector2(-r * 0.6, y_off), Vector2(r * 0.6, y_off), Color(1, 1, 1, 0.7), 2.0)
		2: # Striped vertical
			for i in 3:
				var x_off = (i - 1) * r * 0.35
				canvas.draw_line(Vector2(x_off, -r * 0.6), Vector2(x_off, r * 0.6), Color(1, 1, 1, 0.7), 2.0)
		3: # Wrapped
			canvas.draw_rect(Rect2(Vector2(-r * 0.3, -r * 0.3), Vector2(r * 0.6, r * 0.6)), Color(1, 1, 1, 0.5), false, 2.5)
		4: # Color bomb
			canvas.draw_circle(Vector2.ZERO, r * 0.25, Color.WHITE)
