extends Node2D
class_name Candy

const CandyRenderer = preload("res://scripts/effects/candy_renderer.gd")

enum CandyType { NORMAL, STRIPED_H, STRIPED_V, WRAPPED, COLOR_BOMB, SPIRAL }
# SPIRAL = TrPr 紙飛機(對應 Python 的 2x2 → TrPr 道具),效果:十字 4 格消除

signal candy_selected(candy: Candy)
signal candy_swipe(candy: Candy, direction: Vector2i)

var candy_color: int = 0
var candy_type: CandyType = CandyType.NORMAL
var grid_pos: Vector2i = Vector2i.ZERO
var is_being_destroyed: bool = false
var is_moving: bool = false
var cell_size: float = 70.0

var _selected: bool = false
var _hover: bool = false
var _drag_start: Vector2 = Vector2.ZERO
var _is_dragging: bool = false
var _scale_tween: Tween = null

func _ready() -> void:
	# 主題(live 美術)就緒時強制重畫,否則已存在的糖果會沿用載入當下的貼圖,
	# 要等到下一次 swap/match/掉落才換成新美術(看起來像「玩一陣子才全部置換」)。
	if not ArtTheme.theme_ready.is_connected(_on_theme_ready):
		ArtTheme.theme_ready.connect(_on_theme_ready)
	queue_redraw()

func _on_theme_ready() -> void:
	queue_redraw()

func init(color_idx: int, grid_position: Vector2i, type: CandyType = CandyType.NORMAL) -> void:
	candy_color = color_idx
	grid_pos = grid_position
	candy_type = type
	queue_redraw()

func set_candy_type(type: CandyType) -> void:
	candy_type = type
	queue_redraw()

func set_candy_color(color_idx: int) -> void:
	candy_color = color_idx
	queue_redraw()

func _kill_scale_tween() -> void:
	if _scale_tween and _scale_tween.is_valid():
		_scale_tween.kill()
		_scale_tween = null

func set_selected(selected: bool) -> void:
	_selected = selected
	_kill_scale_tween()
	if _selected:
		_scale_tween = create_tween().set_loops()
		_scale_tween.tween_property(self, "scale", Vector2(1.15, 1.15), 0.3).set_trans(Tween.TRANS_SINE)
		_scale_tween.tween_property(self, "scale", Vector2(1.0, 1.0), 0.3).set_trans(Tween.TRANS_SINE)
	else:
		_scale_tween = create_tween()
		_scale_tween.tween_property(self, "scale", Vector2.ONE, 0.15)
	queue_redraw()

func _draw() -> void:
	if candy_type == CandyType.COLOR_BOMB:
		CandyRenderer.draw_color_bomb(self, cell_size)
	else:
		var special = 0
		match candy_type:
			CandyType.STRIPED_H: special = 1
			CandyType.STRIPED_V: special = 2
			CandyType.WRAPPED: special = 3
			CandyType.SPIRAL: special = 5  # 紙飛機 TrPr
		CandyRenderer.draw_candy(self, candy_color, cell_size, special)

	if _selected:
		draw_arc(Vector2.ZERO, cell_size * 0.48, 0, TAU, 32, Color(1, 1, 1, 0.6), 2.0)

func _input(event: InputEvent) -> void:
	if is_being_destroyed or is_moving:
		return

	if event is InputEventMouseButton:
		var local_pos = to_local(event.global_position)
		var in_bounds = local_pos.length() < cell_size * 0.5
		if event.pressed and event.button_index == MOUSE_BUTTON_LEFT and in_bounds:
			_drag_start = event.global_position
			_is_dragging = true
			candy_selected.emit(self)
		elif not event.pressed and _is_dragging:
			_is_dragging = false

	elif event is InputEventMouseMotion and _is_dragging:
		var diff = event.global_position - _drag_start
		if diff.length() > cell_size * 0.35:
			_is_dragging = false
			var dir = Vector2i.ZERO
			if abs(diff.x) > abs(diff.y):
				dir = Vector2i(1, 0) if diff.x > 0 else Vector2i(-1, 0)
			else:
				dir = Vector2i(0, 1) if diff.y > 0 else Vector2i(0, -1)
			candy_swipe.emit(self, dir)

func animate_to(target_pos: Vector2, duration: float = 0.2) -> Tween:
	# 用於 swap / 一般位移:平滑 ease in-out,不過頭
	is_moving = true
	var tween = create_tween()
	tween.tween_property(self, "position", target_pos, duration)\
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	tween.tween_callback(func(): is_moving = false)
	return tween


func animate_fall(target_pos: Vector2, duration: float = 0.2) -> Tween:
	# 用於掉落(gravity / fill):等速線性,沒有「過頭再彈回」的浮誇感
	# 想要重力感再切 EASE_IN,目前 demo 用 LINEAR 看起來最乾淨
	is_moving = true
	var tween = create_tween()
	tween.tween_property(self, "position", target_pos, duration)\
		.set_trans(Tween.TRANS_LINEAR).set_ease(Tween.EASE_IN_OUT)
	tween.tween_callback(func(): is_moving = false)
	return tween

func animate_destroy() -> Tween:
	is_being_destroyed = true
	var tween = create_tween()
	tween.set_parallel(true)
	tween.tween_property(self, "scale", Vector2(1.3, 1.3), 0.1)\
		.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.tween_property(self, "modulate:a", 0.0, 0.2)\
		.set_delay(0.05)
	tween.set_parallel(false)
	tween.tween_callback(queue_free)
	return tween

func animate_spawn(delay: float = 0.0) -> Tween:
	scale = Vector2.ZERO
	modulate.a = 0.0
	var tween = create_tween()
	if delay > 0:
		tween.tween_interval(delay)
	tween.set_parallel(true)
	tween.tween_property(self, "scale", Vector2.ONE, 0.25)\
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tween.tween_property(self, "modulate:a", 1.0, 0.15)
	return tween

func play_hint() -> void:
	_kill_scale_tween()
	_scale_tween = create_tween().set_loops(3)
	_scale_tween.tween_property(self, "scale", Vector2(1.2, 1.2), 0.25).set_trans(Tween.TRANS_SINE)
	_scale_tween.tween_property(self, "scale", Vector2.ONE, 0.25).set_trans(Tween.TRANS_SINE)
	_scale_tween.finished.connect(func(): scale = Vector2.ONE)

func stop_hint() -> void:
	_kill_scale_tween()
	scale = Vector2.ONE
