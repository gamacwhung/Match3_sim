extends Node2D

const MatchFinder = preload("res://scripts/board/match_finder.gd")
const CandyScript = preload("res://scripts/candy/candy.gd")
const CandyFactory = preload("res://scripts/candy/candy_factory.gd")
const SpecialCandy = preload("res://scripts/candy/special_candy.gd")

@export var grid_width: int = 9
@export var grid_height: int = 9
@export var cell_size: float = 70.0

@onready var candy_container: Node2D = $CandyContainer
@onready var board_bg: Node2D = $BoardBG
@onready var filler_node: Node = $BoardFiller
@onready var effect_spawner_node: Node2D = $EffectSpawner

var candy_scene: PackedScene = preload("res://scenes/candy.tscn")
var filler: Node
var board_offset: Vector2 = Vector2.ZERO
var blocked_cells: Array[Vector2i] = []
var obstacle_map: Dictionary = {}

var selected_candy: CandyScript = null
var is_processing: bool = false
var cascade_level: int = 0

var _hint_timer: float = 0.0
var _hint_delay: float = 3.0
var _hint_candies: Array = []
var _hint_shown: bool = false

signal board_ready
signal turn_completed
signal candies_destroyed(count: int, color: int)

func _ready() -> void:
	_calculate_offset()

func _process(delta: float) -> void:
	if filler == null or is_processing or _hint_shown:
		return
	_hint_timer += delta
	if _hint_timer >= _hint_delay:
		_show_hint()

func _reset_hint_timer() -> void:
	_hint_timer = 0.0
	if _hint_shown:
		_clear_hint()

func _show_hint() -> void:
	var move = MatchFinder.find_hint_move(filler.grid, grid_width, grid_height, blocked_cells)
	if move.size() < 2:
		return
	_hint_shown = true
	for pos in move:
		var candy = filler.get_candy_at(pos)
		if candy and is_instance_valid(candy):
			candy.play_hint()
			_hint_candies.append(candy)

func _clear_hint() -> void:
	for candy in _hint_candies:
		if is_instance_valid(candy):
			candy.stop_hint()
	_hint_candies.clear()
	_hint_shown = false

func _calculate_offset() -> void:
	var board_width = grid_width * cell_size
	var board_height = grid_height * cell_size
	var viewport_size = get_viewport_rect().size
	board_offset = Vector2(
		(viewport_size.x - board_width) / 2.0,
		(viewport_size.y - board_height) / 2.0 + 60
	)
	position = Vector2.ZERO

func init_board(level_data: Resource = null) -> void:
	_clear_board()
	if level_data:
		grid_width = level_data.grid_width
		grid_height = level_data.grid_height
		blocked_cells = level_data.blocked_cells.duplicate()
	_calculate_offset()
	filler = filler_node
	filler.setup(grid_width, grid_height, cell_size, board_offset, candy_container, candy_scene, blocked_cells)
	if level_data and level_data.num_colors > 0:
		filler.num_colors = level_data.num_colors
	_draw_board_background()
	filler.fill_initial()
	_connect_candy_signals()

	var retry_count = 0
	while MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells).size() > 0 and retry_count < 50:
		_clear_board()
		filler.setup(grid_width, grid_height, cell_size, board_offset, candy_container, candy_scene, blocked_cells)
		if level_data and level_data.num_colors > 0:
			filler.num_colors = level_data.num_colors
		filler.fill_initial()
		_connect_candy_signals()
		retry_count += 1

	board_ready.emit()

func _clear_board() -> void:
	for child in candy_container.get_children():
		child.queue_free()

func _draw_board_background() -> void:
	board_bg.queue_redraw()

func _connect_candy_signals() -> void:
	for x in grid_width:
		for y in grid_height:
			var candy = filler.get_candy_at(Vector2i(x, y))
			if candy:
				_connect_single_candy(candy)

func _connect_single_candy(candy: CandyScript) -> void:
	if not candy.candy_selected.is_connected(_on_candy_selected):
		candy.candy_selected.connect(_on_candy_selected)
	if not candy.candy_swipe.is_connected(_on_candy_swiped):
		candy.candy_swipe.connect(_on_candy_swiped)

func _on_candy_selected(candy: CandyScript) -> void:
	if is_processing:
		return
	_reset_hint_timer()

	if selected_candy == null:
		selected_candy = candy
		candy.set_selected(true)
		return

	# 我們的設計:同顆 special candy 被連點兩次 → 直接觸發(像 tap 觸發)
	if selected_candy == candy:
		if candy.candy_type != CandyScript.CandyType.NORMAL:
			selected_candy.set_selected(false)
			selected_candy = null
			_activate_special_directly(candy)
			return
		# normal candy 點兩次 → 取消選取
		selected_candy.set_selected(false)
		selected_candy = null
		return

	var dist = (candy.grid_pos - selected_candy.grid_pos).abs()
	if (dist.x == 1 and dist.y == 0) or (dist.x == 0 and dist.y == 1):
		_try_swap(selected_candy, candy)
	else:
		selected_candy.set_selected(false)
		selected_candy = candy
		candy.set_selected(true)


func _activate_special_directly(candy: CandyScript) -> void:
	# 單擊 special candy 直接觸發 — 我們專案的設計
	# COLOR_BOMB → 隨機選一色,清光該色所有 candy
	# STRIPED/WRAPPED → 觸發自身效果,消除自己
	is_processing = true
	GameManager.use_move()
	cascade_level = 0
	AudioManager.play_special_trigger_sound()
	var pos = candy.grid_pos
	var ct = candy.candy_type
	
	if ct == CandyScript.CandyType.COLOR_BOMB:
		var num_colors_local = 4
		if filler:
			num_colors_local = filler.num_colors
		var target_color = randi() % num_colors_local
		effect_spawner_node.spawn_firework(filler.grid_to_world(pos))
		# 自己先消除
		_trigger_obstacle_adjacent(pos)
		effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), candy.candy_color)
		filler.remove_candy_at(pos)
		candy.animate_destroy()
		# 清光同色
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c and not c.is_being_destroyed and c.candy_color == target_color:
					_trigger_obstacle_adjacent(Vector2i(x, y))
					effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(Vector2i(x, y)), target_color)
					filler.remove_candy_at(Vector2i(x, y))
					c.animate_destroy()
					candies_destroyed.emit(1, target_color)
	else:
		# STRIPED/WRAPPED:觸發自身,然後消除自己
		_trigger_special_candy(candy)
		_trigger_obstacle_adjacent(pos)
		effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), candy.candy_color)
		filler.remove_candy_at(pos)
		candy.animate_destroy()
		candies_destroyed.emit(1, candy.candy_color)
	
	await get_tree().create_timer(0.3).timeout
	await _cascade_loop()
	_post_turn_check()

func _on_candy_swiped(candy: CandyScript, direction: Vector2i) -> void:
	if is_processing:
		return
	_reset_hint_timer()
	# 滑動一律 = swap(normal 跟 special 都一樣)。
	# special candy 想觸發:點兩次同一顆。
	var target_pos = candy.grid_pos + direction
	if target_pos.x < 0 or target_pos.x >= grid_width or target_pos.y < 0 or target_pos.y >= grid_height:
		return
	if Vector2i(target_pos.x, target_pos.y) in blocked_cells:
		return
	var target_candy = filler.get_candy_at(target_pos)
	if target_candy == null:
		return
	if _is_candy_locked(candy.grid_pos) or _is_candy_locked(target_pos):
		return
	if selected_candy:
		selected_candy.set_selected(false)
		selected_candy = null
	_try_swap(candy, target_candy)

func _is_candy_locked(pos: Vector2i) -> bool:
	if obstacle_map.has(pos):
		var obs = obstacle_map[pos]
		if obs.has("type") and obs["type"] == "wire":
			return true
	return false

func _try_swap(candy_a: CandyScript, candy_b: CandyScript) -> void:
	is_processing = true
	_reset_hint_timer()
	if selected_candy:
		selected_candy.set_selected(false)
		selected_candy = null
	AudioManager.play_swap_sound()

	var pos_a = candy_a.grid_pos
	var pos_b = candy_b.grid_pos
	var world_a = filler.grid_to_world(pos_a)
	var world_b = filler.grid_to_world(pos_b)

	filler.set_candy_at(pos_a, candy_b)
	filler.set_candy_at(pos_b, candy_a)
	candy_a.grid_pos = pos_b
	candy_b.grid_pos = pos_a

	var tween_a = candy_a.animate_to(world_b, 0.2)
	candy_b.animate_to(world_a, 0.2)
	await tween_a.finished

	if candy_a.candy_type == CandyScript.CandyType.COLOR_BOMB or candy_b.candy_type == CandyScript.CandyType.COLOR_BOMB:
		_handle_color_bomb_swap(candy_a, candy_b)
		return

	var combo = CandyFactory.get_combo_result(candy_a.candy_type, candy_b.candy_type)
	if combo["effect"] != "none":
		GameManager.use_move()
		cascade_level = 0
		await _handle_special_combo(candy_a, candy_b, combo["effect"])
		_post_turn_check()
		return

	var matches = MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)
	if matches.size() == 0:
		# 沒形成 match。但如果有一邊是 special candy(STRIPED/WRAPPED),
		# 把它滑過去其實是有意義的施放動作 — 直接觸發那顆 special。
		# 這是 Candy Crush 設計慣例:special+normal swap → 觸發 special。
		var a_special = candy_a.candy_type != CandyScript.CandyType.NORMAL
		var b_special = candy_b.candy_type != CandyScript.CandyType.NORMAL
		if a_special or b_special:
			var trigger_candy = candy_a if a_special else candy_b
			var trigger_pos = trigger_candy.grid_pos
			GameManager.use_move()
			cascade_level = 0
			AudioManager.play_special_trigger_sound()
			_trigger_special_candy(trigger_candy)
			_trigger_obstacle_adjacent(trigger_pos)
			effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(trigger_pos), trigger_candy.candy_color)
			filler.remove_candy_at(trigger_pos)
			trigger_candy.animate_destroy()
			candies_destroyed.emit(1, trigger_candy.candy_color)
			await get_tree().create_timer(0.3).timeout
			await _cascade_loop()
			_post_turn_check()
			return
		# 兩邊都是 normal candy 又沒 match → 真的無效,換回去
		AudioManager.play_swap_back_sound()
		filler.set_candy_at(pos_a, candy_a)
		filler.set_candy_at(pos_b, candy_b)
		candy_a.grid_pos = pos_a
		candy_b.grid_pos = pos_b
		var tween_back = candy_a.animate_to(world_a, 0.2)
		candy_b.animate_to(world_b, 0.2)
		await tween_back.finished
		is_processing = false
		return

	GameManager.use_move()
	cascade_level = 0
	# 把玩家 swap 的兩格傳進去:_process_matches 內如果這個 group 內含 swap 格,
	# 會用 swap_dest 當合成位置,避免 special candy 出現在「離手指很遠」的格
	await _process_matches(matches, [pos_a, pos_b])
	_post_turn_check()

func _handle_color_bomb_swap(candy_a: CandyScript, candy_b: CandyScript) -> void:
	GameManager.use_move()
	cascade_level = 0
	var bomb: CandyScript = null
	var other: CandyScript = null

	if candy_a.candy_type == CandyScript.CandyType.COLOR_BOMB:
		bomb = candy_a
		other = candy_b
	else:
		bomb = candy_b
		other = candy_a

	var target_color = other.candy_color
	AudioManager.play_special_trigger_sound()

	if other.candy_type == CandyScript.CandyType.COLOR_BOMB:
		# COLOR_BOMB + COLOR_BOMB: 整盤全消(走 _explode_cells,任何 special 也會 chain
		# — 雖然全盤都會被消,chain 沒視覺差異,但邏輯一致)
		var to_destroy: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null:
					to_destroy.append(Vector2i(x, y))
		effect_spawner_node.spawn_firework(filler.grid_to_world(bomb.grid_pos))
		_explode_cells(to_destroy)

	elif other.candy_type in [CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V]:
		# COLOR_BOMB + STRIPED: 全盤同色 candy 變 STRIPED → 一起觸發(_explode_cells 帶 chain)
		_destroy_candy_at(bomb.grid_pos, target_color)
		_destroy_candy_at(other.grid_pos, target_color)
		var targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color:
					targets.append(Vector2i(x, y))
		for pos in targets:
			var c = filler.get_candy_at(pos)
			if c and not c.is_being_destroyed:
				var striped_type = [CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V].pick_random()
				c.set_candy_type(striped_type)
				effect_spawner_node.spawn_special_destroy_effect(filler.grid_to_world(pos), target_color)
		await get_tree().create_timer(0.4).timeout
		_explode_cells(targets)

	elif other.candy_type == CandyScript.CandyType.WRAPPED:
		# COLOR_BOMB + WRAPPED: 全盤同色 candy 變 WRAPPED → 一起觸發(chain)
		_destroy_candy_at(bomb.grid_pos, target_color)
		_destroy_candy_at(other.grid_pos, target_color)
		var targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color:
					targets.append(Vector2i(x, y))
		for pos in targets:
			var c = filler.get_candy_at(pos)
			if c and not c.is_being_destroyed:
				c.set_candy_type(CandyScript.CandyType.WRAPPED)
				effect_spawner_node.spawn_special_destroy_effect(filler.grid_to_world(pos), target_color)
		await get_tree().create_timer(0.4).timeout
		_explode_cells(targets)

	elif other.candy_type == CandyScript.CandyType.SPIRAL:
		# COLOR_BOMB + SPIRAL(光球 + 紙飛機):全盤同色 candy 變 SPIRAL → 一起觸發
		# (對應設計文件「紙風車 + 道具:盤面最多元素變該道具」,類比同色 → 道具)
		_destroy_candy_at(bomb.grid_pos, target_color)
		_destroy_candy_at(other.grid_pos, target_color)
		var targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color:
					targets.append(Vector2i(x, y))
		for pos in targets:
			var c = filler.get_candy_at(pos)
			if c and not c.is_being_destroyed:
				c.set_candy_type(CandyScript.CandyType.SPIRAL)
				effect_spawner_node.spawn_special_destroy_effect(filler.grid_to_world(pos), target_color)
		await get_tree().create_timer(0.4).timeout
		_explode_cells(targets)

	else:
		# COLOR_BOMB + NORMAL: 同色全消(用 _explode_cells 走連鎖,
		# 萬一同色 candy 裡有 special — 雖然 match_finder 排除 NORMAL 之外,
		# 但可能是上回合留下的 special 撞同色,也會 chain trigger)
		_destroy_candy_at(bomb.grid_pos, target_color)
		var nc_targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color:
					nc_targets.append(Vector2i(x, y))
		_explode_cells(nc_targets)

	await get_tree().create_timer(0.3).timeout
	await _cascade_loop()
	_post_turn_check()

func _destroy_candy_at(pos: Vector2i, color_for_signal: int) -> void:
	var c = filler.get_candy_at(pos)
	if c and not c.is_being_destroyed:
		_trigger_obstacle_adjacent(pos)
		effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), c.candy_color)
		filler.remove_candy_at(pos)
		c.animate_destroy()
		GameManager.add_score(1, true)
		candies_destroyed.emit(1, color_for_signal)


# ===========================================================================
# 連鎖消除 (chain reaction)
# ---------------------------------------------------------------------------
# 設計需求(user 確認):
#   - TNT 爆炸範圍內如果有 Soda / TrPr / 彩球 → 它們也要被觸發
#   - Soda 火箭路徑上有 TNT → TNT 也炸
#   - 彩球被波及 → 也要清同色
#
# 實作:用兩個 helper,所有「批次消除目標 cell」的地方都改走它們
#   _explode_cells(targets): 對每個 target 銷毀 candy;若是 special candy → 觸發 _chain_trigger
#   _chain_trigger(type, pos, color): 觸發 special 的 effect → 對 effect 範圍呼叫 _explode_cells
# 兩者互相 recursive,自然就有 cascade。
# is_being_destroyed flag 防止重複觸發同一格,避免無限遞迴。
# ===========================================================================

func _explode_cells(targets: Array) -> void:
	# targets: Array of Vector2i (untyped Array 接受 Array[Vector2i] / array literal)
	# 對每個 target 銷毀 candy + 鄰邊 obstacle damage。若 candy 本身是 special,加入 chain queue 觸發。
	var chain_queue: Array = []
	for tp in targets:
		var pos: Vector2i = tp as Vector2i
		var c = filler.get_candy_at(pos)
		if c == null or c.is_being_destroyed:
			# 已被別人消掉,仍對鄰邊 obstacle 算一次傷害(例如 TNT 範圍掃過已破的格)
			_trigger_obstacle_adjacent(pos)
			continue
		var ct = c.candy_type
		var color = c.candy_color
		if ct != CandyScript.CandyType.NORMAL:
			# 是 special candy → 加入連鎖佇列,先記下,destroy 後再觸發 effect
			chain_queue.append({"pos": pos, "type": ct, "color": color})
		_trigger_obstacle_adjacent(pos)
		effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), color)
		filler.remove_candy_at(pos)
		c.animate_destroy()
		candies_destroyed.emit(1, color)
	# 連鎖:對每個被波及的 special candy 觸發其 effect
	# (此時該 special candy 已 remove,_chain_trigger 不會再 destroy 自己)
	for ch in chain_queue:
		_chain_trigger(ch["type"], ch["pos"], ch["color"])


func _chain_trigger(ct: int, pos: Vector2i, color: int) -> void:
	# 觸發指定 candy_type 的 effect at pos。pos 上的 candy 已被消除(由 _explode_cells 處理),
	# 這裡只負責收集 effect 範圍 + 呼叫 _explode_cells(targets)。recursive 經由 _explode_cells 串起來。
	var sub_targets: Array[Vector2i] = []
	match ct:
		CandyScript.CandyType.STRIPED_H:
			AudioManager.play_special_trigger_sound()
			for x in grid_width:
				if x != pos.x:
					sub_targets.append(Vector2i(x, pos.y))
		CandyScript.CandyType.STRIPED_V:
			AudioManager.play_special_trigger_sound()
			for y in grid_height:
				if y != pos.y:
					sub_targets.append(Vector2i(pos.x, y))
		CandyScript.CandyType.WRAPPED:
			AudioManager.play_special_trigger_sound()
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(pos))
			sub_targets = SpecialCandy.get_wrapped_targets(pos, grid_width, grid_height)
		CandyScript.CandyType.SPIRAL:
			AudioManager.play_special_trigger_sound()
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(pos))
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					sub_targets.append(tp)
		CandyScript.CandyType.COLOR_BOMB:
			# 連鎖中的彩球:清掉隨機色(沒人 swap 給它指定色)
			AudioManager.play_special_trigger_sound()
			effect_spawner_node.spawn_firework(filler.grid_to_world(pos))
			var num_colors_local = filler.num_colors if filler else 4
			var picked = randi() % num_colors_local
			for x in grid_width:
				for y in grid_height:
					var p = Vector2i(x, y)
					var c2 = filler.get_candy_at(p)
					if c2 and not c2.is_being_destroyed and c2.candy_color == picked:
						sub_targets.append(p)
	_explode_cells(sub_targets)

func _handle_special_combo(candy_a: CandyScript, candy_b: CandyScript, effect: String) -> void:
	var pos_a = candy_a.grid_pos
	var pos_b = candy_b.grid_pos
	var mid_pos = pos_a
	AudioManager.play_special_trigger_sound()

	match effect:
		"double_striped":
			# Cross elimination: full row + full column
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color)
			_destroy_candy_at(pos_b, candy_b.candy_color)
			_explode_cells(SpecialCandy.get_cross_targets(mid_pos, grid_width, grid_height))

		"double_wrapped":
			# 7×7 big explosion (TNT + TNT,半徑 3)
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			effect_spawner_node.spawn_firework(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color)
			_destroy_candy_at(pos_b, candy_b.candy_color)
			_explode_cells(SpecialCandy.get_big_wrapped_targets(mid_pos, grid_width, grid_height))

		"wrapped_striped":
			# Giant cross: 3 rows + 3 columns
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color)
			_destroy_candy_at(pos_b, candy_b.candy_color)
			var ws_targets: Array[Vector2i] = []
			for dy in range(-1, 2):
				var row_y = mid_pos.y + dy
				if row_y < 0 or row_y >= grid_height:
					continue
				for x in grid_width:
					ws_targets.append(Vector2i(x, row_y))
			for dx in range(-1, 2):
				var col_x = mid_pos.x + dx
				if col_x < 0 or col_x >= grid_width:
					continue
				for y in grid_height:
					ws_targets.append(Vector2i(col_x, y))
			_explode_cells(ws_targets)

		"double_spiral":
			# 設計文件「紙飛機+紙飛機」:合成點 4 鄰消除 + 起飛 3 台紙飛機
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color)
			_destroy_candy_at(pos_b, candy_b.candy_color)
			# 合成點 4 鄰
			var nbors: Array[Vector2i] = []
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = mid_pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					nbors.append(tp)
			_explode_cells(nbors)
			# 飛 3 台紙飛機
			var picks = _pick_top_plane_targets(3, [mid_pos, pos_a, pos_b])
			for tgt in picks:
				await get_tree().create_timer(0.12).timeout
				effect_spawner_node.spawn_firework(filler.grid_to_world(tgt))
				_detonate_at(tgt, "spiral")

		"spiral_wrapped":
			# 設計文件「紙飛機+炸彈」:合成點 4 鄰消除 + 飛到新位置「使用炸彈」(5x5)
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color)
			_destroy_candy_at(pos_b, candy_b.candy_color)
			var nbors_w: Array[Vector2i] = []
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = mid_pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					nbors_w.append(tp)
			_explode_cells(nbors_w)
			await get_tree().create_timer(0.15).timeout
			var picks_w = _pick_top_plane_targets(1, [mid_pos, pos_a, pos_b])
			if picks_w.size() > 0:
				var tgt = picks_w[0]
				effect_spawner_node.spawn_firework(filler.grid_to_world(tgt))
				_detonate_at(tgt, "wrapped")

		"spiral_striped":
			# 設計文件「紙飛機+火箭」:合成點 4 鄰消除 + 飛到新位置「使用火箭」
			var striped_kind = "striped_h"
			if candy_a.candy_type == CandyScript.CandyType.STRIPED_V \
			   or candy_b.candy_type == CandyScript.CandyType.STRIPED_V:
				striped_kind = "striped_v"
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color)
			_destroy_candy_at(pos_b, candy_b.candy_color)
			var nbors_s: Array[Vector2i] = []
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = mid_pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					nbors_s.append(tp)
			_explode_cells(nbors_s)
			await get_tree().create_timer(0.15).timeout
			var picks_s = _pick_top_plane_targets(1, [mid_pos, pos_a, pos_b])
			if picks_s.size() > 0:
				var tgt = picks_s[0]
				effect_spawner_node.spawn_firework(filler.grid_to_world(tgt))
				_detonate_at(tgt, striped_kind)

	await get_tree().create_timer(0.3).timeout
	await _cascade_loop()

func _process_matches(matches: Array[Dictionary], swap_cells: Array[Vector2i] = []) -> void:
	# swap_cells:玩家剛 swap 的兩格 [pos_a (來源), pos_b (目標)]。
	# 若某個 match group 內含這兩格之一,合成 special 的位置會用 swap dest
	# (pos_b 優先,代表玩家手指落下的地方),這樣 special candy 不會「噴去別處」。
	# cascade 連鎖呼叫時 swap_cells 為空,沿用 match_finder 原計算的 special_pos。
	for match_data in matches:
		var cells = match_data["cells"] as Array[Vector2i]
		var shape = match_data.get("shape", "line")
		var first_candy = filler.get_candy_at(cells[0])
		var match_color = first_candy.candy_color if first_candy else 0

		AudioManager.play_match_sound(cascade_level)
		GameManager.increment_combo()

		# special_pos 由 match_finder 算好(L_T pivot / FOUR 中段 / 2x2 角)
		var special_pos = match_data.get("special_pos", cells[0]) as Vector2i
		# 玩家 swap 形成的 match:讓 special 出現在玩家手指落下的格
		if swap_cells.size() == 2:
			if swap_cells[1] in cells:
				special_pos = swap_cells[1]
			elif swap_cells[0] in cells:
				special_pos = swap_cells[0]
		var special_type = -1

		# 對齊 Python 設計優先級:FIVE_PLUS > L_T > FOUR > 2x2 > THREE
		# 對應 yuehpo candy_type:COLOR_BOMB(LtBl) / WRAPPED(TNT) / STRIPED(Soda) / WRAPPED 暫代(TrPr)
		if shape == "five":
			special_type = CandyScript.CandyType.COLOR_BOMB
		elif shape == "special":  # L_T (跨方向 h_run>=3 且 v_run>=3)
			special_type = CandyScript.CandyType.WRAPPED
		elif shape == "four":
			if match_data.get("direction", "horizontal") == "horizontal":
				special_type = CandyScript.CandyType.STRIPED_V  # 橫 4 連 → 垂直火箭 (Soda90)
			else:
				special_type = CandyScript.CandyType.STRIPED_H  # 縱 4 連 → 水平火箭 (Soda0d)
		elif shape == "block_2x2":
			# Python 端:2x2 → TrPr (紙飛機,十字 4 格 + 飛行階段)
			# Godot 端:用 SPIRAL candy_type 對應(sprite 用 TrPr.png),
			# 效果先做「十字 4 格消除」的基礎版,飛行階段留 v2
			special_type = CandyScript.CandyType.SPIRAL

		for cell in cells:
			var candy = filler.get_candy_at(cell)
			if candy:
				if candy.candy_type != CandyScript.CandyType.NORMAL and candy.candy_type != CandyScript.CandyType.COLOR_BOMB:
					_trigger_special_candy(candy)
				_trigger_obstacle_adjacent(cell)
				effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(cell), candy.candy_color)
				GameManager.update_objective("collect", candy.candy_color, 1)
				candies_destroyed.emit(1, candy.candy_color)
				filler.remove_candy_at(cell)
				candy.animate_destroy()

		GameManager.add_score(cells.size(), special_type >= 0)

		if special_type >= 0:
			var color_for_special = match_color
			if special_type == CandyScript.CandyType.COLOR_BOMB:
				color_for_special = -1
			AudioManager.play_special_create_sound()
			filler.create_special_candy(
				match_color if special_type != CandyScript.CandyType.COLOR_BOMB else 0,
				special_pos,
				special_type
			)
			var new_candy = filler.get_candy_at(special_pos)
			if new_candy:
				_connect_single_candy(new_candy)

	await get_tree().create_timer(0.25).timeout
	await _cascade_loop()

func _cascade_loop() -> void:
	# Gravity 跟 fill 同時開始 tween:
	# - apply_gravity 把既有 candy 往下移
	# - fill_empty_cells 在上方生新 candy 也開始往下落
	# 兩種 tween 同時跑,看起來是一條連續的「列車」往下掉,不再分兩段。
	var gravity_tweens = filler.apply_gravity()
	var fill_tweens = filler.fill_empty_cells()

	# 新生成的 candy 接 input signals(舊的有 is_connected check,不會重複 connect)
	if fill_tweens.size() > 0:
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c:
					_connect_single_candy(c)

	# 等所有 tween 跑完(sequential await,但 tween 本身是平行跑的)
	var all_tweens = gravity_tweens + fill_tweens
	for tw in all_tweens:
		if tw and tw.is_running():
			await tw.finished

	if all_tweens.size() > 0:
		await get_tree().create_timer(0.08).timeout

	var new_matches = MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)
	if new_matches.size() > 0:
		cascade_level += 1
		AudioManager.play_cascade_sound(cascade_level)
		await _process_matches(new_matches)

func _trigger_special_candy(candy: CandyScript) -> void:
	# 觸發 candy 本身的 effect (不消除 candy 自己 — 由 caller 處理)。
	# 走 _chain_trigger → _explode_cells,所以 effect 範圍內若有 special candy 會自動連鎖。
	_chain_trigger(candy.candy_type, candy.grid_pos, candy.candy_color)

# ===========================================================================
# 紙飛機(SPIRAL / TrPr)目標優先級
# 來源:docs/design/盤面物件設計文件 sheet「4.螺旋槳」§3 物件權重表
#   元素=1, 道具=0, 木箱=10, 繩索=10, 餅乾=10, 果凍=10, 櫻桃=20, 甜甜圈=0(特殊)
# 額外加權:通關目標 +100,層數=1 +1,多層加總(本實作把每 instance 視為一單位)
# 我們專案中文件未明列的障礙物,參照「障礙物 = 10」這個 base 給 10。
# Crt / Rope 設計文件明列 10。
# ===========================================================================
const _PLANE_WEIGHT_BY_PREFIX: Dictionary = {
	"Crt": 10,              # 文件明列
	"Rope": 10,             # 文件明列
	"Barrel": 10,
	"TrafficCone": 10,
	"SalmonCan": 10,
	"WaterChiller": 10,
	"BeverageChiller": 10,
	"Mud": 10,
	"Pool": 10,
	"Stamp": 10,
	"Roadblock": 10,
	"Puddle": 10,
}


func _is_plane_objective_tile(tile_id: String) -> bool:
	# 是否是當前關卡的通關目標。tile_id 格式像 "Crt-1" / "Crt-3",
	# objective 也存類似 tile_id 字串;同字母 prefix(到第一個 '-')即視為同類目標。
	var my_prefix = tile_id.split("-")[0]
	if my_prefix == "":
		return false
	for obj in GameManager.level_objectives:
		var obj_tid = str(obj.get("tile_id", ""))
		if obj_tid != "":
			var obj_prefix = obj_tid.split("-")[0]
			if obj_prefix == my_prefix:
				return true
	return false


func _compute_plane_target_weights() -> Dictionary:
	# 回傳 {Vector2i pos: int weight}。多格 instance 只回傳一個 representative cell。
	var weights: Dictionary = {}
	var seen_inst: Dictionary = {}
	for pos in obstacle_map.keys():
		var obs = obstacle_map[pos]
		var tid = str(obs.get("tile_id", ""))
		var inst_id = str(obs.get("instance_id", ""))
		if inst_id != "" and seen_inst.has(inst_id):
			continue
		var base_w = 0
		for prefix in _PLANE_WEIGHT_BY_PREFIX.keys():
			if tid.begins_with(prefix):
				base_w = _PLANE_WEIGHT_BY_PREFIX[prefix]
				break
		if base_w <= 0:
			continue
		var hp = int(obs.get("hp", 1))
		if hp == 1:
			base_w += 1
		if _is_plane_objective_tile(tid):
			base_w += 100
		weights[pos] = base_w
		if inst_id != "":
			seen_inst[inst_id] = true
	return weights


func _pick_top_plane_targets(n: int, exclude: Array[Vector2i] = []) -> Array[Vector2i]:
	# 取前 n 高權重的 target,排除 exclude 內的 cell。
	# 沒有 obstacle 時 fallback:盤面隨機 n 格(讓紙飛機還是有目標,避免空轉)
	var weights = _compute_plane_target_weights()
	var sorted_keys: Array = weights.keys()
	sorted_keys.sort_custom(func(a, b): return weights[a] > weights[b])
	var picks: Array[Vector2i] = []
	for k in sorted_keys:
		if k in exclude or k in picks:
			continue
		picks.append(k)
		if picks.size() >= n:
			break
	# fallback:盤面找有 candy 的格,扣掉 exclude
	if picks.size() < n:
		var candidates: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var p = Vector2i(x, y)
				if p in exclude or p in picks:
					continue
				if filler.get_candy_at(p) != null:
					candidates.append(p)
		candidates.shuffle()
		for c in candidates:
			picks.append(c)
			if picks.size() >= n:
				break
	return picks


func _detonate_at(pos: Vector2i, kind: String) -> void:
	# 在 pos 觸發指定 special candy 效果(用於紙飛機合成「使用 X」)。
	# kind: "wrapped" / "striped_h" / "striped_v" / "spiral"
	# 把 pos 本身放進 cells,_explode_cells 會處理它(包含 chain — 若該格剛好有 special candy)
	effect_spawner_node.spawn_shockwave(filler.grid_to_world(pos))
	var cells: Array[Vector2i] = [pos]
	match kind:
		"wrapped":
			for tp in SpecialCandy.get_wrapped_targets(pos, grid_width, grid_height):
				cells.append(tp)
		"striped_h":
			for tp in SpecialCandy.get_striped_h_targets(pos, grid_width):
				cells.append(tp)
		"striped_v":
			for tp in SpecialCandy.get_striped_v_targets(pos, grid_height):
				cells.append(tp)
		"spiral":
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					cells.append(tp)
	_explode_cells(cells)


# 對齊 tile_defs.py:每個 obstacle prefix 對應 (can_adjacent_elim, can_inplace_elim)
# 不要在 Godot 端瞎猜 — 完全照 Python tile_defs.py 的設計表
const _ELIM_RULES: Dictionary = {
	"Crt":              {"adj": true,  "inplace": false},
	"Puddle":           {"adj": false, "inplace": true},   # bottom layer
	"Barrel":           {"adj": true,  "inplace": false},
	"TrafficCone":      {"adj": true,  "inplace": false},
	"SalmonCan":        {"adj": false, "inplace": false},  # 只能道具消除
	"WaterChiller":     {"adj": true,  "inplace": false},
	"BeverageChiller":  {"adj": true,  "inplace": false},
	"Rope":             {"adj": false, "inplace": true},   # upper layer
	"Mud":              {"adj": true,  "inplace": false},  # upper layer
	"Pool":             {"adj": true,  "inplace": false},
	"Stamp":            {"adj": true,  "inplace": false},
	"Roadblock":        {"adj": true,  "inplace": false},
}


static func _elim_rule(tile_id: String, kind: String) -> bool:
	for prefix in _ELIM_RULES.keys():
		if tile_id.begins_with(prefix):
			return _ELIM_RULES[prefix].get(kind, false)
	return false


func _trigger_obstacle_adjacent(pos: Vector2i) -> void:
	# 打 4 鄰 — 只對 can_adjacent_elim 的 obstacle 才打
	for dir in [Vector2i(0, -1), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(1, 0)]:
		var adj = pos + dir
		if obstacle_map.has(adj):
			var adj_obs = obstacle_map[adj]
			var adj_tid = adj_obs.get("tile_id", "")
			if _elim_rule(adj_tid, "adj"):
				_damage_obstacle(adj)
	# 打自身 — 只對 can_inplace_elim 的 obstacle 才打(下層 Puddle、上層 Rope)
	if obstacle_map.has(pos):
		var obs = obstacle_map[pos]
		var tid = obs.get("tile_id", "")
		if _elim_rule(tid, "inplace"):
			_damage_obstacle(pos)

func _damage_obstacle(pos: Vector2i) -> void:
	if not obstacle_map.has(pos):
		return
	var obs = obstacle_map[pos]
	# 共用 dict:多格 instance 的 4 個 cell 都指向同個 dict,改 hp 全部跟著變
	# (注意:同回合若 4 cells 都被相鄰打到 → 等於扣 4 次 hp,這對應 WaterChiller
	# multi-hit 的設計;對 BeverageChiller 是 single-per-match 略快,但 demo 接受)
	obs["hp"] -= 1
	AudioManager.play_obstacle_break_sound()
	if obs["hp"] <= 0:
		# 一格 vs. 多格 instance — 共享 dict 帶 instance_cells,把整個 instance 一起 erase
		var cells_to_clear: Array = obs.get("instance_cells", [pos])
		if cells_to_clear.is_empty():
			cells_to_clear = [pos]
		GameManager.update_objective("clear_" + obs["type"], -1, 1)
		# 實體障礙(Crt/Barrel/WaterChiller 等)初始時 cell 都 blocked(沒糖)。
		# 打掉後解封,下一次 _cascade_loop 的 apply_gravity 會自動補糖。
		# filler.blocked_cells 跟 game_board.blocked_cells 共用同一個 array(reference),
		# 所以 erase 一次就好。
		for cell in cells_to_clear:
			obstacle_map.erase(cell)
			if cell in blocked_cells:
				blocked_cells.erase(cell)
	board_bg.queue_redraw()

func _post_turn_check() -> void:
	GameManager.reset_combo()
	_reset_hint_timer()

	if GameManager.check_win_condition():
		GameManager.complete_level()
		is_processing = false
		turn_completed.emit()
		return

	if GameManager.check_lose_condition():
		GameManager.fail_level()
		is_processing = false
		turn_completed.emit()
		return

	if not MatchFinder.has_possible_moves(filler.grid, grid_width, grid_height, blocked_cells):
		await _shuffle_board()

	is_processing = false
	turn_completed.emit()

func _shuffle_board() -> void:
	var candies: Array = []
	for x in grid_width:
		for y in grid_height:
			if filler.get_candy_at(Vector2i(x, y)) != null:
				candies.append(filler.get_candy_at(Vector2i(x, y)))

	candies.shuffle()
	var idx = 0
	for x in grid_width:
		for y in grid_height:
			if Vector2i(x, y) in blocked_cells:
				continue
			if idx < candies.size():
				filler.set_candy_at(Vector2i(x, y), candies[idx])
				candies[idx].grid_pos = Vector2i(x, y)
				candies[idx].animate_to(filler.grid_to_world(Vector2i(x, y)), 0.3)
				idx += 1

	await get_tree().create_timer(0.4).timeout

	if MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells).size() > 0:
		cascade_level = 0
		var matches = MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)
		await _process_matches(matches)

func set_obstacle_map(obs: Dictionary) -> void:
	obstacle_map = obs
	board_bg.queue_redraw()

func get_obstacle_map() -> Dictionary:
	return obstacle_map
