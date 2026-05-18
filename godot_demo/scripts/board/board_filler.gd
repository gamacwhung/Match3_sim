extends Node

signal fill_complete

var grid: Array = []
var width: int = 9
var height: int = 9
var cell_size: float = 70.0
var board_offset: Vector2 = Vector2.ZERO
var blocked_cells: Array[Vector2i] = []
var candy_scene: PackedScene
var candy_container: Node2D
var num_colors: int = 6

func setup(w: int, h: int, c_size: float, offset: Vector2, container: Node2D, scene: PackedScene, blocked: Array[Vector2i] = []) -> void:
	width = w
	height = h
	cell_size = c_size
	board_offset = offset
	candy_container = container
	candy_scene = scene
	blocked_cells = blocked
	grid.clear()
	for x in width:
		var col: Array = []
		col.resize(height)
		col.fill(null)
		grid.append(col)

func grid_to_world(grid_pos: Vector2i) -> Vector2:
	return board_offset + Vector2(grid_pos.x * cell_size + cell_size / 2.0, grid_pos.y * cell_size + cell_size / 2.0)

func fill_initial() -> void:
	var MatchFinder = preload("res://scripts/board/match_finder.gd")
	for y in height:
		for x in width:
			if Vector2i(x, y) in blocked_cells:
				continue
			var color = _pick_no_match_color(x, y)
			var candy = _create_candy(color, Vector2i(x, y))
			grid[x][y] = candy

func _pick_no_match_color(x: int, y: int) -> int:
	var attempts = 0
	while attempts < 100:
		var color = randi() % num_colors
		var h_match = false
		if x >= 2:
			if grid[x - 1][y] != null and grid[x - 2][y] != null:
				if grid[x - 1][y].candy_color == color and grid[x - 2][y].candy_color == color:
					h_match = true
		var v_match = false
		if y >= 2:
			if grid[x][y - 1] != null and grid[x][y - 2] != null:
				if grid[x][y - 1].candy_color == color and grid[x][y - 2].candy_color == color:
					v_match = true
		if not h_match and not v_match:
			return color
		attempts += 1
	return randi() % num_colors

func _create_candy(color: int, grid_pos: Vector2i, candy_type: int = 0) -> Node2D:
	var candy = candy_scene.instantiate()
	candy_container.add_child(candy)
	candy.init(color, grid_pos, candy_type)
	candy.cell_size = cell_size
	candy.position = grid_to_world(grid_pos)
	return candy

# 共用的掉落時長(秒/格)— gravity 跟 fill 用同一個公式,
# 才能在視覺上「連成一條下落的列車」,不會出現兩段斷層。
const _FALL_TIME_PER_CELL: float = 0.07
const _FALL_TIME_BASE: float = 0.08

static func _fall_duration(dist: int) -> float:
	return _FALL_TIME_PER_CELL * dist + _FALL_TIME_BASE


func apply_gravity() -> Array[Tween]:
	var tweens: Array[Tween] = []
	for x in width:
		var write_y = height - 1
		while write_y >= 0 and Vector2i(x, write_y) in blocked_cells:
			write_y -= 1
		for y in range(height - 1, -1, -1):
			if Vector2i(x, y) in blocked_cells:
				continue
			if grid[x][y] != null:
				while write_y >= 0 and Vector2i(x, write_y) in blocked_cells:
					write_y -= 1
				if write_y < 0:
					break
				if y != write_y:
					grid[x][write_y] = grid[x][y]
					grid[x][y] = null
					grid[x][write_y].grid_pos = Vector2i(x, write_y)
					var target = grid_to_world(Vector2i(x, write_y))
					var dist = abs(write_y - y)
					var tween = grid[x][write_y].animate_fall(target, _fall_duration(dist))
					tweens.append(tween)
				write_y -= 1
	return tweens

func fill_empty_cells() -> Array[Tween]:
	# 物理上:從天上掉下來,**第一顆會穿過空格落到最底**,然後第二顆停在它上面,...
	# 視覺上要呈現「一列連續往下掉的隊列」:
	#   - 排在最上方(start_y=-1)的 candy 落到最深的空格(y 最大)
	#   - 排在 start_y=-2 的 candy 落到次深空格
	#   - 每顆 dist 相同 → 等速一起到位,看起來像「整條糖果列車滑下來」
	#
	# 舊版是 y=0..height 順序 fill,start_y 隨著遞減,結果上面 dist 小、下面 dist 大,
	# 變成「上面先到位、下面後到位」,看起來像「先生成的留在上面」。已修正。
	var tweens: Array[Tween] = []
	for x in width:
		# 從上到下收集這一列所有空格(by y ascending)
		var empty_ys: Array[int] = []
		for y in height:
			if Vector2i(x, y) in blocked_cells:
				continue
			if grid[x][y] == null:
				empty_ys.append(y)
		# 反向 fill:第 i 顆 spawn(start_y=-i-1)落到第 i 個最底空格
		for i in empty_ys.size():
			var target_y = empty_ys[empty_ys.size() - 1 - i]
			var start_y = -(i + 1)
			var color = randi() % num_colors
			var candy = _create_candy(color, Vector2i(x, target_y))
			candy.position = grid_to_world(Vector2i(x, start_y))
			grid[x][target_y] = candy
			var target = grid_to_world(Vector2i(x, target_y))
			var dist = abs(target_y - start_y)
			var tween = candy.animate_fall(target, _fall_duration(dist))
			tweens.append(tween)
	return tweens

func remove_candy_at(pos: Vector2i) -> Node2D:
	if pos.x < 0 or pos.x >= width or pos.y < 0 or pos.y >= height:
		return null
	var candy = grid[pos.x][pos.y]
	grid[pos.x][pos.y] = null
	return candy

func set_candy_at(pos: Vector2i, candy: Node2D) -> void:
	grid[pos.x][pos.y] = candy
	if candy != null:
		candy.grid_pos = pos

func get_candy_at(pos: Vector2i) -> Node2D:
	if pos.x < 0 or pos.x >= width or pos.y < 0 or pos.y >= height:
		return null
	return grid[pos.x][pos.y]

func create_special_candy(color: int, grid_pos: Vector2i, candy_type: int) -> Node2D:
	var candy = _create_candy(color, grid_pos, candy_type)
	grid[grid_pos.x][grid_pos.y] = candy
	candy.animate_spawn()
	return candy
