extends Node2D

const CandyRenderer = preload("res://scripts/effects/candy_renderer.gd")

func spawn_destroy_effect(world_pos: Vector2, candy_color: int) -> void:
	var color = CandyRenderer.COLOR_MAP.get(candy_color, Color.WHITE)
	_spawn_particles(world_pos, color, 12, 80.0)
	_spawn_score_text(world_pos)

func spawn_special_destroy_effect(world_pos: Vector2, candy_color: int) -> void:
	var color = CandyRenderer.COLOR_MAP.get(candy_color, Color.WHITE)
	_spawn_particles(world_pos, color, 24, 150.0)
	_spawn_ring(world_pos, color)

func spawn_shockwave(world_pos: Vector2) -> void:
	_spawn_ring(world_pos, Color(1.0, 0.9, 0.5, 0.8))
	_spawn_particles(world_pos, Color.WHITE, 20, 120.0)

func spawn_firework(world_pos: Vector2) -> void:
	for i in 5:
		var offset = Vector2(randf_range(-100, 100), randf_range(-100, 100))
		var color = Color.from_hsv(randf(), 0.9, 1.0)
		_spawn_particles(world_pos + offset, color, 16, 100.0)

func _spawn_particles(pos: Vector2, color: Color, count: int, spread: float) -> void:
	for i in count:
		var particle = _ParticleDot.new()
		particle.position = pos
		particle.color = color.lightened(randf() * 0.3)
		var angle = randf() * TAU
		var speed = randf_range(spread * 0.3, spread)
		particle.velocity = Vector2(cos(angle), sin(angle)) * speed
		particle.lifetime = randf_range(0.3, 0.6)
		add_child(particle)

func _spawn_score_text(pos: Vector2) -> void:
	var label = Label.new()
	label.text = "+%d" % (50 * max(1, GameManager.combo_count))
	label.position = pos - Vector2(20, 10)
	label.add_theme_font_size_override("font_size", 18)
	label.add_theme_color_override("font_color", Color(1.0, 1.0, 0.5))
	label.z_index = 100
	add_child(label)
	var tween = create_tween()
	tween.set_parallel(true)
	tween.tween_property(label, "position:y", pos.y - 60, 0.6).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.tween_property(label, "modulate:a", 0.0, 0.4).set_delay(0.3)
	tween.set_parallel(false)
	tween.tween_callback(label.queue_free)

func _spawn_ring(pos: Vector2, color: Color) -> void:
	var ring = _RingEffect.new()
	ring.position = pos
	ring.ring_color = color
	add_child(ring)

class _ParticleDot extends Node2D:
	var velocity: Vector2 = Vector2.ZERO
	var lifetime: float = 0.5
	var age: float = 0.0
	var color: Color = Color.WHITE
	var sz: float = 4.0

	func _process(delta: float) -> void:
		age += delta
		if age >= lifetime:
			queue_free()
			return
		velocity.y += 200.0 * delta
		velocity *= 0.98
		position += velocity * delta
		sz = lerp(4.0, 0.5, age / lifetime)
		queue_redraw()

	func _draw() -> void:
		var alpha = 1.0 - (age / lifetime)
		draw_circle(Vector2.ZERO, sz, Color(color.r, color.g, color.b, alpha))

class _RingEffect extends Node2D:
	var ring_color: Color = Color.WHITE
	var radius: float = 5.0
	var max_radius: float = 60.0
	var alpha: float = 1.0
	var expand_speed: float = 200.0

	func _process(delta: float) -> void:
		radius += expand_speed * delta
		alpha = 1.0 - (radius / max_radius)
		if alpha <= 0:
			queue_free()
			return
		queue_redraw()

	func _draw() -> void:
		draw_arc(Vector2.ZERO, radius, 0, TAU, 32, Color(ring_color.r, ring_color.g, ring_color.b, alpha), 3.0)
