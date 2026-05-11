shader_type canvas_item;

uniform vec2 center = vec2(0.5, 0.5);
uniform float force : hint_range(0.0, 0.1) = 0.0;
uniform float thickness : hint_range(0.0, 0.2) = 0.05;
uniform float progress : hint_range(0.0, 1.0) = 0.0;

void fragment() {
	vec2 uv = UV;
	float dist = distance(uv, center);
	float radius = progress * 0.8;
	float diff = abs(dist - radius);
	float wave = 1.0 - smoothstep(0.0, thickness, diff);
	wave *= (1.0 - progress);
	vec2 dir = normalize(uv - center);
	vec2 displaced_uv = uv + dir * wave * force;
	COLOR = texture(TEXTURE, displaced_uv);
	COLOR.rgb += vec3(wave * 0.4);
}
