extends Node2D
##
## BoardBG
##
## 畫盤面背景 + 障礙物 sprite。
##
## 障礙物 tile_id → sprite mapping(若 JsonLevelLoader 有帶 tile_id 進來,優先用 sprite)
##

# 關鍵障礙物 sprite — 一次 preload 進來,效能無虞
const OBSTACLE_TEXTURES: Dictionary = {
	"Crt1": preload("res://resources/sprites/Crt1.png"),
	"Crt2": preload("res://resources/sprites/Crt2.png"),
	"Crt3": preload("res://resources/sprites/Crt3.png"),
	"Crt4": preload("res://resources/sprites/Crt4.png"),
	"Puddle_lv1": preload("res://resources/sprites/Puddle_lv1.png"),
	"Puddle_lv2": preload("res://resources/sprites/Puddle_lv2.png"),
	"Barrel": preload("res://resources/sprites/Barrel.png"),
	"TrafficCone_lv1": preload("res://resources/sprites/TrafficCone_lv1.png"),
	"TrafficCone_lv2": preload("res://resources/sprites/TrafficCone_lv2.png"),
	"SalmonCan": preload("res://resources/sprites/SalmonCan.png"),
	"Mud": preload("res://resources/sprites/Mud.png"),
	"Rope_lv1": preload("res://resources/sprites/Rope_lv1.png"),
	"Rope_lv2": preload("res://resources/sprites/Rope_lv2.png"),
	"Stamp": preload("res://resources/sprites/Stamp.png"),
	# 礦泉水櫃 — HP 11 段,closed 等於 lv11
	"WaterChiller_closed": preload("res://resources/sprites/WaterChiller_closed.png"),
	"WaterChiller_lv1": preload("res://resources/sprites/WaterChiller_lv1.png"),
	"WaterChiller_lv2": preload("res://resources/sprites/WaterChiller_lv2.png"),
	"WaterChiller_lv3": preload("res://resources/sprites/WaterChiller_lv3.png"),
	"WaterChiller_lv4": preload("res://resources/sprites/WaterChiller_lv4.png"),
	"WaterChiller_lv5": preload("res://resources/sprites/WaterChiller_lv5.png"),
	"WaterChiller_lv6": preload("res://resources/sprites/WaterChiller_lv6.png"),
	"WaterChiller_lv7": preload("res://resources/sprites/WaterChiller_lv7.png"),
	"WaterChiller_lv8": preload("res://resources/sprites/WaterChiller_lv8.png"),
	"WaterChiller_lv9": preload("res://resources/sprites/WaterChiller_lv9.png"),
	"WaterChiller_lv10": preload("res://resources/sprites/WaterChiller_lv10.png"),
	"WaterChiller_lv11": preload("res://resources/sprites/WaterChiller_lv11.png"),
	# 飲料櫃 — HP 5 段,closed 等於 lv5
	"BeverageChiller_closed": preload("res://resources/sprites/BeverageChiller_closed.png"),
	"BeverageChiller_lv1": preload("res://resources/sprites/BeverageChiller_lv1.png"),
	"BeverageChiller_lv2": preload("res://resources/sprites/BeverageChiller_lv2.png"),
	"BeverageChiller_lv3": preload("res://resources/sprites/BeverageChiller_lv3.png"),
	"BeverageChiller_lv4": preload("res://resources/sprites/BeverageChiller_lv4.png"),
	"BeverageChiller_lv5": preload("res://resources/sprites/BeverageChiller_lv5.png"),
	"Pool_lv1": preload("res://resources/sprites/Pool_lv1.png"),
	"Pool_lv2": preload("res://resources/sprites/Pool_lv2.png"),
	"Pool_lv3": preload("res://resources/sprites/Pool_lv3.png"),
	"Pool_lv4": preload("res://resources/sprites/Pool_lv4.png"),
	"Pool_lv5": preload("res://resources/sprites/Pool_lv5.png"),
}

const BOARD_BG_TEXTURE: Texture2D = preload("res://resources/sprites/board_bg.png")

var board: Node2D


func _ready() -> void:
	board = get_parent()


func _draw() -> void:
	if board == null or not board.has_method("get_obstacle_map"):
		return
	var offset = board.board_offset
	var w = board.grid_width
	var h = board.grid_height
	var cs = board.cell_size
	var blocked = board.blocked_cells

	# 外框 — 用 board_bg 紋理(平鋪在整個盤面範圍 + 邊距)做木紋外圈
	var border = 12.0
	var bg_rect = Rect2(offset - Vector2(border, border), Vector2(w * cs + border * 2, h * cs + border * 2))
	if BOARD_BG_TEXTURE:
		draw_texture_rect(BOARD_BG_TEXTURE, bg_rect, true)
	else:
		draw_rect(bg_rect, Color(0.42, 0.30, 0.20, 1.0), true)
	# 內框深色
	var inner_rect = Rect2(offset, Vector2(w * cs, h * cs))
	draw_rect(inner_rect, Color(0.05, 0.04, 0.10, 1.0), true)
	draw_rect(bg_rect, Color(0.4, 0.3, 0.6, 0.6), false, 3.0)

	# 棋盤底色:斜紋
	for x in w:
		for y in h:
			if Vector2i(x, y) in blocked:
				continue
			var cell_pos = offset + Vector2(x * cs, y * cs)
			var cell_rect = Rect2(cell_pos + Vector2(2, 2), Vector2(cs - 4, cs - 4))
			var shade = Color(0.18, 0.14, 0.28) if (x + y) % 2 == 0 else Color(0.22, 0.17, 0.32)
			draw_rect(cell_rect, shade, true)

	# 障礙物
	var obs_map = board.get_obstacle_map()
	# 多格 instance dedupe — 同個 instance_id 只畫一次(在 anchor 位置畫整張大 sprite)
	var drawn_instances: Dictionary = {}
	for pos in obs_map:
		var obs = obs_map[pos]
		var inst_id = obs.get("instance_id", "")

		# 計算這次該畫的 rect:
		#   - 多格 instance:從 instance_cells 算 anchor (min x, min y) 跟 size (max - min + 1)
		#   - 單格:就是當前 pos 一格
		var anchor_pos: Vector2i = pos
		var size_cells: Vector2i = Vector2i(1, 1)
		if inst_id != "":
			if drawn_instances.has(inst_id):
				continue
			drawn_instances[inst_id] = true
			var cells: Array = obs.get("instance_cells", [pos])
			var min_x: int = pos.x
			var min_y: int = pos.y
			var max_x: int = pos.x
			var max_y: int = pos.y
			for c in cells:
				if c.x < min_x: min_x = c.x
				if c.y < min_y: min_y = c.y
				if c.x > max_x: max_x = c.x
				if c.y > max_y: max_y = c.y
			anchor_pos = Vector2i(min_x, min_y)
			size_cells = Vector2i(max_x - min_x + 1, max_y - min_y + 1)

		var top_left = offset + Vector2(anchor_pos.x * cs, anchor_pos.y * cs)
		var rect = Rect2(
			top_left + Vector2(2, 2),
			Vector2(size_cells.x * cs - 4, size_cells.y * cs - 4)
		)

		var sprite_drawn = false
		# 優先 sprite 渲染(JsonLevelLoader 載入路徑)
		if obs.has("tile_id"):
			var tid = obs["tile_id"]
			var hp = obs.get("hp", 1)
			var sprite_key = _resolve_sprite_key(tid, hp)
			if OBSTACLE_TEXTURES.has(sprite_key):
				draw_texture_rect(OBSTACLE_TEXTURES[sprite_key], rect, false)
				sprite_drawn = true

		if sprite_drawn:
			# HP > 1 時加上小 HP 標記(放在 anchor 右下)
			var hp = obs.get("hp", 1)
			if hp > 1:
				var label_pos = top_left + Vector2(size_cells.x * cs - 14, size_cells.y * cs - 14)
				draw_circle(label_pos, 9, Color(0, 0, 0, 0.75))
				_draw_hp_text(label_pos, hp)
			continue

		# Fallback:yuehpo 原本的程序畫法
		match obs["type"]:
			"ice":
				var alpha = 0.15 + obs["hp"] * 0.12
				draw_rect(rect, Color(0.7, 0.85, 1.0, alpha), true)
				for i in obs["hp"]:
					var inset = 3.0 + i * 4.0
					var r = Rect2(top_left + Vector2(inset, inset), Vector2(size_cells.x * cs - inset * 2, size_cells.y * cs - inset * 2))
					draw_rect(r, Color(0.8, 0.9, 1.0, 0.3), false, 1.5)
			"wire":
				var wr = Rect2(top_left + Vector2(3, 3), Vector2(size_cells.x * cs - 6, size_cells.y * cs - 6))
				draw_rect(wr, Color(0.5, 0.5, 0.5, 0.4), false, 2.5)
			"jelly":
				var jelly_alpha = 0.2 + obs["hp"] * 0.15
				draw_rect(rect, Color(0.9, 0.3, 0.5, jelly_alpha), true)


# tile_id + 當前 HP → sprite key,對齊 match3_board_component/asset_map.py 的邏輯
static func _resolve_sprite_key(tile_id: String, hp: int) -> String:
	# Crt 紙箱:HP 1~4 對應 Crt1~Crt4
	if tile_id.begins_with("Crt"):
		return "Crt%d" % clamp(hp, 1, 4)
	# 礦泉水櫃:HP=11 → closed,HP=10..1 → lv10..lv1
	if tile_id.begins_with("WaterChiller"):
		var lv = clamp(hp, 1, 11)
		if lv == 11:
			return "WaterChiller_closed"
		return "WaterChiller_lv%d" % lv
	# 飲料櫃:HP=5 → closed,HP=4..1 → lv4..lv1
	if tile_id.begins_with("BeverageChiller"):
		var lv = clamp(hp, 1, 5)
		if lv == 5:
			return "BeverageChiller_closed"
		return "BeverageChiller_lv%d" % lv
	# Pool:HP 1~5 對應 lv1~lv5
	if tile_id.begins_with("Pool"):
		return "Pool_lv%d" % clamp(hp, 1, 5)
	# 其他 _lv 系列:Puddle_lv1/2、TrafficCone_lv1/2、Rope_lv1/2
	if "_lv" in tile_id:
		var base = tile_id.split("_lv")[0]
		# 找該 base 系列有的最大 lv
		var max_lv = 1
		for k in OBSTACLE_TEXTURES.keys():
			if str(k).begins_with(base + "_lv"):
				var n = int(str(k).substr(base.length() + 3))
				if n > max_lv:
					max_lv = n
		return "%s_lv%d" % [base, clamp(hp, 1, max_lv)]
	# 沒 _lv 字尾:直接用 tile_id
	return tile_id


func _draw_hp_text(pos: Vector2, hp: int) -> void:
	# 用一個小白色 dot 配合外圍黑圈當 HP 指示;字型對 web 可能渲染問題,盡量避免
	for i in range(min(hp, 4)):
		var dot_pos = pos + Vector2(-3 + i * 2, 0)
		draw_circle(dot_pos, 1.2, Color.WHITE)
