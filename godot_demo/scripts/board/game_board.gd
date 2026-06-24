extends Node2D

const MatchFinder = preload("res://scripts/board/match_finder.gd")
const CandyScript = preload("res://scripts/candy/candy.gd")
const CandyFactory = preload("res://scripts/candy/candy_factory.gd")
const SpecialCandy = preload("res://scripts/candy/special_candy.gd")

## 元素 index → 飲料櫃瓶子顏色名（對齊 Python / official_format）
const CANDY_IDX_TO_COLOR_NAME: Array[String] = ["Red", "Grn", "Blu", "Yel"]

const EXPLODE_MODE_MATCH: int = 0
const EXPLODE_MODE_SPECIAL: int = 1
const EXPLODE_MODE_PLANE: int = 2

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
## 本輪 _explode_cells 的模式；罐頭僅接受 SPECIAL/PLANE 傷害
var _obstacle_damage_mode: int = EXPLODE_MODE_MATCH
var obstacle_map: Dictionary = {}
var bottom_obstacle_map: Dictionary = {}

var selected_candy: CandyScript = null
var selected_movable_obs: Vector2i = Vector2i(-1, -1)
var _obs_drag_from: Vector2i = Vector2i(-1, -1)
var _obs_dragging: bool = false
var _obs_drag_start_global: Vector2 = Vector2.ZERO
var is_processing: bool = false
var cascade_level: int = 0
# 鎖死看門狗：is_processing 卡住(動畫跑完卻沒解鎖)時的累計秒數
var _lock_watchdog: float = 0.0
# flush 卡住看門狗：_deferred_running 一直 true(延遲爆炸/cascade 卡死)時的累計秒數
var _flush_watchdog: float = 0.0

var _hint_timer: float = 0.0
var _hint_delay: float = 3.0
var _hint_candies: Array = []
var _hint_shown: bool = false

# Per-match damage dedup — 每次 _explode_cells / 直接觸發 / 連鎖 都遞增 tick。
# Chiller / Stamp 等障礙物在同一個 tick 內只能算 1 次傷害。
var _damage_tick_id: int = 0
# 水窪(底層)護盾:記錄某格上層(Mud/Rope)在哪個 tick 被處理過。
# 用途:即使「打死上層的那一擊」把上層清掉,同一 tick 內水窪也不受傷 ——
# 必須等下一擊(上層已不在)水窪才開始扣血。{Vector2i: tick_id}
var _upper_blocked_bottom_tick: Dictionary = {}
# 同一個 match 群組內,Stamp 目標只 +1 次(但每個相鄰郵戳都可播蓋章動畫)
var _stamp_goal_last_tick: Dictionary = {}  # {Vector2i: int} per-stamp dedup
# 同一批多架紙飛機選目標時的去重列表（避免全飛向同一目標）
var _plane_batch_claimed: Array[Vector2i] = []

signal board_ready
signal turn_completed
signal candies_destroyed(count: int, color: int)

# Autoplay 相關
var _autoplay_moves: Array = []
var _autoplay_running: bool = false
var _autoplay_delay: float = 0.8

# AI 即時模式 — 每步結束後由 AI Controller 即時計算下一步
const AIController = preload("res://scripts/board/ai_controller.gd")
var _ai_controller: Node = null
var _ai_mode: bool = false

func _ready() -> void:
	_calculate_offset()
	var vp := get_viewport()
	if vp and not vp.size_changed.is_connected(_on_viewport_resized):
		vp.size_changed.connect(_on_viewport_resized)
	# 初始化 AI Controller
	_ai_controller = AIController.new()
	_ai_controller.name = "AIController"
	add_child(_ai_controller)
	# ArtTheme 載完(或套用新主題)後，對盤面現有糖果重新換皮 → 初始盤面也即時變新美術。
	# （否則 web 端非同步載入 live_sprites 時，初始盤面用舊圖，要移動一步、新糖果生成才換。）
	var art := get_node_or_null("/root/ArtTheme")
	if art and art.has_signal("theme_ready") and not art.theme_ready.is_connected(_on_theme_ready):
		art.theme_ready.connect(_on_theme_ready)


func _on_theme_ready() -> void:
	# draw_candy 會動態讀 ArtTheme 的新貼圖 → 對現有糖果 + 背景 queue_redraw 即可即時換皮
	if candy_container:
		for c in candy_container.get_children():
			if c.has_method("queue_redraw"):
				c.queue_redraw()
	if board_bg and board_bg.has_method("queue_redraw"):
		board_bg.queue_redraw()


## Autoplay: 外部傳入動作序列,自動逐步執行並播放動畫
func start_autoplay(moves: Array, delay: float = 0.8) -> void:
	_autoplay_moves = moves
	_autoplay_delay = delay
	_autoplay_running = true
	_run_autoplay()


func _run_autoplay() -> void:
	for move in _autoplay_moves:
		if not _autoplay_running:
			break
		# 等前一步完成
		while is_processing:
			await get_tree().create_timer(0.1).timeout
		await get_tree().create_timer(_autoplay_delay).timeout

		var move_type: String = str(move.get("type", "swap"))
		if move_type == "swap":
			var pos1 = move.get("pos1", [0, 0])
			var pos2 = move.get("pos2", [0, 0])
			var p1 := Vector2i(int(pos1[0]), int(pos1[1]))
			var p2 := Vector2i(int(pos2[0]), int(pos2[1]))
			var candy_a = filler.get_candy_at(p1)
			var candy_b = filler.get_candy_at(p2)
			if candy_a and candy_b:
				_try_swap(candy_a, candy_b)
			elif candy_a and _is_movable_obstacle_at(p2):
				_try_swap_with_movable_obstacle(candy_a, p2)
			elif candy_b and _is_movable_obstacle_at(p1):
				_try_swap_with_movable_obstacle(candy_b, p1)
		elif move_type == "activate":
			var pos = move.get("pos", [0, 0])
			var p := Vector2i(int(pos[0]), int(pos[1]))
			var candy = filler.get_candy_at(p)
			if candy and candy.candy_type != CandyScript.CandyType.NORMAL:
				_activate_special_directly(candy)

	_autoplay_running = false


## AI 即時模式：啟動後，每步結束自動讓 AI Controller 計算下一步
func start_ai_mode(delay: float = 0.8) -> void:
	print("[AI] start_ai_mode called, delay=", delay)
	_autoplay_delay = delay
	_ai_mode = true
	_run_ai_step()


func stop_ai_mode() -> void:
	_ai_mode = false
	_autoplay_running = false


func is_ai_running() -> bool:
	return _ai_mode


func _run_ai_step() -> void:
	if not _ai_mode:
		return
	while is_processing:
		await get_tree().create_timer(0.1).timeout
	if not _ai_mode:
		return
	await get_tree().create_timer(_autoplay_delay).timeout
	if not _ai_mode:
		return

	print("[AI] Computing best action...")
	var action: Dictionary = _ai_controller.find_best_action(self)
	if action.is_empty():
		print("[AI] No action found, stopping.")
		_ai_mode = false
		return

	print("[AI] Action: ", action)
	var action_type: String = action.get("type", "")
	if action_type == "swap":
		var p1: Vector2i = action["pos1"]
		var p2: Vector2i = action["pos2"]
		var candy_a = filler.get_candy_at(p1)
		var candy_b = filler.get_candy_at(p2)
		if candy_a and candy_b:
			_try_swap(candy_a, candy_b)
		elif candy_a and _is_movable_obstacle_at(p2):
			_try_swap_with_movable_obstacle(candy_a, p2)
		elif candy_b and _is_movable_obstacle_at(p1):
			_try_swap_with_movable_obstacle(candy_b, p1)
	elif action_type == "activate":
		var p: Vector2i = action["pos"]
		var candy = filler.get_candy_at(p)
		if candy and candy.candy_type != CandyScript.CandyType.NORMAL:
			_activate_special_directly(candy)

	# 等動作完成後再下一步
	while is_processing:
		await get_tree().create_timer(0.1).timeout
	if _ai_mode and not GameManager.check_win_condition() and GameManager.current_state == GameManager.GameState.PLAYING:
		_run_ai_step()


func _on_viewport_resized() -> void:
	if grid_width <= 0 or grid_height <= 0:
		return
	_relayout_board_positions()


func _relayout_board_positions() -> void:
	_calculate_offset()
	if filler:
		filler.board_offset = board_offset
		for x in grid_width:
			for y in grid_height:
				var candy = filler.get_candy_at(Vector2i(x, y))
				if candy:
					candy.position = filler.grid_to_world(Vector2i(x, y))
	board_bg.queue_redraw()


func _process(delta: float) -> void:
	# 鎖死看門狗：special 道具(光球/紙飛機等)動畫跑完卻沒解鎖時，超時強制恢復可操作。
	# 只在「真的閒置」(沒有待爆炸佇列、沒在跑 flush)時計時；正常動畫/連鎖遠在 5 秒內結束，
	# 所以只有真的卡死才會觸發，不會誤判正常遊玩。
	if is_processing:
		if _deferred_queue.is_empty() and not _deferred_running:
			# 全部 settle 了卻沒解鎖 → 5 秒後強制恢復
			_lock_watchdog += delta
			_flush_watchdog = 0.0
		elif _deferred_running:
			# flush/cascade 卡住(例如 tween 被 free 後 await 永遠不回)→ 8 秒後強制恢復
			_flush_watchdog += delta
			_lock_watchdog = 0.0
		else:
			# 佇列有 entry 但還沒 ready(飛機飛行中)→ 正常，不計時
			_lock_watchdog = 0.0
			_flush_watchdog = 0.0
		if _lock_watchdog > 5.0 or _flush_watchdog > 8.0:
			_lock_watchdog = 0.0
			_flush_watchdog = 0.0
			push_warning("[watchdog] is_processing 卡住 → 強制解鎖")
			_deferred_running = false
			_deferred_queue.clear()
			_post_turn_check()
	else:
		_lock_watchdog = 0.0
		_flush_watchdog = 0.0

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
		move = _find_movable_swap_hint()
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
	# 自動縮放 cell_size，讓盤面塞滿可用空間（適應任何盤面大小 + 螢幕比例，含橫式）。
	# 上方保留給 HUD(關卡/步數/目標列)，其餘空間置中放盤面。
	var viewport_size = get_viewport_rect().size
	var top_reserve := 170.0
	var margin := 24.0
	var avail_w: float = viewport_size.x - margin * 2.0
	var avail_h: float = viewport_size.y - top_reserve - margin
	if grid_width > 0 and grid_height > 0 and avail_w > 0 and avail_h > 0:
		cell_size = minf(avail_w / grid_width, avail_h / grid_height)
		cell_size = clampf(cell_size, 28.0, 120.0)
	var board_width = grid_width * cell_size
	var board_height = grid_height * cell_size
	board_offset = Vector2(
		(viewport_size.x - board_width) / 2.0,
		top_reserve + (avail_h - board_height) / 2.0
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
	call_deferred("_relayout_board_positions")

	# 開局時要跳過填糖的格 = 真正 blocked + 預置道具位置。
	# (Puddle 是下層裝飾物,本身允許糖在上面,所以初始化會跟一般格一樣填糖;
	#  若 puddle 上方被障礙物擋住,那塊區域看起來「空空的」是因為 fill_initial
	#  跳過了 puddle 上層的 blocked 格,而 puddle 雖然填了糖也只是視覺上看不到差別)
	var pre_placed: Array[Dictionary] = []
	if level_data and "pre_placed_specials" in level_data:
		pre_placed = level_data.pre_placed_specials
	var init_skip: Array[Vector2i] = blocked_cells.duplicate()
	for sp in pre_placed:
		var sp_pos: Vector2i = sp.get("pos", Vector2i.ZERO)
		if not sp_pos in init_skip:
			init_skip.append(sp_pos)

	filler.setup(grid_width, grid_height, cell_size, board_offset, candy_container, candy_scene, init_skip)
	if level_data and level_data.num_colors > 0:
		filler.num_colors = level_data.num_colors

	# void_cells — 不存在的格，糖可穿過（必須在 fill_initial 前設定）
	if level_data and level_data.void_cells.size() > 0:
		var vc: Dictionary = {}
		for p in level_data.void_cells:
			vc[p] = true
		filler.void_cells = vc

	# 可移動障礙物的格（Barrel/TrafficCone）：BFS 可穿越（必須在 fill_initial 前設定）
	var movable_cells: Dictionary = {}
	for pos in obstacle_map:
		var obs: Dictionary = obstacle_map[pos]
		var tid: String = str(obs.get("tile_id", ""))
		if _is_movable_obstacle(tid):
			movable_cells[pos] = true
	filler.movable_obstacle_cells = movable_cells

	_draw_board_background()
	filler.fill_initial()
	_connect_candy_signals()

	var retry_count = 0
	while MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, init_skip).size() > 0 and retry_count < 50:
		_clear_board()
		filler.setup(grid_width, grid_height, cell_size, board_offset, candy_container, candy_scene, init_skip)
		if level_data and level_data.num_colors > 0:
			filler.num_colors = level_data.num_colors
		filler.fill_initial()
		_connect_candy_signals()
		retry_count += 1

	_sync_candy_layer_visibility()

	# Puddle/預置道具格 fill_initial 完之後就解封 — 之後 gravity 允許糖落上去
	# 重要:filler.blocked_cells 必須跟 game_board.blocked_cells 共用同一個 array reference,
	# 之後 _damage_obstacle 在 blocked_cells 上 erase 一次,兩邊都會同步看到改變
	filler.blocked_cells = blocked_cells

	# 頂部 Spawner — 把 spawner_data 傳入 filler
	if level_data and level_data.spawner_data.size() > 0:
		filler.set_spawners(level_data.spawner_data)
		filler.obstacle_map_ref = obstacle_map
		if not filler.obstacle_spawned.is_connected(_on_obstacle_spawned):
			filler.obstacle_spawned.connect(_on_obstacle_spawned)

	# 預置道具:在原本被跳過的格上 spawn 對應的 special candy
	_spawn_pre_placed_specials(pre_placed)

	board_ready.emit()


func _spawn_pre_placed_specials(pre_placed: Array[Dictionary]) -> void:
	if pre_placed.is_empty():
		return
	var num_colors_local = filler.num_colors if filler else 4
	for sp in pre_placed:
		var pos: Vector2i = sp.get("pos", Vector2i.ZERO)
		var type_name: String = sp.get("type_name", "")
		var candy_type: int = _powerup_type_to_candy_type(type_name)
		if candy_type < 0:
			continue
		# Color bomb 顏色不影響邏輯,沿用 0;其他 special 取隨機色 — 玩家 swap 時會用對方的色
		var color: int = 0 if candy_type == CandyScript.CandyType.COLOR_BOMB else randi() % num_colors_local
		var c = filler.create_special_candy(color, pos, candy_type)
		# 重要:pre-placed candy 是在 _connect_candy_signals() 之後才 spawn,
		# 必須手動把 candy_selected / candy_swipe 訊號接起來,不然玩家點下去 game_board
		# 收不到事件 → 道具完全不能用(老 bug!)
		if c:
			_connect_single_candy(c)


# powerup type_name(loader 輸出)→ CandyType enum
func _powerup_type_to_candy_type(name_str: String) -> int:
	match name_str:
		"striped_h": return CandyScript.CandyType.STRIPED_H
		"striped_v": return CandyScript.CandyType.STRIPED_V
		"wrapped": return CandyScript.CandyType.WRAPPED
		"spiral": return CandyScript.CandyType.SPIRAL
		"color_bomb": return CandyScript.CandyType.COLOR_BOMB
	return -1

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

	_clear_selected_movable_obs()

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
		var adj_obs = candy.grid_pos
		if _is_movable_obstacle_at(adj_obs):
			_try_swap_with_movable_obstacle(selected_candy, adj_obs)
		elif _is_movable_obstacle_at(selected_candy.grid_pos):
			_try_swap_with_movable_obstacle(candy, selected_candy.grid_pos)
		else:
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
		# 挑「盤面上最多的顏色」(不是隨機),並播放點亮動畫(閃一下最多色再消除)
		var color_count: Dictionary = {}
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c and not c.is_being_destroyed and c.candy_type == CandyScript.CandyType.NORMAL:
					color_count[c.candy_color] = int(color_count.get(c.candy_color, 0)) + 1
		var target_color := 0
		var best := -1
		for col in color_count:
			if int(color_count[col]) > best:
				best = int(color_count[col])
				target_color = col
		_destroy_candy_at(pos, candy.candy_color, EXPLODE_MODE_SPECIAL)
		# 光球只對基本元素產生影響，道具不受影響
		var nc_targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var p = Vector2i(x, y)
				var c = filler.get_candy_at(p)
				if c and not c.is_being_destroyed and c.candy_color == target_color and c.candy_type == CandyScript.CandyType.NORMAL:
					nc_targets.append(p)
		await _animate_color_bomb_sequence(nc_targets, pos, -1)
	else:
		# STRIPED/WRAPPED:觸發自身,然後消除自己(SPECIAL mode → 該格直接打,不擴散到 4 鄰)
		_trigger_special_candy(candy)
		if obstacle_map.has(pos):
			_damage_obstacle(pos)
		effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), candy.candy_color)
		filler.remove_candy_at(pos)
		candy.animate_destroy()
		candies_destroyed.emit(1, candy.candy_color)
	
	await get_tree().create_timer(0.3).timeout
	await _cascade_loop()
	_sync_candy_layer_visibility()
	if _deferred_queue.size() == 0 and not _deferred_running:
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
	var tpos: Vector2i = Vector2i(target_pos.x, target_pos.y)
	if tpos in blocked_cells:
		# 例外:可移動障礙物(Barrel / TrafficCone)可以被 swap(user 確認)。
		# 跟元素互換規則一樣:有 match 成立才有效,沒 match 還原。
		if obstacle_map.has(tpos):
			var obs = obstacle_map[tpos]
			var tid_obs: String = str(obs.get("tile_id", ""))
			# 候選:目標是可移動障礙物 + 不能跟 lock cell(已鎖住的糖)swap
			# + 不能 swap 到自己的 cell 已經有其他 obstacle(避免 Puddle/Rope 被覆寫掉)
			if _is_movable_obstacle(tid_obs) \
				and not _is_candy_locked(candy.grid_pos) \
				and _can_candy_swap_with_movable(candy.grid_pos):
				if selected_candy:
					selected_candy.set_selected(false)
					selected_candy = null
				_try_swap_with_movable_obstacle(candy, tpos)
		return
	var target_candy = filler.get_candy_at(target_pos)
	if target_candy == null:
		# 盤內 playable 空格：元素/道具可移入（需能形成 match 才成立）
		if not _is_playable_cell(tpos):
			return
		if _is_candy_locked(candy.grid_pos):
			return
		if selected_candy:
			selected_candy.set_selected(false)
			selected_candy = null
		_try_move_into_empty(candy, tpos)
		return
	if _is_candy_locked(candy.grid_pos) or _is_candy_locked(target_pos):
		return
	if selected_candy:
		selected_candy.set_selected(false)
		selected_candy = null
	_try_swap(candy, target_candy)

func _is_playable_cell(pos: Vector2i) -> bool:
	return pos.x >= 0 and pos.x < grid_width and pos.y >= 0 and pos.y < grid_height \
		and pos not in blocked_cells


func _global_to_grid(global_pos: Vector2) -> Vector2i:
	var local := to_local(global_pos) - board_offset
	var gx := int(local.x / cell_size)
	var gy := int(local.y / cell_size)
	if gx < 0 or gx >= grid_width or gy < 0 or gy >= grid_height:
		return Vector2i(-1, -1)
	return Vector2i(gx, gy)


func _is_movable_obstacle_at(pos: Vector2i) -> bool:
	if not obstacle_map.has(pos):
		return false
	return _is_movable_obstacle(str(obstacle_map[pos].get("tile_id", "")))


func _can_candy_swap_with_movable(from_pos: Vector2i) -> bool:
	if filler.get_candy_at(from_pos) == null:
		return false
	if not obstacle_map.has(from_pos):
		return true
	var tid := str(obstacle_map[from_pos].get("tile_id", ""))
	if tid.begins_with("Puddle") or tid.begins_with("Rope") or tid.begins_with("Mud"):
		return true
	return _is_movable_obstacle(tid)


func _clear_selected_movable_obs() -> void:
	selected_movable_obs = Vector2i(-1, -1)
	board_bg.queue_redraw()


func _input(event: InputEvent) -> void:
	if is_processing or filler == null:
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		var gpos: Vector2 = event.global_position
		var grid_pos := _global_to_grid(gpos)
		if event.pressed:
			# 該格只有桶/錐、沒有糖時才當成障礙物拖動（避免搶糖果點擊）
			if _is_movable_obstacle_at(grid_pos) and filler.get_candy_at(grid_pos) == null:
				_obs_drag_from = grid_pos
				_obs_dragging = true
				_obs_drag_start_global = gpos
				_on_movable_obstacle_pressed(grid_pos)
		elif _obs_dragging:
			_obs_dragging = false
			_obs_drag_from = Vector2i(-1, -1)
	elif event is InputEventMouseMotion and _obs_dragging:
		var diff: Vector2 = event.global_position - _obs_drag_start_global
		if diff.length() > cell_size * 0.35:
			_obs_dragging = false
			var dir := Vector2i.ZERO
			if abs(diff.x) > abs(diff.y):
				dir = Vector2i(1, 0) if diff.x > 0 else Vector2i(-1, 0)
			else:
				dir = Vector2i(0, 1) if diff.y > 0 else Vector2i(0, -1)
			_on_movable_obstacle_swiped(_obs_drag_from, dir)
			_obs_drag_from = Vector2i(-1, -1)


func _on_movable_obstacle_pressed(obs_pos: Vector2i) -> void:
	_reset_hint_timer()
	if selected_candy:
		var dist := (selected_candy.grid_pos - obs_pos).abs()
		if (dist.x == 1 and dist.y == 0) or (dist.x == 0 and dist.y == 1):
			selected_candy.set_selected(false)
			var c := selected_candy
			selected_candy = null
			_try_swap_with_movable_obstacle(c, obs_pos)
			return
		selected_candy.set_selected(false)
		selected_candy = null
	if selected_movable_obs == obs_pos:
		_clear_selected_movable_obs()
		return
	selected_movable_obs = obs_pos
	board_bg.queue_redraw()


func _on_movable_obstacle_swiped(obs_pos: Vector2i, direction: Vector2i) -> void:
	if not _is_movable_obstacle_at(obs_pos):
		return
	_reset_hint_timer()
	_clear_selected_movable_obs()
	var target := obs_pos + direction
	if target.x < 0 or target.x >= grid_width or target.y < 0 or target.y >= grid_height:
		return
	var target_candy = filler.get_candy_at(target)
	if target_candy and not _is_candy_locked(target_candy.grid_pos) \
			and _can_candy_swap_with_movable(target_candy.grid_pos):
		_try_swap_with_movable_obstacle(target_candy, obs_pos)
	elif _is_playable_cell(target):
		_run_swap_movable_into_empty(obs_pos, target)


func _find_movable_swap_hint() -> Array[Vector2i]:
	if filler == null:
		return []
	for obs_pos in obstacle_map:
		if not _is_movable_obstacle_at(obs_pos):
			continue
		for dir in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var candy_pos: Vector2i = obs_pos + dir
			if candy_pos.x < 0 or candy_pos.x >= grid_width or candy_pos.y < 0 or candy_pos.y >= grid_height:
				continue
			var candy = filler.get_candy_at(candy_pos)
			if candy == null:
				continue
			if _would_match_after_movable_swap(candy_pos, obs_pos):
				return [candy_pos, obs_pos]
	return []


func _would_match_after_movable_swap(candy_pos: Vector2i, obs_pos: Vector2i) -> bool:
	if not _can_candy_swap_with_movable(candy_pos):
		return false
	if obstacle_map.has(candy_pos) and str(obstacle_map[candy_pos].get("tile_id", "")).begins_with("Puddle"):
		return false
	var candy = filler.get_candy_at(candy_pos)
	if candy == null:
		return false
	var obs = obstacle_map[obs_pos]
	filler.set_candy_at(candy_pos, null)
	filler.set_candy_at(obs_pos, candy)
	candy.grid_pos = obs_pos
	obstacle_map.erase(obs_pos)
	obstacle_map[candy_pos] = obs
	var blocked_snapshot := blocked_cells.duplicate()
	if obs_pos in blocked_cells:
		blocked_cells.erase(obs_pos)
	if candy_pos not in blocked_cells:
		blocked_cells.append(candy_pos)
	var found := MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells).size() > 0
	# revert
	filler.set_candy_at(obs_pos, null)
	filler.set_candy_at(candy_pos, candy)
	candy.grid_pos = candy_pos
	obstacle_map.erase(candy_pos)
	obstacle_map[obs_pos] = obs
	blocked_cells.clear()
	for b in blocked_snapshot:
		blocked_cells.append(b)
	return found


func _run_swap_movable_into_empty(obs_pos: Vector2i, empty_pos: Vector2i) -> void:
	if not _is_movable_obstacle_at(obs_pos) or not _is_playable_cell(empty_pos):
		return
	if filler.get_candy_at(empty_pos) != null:
		return
	var obs = obstacle_map[obs_pos]
	obstacle_map.erase(obs_pos)
	if obs_pos in blocked_cells:
		blocked_cells.erase(obs_pos)
	filler.movable_obstacle_cells.erase(obs_pos)
	obstacle_map[empty_pos] = obs
	blocked_cells.append(empty_pos)
	filler.movable_obstacle_cells[empty_pos] = true
	board_bg.queue_redraw()
	var matches := MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)
	if matches.is_empty():
		obstacle_map.erase(empty_pos)
		blocked_cells.erase(empty_pos)
		filler.movable_obstacle_cells.erase(empty_pos)
		obstacle_map[obs_pos] = obs
		blocked_cells.append(obs_pos)
		filler.movable_obstacle_cells[obs_pos] = true
		board_bg.queue_redraw()
		return
	is_processing = true
	_reset_hint_timer()
	GameManager.use_move()
	cascade_level = 0
	await _process_matches(matches, [obs_pos, empty_pos])
	if _deferred_queue.size() == 0 and not _deferred_running:
		_post_turn_check()


func _is_candy_locked(pos: Vector2i) -> bool:
	if obstacle_map.has(pos):
		var obs = obstacle_map[pos]
		if obs.has("type") and obs["type"] == "wire":
			return true
	return false


func _has_mud_at(pos: Vector2i) -> bool:
	if not obstacle_map.has(pos):
		return false
	return str(obstacle_map[pos].get("tile_id", "")).begins_with("Mud")


## 同格正上方是否有「上層障礙物」(Mud / Rope)。
## 用於水窪(底層)傷害判定:上層還蓋著時,要先清掉上層,水窪才會扣血。
## 該格是否有「任何障礙物」蓋住底層水窪（中層 Crt/Barrel… 或上層 Mud/Rope 都算）。
## 有覆蓋物時水窪要先等它清掉才受傷（兩階段：先打障礙物、再消水漥）。
func _obstacle_covers_bottom_at(pos: Vector2i) -> bool:
	return obstacle_map.has(pos)


## 泥巴完全遮住中層元素；繩索/水窪不藏元素（繩索僅鎖操作）
func _sync_candy_layer_visibility() -> void:
	if filler == null:
		return
	for x in grid_width:
		for y in grid_height:
			var c = filler.get_candy_at(Vector2i(x, y))
			if c == null:
				continue
			c.visible = not _has_mud_at(Vector2i(x, y))


func _try_move_into_empty(candy: CandyScript, empty_pos: Vector2i) -> void:
	is_processing = true
	_reset_hint_timer()
	var from_pos = candy.grid_pos
	var world_to = filler.grid_to_world(empty_pos)
	AudioManager.play_swap_sound()
	filler.remove_candy_at(from_pos)
	filler.set_candy_at(empty_pos, candy)
	var tw = candy.animate_to(world_to)
	if tw:
		await tw.finished
	var matches = MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)
	if matches.is_empty():
		filler.remove_candy_at(empty_pos)
		filler.set_candy_at(from_pos, candy)
		var back = filler.grid_to_world(from_pos)
		var tw2 = candy.animate_to(back)
		if tw2:
			await tw2.finished
		is_processing = false
		return
	await _process_matches(matches, [from_pos, empty_pos])
	if _deferred_queue.size() == 0 and not _deferred_running:
		_post_turn_check()

func _try_swap(candy_a: CandyScript, candy_b: CandyScript) -> void:
	is_processing = true
	_reset_hint_timer()
	_clear_selected_movable_obs()
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

	# 道具+道具(兩邊都是 special)→「合成動畫」:被拖曳的 candy_a 滑到目標格
	# (world_b)疊在 candy_b 上,candy_b 留在目標格不動 → 兩顆在「目標位置」合成引爆,
	# 而非互換位置(才有「移過去在目標位置合成」的感覺)。
	# 道具+元素 仍用互換動畫(下方分支各自處理引爆點)。
	var both_special := candy_a.candy_type != CandyScript.CandyType.NORMAL \
			and candy_b.candy_type != CandyScript.CandyType.NORMAL
	var tween_a: Tween
	if both_special:
		candy_a.z_index = 1  # 滑上去疊在 candy_b 之上
		tween_a = candy_a.animate_to(world_b, 0.18)
	else:
		tween_a = candy_a.animate_to(world_b, 0.2)
		candy_b.animate_to(world_a, 0.2)
	await tween_a.finished

	if candy_a.candy_type == CandyScript.CandyType.COLOR_BOMB or candy_b.candy_type == CandyScript.CandyType.COLOR_BOMB:
		# 彩球引爆位置:用合成點 pos_b(兩顆道具疊合處)
		_handle_color_bomb_swap(candy_a, candy_b, pos_b)
		return

	var combo = CandyFactory.get_combo_result(candy_a.candy_type, candy_b.candy_type)
	if combo["effect"] != "none":
		GameManager.use_move()
		cascade_level = 0
		await _handle_special_combo(candy_a, candy_b, combo["effect"])
		if _deferred_queue.size() == 0 and not _deferred_running:
			_post_turn_check()
		return

	var matches = MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)
	# 道具+元素 的引爆點一律用「道具被移動到的位置」(道具 swap 後的格),
	# 與移動方向無關(把元素移過去 / 把道具移過去 都一樣)。
	var a_special = candy_a.candy_type != CandyScript.CandyType.NORMAL
	var b_special = candy_b.candy_type != CandyScript.CandyType.NORMAL

	if matches.size() == 0:
		# 沒形成 match。
		# 如果有一邊是 special candy(STRIPED/WRAPPED/SPIRAL)→ 把它當「滑出去施放」處理:
		# 道具+元素:一律在「道具被移動到的位置」(sp_pos = 道具 swap 後的格)引爆,
		# 跟「把元素移過去道具 / 把道具移過去元素」無關 —— 引爆點永遠是道具的落點。
		if a_special or b_special:
			var trigger_candy = candy_a if a_special else candy_b
			var sp_pos = trigger_candy.grid_pos
			var sp_type = trigger_candy.candy_type
			var sp_color = trigger_candy.candy_color
			GameManager.use_move()
			cascade_level = 0
			AudioManager.play_special_trigger_sound()
			# 道具自身先消除(SPECIAL mode → 不擴散到鄰邊 obstacle)
			_destroy_candy_at(sp_pos, sp_color, EXPLODE_MODE_SPECIAL)
			# 在道具落點 sp_pos 觸發 effect
			_chain_trigger(sp_type, sp_pos, sp_color)
			await get_tree().create_timer(0.3).timeout
			await _cascade_loop()
			if _deferred_queue.size() == 0 and not _deferred_running:
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

	# 有 match:走正常 match 流程。
	# 道具+元素 swap 成 match(user 確認):「兩件事同時發生」=
	#   元素 match 消除 + 道具在 drag_dest 引爆,然後一次 cascade。
	# 做法:**先觸發道具效果**,讓道具 explode 出的 cells 跟 match cells 在同一個
	# tick 一起爆,玩家看到的是同一波消除,不會有「先 match → 等一下 → 道具才爆」的怪 timing。
	# (之前 bug 是先 process_matches 跑完 cascade 才觸發道具,所以中間有時間差,玩家
	# 反映「道具沒觸發」— 其實是觸發了,但效果在 cascade 後才看到。)
	GameManager.use_move()
	cascade_level = 0

	# 只有「一邊 special 一邊 normal」才走 special trigger 分支
	# (兩邊都 special 早就被前面 combo 攔走;兩邊都 normal 沒這個問題)
	if a_special != b_special:
		var pending: CandyScript = candy_a if a_special else candy_b
		var sp_type = pending.candy_type
		var sp_color = pending.candy_color
		# 1) 把道具消除(SPECIAL mode → 不擴散到鄰邊 obstacle,只爆道具自身)
		_destroy_candy_at(pending.grid_pos, sp_color, EXPLODE_MODE_SPECIAL)
		# 2) 同 frame 內觸發道具效果(火箭打整排 / TNT 5x5 / 飛機飛 etc.)
		#    引爆點 = 道具被移動到的位置(pending.grid_pos),與移動方向無關。
		AudioManager.play_special_trigger_sound()
		_chain_trigger(sp_type, pending.grid_pos, sp_color)
		# 給 explode 的 tween 一點時間先跑(否則 match 動畫蓋過去看不見道具效果)
		await get_tree().create_timer(0.05).timeout

	# 3) 處理 match cells(_process_matches 結尾會 await cascade_loop,所以結束時盤面已穩定)
	#    若道具效果剛把某些 match cell 也炸掉了,_process_matches 內部 get_candy_at == null 自然 skip。
	await _process_matches(matches, [pos_a, pos_b])

	if _deferred_queue.size() == 0 and not _deferred_running:
		_post_turn_check()


# Swap 糖果與可移動障礙物(Barrel / TrafficCone)— user 確認:
#   - 我可以主動拿一顆糖跟旁邊的水桶/三角錐互換
#   - 但只有「換完後有 match 成立」才算合法,沒 match 還原(跟正常糖果 swap 規則一致)
#   - 水桶不會 match 自己(neutral),靠的是糖在新位置觸發 3 連
# 實作:data 互換 + 動畫,match 檢查走 MatchFinder。
func _try_swap_with_movable_obstacle(candy: CandyScript, obs_pos: Vector2i) -> void:
	is_processing = true
	_reset_hint_timer()
	_clear_selected_movable_obs()
	if selected_candy:
		selected_candy.set_selected(false)
		selected_candy = null
	AudioManager.play_swap_sound()

	var candy_pos: Vector2i = candy.grid_pos
	if obstacle_map.has(candy_pos) and str(obstacle_map[candy_pos].get("tile_id", "")).begins_with("Puddle"):
		is_processing = false
		return
	var world_candy: Vector2 = filler.grid_to_world(candy_pos)
	var world_obs: Vector2 = filler.grid_to_world(obs_pos)
	var obs = obstacle_map[obs_pos]

	# data 互換:糖 → obs_pos,obstacle → candy_pos
	filler.set_candy_at(candy_pos, null)
	filler.set_candy_at(obs_pos, candy)
	candy.grid_pos = obs_pos
	obstacle_map.erase(obs_pos)
	obstacle_map[candy_pos] = obs
	if obs_pos in blocked_cells:
		blocked_cells.erase(obs_pos)
	if not (candy_pos in blocked_cells):
		blocked_cells.append(candy_pos)
	filler.movable_obstacle_cells.erase(obs_pos)
	filler.movable_obstacle_cells[candy_pos] = true

	# 動畫
	var tween_a = candy.animate_to(world_obs, 0.2)
	board_bg.queue_redraw()
	await tween_a.finished

	# 檢查是否成立 match
	var matches = MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)

	# 如果糖本身是 special candy,允許「滑出去施放」— 直接觸發,不檢查 match
	# (跟正常 _try_swap 的 special-no-match 分支一致)
	var is_special: bool = candy.candy_type != CandyScript.CandyType.NORMAL
	if matches.size() == 0 and not is_special:
		# 沒 match → 還原
		AudioManager.play_swap_back_sound()
		filler.set_candy_at(obs_pos, null)
		filler.set_candy_at(candy_pos, candy)
		candy.grid_pos = candy_pos
		obstacle_map.erase(candy_pos)
		obstacle_map[obs_pos] = obs
		if candy_pos in blocked_cells:
			blocked_cells.erase(candy_pos)
		if not (obs_pos in blocked_cells):
			blocked_cells.append(obs_pos)
		filler.movable_obstacle_cells.erase(candy_pos)
		filler.movable_obstacle_cells[obs_pos] = true
		var tween_back = candy.animate_to(world_candy, 0.2)
		board_bg.queue_redraw()
		await tween_back.finished
		is_processing = false
		return

	GameManager.use_move()
	cascade_level = 0

	if matches.size() == 0 and is_special:
		# special candy 滑出去 → 在新位置(obs_pos)施放
		AudioManager.play_special_trigger_sound()
		var sp_type = candy.candy_type
		var sp_color = candy.candy_color
		_destroy_candy_at(obs_pos, sp_color, EXPLODE_MODE_SPECIAL)
		_chain_trigger(sp_type, obs_pos, sp_color)
		await get_tree().create_timer(0.3).timeout
		await _cascade_loop()
		if _deferred_queue.size() == 0 and not _deferred_running:
			_post_turn_check()
		return

	# 有 match → 正常 match 流程
	await _process_matches(matches, [candy_pos, obs_pos])
	if _deferred_queue.size() == 0 and not _deferred_running:
		_post_turn_check()


func _handle_color_bomb_swap(candy_a: CandyScript, candy_b: CandyScript, drag_dest: Vector2i = Vector2i(-1, -1)) -> void:
	# drag_dest:用戶滑動的目的地(orb 視覺從這格升起)。-1, -1 → fallback 用 bomb 的位置。
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
	# orb 視覺升起位置:
	#   彩球+元素(other 為 NORMAL):用彩球被移動到的位置(bomb.grid_pos),與移動方向無關。
	#   彩球+道具(合成):用合成點 drag_dest(pos_b),兩顆道具疊合處。
	var orb_pos: Vector2i
	if other.candy_type == CandyScript.CandyType.NORMAL:
		orb_pos = bomb.grid_pos
	else:
		orb_pos = drag_dest if drag_dest.x >= 0 else bomb.grid_pos
	AudioManager.play_special_trigger_sound()
	# 光球本身先處理掉(視覺由 _animate_color_bomb_sequence 內部 spawn 一顆小小旋轉浮起的 orb)
	# 蒐集到 targets 時也跳過已 destroyed 的 bomb/other 格

	if other.candy_type == CandyScript.CandyType.COLOR_BOMB:
		# COLOR_BOMB + COLOR_BOMB:整盤全消
		var to_destroy: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var cc = filler.get_candy_at(Vector2i(x, y))
				if cc != null and not cc.is_being_destroyed:
					to_destroy.append(Vector2i(x, y))
		_destroy_candy_at(bomb.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		_destroy_candy_at(other.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		# 整盤一起點亮(stagger 較快不然太久)
		await _animate_color_bomb_sequence(to_destroy, orb_pos, -1, false, 0.03)

	elif other.candy_type in [CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V]:
		# COLOR_BOMB + STRIPED:同色 → STRIPED → 全部一起觸發
		_destroy_candy_at(bomb.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		_destroy_candy_at(other.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		var targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color and not c.is_being_destroyed:
					targets.append(Vector2i(x, y))
		await _animate_color_bomb_sequence(targets, orb_pos, CandyScript.CandyType.STRIPED_H, true)

	elif other.candy_type == CandyScript.CandyType.WRAPPED:
		# COLOR_BOMB + WRAPPED:同色 → WRAPPED → 一起觸發
		_destroy_candy_at(bomb.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		_destroy_candy_at(other.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		var targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color and not c.is_being_destroyed:
					targets.append(Vector2i(x, y))
		await _animate_color_bomb_sequence(targets, orb_pos, CandyScript.CandyType.WRAPPED)

	elif other.candy_type == CandyScript.CandyType.SPIRAL:
		# COLOR_BOMB + SPIRAL(光球 + 紙飛機):同色 → SPIRAL → 一起觸發 → 各自飛出
		_destroy_candy_at(bomb.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		_destroy_candy_at(other.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		var targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color and not c.is_being_destroyed:
					targets.append(Vector2i(x, y))
		await _animate_color_bomb_sequence(targets, orb_pos, CandyScript.CandyType.SPIRAL)

	else:
		# COLOR_BOMB + NORMAL:只消除同色基本元素，道具不受影響
		_destroy_candy_at(bomb.grid_pos, target_color, EXPLODE_MODE_SPECIAL)
		var nc_targets: Array[Vector2i] = []
		for x in grid_width:
			for y in grid_height:
				var c = filler.get_candy_at(Vector2i(x, y))
				if c != null and c.candy_color == target_color and not c.is_being_destroyed and c.candy_type == CandyScript.CandyType.NORMAL:
					nc_targets.append(Vector2i(x, y))
		await _animate_color_bomb_sequence(nc_targets, orb_pos, -1)

	await get_tree().create_timer(0.3).timeout
	await _cascade_loop()
	_sync_candy_layer_visibility()
	if _deferred_queue.size() == 0 and not _deferred_running:
		_post_turn_check()


# 光球主動畫:
#   1. 在 bomb_pos 升起一顆小小旋轉的光球(orb)
#   2. 對 targets 逐一點亮(stagger 間隔),若是 combo(transform_to >= 0)順便把 candy 變成 partner 道具
#   3. 全部點亮後同時呼叫 _explode_cells(targets) → 一起消除/觸發
# transform_to: candy_type(-1 = 純點亮,不變身)
# randomize_striped: 對應 STRIPED combo,每個目標隨機是橫或直 striped
# stagger: 每個目標的間隔秒數(預設 0.05)
func _animate_color_bomb_sequence(targets: Array, bomb_pos: Vector2i, transform_to: int, randomize_striped: bool = false, stagger: float = 0.05) -> void:
	var n = targets.size()
	if n == 0:
		return
	# 點亮階段分批(最多 ~12 批)：格子很多時自動縮短每批間隔 → 整盤光球(尤其雙光球)
	# 不會拖太久,也避免「逐格 await」累積大量單幀開銷(消除瞬間的 lag 來源之一)。
	var max_steps := 12
	var step_size := maxi(1, int(ceil(float(n) / float(max_steps))))
	var steps := int(ceil(float(n) / float(step_size)))
	var batch_wait := minf(stagger * float(step_size), 0.06)
	var orb_duration: float = maxf(float(steps) * batch_wait + 0.2, 0.45)
	effect_spawner_node.spawn_color_bomb_orb(filler.grid_to_world(bomb_pos), orb_duration)
	var i := 0
	while i < n:
		var batch_end := mini(i + step_size, n)
		for j in range(i, batch_end):
			var pos2: Vector2i = targets[j] as Vector2i
			var c2 = filler.get_candy_at(pos2)
			if c2 == null or c2.is_being_destroyed:
				continue
			effect_spawner_node.spawn_target_highlight(filler.grid_to_world(pos2), c2.candy_color)
			if transform_to >= 0:
				var ttype = transform_to
				if randomize_striped:
					ttype = [CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V].pick_random()
				c2.set_candy_type(ttype)
		i = batch_end
		await get_tree().create_timer(batch_wait).timeout
	# 全部點亮 / 變身完成 → 短暫停頓讓玩家感受「滿盤亮起」 → 同時消除
	#
	# 模式選擇(user 確認):
	#   transform_to == -1 (純點亮,沒變身道具):光球+一般元素 → 跟一般 match 等效,
	#     **EXPLODE_MODE_MATCH** 讓鄰邊 obstacle (Crt, Barrel, ...) 也被打,
	#     這樣光球真的有「順便清周圍」的價值。
	#   transform_to != -1 (有變身成道具):被點亮的格已經各自變成 striped/wrapped/...,
	#     **EXPLODE_MODE_SPECIAL** → 每個變身道具觸發自己的 row/col/cross 範圍,
	#     不用再額外擴散到鄰邊(那是道具自己的工作)。
	await get_tree().create_timer(0.15).timeout
	if transform_to < 0:
		_explode_cells_no_chain(targets)
	else:
		_plane_batch_claimed.clear()
		_explode_cells(targets, EXPLODE_MODE_SPECIAL)
		_plane_batch_claimed.clear()

func _destroy_candy_at(pos: Vector2i, color_for_signal: int, mode: int = EXPLODE_MODE_MATCH) -> void:
	var c = filler.get_candy_at(pos)
	if c and not c.is_being_destroyed:
		match mode:
			EXPLODE_MODE_PLANE, EXPLODE_MODE_SPECIAL:
				if obstacle_map.has(pos):
					_damage_obstacle(pos)
				if bottom_obstacle_map.has(pos):
					_damage_bottom_obstacle(pos)
			_:
				_trigger_obstacle_adjacent(pos, c.candy_color)
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

# 消除模式 — 控制「destroy 一顆糖時,要對哪些障礙物造成傷害」。
# 設計需求(user 確認):
#   MATCH   — 一般 match 消除:adj + inplace(鄰邊 obstacle + 自身 inplace obstacle,
#             各種 obstacle 按 _ELIM_RULES 決定能不能被 adj/inplace 打)
#   SPECIAL — 道具觸發的消除(TNT / Rocket / Color Bomb / Spiral chain / 紙飛機落點):
#             「所有被道具影響的格都消除」— 不管是糖、Puddle、Crt、Barrel 等等,
#             只要在 target 範圍內就 obstacle 直接扣 HP(無視 _ELIM_RULES 的 inplace 設定),
#             但「不擴散到 4 鄰」— 鄰邊 obstacle 不會被波及。
#   PLANE   — 同 SPECIAL,留作未來細分用(目前行為與 SPECIAL 一致)


func _explode_cells(targets: Array, mode: int = EXPLODE_MODE_MATCH) -> void:
	# targets: Array of Vector2i
	# mode 行為見上方常數註解。
	# 遞增 _damage_tick_id → 同一個 _explode_cells call 內所有 Chiller/Stamp 的傷害
	# 都跟這個 tick 比對 → 同一瞬間只算 1 次(per-match dedup)。
	_obstacle_damage_mode = mode
	_damage_tick_id += 1
	var chain_queue: Array = []
	var destroyed_cells: Array[Vector2i] = []
	for tp in targets:
		var pos: Vector2i = tp as Vector2i
		var c = filler.get_candy_at(pos)
		if c == null or c.is_being_destroyed:
			# 空格 → 看 mode 決定要不要打 obstacle
			match mode:
				EXPLODE_MODE_PLANE, EXPLODE_MODE_SPECIAL:
					if obstacle_map.has(pos):
						_damage_obstacle(pos)
						effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), 0)
					if bottom_obstacle_map.has(pos):
						_damage_bottom_obstacle(pos)
						if not obstacle_map.has(pos):
							effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), 0)
					destroyed_cells.append(pos)
				_:
					_trigger_obstacle_adjacent(pos, -1)
			continue
		var ct = c.candy_type
		var color: int = c.candy_color
		if ct != CandyScript.CandyType.NORMAL:
			# 是 special candy → 加入連鎖佇列,先記下,destroy 後再觸發 effect
			chain_queue.append({"pos": pos, "type": ct, "color": color})
		# 對該 cell 的 obstacle 傷害判定
		match mode:
			EXPLODE_MODE_PLANE, EXPLODE_MODE_SPECIAL:
				# 該格 obstacle 直接打(無視 inplace 規則),不擴散到 4 鄰
				if obstacle_map.has(pos):
					_damage_obstacle(pos)
				if bottom_obstacle_map.has(pos):
					_damage_bottom_obstacle(pos)
			_:
				_trigger_obstacle_adjacent(pos, color)
		effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), color)
		filler.remove_candy_at(pos)
		c.animate_destroy()
		candies_destroyed.emit(1, color)
		destroyed_cells.append(pos)
	# SPECIAL/PLANE 模式也要觸發相鄰的 manufacturer(Stamp)
	if mode != EXPLODE_MODE_MATCH and destroyed_cells.size() > 0:
		_trigger_manufacturers_adjacent_to_cells(destroyed_cells)
	# 連鎖:對每個被波及的 special candy 觸發其 effect
	# (此時該 special candy 已 remove,_chain_trigger 不會再 destroy 自己)
	for ch in chain_queue:
		_chain_trigger(ch["type"], ch["pos"], ch["color"])


func _explode_cells_no_chain(targets: Array) -> void:
	_obstacle_damage_mode = EXPLODE_MODE_MATCH
	_damage_tick_id += 1
	for tp in targets:
		var pos: Vector2i = tp as Vector2i
		var c = filler.get_candy_at(pos)
		if c == null or c.is_being_destroyed:
			_trigger_obstacle_adjacent(pos, -1)
			continue
		var color: int = c.candy_color
		_trigger_obstacle_adjacent(pos, color)
		effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(pos), color)
		filler.remove_candy_at(pos)
		c.animate_destroy()
		candies_destroyed.emit(1, color)


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
			# 設計:紙飛機觸發 = 原位 4-neighbor 展開 + 飛到高權重目標(目的地只消 1 格)
			AudioManager.play_special_trigger_sound()
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(pos))
			# 原位 4 鄰展開(self 已由 _explode_cells caller 處理)
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					sub_targets.append(tp)
			# 飛到目的地,只消落點 1 格(不展開)；排除同批已被選走的目標
			var excl_plane: Array[Vector2i] = [pos]
			for claimed in _plane_batch_claimed:
				if claimed not in excl_plane:
					excl_plane.append(claimed)
			var picks_spiral = _pick_top_plane_targets(1, excl_plane)
			if picks_spiral.size() > 0:
				var tgt_spiral: Vector2i = picks_spiral[0]
				_plane_batch_claimed.append(tgt_spiral)
				var from_ws: Vector2 = filler.grid_to_world(pos)
				var to_ws: Vector2 = filler.grid_to_world(tgt_spiral)
				effect_spawner_node.spawn_plane_flight(from_ws, to_ws, color, 1.0)
				_deferred_plane_impact(to_ws, 0.92)
				_deferred_explode([tgt_spiral], 1.0, EXPLODE_MODE_PLANE)
		CandyScript.CandyType.COLOR_BOMB:
			# 連鎖中的彩球:只清同色基本元素
			AudioManager.play_special_trigger_sound()
			effect_spawner_node.spawn_firework(filler.grid_to_world(pos))
			var num_colors_local = filler.num_colors if filler else 4
			var picked = randi() % num_colors_local
			for x in grid_width:
				for y in grid_height:
					var p = Vector2i(x, y)
					var c2 = filler.get_candy_at(p)
					if c2 and not c2.is_being_destroyed and c2.candy_color == picked and c2.candy_type == CandyScript.CandyType.NORMAL:
						sub_targets.append(p)
	# 道具連鎖一律用 SPECIAL：直接清掉目標格上的障礙物（含「只吃道具」的 SalmonCan）。
	# (紙飛機十字原本用 MATCH → 打不到 SalmonCan；user 要求十字本身能清鮪魚罐頭 → 改 SPECIAL)
	_explode_cells(sub_targets, EXPLODE_MODE_SPECIAL)


# 延後 delay 秒後觸發 _explode_cells(targets)。用於紙飛機飛行動畫:等飛機落地再爆。
# 用 timer + 一次性 callback,避免阻塞當前 frame。
# mode 跟 _explode_cells 一致:MATCH / SPECIAL / PLANE。
# 使用 _deferred_queue 確保延遲爆炸不會和主 cascade 並行。
var _deferred_queue: Array[Dictionary] = []
var _deferred_running: bool = false

func _deferred_explode(targets: Array, delay: float, mode: int = EXPLODE_MODE_MATCH) -> void:
	# 注意:用 entry 的「字典參考」標記 ready,不要用入列當下的 index ——
	# _try_flush_deferred_queue() 會 pop_front,index 會位移。多重延遲爆炸
	# (光球+紙飛機/條紋/包裝)時,後面項目若用舊 index 會永遠標不到 ready,
	# 導致佇列卡住、is_processing 不解鎖、盤面卡死。
	# GDScript 的 Dictionary 是參考型別,pop_front 不影響這個參考。
	var entry: Dictionary = {"targets": targets, "mode": mode, "ready": false}
	_deferred_queue.append(entry)
	var t = get_tree().create_timer(delay)
	t.timeout.connect(func():
		entry["ready"] = true
		_try_flush_deferred_queue()
	)

func _try_flush_deferred_queue() -> void:
	if _deferred_running:
		return
	_deferred_running = true
	while _deferred_queue.size() > 0 and _deferred_queue[0].get("ready", false):
		var entry = _deferred_queue.pop_front()
		if not is_instance_valid(self):
			break
		if GameManager.current_state == GameManager.GameState.LEVEL_COMPLETE:
			break
		_explode_cells(entry["targets"], entry["mode"])
		await _cascade_loop()
		_sync_candy_layer_visibility()
	_deferred_running = false
	if _deferred_queue.size() == 0 and not _deferred_running:
		_post_turn_check()
	else:
		# 還有 entry 沒處理(front 還沒 ready,或某個 entry 的 timer 剛好在 flush 執行中
		# 觸發、被 _deferred_running 擋掉而漏掉)→ 短延遲後「重試保險」,確保佇列一定會被
		# 排空、_post_turn_check 一定會被呼叫。否則會卡死(is_processing 不解鎖)+ 留空格。
		var t := get_tree().create_timer(0.12)
		t.timeout.connect(_try_flush_deferred_queue)


# 延後 delay 秒後 spawn 飛機落地特效(衝擊環 + 火光 + 閃光)。
# 用於與 _deferred_explode 搭配:impact 先發(視覺先到),稍後 explode(實際消除)。
func _deferred_plane_impact(world_pos: Vector2, delay: float) -> void:
	var t = get_tree().create_timer(delay)
	t.timeout.connect(func(): effect_spawner_node.spawn_plane_impact(world_pos))

func _handle_special_combo(candy_a: CandyScript, candy_b: CandyScript, effect: String) -> void:
	var pos_a = candy_a.grid_pos
	var pos_b = candy_b.grid_pos
	var mid_pos = pos_a
	AudioManager.play_special_trigger_sound()

	match effect:
		"double_striped":
			# Cross elimination: full row + full column
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color, EXPLODE_MODE_SPECIAL)
			_destroy_candy_at(pos_b, candy_b.candy_color, EXPLODE_MODE_SPECIAL)
			# 十字 4 鄰 = 相鄰消除語意(MATCH),不是道具原地炸(SPECIAL)
			_explode_cells(SpecialCandy.get_cross_targets(mid_pos, grid_width, grid_height), EXPLODE_MODE_MATCH)

		"double_wrapped":
			# 7×7 big explosion (TNT + TNT,半徑 3)
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			effect_spawner_node.spawn_firework(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color, EXPLODE_MODE_SPECIAL)
			_destroy_candy_at(pos_b, candy_b.candy_color, EXPLODE_MODE_SPECIAL)
			_explode_cells(SpecialCandy.get_big_wrapped_targets(mid_pos, grid_width, grid_height), EXPLODE_MODE_SPECIAL)

		"wrapped_striped":
			# Giant cross: 3 rows + 3 columns
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color, EXPLODE_MODE_SPECIAL)
			_destroy_candy_at(pos_b, candy_b.candy_color, EXPLODE_MODE_SPECIAL)
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
			_explode_cells(ws_targets, EXPLODE_MODE_SPECIAL)

		"double_spiral":
			# 設計文件「紙飛機+紙飛機」:合成點 4 鄰消除 + 起飛 3 台紙飛機
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color, EXPLODE_MODE_SPECIAL)
			_destroy_candy_at(pos_b, candy_b.candy_color, EXPLODE_MODE_SPECIAL)
			# 合成點 4 鄰
			var nbors: Array[Vector2i] = []
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = mid_pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					nbors.append(tp)
			_explode_cells(nbors, EXPLODE_MODE_MATCH)
			# 飛 3 台紙飛機(平行起飛,弧形飛到 top3 目標)
			var picks = _pick_top_plane_targets(3, [mid_pos, pos_a, pos_b])
			var from_w: Vector2 = filler.grid_to_world(mid_pos)
			for tgt in picks:
				var to_w: Vector2 = filler.grid_to_world(tgt)
				effect_spawner_node.spawn_plane_flight(from_w, to_w, candy_a.candy_color, 1.0)
				_deferred_plane_impact(to_w, 0.92)
			# 等飛行完成再依序爆破(同時也讓畫面看得清楚連鎖)
			await get_tree().create_timer(1.05).timeout
			for tgt2 in picks:
				_detonate_at(tgt2, "spiral")
				await get_tree().create_timer(0.1).timeout

		"spiral_wrapped":
			# 設計文件「紙飛機+炸彈」:合成點 4 鄰消除 + 飛到新位置「使用炸彈」(5x5)
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color, EXPLODE_MODE_SPECIAL)
			_destroy_candy_at(pos_b, candy_b.candy_color, EXPLODE_MODE_SPECIAL)
			var nbors_w: Array[Vector2i] = []
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = mid_pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					nbors_w.append(tp)
			_explode_cells(nbors_w, EXPLODE_MODE_MATCH)
			await get_tree().create_timer(0.15).timeout
			var excl: Array[Vector2i] = [mid_pos, pos_a, pos_b]
			var picks_w = _pick_top_plane_targets_for_combo(1, excl, "wrapped")
			if picks_w.size() > 0:
				var tgt: Vector2i = picks_w[0]
				var to_w2: Vector2 = filler.grid_to_world(tgt)
				var from_w2: Vector2 = filler.grid_to_world(mid_pos)
				_deferred_plane_impact(to_w2, 0.92)
				await effect_spawner_node.spawn_plane_flight(from_w2, to_w2, candy_a.candy_color, 1.0)
				_detonate_at(tgt, "wrapped")

		"spiral_striped":
			# 設計文件「紙飛機+火箭」:合成點 4 鄰消除 + 飛到新位置「使用火箭」
			var striped_kind = "striped_h"
			if candy_a.candy_type == CandyScript.CandyType.STRIPED_V \
			   or candy_b.candy_type == CandyScript.CandyType.STRIPED_V:
				striped_kind = "striped_v"
			effect_spawner_node.spawn_shockwave(filler.grid_to_world(mid_pos))
			_destroy_candy_at(pos_a, candy_a.candy_color, EXPLODE_MODE_SPECIAL)
			_destroy_candy_at(pos_b, candy_b.candy_color, EXPLODE_MODE_SPECIAL)
			var nbors_s: Array[Vector2i] = []
			for offset in [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]:
				var tp = mid_pos + offset
				if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
					nbors_s.append(tp)
			_explode_cells(nbors_s, EXPLODE_MODE_MATCH)
			await get_tree().create_timer(0.15).timeout
			var excl_s: Array[Vector2i] = [mid_pos, pos_a, pos_b]
			var picks_s = _pick_top_plane_targets_for_combo(1, excl_s, striped_kind)
			if picks_s.size() > 0:
				var tgt: Vector2i = picks_s[0]
				var to_w3: Vector2 = filler.grid_to_world(tgt)
				var from_w3: Vector2 = filler.grid_to_world(mid_pos)
				_deferred_plane_impact(to_w3, 0.92)
				await effect_spawner_node.spawn_plane_flight(from_w3, to_w3, candy_a.candy_color, 1.0)
				_detonate_at(tgt, striped_kind)

	await get_tree().create_timer(0.3).timeout
	await _cascade_loop()

func _process_matches(matches: Array[Dictionary], swap_cells: Array[Vector2i] = []) -> void:
	# swap_cells:玩家剛 swap 的兩格 [pos_a (來源), pos_b (目標)]。
	# 若某個 match group 內含這兩格之一,合成 special 的位置會用 swap dest
	# (pos_b 優先,代表玩家手指落下的地方),這樣 special candy 不會「噴去別處」。
	# cascade 連鎖呼叫時 swap_cells 為空,沿用 match_finder 原計算的 special_pos。
	for match_data in matches:
		# 每個 match 群組一個 tick — 讓相鄰障礙物 dedup 正確(含 _process_matches 路徑)
		_damage_tick_id += 1
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
		# 延伸消除（設計 B 節：5 連/炸彈/2×2；T 形四格已併入 cells）
		if filler:
			for ep in MatchFinder.collect_extended_elimination(
					filler.grid, grid_width, grid_height, cells, shape, special_pos,
					match_color, blocked_cells):
				if ep not in cells:
					cells.append(ep)
		var special_type = -1

		# 對齊 Python 設計優先級:FIVE_PLUS > L_T > FOUR > 2x2 > THREE
		# 對應 yuehpo candy_type:COLOR_BOMB(LtBl) / WRAPPED(TNT) / STRIPED(Soda) / WRAPPED 暫代(TrPr)
		if shape == "five":
			special_type = CandyScript.CandyType.COLOR_BOMB
		elif shape == "special":  # L_T (h≥3 且 v≥2，含橫三+下一格)
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
				_trigger_obstacle_adjacent(cell, match_color)
				effect_spawner_node.spawn_destroy_effect(filler.grid_to_world(cell), candy.candy_color)
				GameManager.update_objective("collect", candy.candy_color, 1)
				candies_destroyed.emit(1, candy.candy_color)
				filler.remove_candy_at(cell)
				candy.animate_destroy()
		# 保險:確保與 match 相鄰的郵戳都有觸發到(中間欄消除時常靠這條)
		_trigger_manufacturers_adjacent_to_cells(cells)

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
	# Gravity 跟 fill 一起 tween:
	# - 可移動障礙物 (Barrel / TrafficCone) 先掉(它們不在 grid 裡,要另外處理)
	# - apply_gravity 把既有 candy 往下移(含左/右斜補)
	# - fill_empty_cells 在頂端可達的欄生新 candy 往下落
	#
	# 重要:盤面如果有大量空格(例如 TNT 把中間挖空),光靠一次 gravity + fill 不夠 ——
	# fill 只能從「頂端可達的欄」生糖,中間被障礙物擋住的欄要靠斜補從旁邊流過來。
	# 所以這裡用 while loop,反覆 gravity + fill 直到沒人在動為止。
	# 第一輪算「主要動畫」(等 tween 完),後面幾輪如果有動才繼續等。
	var first_round = true
	var safety = 0
	while safety < (grid_width + grid_height) * 2:
		safety += 1

		# 順序很重要：先讓元素落下 → 再讓木桶落進元素讓出的空格 → 最後才補新元素。
		# (若先補格，fill 會把木桶下方剛空出的格填回新元素——因為 fill 把可移動障礙當「會讓路」
		#  → 木桶永遠等不到空格、卡在上面不落。Level 39「清下面元素、上面木桶不落」就是這個。)
		var gravity_tweens = filler.apply_gravity()
		var obs_tweens = _apply_movable_obstacle_gravity()
		var fill_tweens = filler.fill_empty_cells()

		# 新生成的 candy 接 input signals(舊的有 is_connected check,不會重複 connect)
		if fill_tweens.size() > 0:
			for x in grid_width:
				for y in grid_height:
					var c = filler.get_candy_at(Vector2i(x, y))
					if c:
						_connect_single_candy(c)

		var all_tweens = obs_tweens + gravity_tweens + fill_tweens
		# 沒有任何 tween → 盤面 stable,結束 cascade
		if all_tweens.size() == 0:
			break

		# 等 tween 完(sequential await,但 tween 本身平行跑)
		for tw in all_tweens:
			if tw and tw.is_running():
				await tw.finished
		if first_round:
			await get_tree().create_timer(0.08).timeout
			first_round = false

	var new_matches = MatchFinder.find_all_matches(filler.grid, grid_width, grid_height, blocked_cells)
	if new_matches.size() > 0:
		# cascade 中途如果已達成勝利，提前通知（勝利畫面先出現，動畫背景繼續）
		if GameManager.current_state != GameManager.GameState.LEVEL_COMPLETE and GameManager.check_win_condition():
			GameManager.complete_level()
		cascade_level += 1
		AudioManager.play_cascade_sound(cascade_level)
		await _process_matches(new_matches)
	# 主 cascade 結束，處理排隊中的延遲爆炸
	_try_flush_deferred_queue()

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


func _obs_plane_weight(obs: Dictionary) -> int:
	var tid := str(obs.get("tile_id", ""))
	var base_w := 0
	for prefix in _PLANE_WEIGHT_BY_PREFIX.keys():
		if tid.begins_with(prefix):
			base_w = _PLANE_WEIGHT_BY_PREFIX[prefix]
			break
	if base_w <= 0:
		return 0
	if int(obs.get("hp", 1)) == 1:
		base_w += 1
	if _is_plane_objective_tile(tid):
		base_w += 100
	return base_w


func _compute_plane_target_weights() -> Dictionary:
	# 回傳 {Vector2i pos: int weight}。多格 instance 只回傳一個 representative cell。
	var weights: Dictionary = {}
	var seen_inst: Dictionary = {}
	for pos in obstacle_map.keys():
		var obs = obstacle_map[pos]
		var inst_id = str(obs.get("instance_id", ""))
		if inst_id != "" and seen_inst.has(inst_id):
			continue
		var w := _obs_plane_weight(obs)
		if w <= 0:
			continue
		weights[pos] = w
		if inst_id != "":
			seen_inst[inst_id] = true
	return weights


## 道具在落點引爆時會打到的格（SPECIAL 模式：炸彈 5×5、火箭整行/列、飛機僅落點）
func _powerup_blast_cells_at(center: Vector2i, detonate_kind: String) -> Array[Vector2i]:
	var uniq: Dictionary = {}
	uniq[center] = true
	match detonate_kind:
		"wrapped":
			for tp in SpecialCandy.get_wrapped_targets(center, grid_width, grid_height):
				uniq[tp] = true
		"striped_h":
			for tp in SpecialCandy.get_striped_h_targets(center, grid_width):
				uniq[tp] = true
		"striped_v":
			for tp in SpecialCandy.get_striped_v_targets(center, grid_height):
				uniq[tp] = true
		"spiral":
			pass
	var out: Array[Vector2i] = []
	for k in uniq.keys():
		out.append(k as Vector2i)
	return out


func _sum_obstacle_weights_in_cells(cells: Array[Vector2i]) -> int:
	var total := 0
	var seen_inst: Dictionary = {}
	for pos in cells:
		if not obstacle_map.has(pos):
			continue
		var obs = obstacle_map[pos]
		var inst_id = str(obs.get("instance_id", ""))
		if inst_id != "":
			if seen_inst.has(inst_id):
				continue
			seen_inst[inst_id] = true
		total += _obs_plane_weight(obs)
	return total


## 紙飛機+道具：依「落點施放道具後能覆蓋到的障礙物權重總和」選目標
func _pick_top_plane_targets_for_combo(
		n: int, exclude: Array[Vector2i], detonate_kind: String
) -> Array[Vector2i]:
	var scored: Array[Dictionary] = []
	for x in grid_width:
		for y in grid_height:
			var p := Vector2i(x, y)
			if p in exclude:
				continue
			var blast := _powerup_blast_cells_at(p, detonate_kind)
			var score := _sum_obstacle_weights_in_cells(blast)
			if score > 0:
				scored.append({"pos": p, "score": score})
	scored.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return int(a["score"]) > int(b["score"])
	)
	var picks: Array[Vector2i] = []
	for entry in scored:
		var p: Vector2i = entry["pos"]
		if p in picks:
			continue
		picks.append(p)
		if picks.size() >= n:
			break
	if picks.size() < n:
		var fallback := _pick_top_plane_targets(n - picks.size(), exclude + picks)
		for fp in fallback:
			if fp not in picks:
				picks.append(fp)
			if picks.size() >= n:
				break
	return picks


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
	# 全部走 SPECIAL/PLANE mode(道具觸發 → 只 inplace、不擴散到 4 鄰 obstacle)
	effect_spawner_node.spawn_shockwave(filler.grid_to_world(pos))
	if kind == "spiral":
		# 紙飛機精準打擊落點 1 格(PLANE mode → 即使空格也打 pos 的 obstacle)
		_explode_cells([pos], EXPLODE_MODE_PLANE)
		return
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
	_explode_cells(cells, EXPLODE_MODE_SPECIAL)


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


func _trigger_manufacturers_adjacent_to_cells(cells: Array[Vector2i]) -> void:
	var seen: Dictionary = {}
	for cell in cells:
		for dir in [Vector2i(0, -1), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(1, 0)]:
			var adj: Vector2i = cell + dir
			if seen.has(adj):
				continue
			if not obstacle_map.has(adj):
				continue
			var adj_obs = obstacle_map[adj]
			if adj_obs.get("type", "") != "manufacturer":
				continue
			var adj_tid: String = str(adj_obs.get("tile_id", ""))
			if not _elim_rule(adj_tid, "adj"):
				continue
			seen[adj] = true
			_damage_obstacle(adj)


func _trigger_obstacle_adjacent(pos: Vector2i, match_color_idx: int = -1) -> void:
	# 這條路徑代表「一般 match / 鄰邊消除」語意 → 強制把傷害模式設回 MATCH。
	# 否則會殘留上一波 _explode_cells 設的 SPECIAL/PLANE,導致飲料櫃被普通 match
	# 打到時誤走「道具分支」→ 殺到「標號在前的瓶」而非對色瓶。
	_obstacle_damage_mode = EXPLODE_MODE_MATCH
	var color_name := _color_name_from_candy_idx(match_color_idx)
	for dir in [Vector2i(0, -1), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(1, 0)]:
		var adj = pos + dir
		if obstacle_map.has(adj):
			var adj_obs = obstacle_map[adj]
			var adj_tid = adj_obs.get("tile_id", "")
			if _elim_rule(adj_tid, "adj"):
				_damage_obstacle(adj, color_name)
	if obstacle_map.has(pos):
		var obs = obstacle_map[pos]
		var tid = obs.get("tile_id", "")
		if _elim_rule(tid, "inplace"):
			_damage_obstacle(pos, color_name)
	# bottom layer (Puddle): 糖在上面被 match 消除時 inplace 打水窪
	if bottom_obstacle_map.has(pos):
		var bobs = bottom_obstacle_map[pos]
		var btid: String = str(bobs.get("tile_id", ""))
		if _elim_rule(btid, "inplace"):
			_damage_bottom_obstacle(pos)


static func _color_name_from_candy_idx(idx: int) -> String:
	if idx >= 0 and idx < CANDY_IDX_TO_COLOR_NAME.size():
		return CANDY_IDX_TO_COLOR_NAME[idx]
	return ""


func _damage_bottom_obstacle(pos: Vector2i) -> void:
	if not bottom_obstacle_map.has(pos):
		return
	# 任何障礙物(中層 Crt/Barrel… 或上層 Mud/Rope)還蓋在這格 → 先擋著,水窪不扣血。
	# 必須先把覆蓋的障礙物清掉,水窪才會開始受傷（兩階段：先打障礙再消水漥）。
	# 另外:即使覆蓋物在「這一 tick」被打死,同一 tick 內水窪仍不受傷(該擊算在清障礙)，
	# 要等下一擊才扣 —— 用 _upper_blocked_bottom_tick 判定（涵蓋道具爆炸同時打中層+底層的情況）。
	if _obstacle_covers_bottom_at(pos) \
			or int(_upper_blocked_bottom_tick.get(pos, -1)) == _damage_tick_id:
		return
	var obs = bottom_obstacle_map[pos]
	var tid: String = str(obs.get("tile_id", ""))
	obs["hp"] -= 1
	AudioManager.play_obstacle_break_sound()
	if obs["hp"] <= 0:
		bottom_obstacle_map.erase(pos)
		GameManager.update_objective("clear_" + obs.get("type", "jelly"), -1, 1, tid)
		_fly_goal_feedback(pos, tid)
	board_bg.queue_redraw()


func _damage_obstacle(pos: Vector2i, adj_color_name: String = "") -> void:
	if not obstacle_map.has(pos):
		return
	var obs = obstacle_map[pos]
	var tid: String = str(obs.get("tile_id", ""))

	# 水窪護盾:這一 tick 此格有障礙物(任何中層/上層障礙)被處理 → 記下來,
	# 讓同 tick 的 _damage_bottom_obstacle 知道「覆蓋物擋了這擊」,水窪不受傷。
	# (在扣 HP / 移除之前先記,確保「打死覆蓋物的那一擊」也算擋住 → 道具爆炸不會同時打穿到水窪。)
	_upper_blocked_bottom_tick[pos] = _damage_tick_id

	if tid.begins_with("SalmonCan") \
			and _obstacle_damage_mode != EXPLODE_MODE_SPECIAL \
			and _obstacle_damage_mode != EXPLODE_MODE_PLANE:
		return

	# 飲料櫃：相鄰須對色 + 殺對色瓶；同一 match instance 去重
	if tid.begins_with("BeverageChiller"):
		if not _try_damage_beverage_chiller(obs, adj_color_name):
			return
		_apply_obstacle_hp_after_hit(obs, pos, tid)
		return

	# 同一瞬間去重：飲料櫃(已處理)、郵戳、礦泉水(關門或 match)；
	# 開門後道具範圍每格各算一次（不去重）
	if _should_per_match_dedup(tid, obs, _obstacle_damage_mode):
		if int(obs.get("_last_damage_tick", -1)) == _damage_tick_id:
			return
		obs["_last_damage_tick"] = _damage_tick_id

	# 明信片(Stamp)— 製造機特殊分支:
	#   不扣 HP、不從盤面移除,每次受 adj 消除就 GOAL +1。
	#   對齊 Python match_engine.py::_damage_middle(manufacturer 分支)。
	if obs.get("type", "") == "manufacturer":
		AudioManager.play_obstacle_break_sound()
		if obs.get("stamp_state", "idle") != "victory":
			obs["stamp_state"] = "pressed"
			if board_bg.has_method("trigger_stamp_flash"):
				board_bg.trigger_stamp_flash(pos)
			effect_spawner_node.spawn_stamp_trigger(filler.grid_to_world(pos))
			_schedule_stamp_return_idle(pos, 0.55)
		# 同一 match 群組,同一個 Stamp 只 +1 GOAL;不同 Stamp 各自計算
		var last_tick_for_pos: int = int(_stamp_goal_last_tick.get(pos, -1))
		if _damage_tick_id != last_tick_for_pos:
			_stamp_goal_last_tick[pos] = _damage_tick_id
			GameManager.update_objective("clear_" + obs["type"], -1, 1, tid)
			_fly_goal_feedback(pos, tid)
		board_bg.queue_redraw()
		return

	_apply_obstacle_hp_after_hit(obs, pos, tid)


func _try_damage_beverage_chiller(obs: Dictionary, adj_color_name: String) -> bool:
	var max_hp: int = int(obs.get("max_hp", 5))
	var hp: int = int(obs.get("hp", 0))

	var bottle_colors: Dictionary = obs.get("bottle_colors", {})
	if not obs.has("bottle_alive"):
		obs["bottle_alive"] = {}
	var bottle_alive: Dictionary = obs["bottle_alive"]
	for cell in obs.get("instance_cells", []):
		if not bottle_alive.has(cell):
			bottle_alive[cell] = true

	var is_powerup := (
		_obstacle_damage_mode == EXPLODE_MODE_SPECIAL
		or _obstacle_damage_mode == EXPLODE_MODE_PLANE
	)

	if is_powerup:
		# dedup：同一 tick 同一 instance 只受一次
		if int(obs.get("_last_damage_tick", -1)) == _damage_tick_id:
			return false
		obs["_last_damage_tick"] = _damage_tick_id
		if hp >= max_hp:
			pass
		else:
			var killed := false
			for cell in obs.get("instance_cells", []):
				if bottle_alive.get(cell, true):
					bottle_alive[cell] = false
					killed = true
					break
			if not killed:
				return false
	elif adj_color_name == "":
		return false
	elif hp >= max_hp:
		# 關門狀態：任何相鄰消除都能開門（user 要求不需對色；瓶子才需對色）。只做 dedup。
		if int(obs.get("_last_damage_tick", -1)) == _damage_tick_id:
			return false
		obs["_last_damage_tick"] = _damage_tick_id
	else:
		# 開門狀態：找對色的活瓶子殺掉
		var target: Vector2i = Vector2i(-1, -1)
		for cell in obs.get("instance_cells", []):
			if bottle_alive.get(cell, true) and str(bottle_colors.get(cell, "")) == adj_color_name:
				target = cell
				break
		if target.x < 0:
			return false
		# 有效 hit，dedup
		if int(obs.get("_last_damage_tick", -1)) == _damage_tick_id:
			return false
		obs["_last_damage_tick"] = _damage_tick_id
		bottle_alive[target] = false

	obs["hp"] = hp - 1
	return true


func _apply_obstacle_hp_after_hit(obs: Dictionary, pos: Vector2i, tid: String) -> void:
	if not tid.begins_with("BeverageChiller"):
		obs["hp"] -= 1
	if tid.begins_with("SalmonCan") and obs["hp"] > 0:
		obs["salmon_state"] = "open"
	AudioManager.play_obstacle_break_sound()

	if _is_hits_mode_obstacle(tid):
		GameManager.update_objective("clear_" + obs["type"], -1, 1, tid)
		_fly_goal_feedback(pos, tid)

	if obs["hp"] <= 0:
		var cells_to_clear: Array = obs.get("instance_cells", [pos])
		if cells_to_clear.is_empty():
			cells_to_clear = [pos]
		if not _is_hits_mode_obstacle(tid):
			GameManager.update_objective("clear_" + obs["type"], -1, 1, tid)
			_fly_goal_feedback(pos, tid)
		for cell in cells_to_clear:
			obstacle_map.erase(cell)
			if cell in blocked_cells:
				blocked_cells.erase(cell)
			if filler.movable_obstacle_cells.has(cell):
				filler.movable_obstacle_cells.erase(cell)
		# Pool 打爆後在 2x2 範圍 + 周圍 8 格生成 Puddle_lv1
		if tid.begins_with("Pool"):
			_spawn_pool_puddles(cells_to_clear)
	board_bg.queue_redraw()
	_sync_candy_layer_visibility()


func _spawn_pool_puddles(pool_cells: Array) -> void:
	# Pool 打爆後在 2x2 本體 + 上下左右各擴展一格（共最多 12 格）生成 Puddle_lv1
	var puddle_positions: Array[Vector2i] = []
	# 收集 2x2 本體
	for cell in pool_cells:
		var p: Vector2i = cell as Vector2i
		puddle_positions.append(p)
	# 收集周圍 8 格（2x2 的外圍）
	var pool_set: Dictionary = {}
	for p in puddle_positions:
		pool_set[p] = true
	var neighbors: Array[Vector2i] = []
	for p in puddle_positions:
		for off in [Vector2i(-1,0), Vector2i(1,0), Vector2i(0,-1), Vector2i(0,1)]:
			var np: Vector2i = p + off
			if pool_set.has(np):
				continue
			if np.x < 0 or np.x >= grid_width or np.y < 0 or np.y >= grid_height:
				continue
			if not pool_set.has(np):
				pool_set[np] = true
				neighbors.append(np)
	puddle_positions.append_array(neighbors)
	# 只在沒有障礙物的格子生成 Puddle
	for p in puddle_positions:
		if obstacle_map.has(p):
			continue
		if p in blocked_cells:
			continue
		var puddle_data: Dictionary = {
			"type": "jelly",
			"hp": 1,
			"max_hp": 1,
			"tile_id": "Puddle_lv1",
			"layer": "bottom",
		}
		bottom_obstacle_map[p] = puddle_data


# 官方 Goal Count 對障礙物的意義分兩派(見 _damage_obstacle 註解):
#   hits 模式 = 每扣 1 滴血就 +1 GOAL(因為 goal 數 = HP 總和)
#   instance 模式 = 該 instance 整顆破才 +1 GOAL(因為 goal 數 = 物件數)
static func _is_hits_mode_obstacle(tile_id: String) -> bool:
	return (
		tile_id.begins_with("WaterChiller")
		or tile_id.begins_with("BeverageChiller")
	)


# 同一個 match / _explode_cells tick 內去重：
#   - 飲料櫃、郵戳 — 每 instance 只算 1 次
#   - 礦泉水 — 關門或 match 相鄰只算 1 次；開門後道具每格各算 1 次
static func _should_per_match_dedup(tile_id: String, obs: Dictionary, damage_mode: int = EXPLODE_MODE_MATCH) -> bool:
	if tile_id == "Stamp":
		return true
	if tile_id.begins_with("BeverageChiller"):
		return true
	if tile_id.begins_with("WaterChiller"):
		var hp: int = int(obs.get("hp", 0))
		var max_hp: int = int(obs.get("max_hp", 11))
		if damage_mode == EXPLODE_MODE_SPECIAL or damage_mode == EXPLODE_MODE_PLANE:
			if hp < max_hp:
				return false
		return true
	return false


# 可移動障礙物 = Barrel + TrafficCone — 跟道具/元素一樣會掉(user 確認)。
# (其他障礙物如 Crt、WaterChiller、BeverageChiller、Pool、SalmonCan、Stamp 等都釘死,
#  跟 yuehpo / 官方設計一致。)
static func _is_movable_obstacle(tile_id: String) -> bool:
	return tile_id.begins_with("Barrel") or tile_id.begins_with("TrafficCone")


# 把可移動障礙物往下挪到最底 — 回傳 tween 列表，跟 candy 一起 await。
# 演算法跟糖的重力類似：多輪 column-drop bottom-up。
func _apply_movable_obstacle_gravity() -> Array[Tween]:
	var tweens: Array[Tween] = []
	# 記錄每個障礙物的原始位置 → 最終位置
	var start_positions: Dictionary = {}  # final_pos → original_pos

	var iter = 0
	while iter < grid_height * 2:
		iter += 1
		var moved_this_round = false
		for y in range(grid_height - 2, -1, -1):
			for x in range(grid_width):
				var pos = Vector2i(x, y)
				if not obstacle_map.has(pos):
					continue
				var obs = obstacle_map[pos]
				var tid = str(obs.get("tile_id", ""))
				if not _is_movable_obstacle(tid):
					continue
				var cells: Array = obs.get("instance_cells", [])
				if cells.size() > 1:
					continue
				var below = Vector2i(x, y + 1)
				if below.y >= grid_height:
					continue
				if below in blocked_cells:
					continue
				if filler.get_candy_at(below) != null:
					continue
				if obstacle_map.has(below):
					continue
				# 追蹤原始位置
				var orig: Vector2i = start_positions.get(pos, pos)
				start_positions.erase(pos)
				start_positions[below] = orig
				# 直落
				obstacle_map[below] = obs
				obstacle_map.erase(pos)
				blocked_cells.erase(pos)
				blocked_cells.append(below)
				filler.movable_obstacle_cells.erase(pos)
				filler.movable_obstacle_cells[below] = true
				moved_this_round = true
		if not moved_this_round:
			break

	# 為所有移動過的障礙物建立 tween（時長跟 candy 一致）
	for final_pos in start_positions:
		var from_pos: Vector2i = start_positions[final_pos]
		var dist = absi(final_pos.y - from_pos.y)
		if dist > 0:
			var duration = filler._fall_duration(dist)
			var tw = board_bg.notify_obstacle_moved(from_pos, final_pos, duration)
			if tw:
				tweens.append(tw)
	if tweens.size() > 0:
		board_bg.queue_redraw()
	return tweens

func _schedule_stamp_return_idle(grid_pos: Vector2i, delay: float) -> void:
	await get_tree().create_timer(delay).timeout
	if not is_instance_valid(self) or not obstacle_map.has(grid_pos):
		return
	var o = obstacle_map[grid_pos]
	if str(o.get("stamp_state", "")) == "pressed":
		o["stamp_state"] = "idle"
		board_bg.queue_redraw()


func _fly_goal_feedback(grid_pos: Vector2i, tile_id: String) -> void:
	var hud = get_tree().get_first_node_in_group("game_hud")
	if hud and hud.has_method("play_objective_fly"):
		var fam = GameManager._tile_family(tile_id)
		hud.play_objective_fly(to_global(filler.grid_to_world(grid_pos)), fam)


func _mark_all_stamps_victory() -> void:
	for p in obstacle_map:
		var o = obstacle_map[p]
		if o.get("type", "") == "manufacturer" or str(o.get("tile_id", "")) == "Stamp":
			o["stamp_state"] = "victory"
	board_bg.queue_redraw()


func _post_turn_check() -> void:
	GameManager.reset_combo()
	_reset_hint_timer()

	if GameManager.current_state == GameManager.GameState.LEVEL_COMPLETE:
		is_processing = false
		turn_completed.emit()
		return

	if GameManager.check_win_condition():
		_mark_all_stamps_victory()
		board_bg.queue_redraw()
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
	var retry := 0
	while retry < 30:
		retry += 1
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

		if MatchFinder.has_possible_moves(filler.grid, grid_width, grid_height, blocked_cells):
			break

func set_obstacle_map(obs: Dictionary) -> void:
	obstacle_map = obs
	board_bg.queue_redraw()

func set_bottom_obstacle_map(obs: Dictionary) -> void:
	bottom_obstacle_map = obs
	board_bg.queue_redraw()

func get_obstacle_map() -> Dictionary:
	return obstacle_map


func _on_obstacle_spawned(pos: Vector2i, tile_id: String) -> void:
	var hp: int = 1
	if tile_id.begins_with("TrafficCone_lv"):
		var lv_str = tile_id.substr(tile_id.find("_lv") + 3)
		hp = int(lv_str) if int(lv_str) > 0 else 1
	elif tile_id.begins_with("TrafficCone"):
		hp = 1
	var obs_data: Dictionary = {
		"type": "jelly",
		"hp": hp,
		"max_hp": hp,
		"tile_id": tile_id,
	}
	obstacle_map[pos] = obs_data
	if not pos in blocked_cells:
		blocked_cells.append(pos)
	if _is_movable_obstacle(tile_id):
		filler.movable_obstacle_cells[pos] = true
	# spawn 進來的障礙物也要像元素一樣「從盤面上方落下」,而不是瞬間出現在定點。
	# 用 board_bg 既有的障礙物位移動畫:from = 盤面上方(-1),to = 落點 pos。
	# (一般重力落下也是走 notify_obstacle_moved,所以非 spawn 的木桶才會有動畫；
	#  spawn 的木桶之前直接 emit 到定點、漏了這段 → 看起來卡住不落。)
	var start_above: Vector2i = Vector2i(pos.x, -1)
	var fall_dist: int = pos.y - start_above.y
	board_bg.notify_obstacle_moved(start_above, pos, filler._fall_duration(fall_dist))
