extends Resource
class_name LevelData

@export var level_id: int = 1
@export var grid_width: int = 9
@export var grid_height: int = 9
@export var max_moves: int = 30
@export var num_colors: int = 6
@export var star_thresholds: Array[int] = [1000, 3000, 5000]
@export var objectives: Array[Dictionary] = []
@export var obstacle_data: Array[Dictionary] = []
@export var blocked_cells: Array[Vector2i] = []
