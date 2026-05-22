extends Node2D

const CandyRenderer = preload("res://scripts/effects/candy_renderer.gd")
const PLANE_TEXTURE: Texture2D = preload("res://resources/sprites/TrPr.png")
const COLOR_BOMB_TEXTURE: Texture2D = preload("res://resources/sprites/LtBl.png")
const STAMP_INK_COLOR: Color = Color(0.75, 0.12, 0.18, 0.95)

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

# 紙飛機飛行動畫:由 from 飛到 to,弧形拋物線,沿路留亮色尾跡。
# TrPr.png 原圖 1024×1024,cell_size 約 70 px,scale 0.062 → 顯示 ~63 px(約 = 1 顆 candy 大小)
# 回傳結束 signal,呼叫端可以 await。
const PLANE_SCALE: Vector2 = Vector2(0.062, 0.062)

func spawn_plane_flight(from_pos: Vector2, to_pos: Vector2, candy_color: int = -1, flight_time: float = 1.0) -> Signal:
	var plane = Sprite2D.new()
	plane.texture = PLANE_TEXTURE
	plane.position = from_pos
	plane.z_index = 200
	plane.scale = PLANE_SCALE
	var dir = to_pos - from_pos
	plane.rotation = dir.angle() + PI / 2
	add_child(plane)

	var trail_timer = Timer.new()
	trail_timer.wait_time = 0.02
	trail_timer.one_shot = false
	plane.add_child(trail_timer)
	trail_timer.start()
	trail_timer.timeout.connect(_spawn_trail_dot.bind(plane))

	var mid = (from_pos + to_pos) * 0.5 + Vector2(0, -60.0)
	var tween = create_tween()
	tween.tween_property(plane, "position", mid, flight_time * 0.5).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tween.tween_property(plane, "position", to_pos, flight_time * 0.5).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN)
	tween.tween_callback(plane.queue_free)
	return tween.finished

func _spawn_trail_dot(plane: Node2D) -> void:
	if not is_instance_valid(plane):
		return
	var dot = _ParticleDot.new()
	dot.position = plane.position
	dot.color = Color(1.0, 0.92, 0.55, 1.0)
	dot.velocity = Vector2.ZERO
	dot.lifetime = 0.5
	dot.sz = 6.0
	add_child(dot)

# 紙飛機抵達後的「目的地命中」特效:暖色衝擊波 + 火光迸發 + 中心閃光,讓玩家清楚看到「消除發生在這格」。
# 由 game_board 在 _deferred_explode 之前同步呼叫;比一般 destroy 更明顯。
func spawn_plane_impact(world_pos: Vector2) -> void:
	# 1) 強衝擊環(暖色)
	var ring = _RingEffect.new()
	ring.position = world_pos
	ring.ring_color = Color(1.0, 0.7, 0.2, 1.0)
	ring.expand_speed = 360.0
	ring.max_radius = 55.0
	add_child(ring)
	# 2) 第二層較細的白圈,擴更快讓「punch」感更明顯
	var ring2 = _RingEffect.new()
	ring2.position = world_pos
	ring2.ring_color = Color(1.0, 1.0, 1.0, 0.9)
	ring2.expand_speed = 520.0
	ring2.max_radius = 70.0
	add_child(ring2)
	# 3) 火光迸發 — 多向發散粒子
	_spawn_particles(world_pos, Color(1.0, 0.85, 0.3, 1.0), 22, 220.0)
	_spawn_particles(world_pos, Color(1.0, 0.5, 0.2, 1.0), 12, 160.0)
	# 4) 中心白色閃光(大顆短命粒)— 主視覺
	var flash = _ParticleDot.new()
	flash.position = world_pos
	flash.color = Color(1.0, 1.0, 1.0, 1.0)
	flash.velocity = Vector2.ZERO
	flash.lifetime = 0.18
	flash.sz = 32.0
	add_child(flash)

# 光球(COLOR_BOMB)主視覺:小小一顆 LtBl sprite 浮起 + 持續旋轉。
# 旋轉期間呼叫端會逐一點亮目標(_animate_color_bomb_sequence 處理);
# 等所有目標都點亮後,光球淡出 + 同時觸發。
# duration: 整個浮起+旋轉的時間,通常 = stagger * targets.size() + 緩衝
func spawn_color_bomb_orb(world_pos: Vector2, duration: float) -> void:
	var orb = Sprite2D.new()
	orb.texture = COLOR_BOMB_TEXTURE
	orb.position = world_pos
	orb.z_index = 199
	# LtBl.png 是 1024×1024,scale 0.06 → 顯示 ~61 px(略小於 candy 70px,看起來在 cell 內飄)
	orb.scale = Vector2(0.06, 0.06)
	add_child(orb)
	var tw = create_tween()
	# 飄起 + 同時持續旋轉(parallel)
	tw.tween_property(orb, "position", world_pos + Vector2(0, -30), duration).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
	tw.parallel().tween_property(orb, "rotation", TAU * 2.5, duration).set_trans(Tween.TRANS_LINEAR)
	# 結束時淡出 + queue_free
	tw.tween_property(orb, "modulate:a", 0.0, 0.2)
	tw.tween_callback(orb.queue_free)

# 目標被光球「點亮」的瞬間特效:小範圍彩色脈動 + 環擴張
# 郵戳觸發 — 輕量提示(主視覺由盤面 01→02 + 明信片飛向 HUD 負責)。
func spawn_stamp_trigger(world_pos: Vector2) -> void:
	var ring = _RingEffect.new()
	ring.position = world_pos
	ring.z_index = 204
	ring.ring_color = STAMP_INK_COLOR
	ring.expand_speed = 120.0
	ring.max_radius = 32.0
	add_child(ring)
	_spawn_particles(world_pos, STAMP_INK_COLOR, 6, 55.0)


func spawn_target_highlight(world_pos: Vector2, candy_color: int) -> void:
	var color = CandyRenderer.COLOR_MAP.get(candy_color, Color.WHITE)
	# 中心快速放大+淡出的白光點
	var spot = _ParticleDot.new()
	spot.position = world_pos
	spot.color = Color(1.0, 1.0, 1.0, 1.0)
	spot.velocity = Vector2.ZERO
	spot.lifetime = 0.25
	spot.sz = 14.0
	add_child(spot)
	# 一個小擴散環(對應該 candy 的顏色)
	var ring = _RingEffect.new()
	ring.position = world_pos
	ring.ring_color = color
	ring.expand_speed = 220.0
	ring.max_radius = 45.0
	add_child(ring)

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
	var sz: float = 4.0  # 初始大小,_process 內會 lerp 到 0.5(往生時的尾巴)

	func _process(delta: float) -> void:
		age += delta
		if age >= lifetime:
			queue_free()
			return
		velocity.y += 200.0 * delta
		velocity *= 0.98
		position += velocity * delta
		# 把 sz 當成「初始大小」,lerp 到 0.5 → 小尾巴
		# 先讀第一個 frame 的 sz 當 baseline,確保 spawn 端可以指定不同大小(例如 32 大型閃光)
		if _initial_sz < 0:
			_initial_sz = sz
		sz = lerp(_initial_sz, 0.5, age / lifetime)
		queue_redraw()

	var _initial_sz: float = -1.0

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
