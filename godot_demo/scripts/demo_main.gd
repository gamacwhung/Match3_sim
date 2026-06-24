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
# 攤位模式(?booth=1)：開機不顯示官方 100 關選單，改顯示乾淨的待機畫面；
# 結束/Menu 也回到待機畫面，不掉回官方選關。
var _booth_mode: bool = false
var _idle_ui: CanvasLayer = null
var _hint_ui: CanvasLayer = null
# attract mode：待機一段時間沒人玩 → AI 自動試玩一關循環吸引人
var _in_attract: bool = false
var _attract_timer: Timer = null
const _ATTRACT_IDLE_SEC := 12.0   # 待機畫面停這麼久沒互動 → 開始 AI 自動試玩

# 機制提示（新手看不懂的障礙才提示；單純的 Crt 不提示）。家族名 → 一句白話玩法。
const _MECHANIC_HINTS: Dictionary = {
	"SalmonCan": "鮪魚罐頭只能用道具（火箭／TNT／紙飛機）打掉",
	"BeverageChiller": "飲料櫃：消除對應顏色的瓶子來開門",
	"WaterChiller": "冰箱櫃：在旁邊消除來敲開它",
	"Puddle": "水窪：消除它正上方的元素就能清掉",
	"Pool": "水池：血量高，要在旁邊多消幾次",
	"Rope": "繩索：消除被綁住格子旁的元素來解開",
	"Mud": "泥巴：消除旁邊的元素來清除",
	"Stamp": "郵戳：在它旁邊消除來觸發",
	"Barrel": "木桶：可以推到旁邊、或在旁邊消除",
	"TrafficCone": "三角錐：可以推到旁邊、或在旁邊消除",
}

@onready var scene_container: Control = $SceneContainer


func _configure_web_display() -> void:
	if not OS.has_feature("web"):
		return
	var win := get_window()
	if win == null:
		return
	# Web iframe: 等比縮放、不裁切；避免舊 export 的 stretch/scale 造成畫面放大
	win.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	win.content_scale_aspect = Window.CONTENT_SCALE_ASPECT_KEEP
	win.content_scale_factor = 1.0


func _ready() -> void:
	_configure_web_display()
	_level_paths = JsonLevelLoader.list_demo_levels()
	if _level_paths.is_empty():
		push_error("DemoMain: 找不到 res://levels/*.json,請確認檔案已複製")
		return
	# 嘗試啟動 BGM(若 AudioManager 存在)
	if Engine.has_singleton("AudioManager") or has_node("/root/AudioManager"):
		var audio = get_node_or_null("/root/AudioManager")
		if audio and audio.has_method("start_bgm"):
			audio.start_bgm()

	# 攤位模式偵測(?booth=1)：開機顯示待機畫面、不顯示官方 100 關選單
	if OS.has_feature("web"):
		var booth_param = JavaScriptBridge.eval("""
			(function() {
				var p = new URLSearchParams(window.location.search);
				return p.get('booth') || '';
			})()
		""")
		_booth_mode = (booth_param is String and booth_param == "1")

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

	# 攤位模式 → 乾淨待機畫面（等左邊 Streamlit 生成關卡推進來）；否則官方選關
	if _booth_mode:
		_show_idle_screen()
	else:
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


func _show_idle_screen() -> void:
	# 攤位待機畫面：乾淨、置中，提示玩家從左邊輸入生成關卡。
	_clear_current()
	if _idle_ui != null:
		_idle_ui.queue_free()
		_idle_ui = null
	_idle_ui = CanvasLayer.new()
	_idle_ui.layer = 15
	add_child(_idle_ui)

	var font = load("res://resources/fonts/NotoSansTC-Regular.otf") as Font

	var bg = ColorRect.new()
	bg.color = Color(0.05, 0.04, 0.10, 1.0)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	_idle_ui.add_child(bg)

	var center_box = CenterContainer.new()
	center_box.set_anchors_preset(Control.PRESET_FULL_RECT)
	_idle_ui.add_child(center_box)

	var vbox = VBoxContainer.new()
	vbox.alignment = BoxContainer.ALIGNMENT_CENTER
	vbox.add_theme_constant_override("separation", 20)
	center_box.add_child(vbox)

	var title = Label.new()
	title.text = "Match3 AI 關卡生成"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if font:
		title.add_theme_font_override("font", font)
	title.add_theme_font_size_override("font_size", 48)
	title.add_theme_color_override("font_color", Color(1, 0.95, 0.55))
	vbox.add_child(title)

	var sub = Label.new()
	sub.text = "在左邊輸入一句話，AI 立刻幫你生成關卡並試玩"
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if font:
		sub.add_theme_font_override("font", font)
	sub.add_theme_font_size_override("font_size", 26)
	sub.add_theme_color_override("font_color", Color(0.82, 0.82, 0.92))
	vbox.add_child(sub)

	var hint = Label.new()
	hint.text = "等待生成中…"
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if font:
		hint.add_theme_font_override("font", font)
	hint.add_theme_font_size_override("font_size", 22)
	hint.add_theme_color_override("font_color", Color(0.6, 0.7, 1.0))
	vbox.add_child(hint)

	# 呼吸動畫,讓待機畫面有生命感
	var tw = create_tween().set_loops()
	tw.tween_property(hint, "modulate:a", 0.35, 0.9).set_trans(Tween.TRANS_SINE)
	tw.tween_property(hint, "modulate:a", 1.0, 0.9).set_trans(Tween.TRANS_SINE)

	# 待機一段時間沒人玩 → 啟動 attract(AI 自動試玩)
	_start_attract_timer()


func _start_attract_timer() -> void:
	_cancel_attract_timer()
	if not _booth_mode:
		return   # 只有攤位模式才自動 attract
	_attract_timer = Timer.new()
	_attract_timer.one_shot = true
	_attract_timer.wait_time = _ATTRACT_IDLE_SEC
	add_child(_attract_timer)
	_attract_timer.timeout.connect(_start_attract)
	_attract_timer.start()


func _cancel_attract_timer() -> void:
	if _attract_timer != null:
		_attract_timer.queue_free()
		_attract_timer = null


func _start_attract() -> void:
	if _level_paths.is_empty() or not _booth_mode:
		return
	_in_attract = true
	# 挑前幾關官方關卡來自動試玩(較好看)
	var idx := randi() % mini(_level_paths.size(), 10)
	_start_level(idx)   # 會 _clear_current(含 idle)、清 _custom_level_data
	# 啟動 AI 自動解
	await get_tree().create_timer(1.0).timeout
	if _in_attract and current_board and current_board.has_method("start_ai_mode"):
		current_board.start_ai_mode(0.7)


func _schedule_attract_return() -> void:
	# attract 那關結束後,稍等一下回待機畫面 → 又會啟動 attract → 循環
	await get_tree().create_timer(2.5).timeout
	if _in_attract:
		_in_attract = false
		_show_idle_screen()


static func _tile_family(tile_id: String) -> String:
	var s := tile_id.split("#")[0]
	var lv_idx := s.find("_lv")
	if lv_idx >= 0:
		return s.substr(0, lv_idx)
	var i := s.length()
	while i > 0 and s.substr(i - 1, 1).is_valid_int():
		i -= 1
	return s.substr(0, i) if i > 0 else s


func _show_mechanic_hint(level_data) -> void:
	# 依關卡目標中的「需提示障礙」顯示底部非侵入提示；多個則輪播。
	if _hint_ui != null:
		_hint_ui.queue_free()
		_hint_ui = null
	var hints: Array[String] = []
	var seen: Dictionary = {}
	var objs = []
	if level_data and "objectives" in level_data:
		objs = level_data.objectives
	for obj in objs:
		var tid := str(obj.get("tile_id", ""))
		if tid == "":
			continue
		var fam := _tile_family(tid)
		if _MECHANIC_HINTS.has(fam) and not seen.has(fam):
			seen[fam] = true
			hints.append(str(_MECHANIC_HINTS[fam]))
	if hints.is_empty():
		return

	var font = load("res://resources/fonts/NotoSansTC-Regular.otf") as Font
	_hint_ui = CanvasLayer.new()
	_hint_ui.layer = 18
	add_child(_hint_ui)

	var panel = PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 40
	panel.offset_right = -40
	panel.offset_top = -72
	panel.offset_bottom = -18
	var sb = StyleBoxFlat.new()
	sb.bg_color = Color(0.10, 0.08, 0.16, 0.86)
	sb.border_color = Color(0.5, 0.45, 0.75, 0.8)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(10)
	panel.add_theme_stylebox_override("panel", sb)
	_hint_ui.add_child(panel)

	var lb = Label.new()
	lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if font:
		lb.add_theme_font_override("font", font)
	lb.add_theme_font_size_override("font_size", 20)
	lb.add_theme_color_override("font_color", Color(1, 0.95, 0.7))
	lb.text = "提示：" + hints[0]
	panel.add_child(lb)

	# 淡入
	panel.modulate.a = 0.0
	var tw = create_tween()
	tw.tween_property(panel, "modulate:a", 1.0, 0.4)

	# 多個提示 → 每 4 秒輪播一句
	if hints.size() > 1:
		var state := {"i": 0}
		var timer := Timer.new()
		timer.wait_time = 4.0
		timer.autostart = true
		_hint_ui.add_child(timer)
		timer.timeout.connect(func():
			if not is_instance_valid(lb):
				return
			state.i = (int(state.i) + 1) % hints.size()
			lb.text = "提示：" + hints[int(state.i)]
		)


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
	_in_attract = false
	_cancel_attract_timer()
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
	replay_btn.text = "重玩本關"
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

	# 音效開關 — 左上角
	var audio_btn = Button.new()
	var am0 = get_node_or_null("/root/AudioManager")
	var is_muted: bool = am0 != null and ("muted" in am0) and am0.muted
	audio_btn.text = "音效 關" if is_muted else "音效 開"
	if font:
		audio_btn.add_theme_font_override("font", font)
	audio_btn.add_theme_font_size_override("font_size", 18)
	audio_btn.set_anchors_preset(Control.PRESET_TOP_LEFT)
	audio_btn.offset_left = 16
	audio_btn.offset_right = 132
	audio_btn.offset_top = 16
	audio_btn.offset_bottom = 62
	audio_btn.pressed.connect(func(): _toggle_audio(audio_btn))
	menu_button_ui.add_child(audio_btn)

	# 選關 — 攤位模式（玩 AI 生成的關卡）不顯示，避免客人跳去玩官方 100 關
	if _custom_level_data.is_empty():
		var select_btn = Button.new()
		select_btn.text = "選關"
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
		ai_btn.text = "AI 解關"
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


func _toggle_audio(btn: Button) -> void:
	var am = get_node_or_null("/root/AudioManager")
	if am == null or not am.has_method("toggle_muted"):
		return
	var muted: bool = am.toggle_muted()
	btn.text = "音效 關" if muted else "音效 開"


func _toggle_ai_mode(btn: Button) -> void:
	if current_board == null:
		return
	if current_board.has_method("is_ai_running") and current_board.is_ai_running():
		if current_board.has_method("stop_ai_mode"):
			current_board.stop_ai_mode()
		btn.text = "AI 解關"
	elif current_board.has_method("start_ai_mode"):
		current_board.start_ai_mode(0.8)
		btn.text = "停止 AI"


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
	if _idle_ui:
		_idle_ui.queue_free()
		_idle_ui = null
	if _hint_ui:
		_hint_ui.queue_free()
		_hint_ui = null
	current_board = null


func _start_level_from_dict(data: Dictionary) -> void:
	"""從 URL 參數/postMessage 傳入的 level dict 直接載入遊戲"""
	# 有真實關卡推進來 → 中止 attract 自動試玩
	_in_attract = false
	_cancel_attract_timer()
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

	_show_mechanic_hint(level_data)
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

	_show_mechanic_hint(level_data)
	_show_menu_button()

	GameManager.level_completed.connect(_on_level_completed)
	GameManager.level_failed.connect(_on_level_failed)


func _on_level_completed(_level_id: int, score: int, stars: int) -> void:
	var audio = get_node_or_null("/root/AudioManager")
	if audio and audio.has_method("play_level_complete_sound"):
		audio.play_level_complete_sound()
	_disconnect_game_signals()
	# attract 模式(idle 自動試玩)：不顯示結算，稍後回待機畫面循環
	if _in_attract:
		_schedule_attract_return()
		return
	level_complete_ui = level_complete_scene.instantiate()
	scene_container.add_child(level_complete_ui)
	level_complete_ui.show_result(score, stars)
	# AI 評語(收尾)
	if level_complete_ui.has_method("set_critique"):
		level_complete_ui.set_critique(_make_critique(stars))
	# 攤位模式（玩 AI 生成的關卡）：只給「再玩一次」，不跳官方下一關 / 選單
	if not _custom_level_data.is_empty() and level_complete_ui.has_method("set_booth_mode"):
		level_complete_ui.set_booth_mode()
	level_complete_ui.next_level_pressed.connect(_next_level)
	level_complete_ui.retry_pressed.connect(_retry_level)
	# menu_pressed → demo 沒有 menu,直接重新從 #0 開始
	level_complete_ui.menu_pressed.connect(_restart_demo)


func _make_critique(stars: int) -> String:
	var used: int = maxi(0, GameManager.max_moves - GameManager.moves_remaining)
	var line := "驚險達陣！"
	if stars >= 3:
		line = "神之一手！"
	elif stars == 2:
		line = "穩穩過關，漂亮！"
	return "AI 評語：%s（%d 步通關）" % [line, used]


func _on_level_failed(_level_id: int) -> void:
	var audio = get_node_or_null("/root/AudioManager")
	if audio and audio.has_method("play_level_failed_sound"):
		audio.play_level_failed_sound()
	_disconnect_game_signals()
	# attract 模式：失敗也回待機循環
	if _in_attract:
		_schedule_attract_return()
		return
	level_failed_ui = level_failed_scene.instantiate()
	scene_container.add_child(level_failed_ui)
	level_failed_ui.show_failed()
	level_failed_ui.retry_pressed.connect(_retry_level)
	level_failed_ui.menu_pressed.connect(_restart_demo)


func _next_level() -> void:
	_start_level(_level_index + 1)


func _retry_level() -> void:
	# 自訂關卡(iframe 推進來的)優先重載自己，不要掉回官方關卡清單
	if not _custom_level_data.is_empty():
		_start_level_from_dict(_custom_level_data)
	else:
		_start_level(_level_index)


func _restart_demo() -> void:
	# 攤位模式 → 回乾淨待機畫面；否則回官方選關
	if _booth_mode:
		_show_idle_screen()
	else:
		_show_level_select()


func _disconnect_game_signals() -> void:
	if GameManager.level_completed.is_connected(_on_level_completed):
		GameManager.level_completed.disconnect(_on_level_completed)
	if GameManager.level_failed.is_connected(_on_level_failed):
		GameManager.level_failed.disconnect(_on_level_failed)
