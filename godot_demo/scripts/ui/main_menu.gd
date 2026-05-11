extends Control

signal play_pressed
signal quit_pressed

func _ready() -> void:
	# Demo mode: 若被當成 main scene 跑起來,自動 redirect 到 demo_main.tscn。
	# (項目實際 main scene 是 demo_main,這層是 Web export 設錯時的保險網。)
	# 若要回到 yuehpo 原版選單,把下面 3 行刪掉即可。
	var demo_scene: PackedScene = load("res://scenes/demo_main.tscn")
	if demo_scene and (not get_parent() or get_parent() == get_tree().root):
		get_tree().change_scene_to_packed.call_deferred(demo_scene)
		return
	$VBoxContainer/PlayButton.pressed.connect(_on_play)
	$VBoxContainer/QuitButton.pressed.connect(_on_quit)
	_animate_title()

func _on_play() -> void:
	AudioManager.play_button_sound()
	play_pressed.emit()

func _on_quit() -> void:
	get_tree().quit()

func _animate_title() -> void:
	var title = $VBoxContainer/TitleLabel
	var tween = create_tween().set_loops()
	tween.tween_property(title, "modulate", Color(1.0, 0.85, 0.4), 1.5).set_trans(Tween.TRANS_SINE)
	tween.tween_property(title, "modulate", Color(1.0, 0.5, 0.8), 1.5).set_trans(Tween.TRANS_SINE)
	tween.tween_property(title, "modulate", Color(0.5, 0.85, 1.0), 1.5).set_trans(Tween.TRANS_SINE)
