extends Node

var sfx_players: Array[AudioStreamPlayer] = []
var music_player: AudioStreamPlayer
var sample_rate: float = 44100.0
var master_volume: float = 0.8
var sfx_volume: float = 0.7
var music_volume: float = 0.4

var _bgm_stream: AudioStream = null
const _BGM_PATH = "res://resources/audio/SugarcubePuzzles.mp3"

func _ready() -> void:
	# BGM 是 optional — 如果檔案不存在(godot_demo 沒帶 audio 資產),
	# fallback 到程式合成的 _generate_bgm_loop()
	if ResourceLoader.exists(_BGM_PATH):
		_bgm_stream = load(_BGM_PATH)
	for i in 8:
		var player = AudioStreamPlayer.new()
		player.bus = "Master"
		add_child(player)
		sfx_players.append(player)
	music_player = AudioStreamPlayer.new()
	music_player.bus = "Master"
	add_child(music_player)

func _get_free_player() -> AudioStreamPlayer:
	for player in sfx_players:
		if not player.playing:
			return player
	return sfx_players[0]

func play_match_sound(combo: int = 0) -> void:
	var base_freq = 523.25
	var freq = base_freq * pow(1.12, combo)
	freq = min(freq, 1800.0)
	var stream = _generate_tone(freq, 0.15, 0.6)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_swap_sound() -> void:
	var stream = _generate_sweep(400.0, 600.0, 0.1)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_swap_back_sound() -> void:
	var stream = _generate_sweep(500.0, 300.0, 0.12)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_special_create_sound() -> void:
	var stream = _generate_chord([523.25, 659.25, 783.99], 0.3)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_special_trigger_sound() -> void:
	var stream = _generate_explosion_sound(0.4)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_cascade_sound(cascade_level: int) -> void:
	var freq = 440.0 * pow(1.2, cascade_level)
	var stream = _generate_tone(freq, 0.2, 0.5)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_level_complete_sound() -> void:
	var stream = _generate_fanfare()
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_level_failed_sound() -> void:
	var stream = _generate_sweep(400.0, 150.0, 0.5)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_button_sound() -> void:
	var stream = _generate_tone(880.0, 0.08, 0.3)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func play_obstacle_break_sound() -> void:
	var stream = _generate_noise_burst(0.15)
	var player = _get_free_player()
	player.stream = stream
	player.volume_db = linear_to_db(sfx_volume * master_volume)
	player.play()

func start_bgm() -> void:
	if music_player.playing:
		return
	var stream: AudioStream = _bgm_stream if _bgm_stream != null else _generate_bgm_loop()
	music_player.stream = stream
	music_player.volume_db = linear_to_db(music_volume * master_volume)
	music_player.autoplay = false
	music_player.play()
	if not music_player.finished.is_connected(_on_bgm_finished):
		music_player.finished.connect(_on_bgm_finished, CONNECT_DEFERRED)

func stop_bgm() -> void:
	if music_player.finished.is_connected(_on_bgm_finished):
		music_player.finished.disconnect(_on_bgm_finished)
	music_player.stop()

func _on_bgm_finished() -> void:
	if music_player.stream != null:
		music_player.play()

func _generate_tone(freq: float, duration: float, volume: float = 1.0) -> AudioStreamWAV:
	var samples = int(sample_rate * duration)
	var data = PackedByteArray()
	data.resize(samples * 2)
	for i in samples:
		var t = float(i) / sample_rate
		var envelope = 1.0 - (float(i) / samples)
		envelope = envelope * envelope
		var sample_val = sin(TAU * freq * t) * volume * envelope
		sample_val += sin(TAU * freq * 2.0 * t) * volume * envelope * 0.3
		var int_val = int(clamp(sample_val, -1.0, 1.0) * 32767)
		data[i * 2] = int_val & 0xFF
		data[i * 2 + 1] = (int_val >> 8) & 0xFF
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = int(sample_rate)
	stream.data = data
	return stream

func _generate_sweep(freq_start: float, freq_end: float, duration: float) -> AudioStreamWAV:
	var samples = int(sample_rate * duration)
	var data = PackedByteArray()
	data.resize(samples * 2)
	for i in samples:
		var t = float(i) / sample_rate
		var progress = float(i) / samples
		var freq = lerp(freq_start, freq_end, progress)
		var envelope = 1.0 - progress
		var sample_val = sin(TAU * freq * t) * envelope * 0.6
		var int_val = int(clamp(sample_val, -1.0, 1.0) * 32767)
		data[i * 2] = int_val & 0xFF
		data[i * 2 + 1] = (int_val >> 8) & 0xFF
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = int(sample_rate)
	stream.data = data
	return stream

func _generate_chord(freqs: Array, duration: float) -> AudioStreamWAV:
	var samples = int(sample_rate * duration)
	var data = PackedByteArray()
	data.resize(samples * 2)
	for i in samples:
		var t = float(i) / sample_rate
		var envelope = 1.0 - (float(i) / samples)
		var sample_val = 0.0
		for freq in freqs:
			sample_val += sin(TAU * freq * t) * envelope
		sample_val /= freqs.size()
		sample_val *= 0.7
		var int_val = int(clamp(sample_val, -1.0, 1.0) * 32767)
		data[i * 2] = int_val & 0xFF
		data[i * 2 + 1] = (int_val >> 8) & 0xFF
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = int(sample_rate)
	stream.data = data
	return stream

func _generate_explosion_sound(duration: float) -> AudioStreamWAV:
	var samples = int(sample_rate * duration)
	var data = PackedByteArray()
	data.resize(samples * 2)
	for i in samples:
		var t = float(i) / sample_rate
		var progress = float(i) / samples
		var envelope = (1.0 - progress) * (1.0 - progress)
		var noise = randf_range(-1.0, 1.0)
		var tone = sin(TAU * 120.0 * t * (1.0 - progress * 0.5))
		var sample_val = (noise * 0.4 + tone * 0.6) * envelope * 0.7
		var int_val = int(clamp(sample_val, -1.0, 1.0) * 32767)
		data[i * 2] = int_val & 0xFF
		data[i * 2 + 1] = (int_val >> 8) & 0xFF
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = int(sample_rate)
	stream.data = data
	return stream

func _generate_noise_burst(duration: float) -> AudioStreamWAV:
	var samples = int(sample_rate * duration)
	var data = PackedByteArray()
	data.resize(samples * 2)
	for i in samples:
		var progress = float(i) / samples
		var envelope = (1.0 - progress)
		var sample_val = randf_range(-1.0, 1.0) * envelope * 0.5
		var int_val = int(clamp(sample_val, -1.0, 1.0) * 32767)
		data[i * 2] = int_val & 0xFF
		data[i * 2 + 1] = (int_val >> 8) & 0xFF
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = int(sample_rate)
	stream.data = data
	return stream

func _generate_fanfare() -> AudioStreamWAV:
	var notes = [523.25, 659.25, 783.99, 1046.5]
	var note_duration = 0.2
	var total_duration = notes.size() * note_duration
	var samples = int(sample_rate * total_duration)
	var data = PackedByteArray()
	data.resize(samples * 2)
	for i in samples:
		var t = float(i) / sample_rate
		var note_idx = int(t / note_duration)
		note_idx = min(note_idx, notes.size() - 1)
		var note_t = fmod(t, note_duration)
		var envelope = 1.0 - (note_t / note_duration) * 0.5
		var freq = notes[note_idx]
		var sample_val = sin(TAU * freq * t) * envelope * 0.5
		sample_val += sin(TAU * freq * 2.0 * t) * envelope * 0.2
		var int_val = int(clamp(sample_val, -1.0, 1.0) * 32767)
		data[i * 2] = int_val & 0xFF
		data[i * 2 + 1] = (int_val >> 8) & 0xFF
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = int(sample_rate)
	stream.data = data
	return stream

func _generate_bgm_loop() -> AudioStreamWAV:
	# Extended version of original style: same tone, more melody variety
	# A-B-A-C structure, each section 16 notes at 0.25s = 4s, total ~16s
	var section_a = [
		523.25, 587.33, 659.25, 523.25,
		659.25, 698.46, 783.99, 0,
		783.99, 698.46, 659.25, 587.33,
		523.25, 587.33, 523.25, 0
	]
	var section_b = [
		440.00, 523.25, 587.33, 659.25,
		587.33, 523.25, 440.00, 0,
		392.00, 440.00, 523.25, 587.33,
		523.25, 440.00, 392.00, 0
	]
	var section_c = [
		659.25, 698.46, 783.99, 659.25,
		587.33, 523.25, 587.33, 0,
		440.00, 523.25, 659.25, 587.33,
		523.25, 440.00, 523.25, 0
	]

	var melody_notes: Array = []
	for n in section_a:
		melody_notes.append(n)
	for n in section_b:
		melody_notes.append(n)
	for n in section_a:
		melody_notes.append(n)
	for n in section_c:
		melody_notes.append(n)

	var note_duration = 0.25
	var total_duration = melody_notes.size() * note_duration
	var samples = int(sample_rate * total_duration)
	var data = PackedByteArray()
	data.resize(samples * 2)
	for i in samples:
		var t = float(i) / sample_rate
		var note_idx = int(t / note_duration) % melody_notes.size()
		var freq = melody_notes[note_idx]
		if freq == 0:
			data[i * 2] = 0
			data[i * 2 + 1] = 0
			continue
		var note_t = fmod(t, note_duration)
		var attack = min(note_t / 0.02, 1.0)
		var release_start = note_duration - 0.05
		var release = 1.0 if note_t < release_start else (note_duration - note_t) / 0.05
		var envelope = attack * release
		var sample_val = sin(TAU * freq * t) * envelope * 0.25
		sample_val += sin(TAU * freq * 0.5 * t) * envelope * 0.1
		var int_val = int(clamp(sample_val, -1.0, 1.0) * 32767)
		data[i * 2] = int_val & 0xFF
		data[i * 2 + 1] = (int_val >> 8) & 0xFF
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = int(sample_rate)
	stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
	stream.loop_end = samples
	stream.data = data
	return stream
