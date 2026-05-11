extends Node
class_name CandyFactory

const CandyScript = preload("res://scripts/candy/candy.gd")

static func determine_special_type(match_data: Dictionary) -> int:
	var cells = match_data.get("cells", []) as Array
	var shape = match_data.get("shape", "line")
	var directions = match_data.get("directions", [])

	if cells.size() >= 5 or shape == "five":
		return CandyScript.CandyType.COLOR_BOMB

	if shape == "special" or directions.size() > 1:
		return CandyScript.CandyType.WRAPPED

	if cells.size() == 4 or shape == "four":
		if directions.size() > 0 and directions[0] == "horizontal":
			return CandyScript.CandyType.STRIPED_V
		else:
			return CandyScript.CandyType.STRIPED_H

	return -1

static func get_combo_result(type_a: int, type_b: int) -> Dictionary:
	var types = [type_a, type_b]
	types.sort()

	if types[0] == CandyScript.CandyType.COLOR_BOMB and types[1] == CandyScript.CandyType.COLOR_BOMB:
		return {"effect": "destroy_all"}

	if CandyScript.CandyType.COLOR_BOMB in types:
		var other = type_a if type_b == CandyScript.CandyType.COLOR_BOMB else type_b
		if other == CandyScript.CandyType.WRAPPED:
			return {"effect": "color_bomb_wrapped"}
		elif other in [CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V]:
			return {"effect": "color_bomb_striped"}
		else:
			return {"effect": "color_bomb_normal"}

	var is_striped_a = type_a in [CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V]
	var is_striped_b = type_b in [CandyScript.CandyType.STRIPED_H, CandyScript.CandyType.STRIPED_V]

	if type_a == CandyScript.CandyType.WRAPPED and type_b == CandyScript.CandyType.WRAPPED:
		return {"effect": "double_wrapped"}

	if (type_a == CandyScript.CandyType.WRAPPED and is_striped_b) or \
	   (type_b == CandyScript.CandyType.WRAPPED and is_striped_a):
		return {"effect": "wrapped_striped"}

	if is_striped_a and is_striped_b:
		return {"effect": "double_striped"}

	return {"effect": "none"}

static func get_special_name(candy_type: int) -> String:
	match candy_type:
		CandyScript.CandyType.STRIPED_H: return "Horizontal Striped"
		CandyScript.CandyType.STRIPED_V: return "Vertical Striped"
		CandyScript.CandyType.WRAPPED: return "Wrapped"
		CandyScript.CandyType.COLOR_BOMB: return "Color Bomb"
		_: return "Normal"
