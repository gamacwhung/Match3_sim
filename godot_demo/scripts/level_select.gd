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


func setup(paths: Array[String], show_cancel: bool = false) -> void:
	layer = 50
	# 全螢幕背景
	var bg = ColorRect.new()
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.color = Color(0.08, 0.06, 0.16, 0.98)
	bg.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(bg)

	# 標題 + 提示(放在最上方)
	var title = Label.new()
	title.text = "選擇關卡 ── 共 %d 關" % paths.size()
	title.add_theme_font_size_override("font_size", 38)
	title.add_theme_color_override("font_color", Color.WHITE)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.set_anchors_preset(Control.PRESET_TOP_WIDE)
	title.offset_top = 30
	title.offset_bottom = 80
	add_child(title)

	var hint = Label.new()
	hint.text = "1~100 = 從官方匯入  ·  D1~D6 = 手寫測試關卡"
	hint.add_theme_font_size_override("font_size", 14)
	hint.add_theme_color_override("font_color", Color(1, 1, 1, 0.55))
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.set_anchors_preset(Control.PRESET_TOP_WIDE)
	hint.offset_top = 80
	hint.offset_bottom = 110
	add_child(hint)

	# 取消按鈕 — 只在遊戲中(從遊戲開選關)時顯示
	if show_cancel:
		var cancel_btn = Button.new()
		cancel_btn.text = "× 取消(繼續本關)"
		cancel_btn.add_theme_font_size_override("font_size", 16)
		cancel_btn.set_anchors_preset(Control.PRESET_TOP_RIGHT)
		cancel_btn.offset_left = -200
		cancel_btn.offset_right = -20
		cancel_btn.offset_top = 20
		cancel_btn.offset_bottom = 60
		cancel_btn.pressed.connect(func(): cancelled.emit())
		add_child(cancel_btn)

	# 中央 ScrollContainer 放 GridContainer
	var scroll = ScrollContainer.new()
	scroll.set_anchors_preset(Control.PRESET_FULL_RECT)
	scroll.offset_top = 120
	scroll.offset_bottom = -30
	scroll.offset_left = 30
	scroll.offset_right = -30
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)

	var grid = GridContainer.new()
	grid.columns = 10
	grid.add_theme_constant_override("h_separation", 6)
	grid.add_theme_constant_override("v_separation", 6)
	scroll.add_child(grid)

	for i in paths.size():
		var btn = Button.new()
		btn.custom_minimum_size = Vector2(56, 56)
		btn.text = _short_label(paths[i])
		btn.add_theme_font_size_override("font_size", 16)
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
