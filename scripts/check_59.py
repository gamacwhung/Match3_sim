import json
data = json.load(open('關卡格式資料/Level_59.json', 'r', encoding='utf-8'))
sets = data.get('Sets', [])
for s in sets:
    name = s.get("Name")
    cr = s.get("CreateRatio")
    tf = s.get("TargetFills", [])[:10]
    elems = s.get("Elements", [])
    print(f"Name={name}, CreateRatio={cr}, TargetFills={tf}...")
    for e in elems:
        print(f"  Id={e.get('Id')}, CreateRatio={e.get('CreateRatio')}")
    print()

# check grid items
grid = data.get('Grid', {})
items = grid.get('Items', [])
w = grid.get('Width', 8)
print(f"Grid width={w}, total items={len(items)}")
# look for TrafficCone in grid (92=lv1, 93=lv2)
tc_positions = []
for idx, item in enumerate(items):
    if item in [92, 93, 31, 33]:
        col = idx % w
        row = idx // w
        tc_positions.append((col, row, item))
print(f"TrafficCone in grid: {len(tc_positions)}")
for p in tc_positions[:20]:
    print(f"  col={p[0]}, row={p[1]}, id={p[2]}")
