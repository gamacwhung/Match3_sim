extends Node

signal level_started(level_id: int)
signal level_completed(level_id: int, score: int, stars: int)
signal level_failed(level_id: int)
signal score_changed(new_score: int)
signal moves_changed(remaining: int)
signal objective_updated(objective: Dictionary)

enum GameState { MENU, WORLD_MAP, PLAYING, PAUSED, LEVEL_COMPLETE, LEVEL_FAILED }

var current_state: GameState = GameState.MENU
var current_level_id: int = 0
var current_score: int = 0
var moves_remaining: int = 0
var max_moves: int = 0
var combo_count: int = 0

var level_objectives: Array[Dictionary] = []
var star_thresholds: Array[int] = []

const POINTS_BASE: int = 50
const COMBO_MULTIPLIER: float = 1.5

func start_level(level_data: Resource) -> void:
	current_level_id = level_data.level_id
	current_score = 0
	moves_remaining = level_data.max_moves
	max_moves = level_data.max_moves
	combo_count = 0
	star_thresholds = level_data.star_thresholds.duplicate()
	level_objectives = level_data.objectives.duplicate(true)
	current_state = GameState.PLAYING
	score_changed.emit(current_score)
	moves_changed.emit(moves_remaining)
	level_started.emit(current_level_id)

func use_move() -> void:
	if current_state != GameState.PLAYING:
		return
	moves_remaining -= 1
	combo_count = 0
	moves_changed.emit(moves_remaining)

func add_score(matched_count: int, is_special: bool = false) -> void:
	var base = POINTS_BASE * matched_count
	if is_special:
		base *= 2
	var multiplier = pow(COMBO_MULTIPLIER, combo_count)
	var points = int(base * multiplier)
	current_score += points
	score_changed.emit(current_score)

func increment_combo() -> void:
	combo_count += 1

func reset_combo() -> void:
	combo_count = 0

func update_objective(obj_type: String, color: int = -1, amount: int = 1, tile_id: String = "") -> void:
	# obj_type 對齊 obstacle type ("clear_jelly", "clear_wire", "clear_ice", "collect")。
	# 對於 obstacle 類目標(clear_*),很多關卡多個 family 都是同一 type(e.g. Crt 跟 Puddle 都是
	# clear_jelly),只用 type 比對會誤增。所以多帶一個 tile_id(被打的 obstacle 的 tile_id):
	# 只更新 tile_id 前綴跟自己同 family 的 objective。
	for obj in level_objectives:
		if obj["type"] != obj_type:
			continue
		if obj.has("color") and color >= 0 and obj["color"] != color:
			continue
		# tile_id 過濾:objective 的 tile_id 是 family (e.g. "Crt") 或 specific (e.g. "Crt2"),
		# 只要 broken obstacle 的 tile_id 「開頭」是 objective 的 tile_id family,就算同類
		if tile_id != "" and obj.has("tile_id") and str(obj["tile_id"]) != "":
			var obj_family = _tile_family(str(obj["tile_id"]))
			var broken_family = _tile_family(tile_id)
			if obj_family != broken_family:
				continue
		obj["current"] = obj.get("current", 0) + amount
		objective_updated.emit(obj)


# 抽 family prefix:截掉尾巴數字(Crt1 → Crt) 跟 _lv* 字尾(Puddle_lv2 → Puddle)
# 以及狀態字尾如 _closed/_open(WaterChiller_closed → WaterChiller)
static func _tile_family(tile_id: String) -> String:
	var s = tile_id.split("#")[0]   # 去 instance tag
	var lv_idx = s.find("_lv")
	if lv_idx >= 0:
		return s.substr(0, lv_idx)
	# 去掉 _closed / _open 狀態後綴
	for suffix in ["_closed", "_open"]:
		if s.ends_with(suffix):
			s = s.substr(0, s.length() - suffix.length())
			break
	# 截掉尾巴連續數字(Crt1 → Crt、Crt12 → Crt)
	var i = s.length()
	while i > 0 and s.substr(i - 1, 1).is_valid_int():
		i -= 1
	return s.substr(0, i) if i > 0 else s

func check_win_condition() -> bool:
	for obj in level_objectives:
		if obj["type"] == "score":
			if current_score < obj["target"]:
				return false
		else:
			if obj.get("current", 0) < obj["target"]:
				return false
	return true

func check_lose_condition() -> bool:
	return moves_remaining <= 0

func calculate_stars() -> int:
	var stars = 0
	for threshold in star_thresholds:
		if current_score >= threshold:
			stars += 1
	return stars

func complete_level() -> void:
	current_state = GameState.LEVEL_COMPLETE
	var stars = calculate_stars()
	SaveManager.save_level_progress(current_level_id, current_score, stars)
	level_completed.emit(current_level_id, current_score, stars)

func fail_level() -> void:
	current_state = GameState.LEVEL_FAILED
	level_failed.emit(current_level_id)

func change_state(new_state: GameState) -> void:
	current_state = new_state
