extends Node
class_name JsonLevelLoader
##
## 從我們專案的 levels/*.json 格式載入關卡 → 轉成 yuehpo 的 LevelData
##
## 我們的 JSON 格式 (參考 c:/Users/.../Match3_sim/levels/level_01.json):
##   {
##     "name": "...", "description": "...",
##     "rows": 10, "cols": 9, "num_colors": 4, "max_steps": 35,
##     "goals": { "Crt1": 45 },
##     "board": [["Grn","Red",...], ...]    # 舊格式:整片視為 middle layer
##     // 或新格式:
##     "board": { "middle": [...], "upper": [...], "bottom": [...] }
##   }
##
## tile id 對照:
##   - 元素:   "Red"=0, "Grn"=1, "Blu"=2, "Yel"=3
##   - 障礙:   "Crt1"~"Crt4"  → jelly,HP=1~4
##              "Puddle_lv1"~"Puddle_lv5" → ice (layer=bottom 但 yuehpo 沒 layer 概念,當 ice)
##              "Rope_lv1"~"Rope_lv2"     → wire
##              "TrafficCone_lv1/lv2"     → ice
##              "SalmonCan", "Barrel"     → jelly
##              "WaterChiller_*", "Pool_*", "BeverageChiller_*" → 暫時當大型 jelly
##   - void:   blocked_cells
##

const ELEMENT_TO_COLOR_INDEX: Dictionary = {
	"Red": 0,
	"Grn": 1,
	"Blu": 2,
	"Yel": 3,
	"Pur": 4,
	"Brn": 5,
}

# Tile id 前綴 → yuehpo obstacle type
# 我們的設計:
#   - 實體障礙(BLOCKING_PREFIXES,middle layer):佔整個 cell,沒糖,
#     相鄰 match 打傷它,HP=0 解封
#   - 下層修飾物(Puddle,bottom layer):糖在上面,match 在這 cell 直接打傷它
#     → 跟 yuehpo 的 jelly 一樣(jelly 的 _trigger_obstacle_adjacent 會打自身)
#   - 上層修飾物(Rope, Mud,upper layer):糖在下被鎖,相鄰 match 才能打傷它
#     → 跟 yuehpo 的 wire 一樣
const OBSTACLE_TYPE_MAP: Dictionary = {
	"Crt": "jelly",
	"Puddle": "jelly",
	"Rope": "wire",
	"Mud": "wire",
	"TrafficCone": "jelly",
	"SalmonCan": "jelly",
	"Barrel": "jelly",
	"Stamp": "jelly",
	"WaterChiller": "jelly",
	"BeverageChiller": "jelly",
	"Pool": "jelly",
	"Roadblock": "jelly",
}

# 「會佔據整個 cell」的障礙物前綴 — 糖不能放在這上面
# Puddle 是下層、Rope/Mud 是上層 → 不 blocking,跟糖共存
const BLOCKING_OBSTACLE_PREFIXES: Array[String] = [
	"Crt", "Barrel", "TrafficCone", "SalmonCan", "Stamp",
	"WaterChiller", "BeverageChiller", "Pool", "Roadblock",
]


static func _is_blocking_obstacle(tile_id: String) -> bool:
	for prefix in BLOCKING_OBSTACLE_PREFIXES:
		if tile_id.begins_with(prefix):
			return true
	return false


static func load_from_file(path: String) -> Resource:
	"""讀 res:// 路徑或 user:// 路徑下的 JSON,回傳 LevelData(yuehpo 格式)"""
	if not FileAccess.file_exists(path):
		push_error("JsonLevelLoader: file not found: " + path)
		return null
	var content = FileAccess.get_file_as_string(path)
	var parsed = JSON.parse_string(content)
	if parsed == null or not parsed is Dictionary:
		push_error("JsonLevelLoader: invalid JSON in " + path)
		return null
	return parse_level_dict(parsed)


static func parse_level_dict(data: Dictionary) -> Resource:
	"""把 dict 轉成 LevelData
	
	注意:LevelData 用 typed array (Array[int] / Array[Dictionary] / Array[Vector2i]),
	所以我們要先建 typed 變數再賦值,不能直接用 plain literal 賦值。
	"""
	var level = LevelData.new()
	level.level_id = 1
	level.grid_width = int(data.get("cols", 9))
	level.grid_height = int(data.get("rows", 10))
	level.max_moves = int(data.get("max_steps", 30))
	level.num_colors = int(data.get("num_colors", 4))
	
	# typed array 賦值 — 不能用 plain literal,否則炸 "Invalid assignment of property"
	var thresholds: Array[int] = [1000, 3000, 5000]
	level.star_thresholds = thresholds

	# goals → objectives(收集 obstacle 為主)
	var goals = data.get("goals", {})
	var objectives_arr: Array[Dictionary] = []
	for tile_id in goals.keys():
		var target_count = int(goals[tile_id])
		var obs_type = _resolve_obstacle_type(tile_id)
		if obs_type:
			objectives_arr.append({
				"type": "clear_" + obs_type,
				"target": target_count,
				"current": 0,
				"tile_id": tile_id,
			})
		else:
			# 元素類:收集色
			var color_idx = _resolve_element_color(tile_id)
			if color_idx >= 0:
				objectives_arr.append({
					"type": "collect",
					"color": color_idx,
					"target": target_count,
					"current": 0,
				})
	# Fallback:沒有目標 → 分數目標(避免無法判勝)
	if objectives_arr.size() == 0:
		objectives_arr.append({"type": "score", "target": 1000, "current": 0})
	level.objectives = objectives_arr

	# board → blocked_cells + obstacle_data
	var board_field = data.get("board")
	if board_field == null:
		push_error("JsonLevelLoader: no 'board' key in level data")
		return level

	var middle_grid: Array = []
	var upper_grid: Array = []
	var bottom_grid: Array = []
	if typeof(board_field) == TYPE_ARRAY:
		# 舊格式 — 整片是 middle layer
		middle_grid = board_field
	elif typeof(board_field) == TYPE_DICTIONARY:
		middle_grid = board_field.get("middle", [])
		upper_grid = board_field.get("upper", [])
		bottom_grid = board_field.get("bottom", [])
	else:
		push_error("JsonLevelLoader: unsupported 'board' type")
		return level

	# yuehpo 用 (x, y) 座標,我們的 JSON 是 row-major (row=y, col=x)
	# 注意:yuehpo 的 grid 可能 y=0 在頂或底,需檢查 board_filler;這裡先用 y=row(從上到下)
	var rows = middle_grid.size()
	var cols = level.grid_width

	# typed arrays — 同 objectives,直接 append 進 typed array 再賦值
	var blocked_arr: Array[Vector2i] = []
	var obstacle_arr: Array[Dictionary] = []

	# Pass 1:middle layer 的 void → blocked_cells;tile_id 含 "#" → 多格 instance
	#         非元素 tile → obstacle
	#
	# 多格 instance(e.g. 2x2 礦泉水櫃 "WaterChiller_closed#1")的共享 HP 邏輯:
	#   - 同 "tile_id#tag" 的所有 cells 都 reference 同一個 shared Dictionary
	#   - Godot Dictionary 是 reference type,改 shared["hp"] 全部 cell 看到的 HP 都會變
	#   - shared dict 帶 instance_id + instance_cells,_damage_obstacle / board_bg 都用得到
	var shared_by_key: Dictionary = {}  # "tile#tag" -> shared dict
	for r in range(rows):
		var row_data = middle_grid[r]
		if typeof(row_data) != TYPE_ARRAY:
			continue
		for c in range(cols):
			if c >= row_data.size():
				continue
			var raw = str(row_data[c])
			var pos = Vector2i(c, r)
			if raw == "" or raw == "null":
				continue
			if raw == "void":
				blocked_arr.append(pos)
				continue

			# 拆 instance_tag (e.g. "Pool_lv3#1")
			var tile_id = raw
			var inst_tag = ""
			if "#" in raw:
				var parts = raw.split("#", true, 1)
				tile_id = parts[0]
				inst_tag = parts[1]

			# 元素 → 不放障礙(讓 game_board 用 candy 自動填)
			if _resolve_element_color(tile_id) >= 0:
				continue
			# 道具 → 暫時也不放(需要 yuehpo 的 special_candy 機制,目前簡化省略)
			if _is_powerup(tile_id):
				continue
			# 障礙
			var obs_type = _resolve_obstacle_type(tile_id)
			if obs_type == null:
				continue
			var hp = _resolve_obstacle_hp(tile_id)

			if inst_tag != "":
				# 多格 instance — 同 tag 的 cells 共享同個 dict
				var key = "%s#%s" % [tile_id, inst_tag]
				var shared: Dictionary
				if shared_by_key.has(key):
					shared = shared_by_key[key]
				else:
					var instance_cells: Array[Vector2i] = []
					shared = {
						"type": obs_type,
						"hp": hp,
						"max_hp": hp,
						"tile_id": tile_id,
						"instance_id": key,
						"instance_cells": instance_cells,
					}
					shared_by_key[key] = shared
				shared["instance_cells"].append(pos)
				# 每個 cell 都把 shared 加進 obstacle_arr(同個 dict reference)
				obstacle_arr.append({
					"pos": [pos.x, pos.y],
					"shared_ref": shared,
				})
			else:
				# 單格 obstacle — 各自獨立 dict
				obstacle_arr.append({
					"pos": [pos.x, pos.y],
					"type": obs_type,
					"hp": hp,
					"max_hp": hp,
					"tile_id": tile_id,
				})

			# 實體障礙也加進 blocked_cells → fill_initial 不會放糖,
			# HP=0 時 game_board._damage_obstacle 會把它從 blocked 移除,
			# 接著 cascade 的 gravity 自然會讓糖落下來補洞。
			if _is_blocking_obstacle(tile_id):
				blocked_arr.append(pos)

	# Pass 2:upper layer 的 Rope/Mud — 同樣 block + obstacle
	# 若該 pos 已經有 middle obstacle,跳過(避免 obs_map 被 overwrite)
	for r in range(min(upper_grid.size(), rows)):
		var row_data = upper_grid[r]
		if typeof(row_data) != TYPE_ARRAY:
			continue
		for c in range(cols):
			if c >= row_data.size():
				continue
			var raw = str(row_data[c])
			if raw == "" or raw == "null" or raw == "void":
				continue
			var pos = Vector2i(c, r)
			if pos in blocked_arr:
				continue  # 已被 middle 占用
			var tid = raw.split("#", true, 1)[0]
			var obs_type = _resolve_obstacle_type(tid)
			if obs_type:
				obstacle_arr.append({
					"pos": [c, r],
					"type": obs_type,
					"hp": _resolve_obstacle_hp(tid),
					"tile_id": tid,
					"layer": "upper",
				})
				if _is_blocking_obstacle(tid):
					blocked_arr.append(pos)

	# Pass 3:bottom layer 的 Puddle — 同樣 block + obstacle
	for r in range(min(bottom_grid.size(), rows)):
		var row_data = bottom_grid[r]
		if typeof(row_data) != TYPE_ARRAY:
			continue
		for c in range(cols):
			if c >= row_data.size():
				continue
			var raw = str(row_data[c])
			if raw == "" or raw == "null" or raw == "void":
				continue
			var pos = Vector2i(c, r)
			if pos in blocked_arr:
				continue
			var tid = raw.split("#", true, 1)[0]
			var obs_type = _resolve_obstacle_type(tid)
			if obs_type:
				obstacle_arr.append({
					"pos": [c, r],
					"type": obs_type,
					"hp": _resolve_obstacle_hp(tid),
					"tile_id": tid,
					"layer": "bottom",
				})
				if _is_blocking_obstacle(tid):
					blocked_arr.append(pos)

	level.blocked_cells = blocked_arr
	level.obstacle_data = obstacle_arr

	return level


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
static func _resolve_element_color(tile_id: String) -> int:
	if ELEMENT_TO_COLOR_INDEX.has(tile_id):
		return ELEMENT_TO_COLOR_INDEX[tile_id]
	return -1


static func _resolve_obstacle_type(tile_id: String):
	for prefix in OBSTACLE_TYPE_MAP.keys():
		if tile_id.begins_with(prefix):
			return OBSTACLE_TYPE_MAP[prefix]
	return null


static func _resolve_obstacle_hp(tile_id: String) -> int:
	# 從 tile_id 末尾數字解析 HP,例如 "Crt3" → 3
	var match_lv = tile_id.find("_lv")
	if match_lv >= 0:
		var num_str = tile_id.substr(match_lv + 3)
		var n = int(num_str)
		if n > 0:
			return n
	# Crt1, Crt2, Crt3, Crt4 等沒有 _lv 字尾:取最後一位數字
	var last_char = tile_id.right(1)
	if last_char.is_valid_int():
		var n = int(last_char)
		if n > 0:
			return n
	return 1


static func _is_powerup(tile_id: String) -> bool:
	return tile_id in ["Soda0d", "Soda90", "TNT", "TrPr", "LtBl"]


# ---------------------------------------------------------------------------
# Demo helper:列出 res://levels/ 下的所有 .json
# ---------------------------------------------------------------------------
static func list_demo_levels() -> Array[String]:
	var result: Array[String] = []
	var dir = DirAccess.open("res://levels/")
	if dir == null:
		return result
	dir.list_dir_begin()
	var file = dir.get_next()
	while file != "":
		if file.ends_with(".json") and not dir.current_is_dir():
			result.append("res://levels/" + file)
		file = dir.get_next()
	dir.list_dir_end()
	result.sort()
	return result
