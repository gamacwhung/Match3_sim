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
const POSTMARK_CARD_TEX: Texture2D = preload("res://resources/sprites/Postmark_card.png")

# 目標列用障礙物圖示(玩家不需記名稱)
const OBJECTIVE_ICONS: Dictionary = {
	"Crt": preload("res://resources/sprites/Crt1.png"),
	"Barrel": preload("res://resources/sprites/Barrel.png"),
	"TrafficCone": preload("res://resources/sprites/TrafficCone_lv1.png"),
	"SalmonCan": preload("res://resources/sprites/SalmonCan.png"),
	"Stamp": preload("res://resources/sprites/Postmark_goal.png"),
	"WaterChiller": preload("res://resources/sprites/WaterChiller_closed.png"),
	"BeverageChiller": preload("res://resources/sprites/BeverageChiller_closed.png"),
	"Pool": preload("res://resources/sprites/Pool_lv5.png"),
	"Puddle": preload("res://resources/sprites/Puddle_lv1.png"),
	"Rope": preload("res://resources/sprites/Rope_lv1.png"),
	"Mud": preload("res://resources/sprites/Mud.png"),
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
		panel.custom_minimum_size = Vector2(88, 72)
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


func _icon_for_family(family: String, obj_type: String) -> Texture2D:
	if family != "" and OBJECTIVE_ICONS.has(family):
		return OBJECTIVE_ICONS[family]
	if obj_type == "clear_manufacturer":
		return OBJECTIVE_ICONS.get("Stamp", null)
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
		var done := cur >= tgt and tgt > 0
		var remaining := max(0, tgt - cur)

		w["count"].text = "%d / %d" % [cur, tgt]
		w["check"].visible = done

		var sb: StyleBoxFlat = w["style"]
		if done:
			sb.bg_color = Color(0.08, 0.14, 0.08, 0.75)
			sb.border_color = Color(0.35, 0.85, 0.4, 0.7)
			if w["icon"]:
				w["icon"].modulate = Color(0.55, 0.55, 0.55, 0.85)
			w["count"].add_theme_color_override("font_color", Color(0.55, 0.85, 0.55))
		else:
			sb.bg_color = Color(0.18, 0.12, 0.08, 0.95)
			sb.border_color = Color(1.0, 0.82, 0.25, 1.0)
			sb.set_border_width_all(3)
			if w["icon"]:
				w["icon"].modulate = Color(1.15, 1.1, 1.0, 1.0)
			w["count"].add_theme_color_override("font_color", Color(1.0, 0.95, 0.55))
			w["count"].text = "%d / %d" % [cur, tgt] if tgt > 0 else "—"
			if remaining > 0 and tgt > 0:
				w["count"].text = "%d / %d\n還差 %d" % [cur, tgt, remaining]


func play_stamp_card_fly(from_global: Vector2) -> void:
	var card = Sprite2D.new()
	card.texture = POSTMARK_CARD_TEX
	card.global_position = from_global
	card.scale = Vector2(0.055, 0.055)
	card.z_index = 120
	add_child(card)

	var target := _stamp_objective_fly_target()
	var tw = create_tween()
	tw.set_parallel(true)
	tw.tween_property(card, "global_position", target, 0.5).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
	tw.tween_property(card, "scale", Vector2(0.032, 0.032), 0.5)
	tw.tween_property(card, "modulate:a", 0.0, 0.12).set_delay(0.42)
	tw.chain().tween_callback(card.queue_free)
	tw.chain().tween_callback(_pulse_stamp_objective)


func _stamp_objective_fly_target() -> Vector2:
	if _objective_widgets.has("Stamp"):
		var panel: Control = _objective_widgets["Stamp"]["panel"]
		return panel.global_position + panel.size * 0.5
	return Vector2(get_viewport().get_visible_rect().size.x * 0.5, 80)


func _pulse_stamp_objective() -> void:
	if not _objective_widgets.has("Stamp"):
		return
	var panel: Control = _objective_widgets["Stamp"]["panel"]
	var tw = create_tween()
	tw.tween_property(panel, "scale", Vector2(1.12, 1.12), 0.08).set_trans(Tween.TRANS_BACK)
	tw.tween_property(panel, "scale", Vector2.ONE, 0.12)


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
