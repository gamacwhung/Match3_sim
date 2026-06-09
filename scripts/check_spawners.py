"""檢查所有官方關卡中的障礙物生成器 Sets"""
import json, os

TILE_NAMES = {
    21: "Cardboard", 22: "Cardboard_lv2", 23: "Stamp", 24: "Stamp_lv2",
    25: "Stamp_lv3", 26: "Mud", 27: "Mud_lv2", 28: "IceCube",
    29: "IceCube_lv2", 30: "IceCube_lv3", 31: "TrafficCone", 32: "Barrel",
    33: "TrafficCone_lv2", 34: "Puddle", 35: "Puddle_lv2", 36: "Puddle_lv3",
    37: "BeverageChiller", 38: "WaterChiller", 39: "SalmonCan",
    40: "SalmonCan_lv2", 41: "Pool", 42: "Rope",
}

src_dir = '關卡格式資料'
results = []

for i in range(1, 101):
    path = os.path.join(src_dir, f'Level_{i}.json')
    if not os.path.exists(path):
        continue
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    sets = data.get('Sets', [])
    for s in sets:
        elements = s.get('Elements', [])
        has_obstacle = any(e.get('Id', 0) >= 21 for e in elements)
        if not has_obstacle:
            continue

        target_fills = s.get('TargetFills', [])
        # 找同 TargetFills 的普通糖果 Set
        candy_ratio = 0
        for other_s in sets:
            if other_s is s:
                continue
            if other_s.get('TargetFills', []) == target_fills:
                other_elems = other_s.get('Elements', [])
                if not any(e.get('Id', 0) >= 21 for e in other_elems):
                    candy_ratio = other_s.get('CreateRatio', 1)

        obs_elems = [(e['Id'], TILE_NAMES.get(e['Id'], f"?{e['Id']}"), e.get('CreateRatio', 1))
                     for e in elements if e.get('Id', 0) >= 21]

        total_weight = s.get('CreateRatio', 1) + candy_ratio
        prob = s.get('CreateRatio', 1) / total_weight * 100 if total_weight > 0 else 0

        results.append({
            'level': i,
            'set_name': s.get('Name', ''),
            'obs_elems': obs_elems,
            'create_ratio': s.get('CreateRatio', 1),
            'candy_ratio': candy_ratio,
            'total_weight': total_weight,
            'prob': prob,
            'num_cols': len(set(idx % 10 for idx in target_fills[:20])),
            'max_item': s.get('MaxItemCounts', []),
        })

print(f"共找到 {len(results)} 個障礙物生成器，分布在以下關卡：\n")
print(f"{'Level':<7}{'Set':<6}{'障礙物':<30}{'自身ratio':<10}{'糖果ratio':<10}{'生成機率':<10}{'MaxItem'}")
print("-" * 95)
for r in results:
    obs_str = ", ".join(f"{name}(x{cr})" for _, name, cr in r['obs_elems'])
    max_str = str(r['max_item']) if r['max_item'] else "-"
    print(f"{r['level']:<7}{r['set_name']:<6}{obs_str:<30}{r['create_ratio']:<10}{r['candy_ratio']:<10}{r['prob']:.0f}%{'':<7}{max_str}")
