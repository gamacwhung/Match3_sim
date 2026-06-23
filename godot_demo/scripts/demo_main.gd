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
# 外部(iframe/postMessage)推進來的自訂關卡原始 dict；非空時「重玩本關」要重載它，
# 不能掉回官方關卡清單。載入官方關卡時會清空。
var _custom_level_data: Dictionary = {}

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

	# Web: 檢查 URL 參數是否帶 level JSON
	if OS.has_feature("web"):
		var level_json = JavaScriptBridge.eval("""
			(function() {
				var params = new URLSearchParams(window.location.search);
				var lz = params.get('level_lz');
				if (lz) {
					try { return decodeURIComponent(atob(lz)); } catch(e) { return ''; }
				}
				var raw = params.get('level');
				if (raw) {
					try { return decodeURIComponent(raw); } catch(e) { return ''; }
				}
				return '';
			})()
		""")
		if level_json is String and level_json.length() > 2:
			var json = JSON.new()
			if json.parse(level_json) == OK:
				var data = json.data
				if data is Dictionary:
					_start_level_from_dict(data)
					# 檢查 autoplay 參數
					_check_url_autoplay()
					return

	# 註冊 JS callback 讓外部 iframe 可以動態載入關卡
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window._godotLevelJson = '';")
		# 監聽 postMessage — 讓父頁面可以跨域通知載入關卡/啟動 AI
		JavaScriptBridge.eval("""
			window.addEventListener('message', function(event) {
				if (!event.data) return;
				if (event.data.type === 'ai_mode_start') {
					window._godotAiMode = 'start';
				}
				if (event.data.type === 'load_level' && event.data.level_json) {
					window._godotLevelJson = event.data.level_json;
				}
			});
		""")

	_show_level_select()


func _check_url_autoplay() -> void:
	if not OS.has_feature("web"):
		return
	# AI mode 參數
	var ai_param = JavaScriptBridge.eval("""
		(function() {
			var params = new URLSearchParams(window.location.search);
			return params.get('ai_mode') || '';
		})()
	""")
	if ai_param is String and ai_param == "1":
		await get_tree().create_timer(1.0).timeout
		if current_board and current_board.has_method("start_ai_mode"):
			current_board.start_ai_mode(0.8)
		return

	var autoplay_json = JavaScriptBridge.eval("""
		(function() {
			var params = new URLSearchParams(window.location.search);
			var ap = params.get('autoplay');
			if (ap) {
				try { return atob(ap); } catch(e) { return ''; }
			}
			return '';
		})()
	""")
	if autoplay_json is String and autoplay_json.length() > 2:
		var json = JSON.new()
		if json.parse(autoplay_json) == OK and json.data is Array:
			# 延遲一點讓盤面初始化完成
			await get_tree().create_timer(1.0).timeout
			if current_board and current_board.has_method("start_autoplay"):
				current_board.start_autoplay(json.data, 0.8)


func _process(_delta: float) -> void:
	if not OS.has_feature("web"):
		return
	# 動態載入關卡
	var pending = JavaScriptBridge.eval("window._godotLevelJson || ''")
	if pending is String and pending.length() > 2:
		JavaScriptBridge.eval("window._godotLevelJson = '';")
		var json = JSON.new()
		if json.parse(pending) == OK and json.data is Dictionary:
			_start_level_from_dict(json.data)

	# Autoplay: 接收動作序列
	var autoplay = JavaScriptBridge.eval("window._godotAutoplayMoves || ''")
	if autoplay is String and autoplay.length() > 2:
		JavaScriptBridge.eval("window._godotAutoplayMoves = '';")
		var json2 = JSON.new()
		if json2.parse(autoplay) == OK and json2.data is Array:
			if current_board and current_board.has_method("start_autoplay"):
				current_board.start_autoplay(json2.data, 0.8)

	# AI 即時模式
	var ai_mode_val = JavaScriptBridge.eval("window._godotAiMode || ''")
	if ai_mode_val is String and ai_mode_val == "start":
		JavaScriptBridge.eval("window._godotAiMode = '';")
		if current_board and current_board.has_method("start_ai_mode"):
			current_board.start_ai_mode(0.8)


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

	# 選關 — 攤位模式（玩 AI 生成的關卡）不顯示，避免客人跳去玩官方 100 關
	if _custom_level_data.is_empty():
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
	else:
		# 攤位模式：放「🧠 AI 解關」開關（可開可關；重玩本關會重置成關）
		var ai_btn = Button.new()
		ai_btn.text = "🧠 AI 解關"
		if font:
			ai_btn.add_theme_font_override("font", font)
		ai_btn.add_theme_font_size_override("font_size", 18)
		ai_btn.set_anchors_preset(Control.PRESET_TOP_RIGHT)
		ai_btn.offset_left = -150
		ai_btn.offset_right = -16
		ai_btn.offset_top = 16
		ai_btn.offset_bottom = 62
		ai_btn.pressed.connect(func(): _toggle_ai_mode(ai_btn))
		menu_button_ui.add_child(ai_btn)


func _toggle_ai_mode(btn: Button) -> void:
	if current_board == null:
		return
	if current_board.has_method("is_ai_running") and current_board.is_ai_running():
		if current_board.has_method("stop_ai_mode"):
			current_board.stop_ai_mode()
		btn.text = "🧠 AI 解關"
	elif current_board.has_method("start_ai_mode"):
		current_board.start_ai_mode(0.8)
		btn.text = "⏸ 停止 AI"


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


func _start_level_from_dict(data: Dictionary) -> void:
	"""從 URL 參數/postMessage 傳入的 level dict 直接載入遊戲"""
	_custom_level_data = data.duplicate(true)  # 記住 → 重玩本關時重載這關，不掉回官方關
	_clear_current()
	var level_data = JsonLevelLoader.parse_level_dict(data)
	if level_data == null:
		push_error("DemoMain: parse_level_dict failed from URL param")
		_show_level_select()
		return

	if level_data.level_id <= 0:
		level_data.level_id = 999

	GameManager.start_level(level_data)

	var board = game_board_scene.instantiate()
	scene_container.add_child(board)
	current_scene = board
	current_board = board

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

	board.init_board(level_data)

	hud = hud_scene.instantiate()
	scene_container.add_child(hud)
	hud.setup(level_data)

	_show_menu_button()

	GameManager.level_completed.connect(_on_level_completed)
	GameManager.level_failed.connect(_on_level_failed)


func _start_level(idx: int) -> void:
	_custom_level_data = {}  # 進官方關卡 → 清掉自訂關卡記憶，重玩才不會重載舊自訂關
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

	# obstacle_map 必須在 init_board 前設定，fill_initial 的 BFS 需要知道可移動障礙物位置
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

	board.init_board(level_data)

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
	# 攤位模式（玩 AI 生成的關卡）：只給「再玩一次」，不跳官方下一關 / 選單
	if not _custom_level_data.is_empty() and level_complete_ui.has_method("set_booth_mode"):
		level_complete_ui.set_booth_mode()
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
	# 自訂關卡(iframe 推進來的)優先重載自己，不要掉回官方關卡清單
	if not _custom_level_data.is_empty():
		_start_level_from_dict(_custom_level_data)
	else:
		_start_level(_level_index)


func _restart_demo() -> void:
	# 通關/失敗的 Menu 按鈕 → 回到選關
	_show_level_select()


func _disconnect_game_signals() -> void:
	if GameManager.level_completed.is_connected(_on_level_completed):
		GameManager.level_completed.disconnect(_on_level_completed)
	if GameManager.level_failed.is_connected(_on_level_failed):
		GameManager.level_failed.disconnect(_on_level_failed)
