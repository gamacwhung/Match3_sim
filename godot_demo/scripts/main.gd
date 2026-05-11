extends Control
##
## Fallback entry — 若 export 時誤把 main.tscn 設為 Main Scene,_ready 會把
## 場景換成 res://scenes/demo_main.tscn,確保 demo flow 一定啟動。
##
## 原本 yuehpo 的 main_menu → world_map → game_board 流程已移除,
## 現在 demo 只有一條路:demo_main → level_select → game_board。
##

func _ready() -> void:
	var demo_scene: PackedScene = load("res://scenes/demo_main.tscn")
	if demo_scene:
		get_tree().change_scene_to_packed.call_deferred(demo_scene)
