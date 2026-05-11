extends Control

const LevelLoaderScript = preload("res://scripts/levels/level_loader.gd")
const ObstacleScript = preload("res://scripts/obstacles/obstacle.gd")

var main_menu_scene: PackedScene = preload("res://scenes/ui/main_menu.tscn")
var world_map_scene: PackedScene = preload("res://scenes/world_map.tscn")
var game_board_scene: PackedScene = preload("res://scenes/game_board.tscn")
var hud_scene: PackedScene = preload("res://scenes/ui/hud.tscn")
var level_complete_scene: PackedScene = preload("res://scenes/ui/level_complete.tscn")
var level_failed_scene: PackedScene = preload("res://scenes/ui/level_failed.tscn")

var current_scene: Node = null
var hud: CanvasLayer = null
var level_complete_ui: Control = null
var level_failed_ui: Control = null
var current_board: Node2D = null
var current_level_id: int = 1

@onready var scene_container: Control = $SceneContainer

func _ready() -> void:
	# Demo mode: 跳過 main_menu / world_map,直接導向 demo 入口。
	# 不論 export 設成 main.tscn 還是 demo_main.tscn,都會走 demo flow。
	# (若日後要恢復原 yuehpo menu,把下面三行刪掉、改回 _show_main_menu())
	var demo_scene: PackedScene = load("res://scenes/demo_main.tscn")
	if demo_scene:
		get_tree().change_scene_to_packed.call_deferred(demo_scene)
		return
	_show_main_menu()
	AudioManager.start_bgm()

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
	current_board = null

func _show_main_menu() -> void:
	_clear_current()
	GameManager.change_state(GameManager.GameState.MENU)
	var menu = main_menu_scene.instantiate()
	scene_container.add_child(menu)
	current_scene = menu
	menu.play_pressed.connect(_show_world_map)

func _show_world_map() -> void:
	_clear_current()
	GameManager.change_state(GameManager.GameState.WORLD_MAP)
	var world_map = world_map_scene.instantiate()
	scene_container.add_child(world_map)
	current_scene = world_map
	world_map.level_selected.connect(_start_level)
	world_map.back_pressed.connect(_show_main_menu)

func _start_level(level_id: int) -> void:
	_clear_current()
	current_level_id = level_id

	var level_data = LevelLoaderScript.load_level(level_id)
	GameManager.start_level(level_data)

	var board = game_board_scene.instantiate()
	scene_container.add_child(board)
	current_scene = board
	current_board = board

	board.init_board(level_data)

	if level_data.obstacle_data.size() > 0:
		var obs_map = ObstacleScript.build_obstacle_map(level_data.obstacle_data, level_data.grid_width, level_data.grid_height)
		board.set_obstacle_map(obs_map)

	hud = hud_scene.instantiate()
	scene_container.add_child(hud)
	hud.setup(level_data)

	GameManager.level_completed.connect(_on_level_completed)
	GameManager.level_failed.connect(_on_level_failed)

func _on_level_completed(_level_id: int, score: int, stars: int) -> void:
	AudioManager.play_level_complete_sound()
	level_complete_ui = level_complete_scene.instantiate()
	scene_container.add_child(level_complete_ui)
	level_complete_ui.show_result(score, stars)
	level_complete_ui.next_level_pressed.connect(_next_level)
	level_complete_ui.retry_pressed.connect(_retry_level)
	level_complete_ui.menu_pressed.connect(_show_world_map)
	_disconnect_game_signals()

func _on_level_failed(_level_id: int) -> void:
	AudioManager.play_level_failed_sound()
	level_failed_ui = level_failed_scene.instantiate()
	scene_container.add_child(level_failed_ui)
	level_failed_ui.show_failed()
	level_failed_ui.retry_pressed.connect(_retry_level)
	level_failed_ui.menu_pressed.connect(_show_world_map)
	_disconnect_game_signals()

func _next_level() -> void:
	current_level_id += 1
	if current_level_id > 10:
		_show_world_map()
	else:
		_start_level(current_level_id)

func _retry_level() -> void:
	_start_level(current_level_id)

func _disconnect_game_signals() -> void:
	if GameManager.level_completed.is_connected(_on_level_completed):
		GameManager.level_completed.disconnect(_on_level_completed)
	if GameManager.level_failed.is_connected(_on_level_failed):
		GameManager.level_failed.disconnect(_on_level_failed)
