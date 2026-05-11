extends Control

signal next_level_pressed
signal retry_pressed
signal menu_pressed

var _star_count: int = 0
@onready var _stars_node: Control = $Panel/VBox/StarsLabel

func _ready() -> void:
	$Panel/VBox/NextButton.pressed.connect(func(): AudioManager.play_button_sound(); next_level_pressed.emit())
	$Panel/VBox/RetryButton.pressed.connect(func(): AudioManager.play_button_sound(); retry_pressed.emit())
	$Panel/VBox/MenuButton.pressed.connect(func(): AudioManager.play_button_sound(); menu_pressed.emit())
	_stars_node.draw.connect(_draw_stars)

func show_result(score: int, stars: int) -> void:
	$Panel/VBox/ScoreLabel.text = "Score: %d" % score
	_star_count = stars
	_stars_node.queue_redraw()
	_animate_in()

func _draw_stars() -> void:
	var center_x = _stars_node.size.x / 2.0
	var center_y = _stars_node.size.y / 2.0
	var spacing = 50.0
	var start_x = center_x - spacing
	for i in 3:
		var center = Vector2(start_x + i * spacing, center_y)
		var color = Color.GOLD if i < _star_count else Color(0.4, 0.4, 0.4)
		var pts = _star_points(center, 18.0, 8.0, 5)
		_stars_node.draw_colored_polygon(pts, color)
		var pts_inner = _star_points(center, 13.0, 6.0, 5)
		_stars_node.draw_colored_polygon(pts_inner, lerp(color, Color.WHITE, 0.3))

static func _star_points(center: Vector2, outer_r: float, inner_r: float, points: int) -> PackedVector2Array:
	var result = PackedVector2Array()
	for i in points * 2:
		var angle = TAU * i / (points * 2) - PI / 2
		var r = outer_r if i % 2 == 0 else inner_r
		result.append(center + Vector2(cos(angle), sin(angle)) * r)
	return result

func _animate_in() -> void:
	modulate.a = 0.0
	$Panel.scale = Vector2(0.5, 0.5)
	visible = true
	var tween = create_tween()
	tween.set_parallel(true)
	tween.tween_property(self, "modulate:a", 1.0, 0.3)
	tween.tween_property($Panel, "scale", Vector2.ONE, 0.4).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
