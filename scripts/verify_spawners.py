"""驗證模擬器 JSON 的 spawner 是否完整"""
import json

levels_with_spawners = [37, 38, 39, 40, 46, 58, 60, 66, 80, 93, 95]
for lv in levels_with_spawners:
    path = f'godot_demo/levels/Level_{lv:03d}.json'
    try:
        data = json.load(open(path, 'r', encoding='utf-8'))
        spawners = data.get('spawners', [])
        if spawners:
            for s in spawners:
                elems = s.get('elements', [])
                names = [e['tile_id'] for e in elems]
                print(f"Level {lv:3d}: cols={s.get('spawn_cols')}, tiles={names}, "
                      f"ratio={s.get('set_ratio')}, total_weight={s.get('total_weight', 'MISSING')}")
        else:
            print(f"Level {lv:3d}: NO SPAWNERS in simulator JSON!")
    except Exception as e:
        print(f"Level {lv:3d}: ERROR - {e}")
