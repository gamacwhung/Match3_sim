extends Node
class_name LevelLoader

const ObstacleScript = preload("res://scripts/obstacles/obstacle.gd")

static func load_level(level_id: int) -> Resource:
	var path = "res://resources/levels/level_%03d.tres" % level_id
	if ResourceLoader.exists(path):
		return load(path)
	return _generate_level(level_id)

static func _generate_level(level_id: int) -> Resource:
	var level = LevelData.new()
	level.level_id = level_id
	level.grid_width = 9
	level.grid_height = 9
	level.num_colors = min(4 + (level_id / 5), 6)

	level.max_moves = max(35 - level_id, 15)

	var base_score = 1000 + level_id * 500
	level.star_thresholds = [base_score, base_score * 2, base_score * 3]

	if level_id <= 3:
		level.objectives = [{"type": "score", "target": base_score, "current": 0}]
	elif level_id <= 6:
		var color = randi() % level.num_colors
		level.objectives = [{"type": "collect", "color": color, "target": 20 + level_id * 3, "current": 0}]
	elif level_id <= 8:
		level.objectives = [{"type": "clear_jelly", "target": 5 + level_id, "current": 0}]
		_add_jelly_obstacles(level)
	else:
		level.objectives = [{"type": "clear_ice", "target": 4 + level_id, "current": 0}]
		_add_ice_obstacles(level)

	if level_id >= 5:
		_add_wire_obstacles(level, min(level_id - 3, 6))

	if level_id >= 8:
		_add_blocked_cells(level)

	return level

static func _add_jelly_obstacles(level: LevelData) -> void:
	var count = level.objectives[0]["target"]
	var positions: Array[Vector2i] = []
	for i in count:
		var pos = _random_free_pos(level, positions)
		if pos != Vector2i(-1, -1):
			positions.append(pos)
			var hp = 1 if level.level_id < 9 else randi_range(1, 2)
			level.obstacle_data.append({"pos": [pos.x, pos.y], "type": "jelly", "hp": hp})

static func _add_ice_obstacles(level: LevelData) -> void:
	var count = level.objectives[0]["target"]
	var positions: Array[Vector2i] = []
	for i in count:
		var pos = _random_free_pos(level, positions)
		if pos != Vector2i(-1, -1):
			positions.append(pos)
			var hp = randi_range(1, min(level.level_id / 4 + 1, 3))
			level.obstacle_data.append({"pos": [pos.x, pos.y], "type": "ice", "hp": hp})

static func _add_wire_obstacles(level: LevelData, count: int) -> void:
	var positions: Array[Vector2i] = []
	for entry in level.obstacle_data:
		positions.append(Vector2i(entry["pos"][0], entry["pos"][1]))
	for i in count:
		var pos = _random_free_pos(level, positions)
		if pos != Vector2i(-1, -1):
			positions.append(pos)
			level.obstacle_data.append({"pos": [pos.x, pos.y], "type": "wire", "hp": 1})

static func _add_blocked_cells(level: LevelData) -> void:
	var corners = [
		Vector2i(0, 0), Vector2i(1, 0), Vector2i(0, 1), Vector2i(1, 1),
		Vector2i(level.grid_width - 1, 0), Vector2i(level.grid_width - 2, 0),
		Vector2i(level.grid_width - 1, 1), Vector2i(level.grid_width - 2, 1),
	]
	var num_blocked = randi_range(2, 4)
	for i in num_blocked:
		if i < corners.size():
			level.blocked_cells.append(corners[i])

static func _random_free_pos(level: LevelData, existing: Array[Vector2i]) -> Vector2i:
	for _attempt in 100:
		var x = randi_range(1, level.grid_width - 2)
		var y = randi_range(1, level.grid_height - 2)
		var pos = Vector2i(x, y)
		if pos not in existing and pos not in level.blocked_cells:
			return pos
	return Vector2i(-1, -1)
