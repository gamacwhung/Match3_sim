extends Node

const SAVE_PATH = "user://save_data.json"

var save_data: Dictionary = {
	"levels": {},
	"highest_unlocked": 1,
	"items": {
		"extra_moves": 3,
		"color_bomb": 1,
		"shuffle": 2
	}
}

func _ready() -> void:
	load_game()

func save_game() -> void:
	var file = FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(save_data, "\t"))

func load_game() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		save_game()
		return
	var file = FileAccess.open(SAVE_PATH, FileAccess.READ)
	if file:
		var json = JSON.new()
		var result = json.parse(file.get_as_text())
		if result == OK:
			save_data = json.data

func save_level_progress(level_id: int, score: int, stars: int) -> void:
	var key = str(level_id)
	if not save_data["levels"].has(key):
		save_data["levels"][key] = {"best_score": 0, "stars": 0}
	var level_save = save_data["levels"][key]
	if score > level_save["best_score"]:
		level_save["best_score"] = score
	if stars > level_save["stars"]:
		level_save["stars"] = stars
	if level_id >= save_data["highest_unlocked"]:
		save_data["highest_unlocked"] = level_id + 1
	save_game()

func get_level_stars(level_id: int) -> int:
	var key = str(level_id)
	if save_data["levels"].has(key):
		return save_data["levels"][key]["stars"]
	return 0

func get_level_best_score(level_id: int) -> int:
	var key = str(level_id)
	if save_data["levels"].has(key):
		return save_data["levels"][key]["best_score"]
	return 0

func is_level_unlocked(level_id: int) -> bool:
	return level_id <= save_data["highest_unlocked"]

func get_highest_unlocked() -> int:
	return save_data["highest_unlocked"]

func get_item_count(item_name: String) -> int:
	if save_data["items"].has(item_name):
		return save_data["items"][item_name]
	return 0

func use_item(item_name: String) -> bool:
	if get_item_count(item_name) > 0:
		save_data["items"][item_name] -= 1
		save_game()
		return true
	return false

func reset_save() -> void:
	save_data = {
		"levels": {},
		"highest_unlocked": 1,
		"items": {
			"extra_moves": 3,
			"color_bomb": 1,
			"shuffle": 2
		}
	}
	save_game()
