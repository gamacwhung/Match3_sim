extends Node
class_name SpecialCandy

const CandyScript = preload("res://scripts/candy/candy.gd")

static func get_striped_h_targets(pos: Vector2i, grid_width: int) -> Array[Vector2i]:
	var targets: Array[Vector2i] = []
	for x in grid_width:
		if x != pos.x:
			targets.append(Vector2i(x, pos.y))
	return targets

static func get_striped_v_targets(pos: Vector2i, grid_height: int) -> Array[Vector2i]:
	var targets: Array[Vector2i] = []
	for y in grid_height:
		if y != pos.y:
			targets.append(Vector2i(pos.x, y))
	return targets

static func get_wrapped_targets(pos: Vector2i, grid_width: int, grid_height: int) -> Array[Vector2i]:
	var targets: Array[Vector2i] = []
	for dx in range(-1, 2):
		for dy in range(-1, 2):
			if dx == 0 and dy == 0:
				continue
			var tp = Vector2i(pos.x + dx, pos.y + dy)
			if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
				targets.append(tp)
	return targets

static func get_cross_targets(pos: Vector2i, grid_width: int, grid_height: int) -> Array[Vector2i]:
	var targets: Array[Vector2i] = []
	for x in grid_width:
		if x != pos.x:
			targets.append(Vector2i(x, pos.y))
	for y in grid_height:
		if y != pos.y:
			targets.append(Vector2i(pos.x, y))
	return targets

static func get_big_wrapped_targets(pos: Vector2i, grid_width: int, grid_height: int) -> Array[Vector2i]:
	var targets: Array[Vector2i] = []
	for dx in range(-2, 3):
		for dy in range(-2, 3):
			if dx == 0 and dy == 0:
				continue
			var tp = Vector2i(pos.x + dx, pos.y + dy)
			if tp.x >= 0 and tp.x < grid_width and tp.y >= 0 and tp.y < grid_height:
				targets.append(tp)
	return targets

static func get_color_targets(target_color: int, grid: Array, width: int, height: int) -> Array[Vector2i]:
	var targets: Array[Vector2i] = []
	for x in width:
		for y in height:
			if grid[x][y] != null:
				var candy = grid[x][y]
				if candy.candy_color == target_color:
					targets.append(Vector2i(x, y))
	return targets
