extends Node
##
## AI Controller — 對齊 Python scripts/ai_player.py 的完整策略
##
## 決策流程：
##   1. 掃描所有合法 swap → 模擬 match → 打分
##   2. 道具組合：精確計算 combo 爆炸範圍
##   3. 戰術移動：道具移到更好位置再引爆
##   4. 單點道具：直接啟動
##
## 讀取 ai_weights.json 共用權重（和 Python 版一致）
##

const MatchFinder = preload("res://scripts/board/match_finder.gd")
const CandyScript = preload("res://scripts/candy/candy.gd")

# === 權重（從 ai_weights.json 載入） ===
var weight_element: float = 1.0
var weight_obstacle: float = 5.0
var weight_goal_obstacle: float = 20.0
var bonus_ltbl: float = 15.0
var bonus_tnt: float = 8.0
var bonus_soda: float = 5.0
var bonus_trpr: float = 6.0
var cost_normal_prop: float = 2.0
var cost_rainbow: float = 10.0
var endgame_obstacle_threshold: int = 10


func _ready() -> void:
	_load_weights()


func _load_weights() -> void:
	var path = "res://ai_weights.json"
	if not FileAccess.file_exists(path):
		path = "user://ai_weights.json"
		if not FileAccess.file_exists(path):
			return
	var f = FileAccess.open(path, FileAccess.READ)
	if f == null:
		return
	var json_text = f.get_as_text()
	f.close()
	var json = JSON.new()
	if json.parse(json_text) != OK:
		return
	var data: Dictionary = json.data
	weight_element = data.get("weight_element", weight_element)
	weight_obstacle = data.get("weight_obstacle", weight_obstacle)
	weight_goal_obstacle = data.get("weight_goal_obstacle", weight_goal_obstacle)
	bonus_ltbl = data.get("bonus_ltbl", bonus_ltbl)
	bonus_tnt = data.get("bonus_tnt", bonus_tnt)
	bonus_soda = data.get("bonus_soda", bonus_soda)
	bonus_trpr = data.get("bonus_trpr", bonus_trpr)
	cost_normal_prop = data.get("cost_normal_prop", cost_normal_prop)
	cost_rainbow = data.get("cost_rainbow", cost_rainbow)
	endgame_obstacle_threshold = int(data.get("endgame_obstacle_threshold", endgame_obstacle_threshold))


## 主要介面：找最佳動作
## 回傳 Dictionary: {"type": "swap", "pos1": Vector2i, "pos2": Vector2i}
##                或 {"type": "activate", "pos": Vector2i}
##                或 {} (無可行動作)
func find_best_action(board: Node2D) -> Dictionary:
	if board.filler == null or board.filler.grid.is_empty():
		return {}
	var grid = board.filler.grid
	var width: int = board.grid_width
	var height: int = board.grid_height
	var blocked: Array[Vector2i] = board.blocked_cells
	var obstacle_map: Dictionary = board.obstacle_map
	var bottom_map: Dictionary = board.bottom_obstacle_map
	var goals: Dictionary = _get_goals()

	var total_goal_obs: int = _count_goal_obstacles(grid, width, height, obstacle_map, bottom_map, goals)
	var is_endgame: bool = total_goal_obs <= endgame_obstacle_threshold

	var candidates: Array = []  # [[score, action_dict], ...]

	# 1. 掃描所有 swap
	for y in height:
		for x in width:
			for dir in [Vector2i(1, 0), Vector2i(0, 1)]:
				var nx = x + dir.x
				var ny = y + dir.y
				if nx >= width or ny >= height:
					continue
				var pos_a = Vector2i(x, y)
				var pos_b = Vector2i(nx, ny)

				if pos_a in blocked or pos_b in blocked:
					continue
				var candy_a = grid[x][y] as CandyScript
				var candy_b = grid[nx][ny] as CandyScript
				if candy_a == null and candy_b == null:
					continue
				if candy_a == null or candy_b == null:
					# one is null — check if movable obstacle swap
					continue

				# Check rope lock
				if _is_locked(pos_a, board) or _is_locked(pos_b, board):
					continue

				var is_prop_a = _is_powerup(candy_a)
				var is_prop_b = _is_powerup(candy_b)

				# 2. 道具組合
				if is_prop_a and is_prop_b:
					var score = _evaluate_combo(
						candy_a, candy_b, pos_b,
						grid, width, height, obstacle_map, bottom_map, goals,
						is_endgame, total_goal_obs
					)
					if score > 0:
						candidates.append([score, {"type": "swap", "pos1": pos_a, "pos2": pos_b}])
					continue

				# LtBl + element
				if is_prop_a and candy_a.candy_type == CandyScript.CandyType.COLOR_BOMB:
					if not is_prop_b and candy_b.candy_type == CandyScript.CandyType.NORMAL:
						var score = _evaluate_rainbow_element(
							candy_b.candy_color, grid, width, height,
							obstacle_map, bottom_map, goals, is_endgame
						)
						if score > 0:
							candidates.append([score, {"type": "swap", "pos1": pos_a, "pos2": pos_b}])
						continue
				if is_prop_b and candy_b.candy_type == CandyScript.CandyType.COLOR_BOMB:
					if not is_prop_a and candy_a.candy_type == CandyScript.CandyType.NORMAL:
						var score = _evaluate_rainbow_element(
							candy_a.candy_color, grid, width, height,
							obstacle_map, bottom_map, goals, is_endgame
						)
						if score > 0:
							candidates.append([score, {"type": "swap", "pos1": pos_a, "pos2": pos_b}])
						continue

				# 3. 戰術移動
				if is_prop_a and not is_prop_b:
					var tac = _evaluate_tactical(
						candy_a, pos_a, pos_b,
						grid, width, height, blocked, obstacle_map, bottom_map, goals,
						is_endgame, total_goal_obs
					)
					if tac > 0:
						candidates.append([tac, {"type": "swap", "pos1": pos_a, "pos2": pos_b}])

				if is_prop_b and not is_prop_a:
					var tac = _evaluate_tactical(
						candy_b, pos_b, pos_a,
						grid, width, height, blocked, obstacle_map, bottom_map, goals,
						is_endgame, total_goal_obs
					)
					if tac > 0:
						candidates.append([tac, {"type": "swap", "pos1": pos_a, "pos2": pos_b}])

				# 普通 match
				var score = _evaluate_swap(
					pos_a, pos_b, grid, width, height, blocked,
					obstacle_map, bottom_map, goals
				)
				if score > 0:
					candidates.append([score, {"type": "swap", "pos1": pos_a, "pos2": pos_b}])

	# 4. 道具直接啟動
	for y in height:
		for x in width:
			var pos = Vector2i(x, y)
			if pos in blocked:
				continue
			var candy = grid[x][y] as CandyScript
			if candy == null or not _is_powerup(candy):
				continue
			var score = _evaluate_activate(
				candy, pos, grid, width, height,
				obstacle_map, bottom_map, goals,
				is_endgame, total_goal_obs
			)
			if score > 0:
				candidates.append([score, {"type": "activate", "pos": pos}])

	if candidates.is_empty():
		return {}

	# 取最高分
	candidates.sort_custom(func(a, b): return a[0] > b[0])
	var top_score = candidates[0][0]
	var top_actions: Array = []
	for c in candidates:
		if c[0] == top_score:
			top_actions.append(c[1])
		else:
			break
	return top_actions[randi() % top_actions.size()]


# ===========================================================================
# Swap 評分（普通 match）
# ===========================================================================

func _evaluate_swap(
	pos_a: Vector2i, pos_b: Vector2i,
	grid: Array, width: int, height: int, blocked: Array[Vector2i],
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> float:
	# 暫時 swap
	var candy_a = grid[pos_a.x][pos_a.y]
	var candy_b = grid[pos_b.x][pos_b.y]
	grid[pos_a.x][pos_a.y] = candy_b
	grid[pos_b.x][pos_b.y] = candy_a

	var matches = MatchFinder.find_all_matches(grid, width, height, blocked)

	# swap back
	grid[pos_a.x][pos_a.y] = candy_a
	grid[pos_b.x][pos_b.y] = candy_b

	if matches.is_empty():
		return -1.0
	return _score_matches(matches, grid, width, height, obstacle_map, bottom_map, goals)


func _score_matches(
	matches: Array, grid: Array, width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> float:
	var score: float = 0.0
	for m in matches:
		var cells: Array = m.get("cells", [])
		score += cells.size() * weight_element

		for cell_pos in cells:
			var pos: Vector2i = cell_pos as Vector2i
			# bottom obstacle (Puddle)
			if bottom_map.has(pos):
				var tid: String = bottom_map[pos].get("tile_id", "")
				score += weight_goal_obstacle if _is_goal_tile(tid, goals) else weight_obstacle
			# 4-neighbor obstacles
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var np = pos + offset
				if np.x < 0 or np.x >= width or np.y < 0 or np.y >= height:
					continue
				if obstacle_map.has(np):
					var tid: String = obstacle_map[np].get("tile_id", "")
					score += weight_goal_obstacle if _is_goal_tile(tid, goals) else weight_obstacle

		# 道具合成獎勵
		var shape: String = m.get("shape", "")
		match shape:
			"five":
				score += bonus_ltbl
			"special":
				score += bonus_tnt
			"four":
				score += bonus_soda
			"block_2x2":
				score += bonus_trpr

	return score


# ===========================================================================
# 道具 Combo
# ===========================================================================

func _evaluate_combo(
	candy_a: CandyScript, candy_b: CandyScript, center: Vector2i,
	grid: Array, width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary,
	is_endgame: bool, total_goal_obs: int
) -> float:
	var t1 = _get_prop_type(candy_a)
	var t2 = _get_prop_type(candy_b)

	# Rainbow + anything
	if t1 == "RAINBOW" or t2 == "RAINBOW":
		var other = t2 if t1 == "RAINBOW" else t1
		if other in ["BOMB", "ROCKET", "PROPELLER", "RAINBOW"]:
			return 999.0
		return 0.0

	var types = [t1, t2]
	types.sort()

	var area_cells: Array[Vector2i] = []
	if types == ["BOMB", "BOMB"]:
		area_cells = _get_area(center, "7x7", width, height)
	elif types == ["BOMB", "ROCKET"]:
		area_cells = _get_area(center, "cross_3", width, height)
	elif types == ["ROCKET", "ROCKET"]:
		area_cells = _get_area(center, "cross_1", width, height)
	elif "PROPELLER" in types:
		var base_cells = _get_area(center, "1x1_cross", width, height)
		var base_score = _count_obstacles_in(base_cells, obstacle_map, bottom_map, goals)
		var other_type = types[0] if types[1] == "PROPELLER" else types[1]
		if other_type == "PROPELLER":
			return base_score + 3.0
		elif other_type == "BOMB":
			return base_score + _scan_best("5x5", width, height, obstacle_map, bottom_map, goals)
		elif other_type == "ROCKET":
			return base_score + _scan_best("line", width, height, obstacle_map, bottom_map, goals)
		return base_score
	else:
		return 35.0

	var score = _count_obstacles_in(area_cells, obstacle_map, bottom_map, goals)
	var is_lethal = score >= total_goal_obs
	var penalty = 0.0 if (is_endgame or is_lethal) else cost_normal_prop * 2
	return maxf(0.0, score - penalty)


# ===========================================================================
# 戰術移動
# ===========================================================================

func _evaluate_tactical(
	prop_candy: CandyScript, prop_pos: Vector2i, dest_pos: Vector2i,
	grid: Array, width: int, height: int, blocked: Array[Vector2i],
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary,
	is_endgame: bool, total_goal_obs: int
) -> float:
	if prop_candy.candy_type == CandyScript.CandyType.COLOR_BOMB:
		return 0.0

	# 道具移到 dest 後的引爆效益
	var impact = _estimate_impact_at(dest_pos, prop_candy, width, height, obstacle_map, bottom_map, goals)

	# 也算交換後的 match 分
	var candy_a = grid[prop_pos.x][prop_pos.y]
	var candy_b = grid[dest_pos.x][dest_pos.y]
	grid[prop_pos.x][prop_pos.y] = candy_b
	grid[dest_pos.x][dest_pos.y] = candy_a
	var matches = MatchFinder.find_all_matches(grid, width, height, blocked)
	var match_score = _score_matches(matches, grid, width, height, obstacle_map, bottom_map, goals) if not matches.is_empty() else 0.0
	grid[prop_pos.x][prop_pos.y] = candy_a
	grid[dest_pos.x][dest_pos.y] = candy_b

	var best_val = maxf(impact, match_score)
	var is_lethal = best_val >= total_goal_obs
	var penalty = 0.0 if (is_endgame or is_lethal) else cost_normal_prop
	return maxf(0.0, best_val - penalty)


# ===========================================================================
# 道具啟動
# ===========================================================================

func _evaluate_activate(
	candy: CandyScript, pos: Vector2i,
	grid: Array, width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary,
	is_endgame: bool, total_goal_obs: int
) -> float:
	var raw_score = _estimate_impact_at(pos, candy, width, height, obstacle_map, bottom_map, goals)
	var is_lethal = raw_score >= total_goal_obs
	var is_rainbow = (candy.candy_type == CandyScript.CandyType.COLOR_BOMB)
	var penalty = 0.0 if (is_endgame or is_lethal) else (cost_rainbow if is_rainbow else cost_normal_prop)
	return maxf(0.0, raw_score - penalty)


func _estimate_impact_at(
	pos: Vector2i, candy: CandyScript,
	width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> float:
	var cells: Array[Vector2i] = []
	match candy.candy_type:
		CandyScript.CandyType.STRIPED_H:
			for c in width:
				cells.append(Vector2i(c, pos.y))
		CandyScript.CandyType.STRIPED_V:
			for r in height:
				cells.append(Vector2i(pos.x, r))
		CandyScript.CandyType.WRAPPED:
			for dr in range(-1, 2):
				for dc in range(-1, 2):
					cells.append(Vector2i(pos.x + dc, pos.y + dr))
		CandyScript.CandyType.SPIRAL:
			# 紙飛機 = 原位十字 5 格 + 「飛到最高權重目標」再清 1 格(見 game_board 紙飛機落點設計)。
			# 原本只估原地 5 格 → 殘局時最後的目標障礙若不在旁邊會被估成 0,AI 就不啟動它、改去削步數。
			cells.append(pos)
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				cells.append(pos + offset)
			var local_impact := _count_obstacles_in(cells, obstacle_map, bottom_map, goals)
			return local_impact + _best_fly_target_value(cells, obstacle_map, bottom_map, goals)
		CandyScript.CandyType.COLOR_BOMB:
			# 清最多色
			return _estimate_rainbow_impact(pos, width, height, obstacle_map, bottom_map, goals)
	return _count_obstacles_in(cells, obstacle_map, bottom_map, goals)


# 紙飛機/螺旋槳會「飛到最高權重目標」再清 1 格 → 盤上只要還有目標障礙,啟動它就等於能清掉 1 個目標。
# (排除已算進原位十字的格,避免重複計)
func _best_fly_target_value(
	exclude: Array, obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> float:
	var has_any := false
	for p in obstacle_map:
		if p in exclude:
			continue
		has_any = true
		if _is_goal_tile(obstacle_map[p].get("tile_id", ""), goals):
			return weight_goal_obstacle
	for p in bottom_map:
		if p in exclude:
			continue
		has_any = true
		if _is_goal_tile(bottom_map[p].get("tile_id", ""), goals):
			return weight_goal_obstacle
	return weight_obstacle if has_any else 0.0


func _evaluate_rainbow_element(
	target_color: int, grid: Array, width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary,
	is_endgame: bool
) -> float:
	var cells: Array[Vector2i] = []
	for x in width:
		for y in height:
			var c = grid[x][y] as CandyScript
			if c != null and c.candy_type == CandyScript.CandyType.NORMAL and c.candy_color == target_color:
				cells.append(Vector2i(x, y))
	var score = _count_obstacles_in(cells, obstacle_map, bottom_map, goals)
	score += cells.size() * weight_element
	var penalty = 0.0 if is_endgame else cost_rainbow
	return maxf(0.0, score - penalty)


func _estimate_rainbow_impact(
	pos: Vector2i, width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> float:
	# 找場上最多的顏色，估算清光後的分數
	# 簡化：直接回傳一個保守估計
	return weight_goal_obstacle * 3.0


# ===========================================================================
# Area helpers
# ===========================================================================

func _get_area(center: Vector2i, area_type: String, width: int, height: int) -> Array[Vector2i]:
	var cells: Array[Vector2i] = []
	match area_type:
		"7x7":
			for r in range(maxi(0, center.y - 3), mini(height, center.y + 4)):
				for c in range(maxi(0, center.x - 3), mini(width, center.x + 4)):
					cells.append(Vector2i(c, r))
		"cross_3":
			for r in range(maxi(0, center.y - 1), mini(height, center.y + 2)):
				for c in width:
					cells.append(Vector2i(c, r))
			for c in range(maxi(0, center.x - 1), mini(width, center.x + 2)):
				for r in height:
					var p = Vector2i(c, r)
					if p not in cells:
						cells.append(p)
		"cross_1":
			for c in width:
				cells.append(Vector2i(c, center.y))
			for r in height:
				var p = Vector2i(center.x, r)
				if p not in cells:
					cells.append(p)
		"5x5":
			for r in range(maxi(0, center.y - 2), mini(height, center.y + 3)):
				for c in range(maxi(0, center.x - 2), mini(width, center.x + 3)):
					cells.append(Vector2i(c, r))
		"1x1_cross":
			cells.append(center)
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var np = center + offset
				if np.x >= 0 and np.x < width and np.y >= 0 and np.y < height:
					cells.append(np)
	return cells


func _count_obstacles_in(
	cells: Array[Vector2i],
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> float:
	var score: float = 0.0
	var counted: Dictionary = {}
	for pos in cells:
		if obstacle_map.has(pos):
			var key = str(pos) + "_mid"
			if not counted.has(key):
				counted[key] = true
				var tid: String = obstacle_map[pos].get("tile_id", "")
				score += weight_goal_obstacle if _is_goal_tile(tid, goals) else weight_obstacle
		if bottom_map.has(pos):
			var key = str(pos) + "_bot"
			if not counted.has(key):
				counted[key] = true
				var tid: String = bottom_map[pos].get("tile_id", "")
				score += weight_goal_obstacle if _is_goal_tile(tid, goals) else weight_obstacle
	return score


func _scan_best(impact_type: String, width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> float:
	var max_score: float = 0.0
	for y in height:
		for x in width:
			var center = Vector2i(x, y)
			var cells = _get_area(center, impact_type, width, height)
			var s = _count_obstacles_in(cells, obstacle_map, bottom_map, goals)
			if s > max_score:
				max_score = s
	return max_score


# ===========================================================================
# Utility
# ===========================================================================

func _is_powerup(candy: CandyScript) -> bool:
	if candy == null:
		return false
	return candy.candy_type != CandyScript.CandyType.NORMAL


func _get_prop_type(candy: CandyScript) -> String:
	match candy.candy_type:
		CandyScript.CandyType.COLOR_BOMB:
			return "RAINBOW"
		CandyScript.CandyType.WRAPPED:
			return "BOMB"
		CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V:
			return "ROCKET"
		CandyScript.CandyType.SPIRAL:
			return "PROPELLER"
	return ""


func _is_locked(pos: Vector2i, board: Node2D) -> bool:
	# Rope / Mud locks swap
	if board.obstacle_map.has(pos):
		var obs = board.obstacle_map[pos]
		var tid: String = obs.get("tile_id", "")
		if tid.begins_with("Rope") or tid.begins_with("Mud"):
			return true
	return false


func _is_goal_tile(tile_id: String, goals: Dictionary) -> bool:
	if goals.is_empty():
		return false
	if goals.has(tile_id):
		return true
	var base_tile = tile_id.split("_lv")[0].rstrip("0123456789")
	for goal_id in goals:
		var base_goal = goal_id.split("_lv")[0].rstrip("0123456789")
		if base_goal == base_tile:
			return true
	return false


func _count_goal_obstacles(
	grid: Array, width: int, height: int,
	obstacle_map: Dictionary, bottom_map: Dictionary, goals: Dictionary
) -> int:
	var count: int = 0
	for pos in obstacle_map:
		var tid: String = obstacle_map[pos].get("tile_id", "")
		if _is_goal_tile(tid, goals):
			count += 1
	for pos in bottom_map:
		var tid: String = bottom_map[pos].get("tile_id", "")
		if _is_goal_tile(tid, goals):
			count += 1
	return count


func _get_goals() -> Dictionary:
	var result: Dictionary = {}
	if not GameManager:
		return result
	for obj in GameManager.level_objectives:
		var tid = str(obj.get("tile_id", ""))
		if tid != "":
			result[tid] = int(obj.get("target", 0))
	return result
