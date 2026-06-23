extends Node2D
##
## BoardBG
##
## 畫盤面背景 + 障礙物 sprite。
##
## 障礙物 tile_id → sprite mapping(若 JsonLevelLoader 有帶 tile_id 進來,優先用 sprite)
##

# 關鍵障礙物 sprite — packed 預設(一次 preload,效能無虞)。
# 執行時 OBSTACLE_TEXTURES 會以此為基底,並由 ArtTheme 套上 live 覆蓋。
const _DEFAULT_OBSTACLE_TEXTURES: Dictionary = {
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
	"SalmonCan_body": preload("res://resources/sprites/SalmonCan_body.png"),
	"SalmonCan_top1": preload("res://resources/sprites/SalmonCan_top1.png"),
	"SalmonCan_top2": preload("res://resources/sprites/SalmonCan_top2.png"),
	"Mud": preload("res://resources/sprites/Mud.png"),
	"Rope_lv1": preload("res://resources/sprites/Rope_lv1.png"),
	"Rope_lv2": preload("res://resources/sprites/Rope_lv2.png"),
	"Stamp": preload("res://resources/sprites/Stamp.png"),
	"Postmark_bundle": preload("res://resources/sprites/Postmark_bundle.png"),
	"Postmark_01": preload("res://resources/sprites/Postmark_01.png"),
	"Postmark_02": preload("res://resources/sprites/Postmark_02.png"),
	"Postmark_card": preload("res://resources/sprites/Postmark_card.png"),
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
	# 飲料櫃 — 分層 composite (body + 個別瓶子 + 門)
	"BeverageChiller_body": preload("res://resources/sprites/BeverageChiller_body.png"),
	"BeverageChiller_door": preload("res://resources/sprites/BeverageChiller_door.png"),
	"BeverageChiller_bottle_red": preload("res://resources/sprites/BeverageChiller_bottle_red.png"),
	"BeverageChiller_bottle_blue": preload("res://resources/sprites/BeverageChiller_bottle_blue.png"),
	"BeverageChiller_bottle_green": preload("res://resources/sprites/BeverageChiller_bottle_green.png"),
	"BeverageChiller_bottle_yellow": preload("res://resources/sprites/BeverageChiller_bottle_yellow.png"),
	# 礦泉水櫃 — 門(疊在 lv* 圖上面)
	"WaterChiller_door": preload("res://resources/sprites/WaterChiller_door.png"),
	"Pool_lv1": preload("res://resources/sprites/Pool_lv1.png"),
	"Pool_lv2": preload("res://resources/sprites/Pool_lv2.png"),
	"Pool_lv3": preload("res://resources/sprites/Pool_lv3.png"),
	"Pool_lv4": preload("res://resources/sprites/Pool_lv4.png"),
	"Pool_lv5": preload("res://resources/sprites/Pool_lv5.png"),
}

# 飲料櫃瓶色 (來自 official_format 的 corner item id) → sprite key
const BEVERAGE_BOTTLE_TEXTURE_KEY: Dictionary = {
	"Red": "BeverageChiller_bottle_red",
	"Blu": "BeverageChiller_bottle_blue",
	"Grn": "BeverageChiller_bottle_green",
	"Yel": "BeverageChiller_bottle_yellow",
}

const BOARD_BG_TEXTURE: Texture2D = preload("res://resources/sprites/board_bg.png")
const STAMP_FLASH_DURATION: float = 0.28

var board: Node2D
# 執行期障礙物貼圖 = packed 預設 + ArtTheme live 覆蓋
var OBSTACLE_TEXTURES: Dictionary = _DEFAULT_OBSTACLE_TEXTURES.duplicate()
# 郵戳蓋章閃爍 — grid pos → 結束時間(秒)
var _stamp_flash_until: Dictionary = {}
# 障礙物掉落動畫 — grid pos → 剩餘 pixel offset (Vector2)；tween-based
var _obs_fall_offset: Dictionary = {}
var _obs_fall_tweens: Array[Tween] = []


func _ready() -> void:
	board = get_parent()
	set_process(false)
	# 障礙物 / board_bg 走 ArtTheme,支援 live_sprites 即時替換 → 主題更新就重畫
	_apply_theme_overrides()
	if not ArtTheme.theme_ready.is_connected(_on_theme_ready):
		ArtTheme.theme_ready.connect(_on_theme_ready)


func _on_theme_ready() -> void:
	_apply_theme_overrides()
	queue_redraw()


func _apply_theme_overrides() -> void:
	OBSTACLE_TEXTURES = _DEFAULT_OBSTACLE_TEXTURES.duplicate()
	for key in _DEFAULT_OBSTACLE_TEXTURES:
		if ArtTheme.has_named_texture(key):
			OBSTACLE_TEXTURES[key] = ArtTheme.get_named_texture(key)


func _board_bg_texture() -> Texture2D:
	if ArtTheme.has_named_texture("board_bg"):
		return ArtTheme.get_named_texture("board_bg")
	return BOARD_BG_TEXTURE


func trigger_stamp_flash(grid_pos: Vector2i) -> void:
	_stamp_flash_until[grid_pos] = Time.get_ticks_msec() / 1000.0 + STAMP_FLASH_DURATION
	if not is_processing():
		set_process(true)
	queue_redraw()


func notify_obstacle_moved(from_pos: Vector2i, to_pos: Vector2i, duration: float = 0.15) -> Tween:
	if board == null:
		return null
	var cs: float = board.cell_size
	var pixel_diff = Vector2((from_pos.x - to_pos.x) * cs, (from_pos.y - to_pos.y) * cs)
	_obs_fall_offset[to_pos] = pixel_diff
	queue_redraw()
	var tw = create_tween()
	tw.tween_method(func(t: float):
		_obs_fall_offset[to_pos] = pixel_diff * (1.0 - t)
		queue_redraw()
	, 0.0, 1.0, duration)
	tw.tween_callback(func():
		_obs_fall_offset.erase(to_pos)
		queue_redraw()
	)
	_obs_fall_tweens.append(tw)
	return tw


func _process(delta: float) -> void:
	var now = Time.get_ticks_msec() / 1000.0
	var changed := false
	for pos in _stamp_flash_until.keys():
		if _stamp_flash_until[pos] <= now:
			_stamp_flash_until.erase(pos)
			changed = true
	if changed:
		queue_redraw()
	if _stamp_flash_until.is_empty():
		set_process(false)


func _stamp_flash_progress(grid_pos: Vector2i) -> float:
	if not _stamp_flash_until.has(grid_pos):
		return -1.0
	var now = Time.get_ticks_msec() / 1000.0
	var end_t: float = _stamp_flash_until[grid_pos]
	if now >= end_t:
		return -1.0
	var start_t = end_t - STAMP_FLASH_DURATION
	return clampf((now - start_t) / STAMP_FLASH_DURATION, 0.0, 1.0)


func _draw() -> void:
	if board == null or not board.has_method("get_obstacle_map"):
		return
	var offset = board.board_offset
	var w = board.grid_width
	var h = board.grid_height
	var cs = board.cell_size
	var blocked = board.blocked_cells
	var obs_map = board.get_obstacle_map()

	# 外框 — 用 board_bg 紋理(平鋪在整個盤面範圍 + 邊距)做木紋外圈
	var border = 12.0
	var bg_rect = Rect2(offset - Vector2(border, border), Vector2(w * cs + border * 2, h * cs + border * 2))
	var bg_tex := _board_bg_texture()
	if bg_tex:
		draw_texture_rect(bg_tex, bg_rect, true)
	else:
		draw_rect(bg_rect, Color(0.42, 0.30, 0.20, 1.0), true)
	# 內框深色
	var inner_rect = Rect2(offset, Vector2(w * cs, h * cs))
	draw_rect(inner_rect, Color(0.05, 0.04, 0.10, 1.0), true)
	draw_rect(bg_rect, Color(0.4, 0.3, 0.6, 0.6), false, 3.0)

	# 棋盤底色:所有盤面格子都畫（void 除外）
	# void = 在 blocked 裡但不在 obstacle_map/bottom_obstacle_map 裡的格子
	var bottom_map: Dictionary = board.bottom_obstacle_map
	for x in w:
		for y in h:
			var pos_v = Vector2i(x, y)
			if pos_v in blocked and not obs_map.has(pos_v) and not bottom_map.has(pos_v):
				continue
			var cell_pos = offset + Vector2(x * cs, y * cs)
			var cell_rect = Rect2(cell_pos + Vector2(2, 2), Vector2(cs - 4, cs - 4))
			var shade = Color(0.18, 0.14, 0.28) if (x + y) % 2 == 0 else Color(0.22, 0.17, 0.32)
			draw_rect(cell_rect, shade, true)

	# 下層水窪 — 畫在底色上，不降低透明度（只是疊在糖果下面的圖層）
	for pos in bottom_map:
		var obs_p = bottom_map[pos]
		var tid_p = str(obs_p.get("tile_id", ""))
		var rect_p = Rect2(
			offset + Vector2(pos.x * cs, pos.y * cs) + Vector2(2, 2),
			Vector2(cs - 4, cs - 4)
		)
		var key_p = _resolve_sprite_key(tid_p, obs_p.get("hp", 1))
		if OBSTACLE_TEXTURES.has(key_p):
			draw_texture_rect(OBSTACLE_TEXTURES[key_p], rect_p, false)
	# 相容舊的 obs_map 中殘留的 bottom layer(不應再有,保險起見)
	for pos in obs_map:
		var obs_p = obs_map[pos]
		var tid_p = str(obs_p.get("tile_id", ""))
		if obs_p.get("layer", "") != "bottom" and not tid_p.begins_with("Puddle"):
			continue
		var rect_p = Rect2(
			offset + Vector2(pos.x * cs, pos.y * cs) + Vector2(2, 2),
			Vector2(cs - 4, cs - 4)
		)
		var key_p = _resolve_sprite_key(tid_p, obs_p.get("hp", 1))
		if OBSTACLE_TEXTURES.has(key_p):
			draw_texture_rect(OBSTACLE_TEXTURES[key_p], rect_p, false)

	# 中層 / 上層障礙物(略過 bottom Puddle、泥巴另處理遮罩)
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
		# 掉落動畫偏移
		var fall_off := Vector2.ZERO
		if inst_id == "" and _obs_fall_offset.has(pos):
			fall_off = _obs_fall_offset[pos]
		var rect = Rect2(
			top_left + Vector2(2, 2) + fall_off,
			Vector2(size_cells.x * cs - 4, size_cells.y * cs - 4)
		)

		var sprite_drawn = false
		# 優先 sprite 渲染(JsonLevelLoader 載入路徑)
		if obs.has("tile_id"):
			var tid = obs["tile_id"]
			if obs.get("layer", "") == "bottom" or str(tid).begins_with("Puddle"):
				continue
			if str(tid).begins_with("Mud"):
				continue
			var hp = obs.get("hp", 1)
			# BeverageChiller 有 bottle_colors → 用分層 composite (body + 4 罐子 + 門)
			# 沒有就 fallback 走原來 lv*/closed 單張圖。
			if tid.begins_with("BeverageChiller") and obs.has("bottle_colors") and (obs["bottle_colors"] as Dictionary).size() > 0:
				_draw_beverage_chiller_composite(rect, anchor_pos, size_cells, cs, offset, obs)
				sprite_drawn = true
			elif tid == "Stamp" or obs.get("type", "") == "manufacturer":
				_draw_postmark_composite(rect, obs, pos)
				sprite_drawn = true
			else:
				var sprite_key = _resolve_sprite_key(tid, hp, obs)
				# SalmonCan: body + top1(sealed) / top2(open) 複合渲染
				if str(tid).begins_with("SalmonCan") and OBSTACLE_TEXTURES.has("SalmonCan_body"):
					draw_texture_rect(OBSTACLE_TEXTURES["SalmonCan_body"], rect, false)
					var salmon_state = str(obs.get("salmon_state", "sealed"))
					if salmon_state == "sealed" and OBSTACLE_TEXTURES.has("SalmonCan_top1"):
						draw_texture_rect(OBSTACLE_TEXTURES["SalmonCan_top1"], rect, false)
					elif OBSTACLE_TEXTURES.has("SalmonCan_top2"):
						draw_texture_rect(OBSTACLE_TEXTURES["SalmonCan_top2"], rect, false)
					sprite_drawn = true
				elif OBSTACLE_TEXTURES.has(sprite_key):
					draw_texture_rect(OBSTACLE_TEXTURES[sprite_key], rect, false)
					sprite_drawn = true
				# 礦泉水櫃 — 「門」設計(user 確認):HP=max(closed)時門關著,
				# 1 hit 開門 → HP=10..1 已經是開門狀態,就不用再疊門了。
				# closed.png 本身有畫門,但對比比較弱;額外疊一層 WaterChiller_door 強調「門關著」,
				# 玩家看一眼就知道「現在門是關的」。
				if tid.begins_with("WaterChiller") and hp >= 11 and OBSTACLE_TEXTURES.has("WaterChiller_door"):
					draw_texture_rect(OBSTACLE_TEXTURES["WaterChiller_door"], rect, false, Color(1, 1, 1, 0.6))

		if sprite_drawn:
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

	# 泥巴 — 不透明上層，完全蓋住中層元素(candy.visible 也會關掉)
	for pos in obs_map:
		var obs_m = obs_map[pos]
		if not str(obs_m.get("tile_id", "")).begins_with("Mud"):
			continue
		var rect_m = Rect2(
			offset + Vector2(pos.x * cs, pos.y * cs) + Vector2(2, 2),
			Vector2(cs - 4, cs - 4)
		)
		if OBSTACLE_TEXTURES.has("Mud"):
			draw_texture_rect(OBSTACLE_TEXTURES["Mud"], rect_m, false)


# 官方風格郵戳 — bundle(明信片疊) + 01(抬起) / 02(蓋下) / victory(通關後倒下+已蓋章疊)
func _draw_postmark_composite(rect: Rect2, obs: Dictionary, grid_pos: Vector2i) -> void:
	var state: String = str(obs.get("stamp_state", "idle"))
	var ft = _stamp_flash_progress(grid_pos)
	if ft >= 0.0 and state == "idle":
		state = "pressed"

	match state:
		"victory":
			# 通關:明信片疊顯示已蓋章 card;郵戳倒下(02 旋轉,頭朝左)
			if OBSTACLE_TEXTURES.has("Postmark_card"):
				draw_texture_rect(OBSTACLE_TEXTURES["Postmark_card"], rect, false)
			if OBSTACLE_TEXTURES.has("Postmark_02"):
				var fallen = Rect2(rect.position, Vector2(rect.size.x * 0.55, rect.size.y * 0.55))
				draw_set_transform(
					rect.position + Vector2(rect.size.x * 0.12, rect.size.y * 0.72),
					-PI * 0.5,
					Vector2.ONE
				)
				draw_texture_rect(OBSTACLE_TEXTURES["Postmark_02"], fallen, false)
				draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		"pressed":
			if OBSTACLE_TEXTURES.has("Postmark_bundle"):
				draw_texture_rect(OBSTACLE_TEXTURES["Postmark_bundle"], rect, false)
			if OBSTACLE_TEXTURES.has("Postmark_02"):
				draw_texture_rect(OBSTACLE_TEXTURES["Postmark_02"], rect, false)
			if ft >= 0.0:
				var pulse = sin(ft * PI) * 0.25
				draw_rect(rect, Color(0.95, 0.2, 0.15, pulse), true)
		_:
			# idle — 空白疊 + 郵戳抬起(01)
			if OBSTACLE_TEXTURES.has("Postmark_bundle"):
				draw_texture_rect(OBSTACLE_TEXTURES["Postmark_bundle"], rect, false)
			if OBSTACLE_TEXTURES.has("Postmark_01"):
				draw_texture_rect(OBSTACLE_TEXTURES["Postmark_01"], rect, false)


# tile_id + 當前 HP → sprite key,對齊 match3_board_component/asset_map.py 的邏輯
static func _resolve_sprite_key(tile_id: String, hp: int, _obs: Dictionary = {}) -> String:
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
		for k in _DEFAULT_OBSTACLE_TEXTURES.keys():
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


# BeverageChiller 分層 composite — 一層 body + 4 個對應顏色的罐子 + 門。
# 設計需求(user 確認):
#   1. 飲料櫃要看得到門(目前 lv*/closed 圖少了門)
#   2. 不同關卡的罐子顏色不同,要按 level 的 bottle_colors 數據放
# 罐子位置:每個 instance_cells 對應到 anchor 內的 (x_off, y_off) 局部位置。
# HP-based 視覺淡化:hp 越低 → 已被「砸」的罐子越多。挑「離左上最遠」的先消失,
# 跟玩家直覺對齊(從右下方往左上扣)。
func _draw_beverage_chiller_composite(rect: Rect2, anchor_pos: Vector2i, size_cells: Vector2i, cs: float, offset: Vector2, obs: Dictionary) -> void:
	# 1) 畫底層 body
	if OBSTACLE_TEXTURES.has("BeverageChiller_body"):
		draw_texture_rect(OBSTACLE_TEXTURES["BeverageChiller_body"], rect, false)

	# 2) 罐子 — 按 hp 決定要畫幾個,從「右下→左上」的順序保留(被砸掉的先從右下消失)
	# Note:讓 「left-top is the most-recently destroyed」的逆順序 → 用 instance_cells
	# 排序 by (-r, -c) 後取前 hp 個 cell 來畫(其餘空著)。
	var max_hp: int = obs.get("max_hp", 4)
	var cells: Array = obs.get("instance_cells", [])
	var bottle_colors: Dictionary = obs.get("bottle_colors", {})
	var bottle_alive: Dictionary = obs.get("bottle_alive", {})
	var sorted_cells: Array = cells.duplicate()
	sorted_cells.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
		if a.y != b.y:
			return a.y < b.y
		return a.x < b.x
	)
	for cell in sorted_cells:
		var cell_v: Vector2i = cell as Vector2i
		if bottle_alive.has(cell_v) and not bool(bottle_alive[cell_v]):
			continue
		var color_id: String = str(bottle_colors.get(cell_v, ""))
		if not BEVERAGE_BOTTLE_TEXTURE_KEY.has(color_id):
			continue
		var key: String = BEVERAGE_BOTTLE_TEXTURE_KEY[color_id]
		if not OBSTACLE_TEXTURES.has(key):
			continue
		var cell_top_left = offset + Vector2(cell_v.x * cs, cell_v.y * cs)
		var cell_rect = Rect2(cell_top_left + Vector2(2, 2), Vector2(cs - 4, cs - 4))
		# 罐子稍微縮小一點,避免溢出格邊
		var inset := Vector2(cs * 0.10, cs * 0.10)
		cell_rect = Rect2(cell_top_left + inset, Vector2(cs, cs) - inset * 2.0)
		draw_texture_rect(OBSTACLE_TEXTURES[key], cell_rect, false)

	# 3) 門 — 只在關門狀態才畫
	var hp: int = obs.get("hp", 0)
	if hp >= max_hp and OBSTACLE_TEXTURES.has("BeverageChiller_door"):
		draw_texture_rect(OBSTACLE_TEXTURES["BeverageChiller_door"], rect, false, Color(1, 1, 1, 0.92))
