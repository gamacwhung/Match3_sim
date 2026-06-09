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

		# 直接以 entry["type"] 字串傳遞 — 支援 manufacturer / 之後新增的 type
		# (改之前透過 enum 走 match,Stamp 的 "manufacturer" 沒被認到會被默默改成 "ice",
		#  害 _damage_obstacle 的 manufacturer 分支永遠跳不到 → Stamp 會被當 ice 扣 HP/消除。
		#  改成直接 copy entry 內欄位,避免再丟資訊。)
		var hp: int = int(entry.get("hp", 1))
		var data: Dictionary = {
			"type": str(entry["type"]),
			"hp": hp,
			"max_hp": int(entry.get("max_hp", hp)),
		}
		if entry.has("tile_id"):
			data["tile_id"] = entry["tile_id"]
		if entry.has("layer"):
			data["layer"] = entry["layer"]
		if entry.has("stamp_state"):
			data["stamp_state"] = entry["stamp_state"]
		if entry.has("salmon_state"):
			data["salmon_state"] = entry["salmon_state"]
		obs_map[pos] = data
	return obs_map

static func count_obstacles_by_type(obs_map: Dictionary, type_name: String) -> int:
	var count = 0
	for pos in obs_map:
		if obs_map[pos]["type"] == type_name:
			count += 1
	return count
