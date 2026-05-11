extends Node
class_name Obstacle

enum ObstacleType { ICE, WIRE, JELLY }

static func create_obstacle_data(type: ObstacleType, hp: int = 1) -> Dictionary:
	var type_name = ""
	match type:
		ObstacleType.ICE: type_name = "ice"
		ObstacleType.WIRE: type_name = "wire"
		ObstacleType.JELLY: type_name = "jelly"
	return {
		"type": type_name,
		"hp": hp,
		"max_hp": hp
	}

static func build_obstacle_map(obstacle_data: Array, grid_width: int, grid_height: int) -> Dictionary:
	var obs_map: Dictionary = {}
	for entry in obstacle_data:
		if not entry.has("pos"):
			continue
		var pos: Vector2i
		if entry["pos"] is Vector2i:
			pos = entry["pos"]
		elif entry["pos"] is Array and entry["pos"].size() >= 2:
			pos = Vector2i(entry["pos"][0], entry["pos"][1])
		else:
			continue

		if pos.x < 0 or pos.x >= grid_width or pos.y < 0 or pos.y >= grid_height:
			continue

		# 多格 instance:直接把 shared_ref dict 設成 obstacle_map[pos]
		# 同 instance 的多個 pos 都會指向同個 dict,改 hp 全部跟著變。
		if entry.has("shared_ref"):
			obs_map[pos] = entry["shared_ref"]
			continue

		if not entry.has("type"):
			continue

		var type_enum = ObstacleType.ICE
		match entry["type"]:
			"ice": type_enum = ObstacleType.ICE
			"wire": type_enum = ObstacleType.WIRE
			"jelly": type_enum = ObstacleType.JELLY

		var hp = entry.get("hp", 1)
		var data = create_obstacle_data(type_enum, hp)
		if entry.has("tile_id"):
			data["tile_id"] = entry["tile_id"]
		if entry.has("layer"):
			data["layer"] = entry["layer"]
		if entry.has("max_hp"):
			data["max_hp"] = entry["max_hp"]
		obs_map[pos] = data
	return obs_map

static func count_obstacles_by_type(obs_map: Dictionary, type_name: String) -> int:
	var count = 0
	for pos in obs_map:
		if obs_map[pos]["type"] == type_name:
			count += 1
	return count
