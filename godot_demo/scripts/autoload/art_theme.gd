extends Node
##
## ArtTheme — runtime sprite overrides for AI-generated art.
##
## Web: loads godot_demo/web/live_sprites/*.png only when URL has ?live=1
##      (AI Art Lab sets this after「套用到遊戲」; normal page load uses packed defaults).
## Editor / desktop: uses res://resources/sprites/ (live folder ignored).
##

signal theme_ready

const ELEMENT_NAMES: Dictionary = {
	0: "Red",
	1: "Grn",
	2: "Blu",
	3: "Yel",
	4: "Pur",
}

# sprite 檔名 → 元素色 index(live 覆蓋時同步寫進 _textures 供 candy_renderer 用)
const ELEMENT_INDEX: Dictionary = {
	"Red": 0, "Grn": 1, "Blu": 2, "Yel": 3, "Pur": 4,
}

# board_bg 一定要有 packed 預設(全螢幕背景 + 盤面木框 fallback)
const NAMED_TEXTURES: Array[String] = ["board_bg"]

# Web 端 live 貼圖最大邊長(避免大圖吃光 WASM/GPU 記憶體)。攤位畫面小，256 就很夠，
# 換皮一次載 60+ 張，太大會 GPU OOM 整個瀏覽器當掉。
const LIVE_MAX_DIM_ELEMENTS: int = 256
const LIVE_MAX_DIM_NAMED: Dictionary = {"board_bg": 512}

var theme_revision: int = 0
# 目前套用的換皮主題:空字串 = 預設 candy(flat live_sprites/);否則 = live_sprites/themes/<name>/。
var current_theme: String = ""
# themes.json 內容(切換 UI 用):[{name,label,default?}, ...]
var available_themes: Array = []
var _textures: Dictionary = {}
# 任意具名 sprite 的 live 覆蓋(stem → Texture2D);board_bg 另含 packed 預設。
var _named: Dictionary = {}


func _ready() -> void:
	await reload()


func reload() -> void:
	theme_revision = int(Time.get_unix_time_from_system())
	_textures.clear()
	_named.clear()
	_load_packed_defaults()
	if OS.has_feature("web"):
		# 換風格走「外面(Streamlit)選 → 重載 iframe ?theme=xxx → 開機套用」流程
		#（跟 AI Art Lab 一樣是乾淨重開，不會像在 WASM 內反覆載貼圖那樣 GPU OOM）
		var url_theme := _url_param("theme")
		if url_theme != "":
			current_theme = url_theme
		if available_themes.is_empty():
			await _load_themes_index()
		# 有選主題(current_theme)或 URL ?live=1 都要套 live 覆蓋
		if current_theme != "" or _live_requested():
			await _apply_live_overrides()
		# 通知開機 splash:packed(或 live)美術就緒,可以收掉進度條
		JavaScriptBridge.eval("window._artThemeReady=true;", true)
	theme_ready.emit()


# 切換換皮主題("" = 預設 candy);重載 + 重新 emit theme_ready 讓全場 re-skin。
func set_theme(theme_name: String) -> void:
	if theme_name == current_theme:
		return
	current_theme = theme_name
	await reload()


# 循環切到下一套主題,回傳新主題的顯示 label(給按鈕顯示用)。
func cycle_theme() -> String:
	if OS.has_feature("web") and available_themes.is_empty():
		await _load_themes_index()
	if available_themes.is_empty():
		return ""
	var idx := -1
	for i in available_themes.size():
		if str(available_themes[i].get("name", "")) == current_theme:
			idx = i
			break
	var nxt: Dictionary = available_themes[(idx + 1) % available_themes.size()]
	await set_theme(str(nxt.get("name", "")))
	return str(nxt.get("label", nxt.get("name", "")))


# 載入 themes.json(切換清單);固定從 flat live_sprites/ 取(與 current_theme 無關)。
func _load_themes_index() -> void:
	var base := _flat_base_url()
	if base.is_empty():
		return
	var http := HTTPRequest.new()
	add_child(http)
	if http.request("%sthemes.json?v=%d" % [base, theme_revision]) != OK:
		http.queue_free()
		return
	var args = await http.request_completed
	http.queue_free()
	var code: int = args[1]
	var body: PackedByteArray = args[3]
	if code != 200 or body.is_empty():
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if parsed is Array:
		available_themes = parsed


func get_element_texture(color_index: int) -> Texture2D:
	return _textures.get(color_index)


func has_element_texture(color_index: int) -> bool:
	return _textures.has(color_index)


func get_named_texture(name: String) -> Texture2D:
	return _named.get(name)


func has_named_texture(name: String) -> bool:
	return _named.has(name)


func _load_packed_defaults() -> void:
	for color_index in ELEMENT_NAMES:
		var name: String = ELEMENT_NAMES[color_index]
		var path := "res://resources/sprites/%s.png" % name
		if ResourceLoader.exists(path):
			_textures[color_index] = load(path)
	for tex_name in NAMED_TEXTURES:
		var named_path := "res://resources/sprites/%s.png" % tex_name
		if ResourceLoader.exists(named_path):
			_named[tex_name] = load(named_path)


func _apply_live_overrides() -> void:
	var base_url := _live_base_url()
	if base_url.is_empty():
		return
	# manifest.json 列出目前 live_sprites 內所有可覆蓋的 sprite 名稱
	var names := await _fetch_manifest(base_url)
	# 先全部收完再一次性套用,避免半途的字典被 candy_renderer 讀到造成逐張跳入。
	# 逐張序列下載(web 端 HTTPRequest 併發不穩,序列才可靠);進度回報給開機 splash。
	var loaded_named: Dictionary = {}
	var loaded_textures: Dictionary = {}
	var total := names.size()
	var done := 0
	_js_progress(0, total)
	for nm in names:
		var max_dim: int = int(LIVE_MAX_DIM_NAMED.get(nm, LIVE_MAX_DIM_ELEMENTS))
		var url := "%s%s.png?v=%d" % [base_url, nm, theme_revision]
		var tex := await _fetch_texture(url, max_dim)
		done += 1
		_js_progress(done, total)
		if tex == null:
			continue
		loaded_named[nm] = tex
		if ELEMENT_INDEX.has(nm):
			loaded_textures[ELEMENT_INDEX[nm]] = tex
	for key in loaded_named:
		_named[key] = loaded_named[key]
	for idx in loaded_textures:
		_textures[idx] = loaded_textures[idx]


func _fetch_manifest(base_url: String) -> Array:
	var http := HTTPRequest.new()
	add_child(http)
	var err := http.request("%smanifest.json?v=%d" % [base_url, theme_revision])
	if err != OK:
		http.queue_free()
		return NAMED_TEXTURES.duplicate()
	var args = await http.request_completed
	http.queue_free()
	var response_code: int = args[1]
	var body: PackedByteArray = args[3]
	if response_code != 200 or body.is_empty():
		return NAMED_TEXTURES.duplicate()
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if parsed is Array and not parsed.is_empty():
		return parsed
	return NAMED_TEXTURES.duplicate()


func _js_progress(current: int, total: int) -> void:
	# 回報 live 美術載入進度給開機 splash 的進度條
	JavaScriptBridge.eval("window._artThemeProgress={current:%d,total:%d};" % [current, total], true)


func _live_requested() -> bool:
	if not OS.has_feature("web"):
		return false
	var js := """
	(function() {
	  var q = new URLSearchParams(window.location.search);
	  var v = q.get('live');
	  return v === '1' || v === 'true';
	})()
	"""
	var result = JavaScriptBridge.eval(js, true)
	return bool(result)


# 讀任意 URL query 參數(如 ?theme=ocean_theme)；非 web 或沒有則回空字串。
func _url_param(key: String) -> String:
	if not OS.has_feature("web"):
		return ""
	var js := "(function(){var q=new URLSearchParams(window.location.search);return q.get('%s')||'';})()" % key
	var r = JavaScriptBridge.eval(js, true)
	return str(r) if r != null else ""


# flat live_sprites/ 根目錄(預設 candy + themes.json 都在這層)
func _flat_base_url() -> String:
	if not OS.has_feature("web"):
		return ""
	var js := """
	(function() {
	  var p = window.location.pathname;
	  var i = p.lastIndexOf('/');
	  var base = window.location.origin + (i >= 0 ? p.substring(0, i + 1) : '/');
	  return base + 'live_sprites/';
	})()
	"""
	var result = JavaScriptBridge.eval(js, true)
	return str(result) if result != null else ""


# 目前主題的 sprite 基底:選了主題就指到 themes/<name>/,否則用 flat(預設 candy)。
func _live_base_url() -> String:
	var base := _flat_base_url()
	if base.is_empty():
		return ""
	if current_theme != "":
		return base + "themes/" + current_theme + "/"
	return base


func _fetch_texture(url: String, max_dim: int = 0) -> Texture2D:
	var http := HTTPRequest.new()
	add_child(http)
	if http.request(url) != OK:
		http.queue_free()
		return null
	var args = await http.request_completed
	http.queue_free()
	return _texture_from_response(args, max_dim)


func _texture_from_response(args: Array, max_dim: int = 0) -> Texture2D:
	var result: int = args[0]
	var response_code: int = args[1]
	var body: PackedByteArray = args[3]
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200 or body.is_empty():
		return null

	var image := Image.new()
	if image.load_png_from_buffer(body) != OK:
		return null
	if max_dim > 0:
		_downscale_image(image, max_dim)
	return ImageTexture.create_from_image(image)


func _downscale_image(image: Image, max_dim: int) -> void:
	var w := image.get_width()
	var h := image.get_height()
	var longest := maxi(w, h)
	if longest <= max_dim:
		return
	var scale := float(max_dim) / float(longest)
	image.resize(int(w * scale), int(h * scale), Image.INTERPOLATE_LANCZOS)
