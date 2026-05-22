extends Control
##
## DemoMain
##
## Demo 模式入口 — 跳過 main_menu / world_map,直接從 res://levels/*.json 載入循環試玩。
##
## 流程:
##   _ready → 找到所有 levels/*.json(由 JsonLevelLoader 收集)
##         → 載入 #0 → game_board.init_board → 顯示 HUD
##         → 通關 → "下一關" → 載入 #1 ... 循環(到底回到 #0)
##         → 失敗 → "重新挑戰" / "下一關"
##
## 不依賴 menu / world_map / save_manager(autoload 仍會啟動,但不參與 demo flow)
##

const JsonLevelLoader = preload("res://scripts/levels/json_level_loader.gd")
const ObstacleScript = preload("res://scripts/obstacles/obstacle.gd")
const LevelSelectScript = preload("res://scripts/level_select.gd")

var game_board_scene: PackedScene = preload("res://scenes/game_board.tscn")
var hud_scene: PackedScene = preload("res://scenes/ui/hud.tscn")
var level_complete_scene: PackedScene = preload("res://scenes/ui/level_complete.tscn")
var level_failed_scene: PackedScene = preload("res://scenes/ui/level_failed.tscn")

var _level_paths: Array[String] = []
var _level_index: int = 0

var current_scene: Node = null
var hud: CanvasLayer = null
var level_complete_ui: Control = null
var level_failed_ui: Control = null
var level_select_ui: CanvasLayer = null
var menu_button_ui: CanvasLayer = null
var current_board: Node2D = null

@onready var scene_container: Control = $SceneContainer


func _ready() -> void:
	_level_paths = JsonLevelLoader.list_demo_levels()
	if _level_paths.is_empty():
		push_error("DemoMain: 找不到 res://levels/*.json,請確認檔案已複製")
		return
	# 嘗試啟動 BGM(若 AudioManager 存在)
	if Engine.has_singleton("AudioManager") or has_node("/root/AudioManager"):
		var audio = get_node_or_null("/root/AudioManager")
		if audio and audio.has_method("start_bgm"):
			audio.start_bgm()
	_show_level_select()


func _show_level_select(from_game: bool = false) -> void:
	# from_game = true 時表示「從遊戲中按選關」,需要顯示「取消」按鈕,
	# 也不能 _clear_current()(否則當前關卡狀態被毀,取消就回不去)
	if not from_game:
		_clear_current()
	if level_select_ui != null:
		level_select_ui.queue_free()
		level_select_ui = null
	level_select_ui = LevelSelectScript.new()
	scene_container.add_child(level_select_ui)
	level_select_ui.setup(_level_paths, from_game)
	level_select_ui.level_selected.connect(_on_level_button_pressed)
	if from_game:
		level_select_ui.cancelled.connect(_on_level_select_cancelled)


func _on_level_select_cancelled() -> void:
	# 從遊戲中按取消 → 關閉 panel,繼續玩本關
	if level_select_ui != null:
		level_select_ui.queue_free()
		level_select_ui = null


func _on_level_button_pressed(idx: int) -> void:
	if level_select_ui != null:
		level_select_ui.queue_free()
		level_select_ui = null
	_start_level(idx)


func _show_menu_button() -> void:
	# 遊戲中右上角的兩顆按鈕:「↻ 重玩」「☰ 選關」,demo 操作起來不卡頓
	if menu_button_ui != null:
		menu_button_ui.queue_free()
	menu_button_ui = CanvasLayer.new()
	menu_button_ui.layer = 20
	add_child(menu_button_ui)

	var font = load("res://resources/fonts/NotoSansTC-Regular.otf") as Font

	# 重玩本關 — 比 demo 跟客戶說「再來一次」最快的入口
	var replay_btn = Button.new()
	replay_btn.text = "↻ 重玩本關"
	if font:
		replay_btn.add_theme_font_override("font", font)
	replay_btn.add_theme_font_size_override("font_size", 18)
	replay_btn.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	replay_btn.offset_left = -310
	replay_btn.offset_right = -160
	replay_btn.offset_top = 16
	replay_btn.offset_bottom = 62
	replay_btn.pressed.connect(func(): _retry_level())
	menu_button_ui.add_child(replay_btn)

	# 選關
	var select_btn = Button.new()
	select_btn.text = "☰ 選關"
	if font:
		select_btn.add_theme_font_override("font", font)
	select_btn.add_theme_font_size_override("font_size", 18)
	select_btn.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	select_btn.offset_left = -150
	select_btn.offset_right = -16
	select_btn.offset_top = 16
	select_btn.offset_bottom = 62
	select_btn.pressed.connect(func(): _show_level_select(true))
	menu_button_ui.add_child(select_btn)


func _clear_current() -> void:
	_disconnect_game_signals()
	if current_scene:
		current_scene.queue_free()
		current_scene = null
	if hud:
		hud.queue_free()
		hud = null
	if level_complete_ui:
		level_complete_ui.queue_free()
		level_complete_ui = null
	if level_failed_ui:
		level_failed_ui.queue_free()
		level_failed_ui = null
	if level_select_ui:
		level_select_ui.queue_free()
		level_select_ui = null
	if menu_button_ui:
		menu_button_ui.queue_free()
		menu_button_ui = null
	current_board = null


func _start_level(idx: int) -> void:
	_clear_current()
	if _level_paths.is_empty():
		return
	_level_index = idx % _level_paths.size()

	var path = _level_paths[_level_index]
	var level_data = JsonLevelLoader.load_from_file(path)
	if level_data == null:
		push_error("DemoMain: load_from_file failed: " + path)
		return

	# level_id 由 JsonLevelLoader 從 JSON 的 "name" 欄位解析(e.g. "Level_26" → 26),
	# 這裡只在 loader 沒解析成功時 fallback 用陣列 index。
	if level_data.level_id <= 0:
		level_data.level_id = _level_index + 1

	GameManager.start_level(level_data)

	var board = game_board_scene.instantiate()
	scene_container.add_child(board)
	current_scene = board
	current_board = board

	board.init_board(level_data)

	if level_data.obstacle_data.size() > 0:
		var obs_map = ObstacleScript.build_obstacle_map(
			level_data.obstacle_data, level_data.grid_width, level_data.grid_height
		)
		board.set_obstacle_map(obs_map)

	if level_data.bottom_obstacle_data.size() > 0:
		var bottom_map = ObstacleScript.build_obstacle_map(
			level_data.bottom_obstacle_data, level_data.grid_width, level_data.grid_height
		)
		board.set_bottom_obstacle_map(bottom_map)

	hud = hud_scene.instantiate()
	scene_container.add_child(hud)
	hud.setup(level_data)

	_show_menu_button()

	GameManager.level_completed.connect(_on_level_completed)
	GameManager.level_failed.connect(_on_level_failed)


func _on_level_completed(_level_id: int, score: int, stars: int) -> void:
	var audio = get_node_or_null("/root/AudioManager")
	if audio and audio.has_method("play_level_complete_sound"):
		audio.play_level_complete_sound()
	level_complete_ui = level_complete_scene.instantiate()
	scene_container.add_child(level_complete_ui)
	level_complete_ui.show_result(score, stars)
	level_complete_ui.next_level_pressed.connect(_next_level)
	level_complete_ui.retry_pressed.connect(_retry_level)
	# menu_pressed → demo 沒有 menu,直接重新從 #0 開始
	level_complete_ui.menu_pressed.connect(_restart_demo)
	_disconnect_game_signals()


func _on_level_failed(_level_id: int) -> void:
	var audio = get_node_or_null("/root/AudioManager")
	if audio and audio.has_method("play_level_failed_sound"):
		audio.play_level_failed_sound()
	level_failed_ui = level_failed_scene.instantiate()
	scene_container.add_child(level_failed_ui)
	level_failed_ui.show_failed()
	level_failed_ui.retry_pressed.connect(_retry_level)
	level_failed_ui.menu_pressed.connect(_restart_demo)
	_disconnect_game_signals()


func _next_level() -> void:
	_start_level(_level_index + 1)


func _retry_level() -> void:
	_start_level(_level_index)


func _restart_demo() -> void:
	# 通關/失敗的 Menu 按鈕 → 回到選關
	_show_level_select()


func _disconnect_game_signals() -> void:
	if GameManager.level_completed.is_connected(_on_level_completed):
		GameManager.level_completed.disconnect(_on_level_completed)
	if GameManager.level_failed.is_connected(_on_level_failed):
		GameManager.level_failed.disconnect(_on_level_failed)
