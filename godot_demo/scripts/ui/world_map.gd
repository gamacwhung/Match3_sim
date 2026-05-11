extends Control

signal level_selected(level_id: int)
signal back_pressed

const TOTAL_LEVELS = 10
const NODE_RADIUS = 28.0
const PATH_WIDTH = 4.0

var level_positions: Array[Vector2] = []
var scroll_offset: float = 0.0
var scroll_target: float = 0.0
var dragging: bool = false
var drag_start_y: float = 0.0
var drag_start_offset: float = 0.0
var content_height: float = 0.0

@onready var draw_layer: Node2D = $DrawLayer
@onready var back_button: Button = $BackButton

func _ready() -> void:
	back_button.pressed.connect(func(): AudioManager.play_button_sound(); back_pressed.emit())
	_generate_level_positions()
	_scroll_to_current_level()

func _generate_level_positions() -> void:
	level_positions.clear()
	var center_x = size.x / 2.0 if size.x > 0 else 360.0
	var start_y = 200.0
	var spacing_y = 140.0

	for i in TOTAL_LEVELS:
		var x_offset = sin(float(i) * 0.8) * 120.0
		var pos = Vector2(center_x + x_offset, start_y + i * spacing_y)
		level_positions.append(pos)

	content_height = start_y + TOTAL_LEVELS * spacing_y + 200.0

func _scroll_to_current_level() -> void:
	var highest = SaveManager.get_highest_unlocked()
	var idx = min(highest - 1, TOTAL_LEVELS - 1)
	if idx >= 0 and idx < level_positions.size():
		scroll_target = max(0, level_positions[idx].y - size.y / 2.0)
		scroll_offset = scroll_target

func _process(_delta: float) -> void:
	scroll_offset = lerp(scroll_offset, scroll_target, 0.15)
	draw_layer.position.y = -scroll_offset
	draw_layer.queue_redraw()

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				dragging = true
				drag_start_y = event.position.y
				drag_start_offset = scroll_offset
				var click_pos = event.position + Vector2(0, scroll_offset)
				_check_level_click(click_pos)
			else:
				dragging = false
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			scroll_target = max(0, scroll_target - 50)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			scroll_target = min(content_height - size.y, scroll_target + 50)

	elif event is InputEventMouseMotion and dragging:
		var diff = drag_start_y - event.position.y
		scroll_target = clamp(drag_start_offset + diff, 0, max(0, content_height - size.y))

func _check_level_click(pos: Vector2) -> void:
	for i in level_positions.size():
		if pos.distance_to(level_positions[i]) < NODE_RADIUS + 10:
			if SaveManager.is_level_unlocked(i + 1):
				AudioManager.play_button_sound()
				level_selected.emit(i + 1)
			return

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.08, 0.05, 0.15))
