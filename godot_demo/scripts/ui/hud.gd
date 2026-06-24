extends CanvasLayer

@onready var score_label: Label = $TopBar/ScoreLabel
@onready var level_label: Label = $TopBar/LevelLabel
@onready var moves_label: Label = $TopBar/MovesLabel
@onready var objective_label: Label = $TopBar/ObjectiveLabel
@onready var objectives_bar: HBoxContainer = $TopBar/ObjectivesBar
@onready var score_bar: ProgressBar = $TopBar/ScoreBar
@onready var star1: Node2D = $TopBar/ScoreBar/Star1
@onready var star2: Node2D = $TopBar/ScoreBar/Star2
@onready var star3: Node2D = $TopBar/ScoreBar/Star3

const FONT_PATH: String = "res://resources/fonts/NotoSansTC-Regular.otf"

# 目標列 family → sprite stem(執行時由 ArtTheme 套上 live 覆蓋)
const OBJECTIVE_ICON_STEMS: Dictionary = {
	"Crt": "Crt1",
	"Barrel": "Barrel",
	"TrafficCone": "TrafficCone_lv1",
	"SalmonCan": "SalmonCan",
	"Stamp": "Postmark_goal",
	"WaterChiller": "WaterChiller_closed",
	"BeverageChiller": "BeverageChiller_closed",
	"Pool": "Pool_lv5",
	"Puddle": "Puddle_lv1",
	"Rope": "Rope_lv1",
	"Mud": "Mud",
}

const _FALLBACK_OBJECTIVE_TEXTURES: Dictionary = {
	"Crt1": preload("res://resources/sprites/Crt1.png"),
	"Barrel": preload("res://resources/sprites/Barrel.png"),
	"TrafficCone_lv1": preload("res://resources/sprites/TrafficCone_lv1.png"),
	"SalmonCan": preload("res://resources/sprites/SalmonCan.png"),
	"Postmark_goal": preload("res://resources/sprites/Postmark_goal.png"),
	"WaterChiller_closed": preload("res://resources/sprites/WaterChiller_closed.png"),
	"BeverageChiller_closed": preload("res://resources/sprites/BeverageChiller_closed.png"),
	"Pool_lv5": preload("res://resources/sprites/Pool_lv5.png"),
	"Puddle_lv1": preload("res://resources/sprites/Puddle_lv1.png"),
	"Rope_lv1": preload("res://resources/sprites/Rope_lv1.png"),
	"Mud": preload("res://resources/sprites/Mud.png"),
	"Postmark_card": preload("res://resources/sprites/Postmark_card.png"),
}

var _font: FontFile = null
var star_thresholds: Array[int] = []
var _score_objective_target: int = 0
var _star_colors: Array[Color] = [Color(0.4, 0.4, 0.4), Color(0.4, 0.4, 0.4), Color(0.4, 0.4, 0.4)]

# tile_id family → 目標列 widget {panel, icon, count_label, check}
var _objective_widgets: Dictionary = {}


func _ready() -> void:
	add_to_group("game_hud")
	_font = load(FONT_PATH) as FontFile
	_apply_font_overrides()
	GameManager.score_changed.connect(_on_score_changed)
	GameManager.moves_changed.connect(_on_moves_changed)
	GameManager.objective_updated.connect(_on_objective_updated)
	star1.draw.connect(func(): _draw_star(star1, 0))
	star2.draw.connect(func(): _draw_star(star2, 1))
	star3.draw.connect(func(): _draw_star(star3, 2))
	if not ArtTheme.theme_ready.is_connected(_on_theme_ready):
		ArtTheme.theme_ready.connect(_on_theme_ready)


func _apply_font_overrides() -> void:
	if _font == null:
		return
	for lb in [score_label, level_label, moves_label, objective_label]:
		if lb:
			lb.add_theme_font_override("font", _font)


func setup(level_data: Resource) -> void:
	score_label.visible = false
	score_bar.visible = false
	star1.visible = false
	star2.visible = false
	star3.visible = false
	objective_label.visible = false
	star_thresholds = level_data.star_thresholds.duplicate()
	_score_objective_target = 0
	_apply_font_overrides()
	var lid = int(level_data.level_id) if level_data and "level_id" in level_data else 0
	level_label.text = "第 %d 關" % lid if lid > 0 else "Demo 關卡"
	level_label.add_theme_color_override("font_color", Color(1, 0.95, 0.55))
	_on_moves_changed(level_data.max_moves)
	_build_objective_icons(level_data.objectives)


func _build_objective_icons(objectives: Array) -> void:
	for c in objectives_bar.get_children():
		c.queue_free()
	_objective_widgets.clear()

	if objectives.is_empty():
		return

	objectives_bar.add_theme_constant_override("separation", 14)
	for obj in objectives:
		var tile_id: String = str(obj.get("tile_id", ""))
		var family = _tile_family(tile_id) if tile_id != "" else ""
		var tex = _icon_for_family(family, str(obj.get("type", "")))

		var panel = PanelContainer.new()
		panel.custom_minimum_size = Vector2(96, 82)
		var sb = StyleBoxFlat.new()
		sb.bg_color = Color(0.12, 0.08, 0.18, 0.88)
		sb.border_color = Color(0.55, 0.45, 0.75, 0.9)
		sb.set_border_width_all(2)
		sb.set_corner_radius_all(8)
		sb.set_content_margin_all(6)
		panel.add_theme_stylebox_override("panel", sb)

		var vbox = VBoxContainer.new()
		vbox.alignment = BoxContainer.ALIGNMENT_CENTER
		panel.add_child(vbox)

		var row = HBoxContainer.new()
		row.alignment = BoxContainer.ALIGNMENT_CENTER
		vbox.add_child(row)

		if tex:
			var icon = TextureRect.new()
			icon.custom_minimum_size = Vector2(44, 44)
			icon.expand_mode = TextureRect.EXPAND_FIT_WIDTH_PROPORTIONAL
			icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			icon.texture = tex
			row.add_child(icon)

		var count_lb = Label.new()
		count_lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		if _font:
			count_lb.add_theme_font_override("font", _font)
		count_lb.add_theme_font_size_override("font_size", 18)
		vbox.add_child(count_lb)

		var check_lb = Label.new()
		check_lb.text = "✓"
		check_lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		check_lb.visible = false
		if _font:
			check_lb.add_theme_font_override("font", _font)
		check_lb.add_theme_font_size_override("font_size", 20)
		check_lb.add_theme_color_override("font_color", Color(0.35, 1.0, 0.45))
		vbox.add_child(check_lb)

		objectives_bar.add_child(panel)
		var key = family if family != "" else str(obj.get("type", ""))
		_objective_widgets[key] = {
			"panel": panel,
			"style": sb,
			"icon": row.get_child(0) if tex and row.get_child_count() > 0 else null,
			"count": count_lb,
			"check": check_lb,
			"obj_ref": obj,
		}

	_update_objective_icons(objectives)


func _on_theme_ready() -> void:
	_refresh_objective_textures()


func _refresh_objective_textures() -> void:
	for key in _objective_widgets:
		var w: Dictionary = _objective_widgets[key]
		var icon: TextureRect = w.get("icon")
		if icon == null:
			continue
		var obj_ref: Dictionary = w.get("obj_ref", {})
		var obj_type: String = str(obj_ref.get("type", ""))
		icon.texture = _icon_for_family(key, obj_type)


static func _named_or(name: String, fallback: Texture2D) -> Texture2D:
	if ArtTheme.has_named_texture(name):
		return ArtTheme.get_named_texture(name)
	return fallback


func _texture_for_stem(stem: String) -> Texture2D:
	var fallback: Texture2D = _FALLBACK_OBJECTIVE_TEXTURES.get(stem)
	if fallback == null:
		return null
	return _named_or(stem, fallback)


func _icon_for_family(family: String, obj_type: String) -> Texture2D:
	if family != "" and OBJECTIVE_ICON_STEMS.has(family):
		return _texture_for_stem(OBJECTIVE_ICON_STEMS[family])
	if obj_type == "clear_manufacturer":
		return _texture_for_stem("Postmark_goal")
	return null


static func _tile_family(tile_id: String) -> String:
	var s = tile_id.split("#")[0]
	var lv_idx = s.find("_lv")
	if lv_idx >= 0:
		return s.substr(0, lv_idx)
	var i = s.length()
	while i > 0 and s.substr(i - 1, 1).is_valid_int():
		i -= 1
	return s.substr(0, i) if i > 0 else s


func _on_score_changed(_new_score: int) -> void:
	pass


func _on_moves_changed(remaining: int) -> void:
	moves_label.text = "剩餘步數: %d" % remaining
	if remaining <= 5:
		moves_label.add_theme_color_override("font_color", Color(1.0, 0.3, 0.3))
	else:
		moves_label.add_theme_color_override("font_color", Color.WHITE)


func _on_objective_updated(_obj: Dictionary) -> void:
	_update_objective_icons(GameManager.level_objectives)


func _update_objective_icons(objectives: Array) -> void:
	for obj in objectives:
		var tile_id: String = str(obj.get("tile_id", ""))
		var family = _tile_family(tile_id) if tile_id != "" else ""
		var key = family if family != "" else str(obj.get("type", ""))
		if not _objective_widgets.has(key):
			continue
		var w: Dictionary = _objective_widgets[key]
		var cur: int = int(obj.get("current", 0))
		var tgt: int = int(obj.get("target", 0))
		var done: bool = cur >= tgt and tgt > 0
		var remaining: int = maxi(0, tgt - cur)
		var goal_kind: String = str(obj.get("goal_kind", ""))
		var n_inst: int = int(obj.get("board_instances", 0))

		w["count"].text = _format_objective_count(obj, cur, tgt, remaining, done)
		w["check"].visible = done

		var sb: StyleBoxFlat = w["style"]
		if done:
			sb.bg_color = Color(0.08, 0.14, 0.08, 0.75)
			sb.border_color = Color(0.35, 0.85, 0.4, 0.7)
			sb.set_border_width_all(2)
			if w["icon"]:
				w["icon"].modulate = Color(0.55, 0.55, 0.55, 0.85)
			w["count"].add_theme_color_override("font_color", Color(0.55, 0.85, 0.55))
		else:
			sb.bg_color = Color(0.18, 0.12, 0.08, 0.95)
			sb.border_color = Color(1.0, 0.82, 0.25, 1.0)
			sb.set_border_width_all(3)
			if w["icon"]:
				w["icon"].modulate = Color(1.2, 1.15, 1.05, 1.0)
			w["count"].add_theme_color_override("font_color", Color(1.0, 0.95, 0.55))


func _format_objective_count(obj: Dictionary, cur: int, tgt: int, remaining: int, done: bool) -> String:
	var kind: String = str(obj.get("goal_kind", ""))
	var n_inst: int = int(obj.get("board_instances", 0))
	if kind == "hits" and n_inst > 0:
		# 2×2 櫃:目標數=總敲擊次數,不是格子數;標示盤上有幾「台」
		var lines: String = "%d / %d 次" % [cur, tgt]
		if not done and remaining > 0:
			lines += "\n還差 %d 次" % remaining
		lines += "\n（%d 台 2×2）" % n_inst
		return lines
	if kind == "triggers":
		var lines_t: String = "%d / %d 次" % [cur, tgt]
		if not done and remaining > 0:
			lines_t += "\n還差 %d 次" % remaining
		return lines_t
	var lines_i: String = "%d / %d" % [cur, tgt]
	if not done and remaining > 0:
		lines_i += "\n還差 %d" % remaining
	return lines_i


func play_objective_fly(from_global: Vector2, family: String) -> void:
	var tex: Texture2D = _texture_for_stem("Postmark_card") if family == "Stamp" else _icon_for_family(family, "")
	if tex == null:
		return
	var target: Vector2 = _objective_fly_target(family)
	var start_scale: float = 0.055 if family == "Stamp" else 0.04
	var end_scale: float = 0.032 if family == "Stamp" else 0.028
	var duration: float = 0.78 if family == "Stamp" else 0.72

	var sprite = Sprite2D.new()
	sprite.texture = tex
	sprite.global_position = from_global
	sprite.scale = Vector2(start_scale, start_scale)
	sprite.z_index = 120
	add_child(sprite)

	var mid: Vector2 = from_global.lerp(target, 0.45) + Vector2(0, -42)
	var tw = create_tween()
	tw.tween_property(sprite, "global_position", mid, duration * 0.45).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tw.tween_property(sprite, "global_position", target, duration * 0.55).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN)
	tw.parallel().tween_property(sprite, "scale", Vector2(end_scale, end_scale), duration)
	tw.parallel().tween_property(sprite, "modulate:a", 0.0, 0.18).set_delay(duration - 0.15)
	tw.chain().tween_callback(sprite.queue_free)
	tw.chain().tween_callback(_pulse_objective.bind(family))


func _objective_fly_target(family: String) -> Vector2:
	if _objective_widgets.has(family):
		var panel: Control = _objective_widgets[family]["panel"]
		return panel.global_position + panel.size * 0.5
	return Vector2(get_viewport().get_visible_rect().size.x * 0.5, 90)


func _pulse_objective(family: String) -> void:
	if not _objective_widgets.has(family):
		return
	var panel: Control = _objective_widgets[family]["panel"]
	var tw = create_tween()
	tw.tween_property(panel, "scale", Vector2(1.14, 1.14), 0.1).set_trans(Tween.TRANS_BACK)
	tw.tween_property(panel, "scale", Vector2.ONE, 0.14)


# 相容舊呼叫
func play_stamp_card_fly(from_global: Vector2) -> void:
	play_objective_fly(from_global, "Stamp")


func _update_stars(score: int) -> void:
	if star_thresholds.size() < 3:
		return
	_star_colors[0] = Color.GOLD if score >= star_thresholds[0] else Color(0.4, 0.4, 0.4)
	_star_colors[1] = Color.GOLD if score >= star_thresholds[1] else Color(0.4, 0.4, 0.4)
	_star_colors[2] = Color.GOLD if score >= star_thresholds[2] else Color(0.4, 0.4, 0.4)
	star1.queue_redraw()
	star2.queue_redraw()
	star3.queue_redraw()


func _draw_star(node: Node2D, idx: int) -> void:
	var color = _star_colors[idx]
	var pts = _star_points(Vector2.ZERO, 10.0, 4.5, 5)
	node.draw_colored_polygon(pts, color)
	var pts_inner = _star_points(Vector2.ZERO, 7.0, 3.5, 5)
	var highlight = lerp(color, Color.WHITE, 0.3)
	node.draw_colored_polygon(pts_inner, highlight)


static func _star_points(center: Vector2, outer_r: float, inner_r: float, points: int) -> PackedVector2Array:
	var result = PackedVector2Array()
	for i in points * 2:
		var angle = TAU * i / (points * 2) - PI / 2
		var r = outer_r if i % 2 == 0 else inner_r
		result.append(center + Vector2(cos(angle), sin(angle)) * r)
	return result
