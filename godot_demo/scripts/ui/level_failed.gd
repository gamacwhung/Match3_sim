extends Control

signal retry_pressed
signal menu_pressed

func _ready() -> void:
	$Panel/VBox/RetryButton.pressed.connect(func(): AudioManager.play_button_sound(); retry_pressed.emit())
	$Panel/VBox/MenuButton.pressed.connect(func(): AudioManager.play_button_sound(); menu_pressed.emit())

func show_failed() -> void:
	_animate_in()

func _animate_in() -> void:
	modulate.a = 0.0
	$Panel.scale = Vector2(0.5, 0.5)
	visible = true
	var tween = create_tween()
	tween.set_parallel(true)
	tween.tween_property(self, "modulate:a", 1.0, 0.3)
	tween.tween_property($Panel, "scale", Vector2.ONE, 0.4).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
