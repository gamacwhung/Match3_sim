extends Node
class_name CascadeManager

signal cascade_started(level: int)
signal cascade_ended

var cascade_level: int = 0
var is_cascading: bool = false

func start_cascade() -> void:
	cascade_level = 0
	is_cascading = true

func next_cascade() -> int:
	cascade_level += 1
	cascade_started.emit(cascade_level)
	return cascade_level

func end_cascade() -> void:
	is_cascading = false
	cascade_ended.emit()
	cascade_level = 0

func get_score_multiplier() -> float:
	return pow(1.5, cascade_level)

func get_cascade_level() -> int:
	return cascade_level
