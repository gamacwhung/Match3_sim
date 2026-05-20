extends CanvasLayer
##
## LevelSelect (CanvasLayer 版)
##
## CanvasLayer 比 Control 穩,layer=高,永遠在最上層接收 input,不會被 SceneContainer
## 或其他 Control 的 mouse_filter 卡到。
##
## 用法:
##   var ls = preload("res://scripts/level_select.gd").new()
##   parent.add_child(ls)
##   ls.setup(paths)
##   ls.level_selected.connect(...)
##

signal level_selected(level_index: int)
signal cancelled

# 直接 load 中文字型,在每個 Label/Button 上 add_theme_font_override("font", ...)。
# 不依賴 project.godot::theme/default_font(Godot 4 web export 有時不會 honor),
# 雙保險:UI 字體永遠是 NotoSansTC (含 CJK 字元)。
const FONT_PATH := "res://resources/fonts/NotoSansTC-Regular.otf"


func setup(paths: Array[String], show_cancel: bool = false) -> void:
	layer = 50
	var font = load(FONT_PATH) as Font
	# 全螢幕背景
	var bg = ColorRect.new()
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.color = Color(0.08, 0.06, 0.16, 0.98)
	bg.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(bg)

	# 標題 + 提示(放在最上方)
	var title = Label.new()
	title.text = "選擇關卡 ── 共 %d 關" % paths.size()
	if font:
		title.add_theme_font_override("font", font)
	title.add_theme_font_size_override("font_size", 48)
	title.add_theme_color_override("font_color", Color.WHITE)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.set_anchors_preset(Control.PRESET_TOP_WIDE)
	title.offset_top = 40
	title.offset_bottom = 100
	add_child(title)

	var hint = Label.new()
	hint.text = "1~100 = 從官方匯入  ·  D1~D6 = 手寫測試關卡"
	if font:
		hint.add_theme_font_override("font", font)
	hint.add_theme_font_size_override("font_size", 18)
	hint.add_theme_color_override("font_color", Color(1, 1, 1, 0.6))
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.set_anchors_preset(Control.PRESET_TOP_WIDE)
	hint.offset_top = 100
	hint.offset_bottom = 140
	add_child(hint)

	# 取消按鈕 — 只在遊戲中(從遊戲開選關)時顯示
	if show_cancel:
		var cancel_btn = Button.new()
		cancel_btn.text = "× 取消(繼續本關)"
		if font:
			cancel_btn.add_theme_font_override("font", font)
		cancel_btn.add_theme_font_size_override("font_size", 22)
		cancel_btn.set_anchors_preset(Control.PRESET_TOP_RIGHT)
		cancel_btn.offset_left = -280
		cancel_btn.offset_right = -30
		cancel_btn.offset_top = 30
		cancel_btn.offset_bottom = 86
		cancel_btn.pressed.connect(func(): cancelled.emit())
		add_child(cancel_btn)

	# ── 置中:用 anchor center + 固定寬度,然後 ScrollContainer 垂直捲動 ──
	# 估算:10 cols × 110 = 1100 + 9 × 16 sep + 48 padding ≈ 1292
	# 為了讓 demo 解析度(1920x893)時看起來舒服居中,寬度設 1300。
	# 高度填滿剩餘空間,垂直靠 scroll 處理。
	var scroll = ScrollContainer.new()
	scroll.set_anchors_preset(Control.PRESET_CENTER)
	scroll.anchor_left = 0.5
	scroll.anchor_right = 0.5
	scroll.anchor_top = 0.0
	scroll.anchor_bottom = 1.0
	scroll.offset_left = -650
	scroll.offset_right = 650
	scroll.offset_top = 180
	scroll.offset_bottom = -40
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)

	var pad = MarginContainer.new()
	pad.add_theme_constant_override("margin_top", 24)
	pad.add_theme_constant_override("margin_bottom", 24)
	pad.add_theme_constant_override("margin_left", 24)
	pad.add_theme_constant_override("margin_right", 24)
	pad.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(pad)

	# 10 cols × 10 rows(100 關剛好整齊)— button 110x110 demo 時很大顆好按
	var grid = GridContainer.new()
	grid.columns = 10
	grid.add_theme_constant_override("h_separation", 16)
	grid.add_theme_constant_override("v_separation", 16)
	grid.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	pad.add_child(grid)

	for i in paths.size():
		var btn = Button.new()
		btn.custom_minimum_size = Vector2(110, 110)
		btn.text = _short_label(paths[i])
		if font:
			btn.add_theme_font_override("font", font)
		btn.add_theme_font_size_override("font_size", 36)
		var idx = i
		btn.pressed.connect(func(): level_selected.emit(idx))
		grid.add_child(btn)


func _short_label(path: String) -> String:
	# "res://levels/Level_003.json" → "3";"res://levels/level_02.json" → "D2"
	var basename = path.get_file().get_basename()
	if basename.begins_with("Level_"):
		var s = basename.substr(len("Level_"))
		return str(int(s))
	if basename.begins_with("level_"):
		var s = basename.substr(len("level_"))
		return "D%d" % int(s)
	return basename
