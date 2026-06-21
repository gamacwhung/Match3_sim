extends TextureRect
##
## 全螢幕背景 — 從 ArtTheme 取 board_bg 紋理,支援 live_sprites 即時替換。
## packed 預設為 res://resources/sprites/board_bg.png;web 端會被 live 覆蓋。
##

const TEX_NAME: String = "board_bg"
const FALLBACK: Texture2D = preload("res://resources/sprites/board_bg.png")


func _ready() -> void:
	_apply()
	if not ArtTheme.theme_ready.is_connected(_apply):
		ArtTheme.theme_ready.connect(_apply)


func _apply() -> void:
	if ArtTheme.has_named_texture(TEX_NAME):
		texture = ArtTheme.get_named_texture(TEX_NAME)
	else:
		texture = FALLBACK
