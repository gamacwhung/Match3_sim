"""比對官方關卡 Goals.Count 與盤面障礙物數量 / HP；列出會落下或生成的關卡。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OFF = Path(__file__).resolve().parents[1] / "關卡格式資料"

GOAL_ID_TO_FAMILY = {
    12: "Crt",
    13: "Puddle",
    14: "WaterChiller",
    15: "Stamp",
    16: "Barrel",
    17: "BeverageChiller",
    19: "SalmonCan",
    20: "Pool",
    21: "Mud",
    26: "TrafficCone",
}


def _corner_kind(item_id: int) -> str | None:
    if 27 <= item_id <= 30:
        return "water"
    if 33 <= item_id <= 56:
        return "bev"
    if 61 <= item_id <= 64:
        return "pool"
    return None


def count_board(official: dict) -> Counter:
    grid = official["Grid"]
    w, h = grid["Width"], grid["Height"]
    items = grid["Items"]
    inst: Counter = Counter()
    seen: set[int] = set()
    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if idx in seen:
                continue
            i = items[idx]
            if i in (0, 12, 13, 15, 16, 17, 18):
                continue
            if 21 <= i <= 24:
                inst["Crt"] += 1
            elif i == 31:
                inst["Stamp"] += 1
            elif i == 32:
                inst["Barrel"] += 1
            elif i == 58:
                inst["SalmonCan"] += 1
            elif i in (25, 26):
                inst["Puddle"] += 1
            elif i == 65:
                inst["Mud"] += 1
            elif i in (92, 93):
                inst["TrafficCone"] += 1
            elif i in (156, 157):
                inst["Rope"] += 1
            elif ck := _corner_kind(i):
                for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    seen.add((y + dy) * w + (x + dx))
                if ck == "water":
                    inst["WaterChiller"] += 11
                elif ck == "bev":
                    inst["BeverageChiller"] += 5
                elif ck == "pool":
                    inst["Pool"] += 1
    return inst


def has_obstacle_spawn(official: dict) -> bool:
    for s in official.get("Sets", []):
        for e in s.get("Elements", []):
            if e.get("Id", 0) >= 21:
                return True
    return bool(official.get("Counts"))


def has_fill_spawner(official: dict) -> bool:
    return any(c.get("FillType", 0) == 1 for c in official["Grid"].get("Cells", []))


def main() -> None:
    mismatch_static: list[tuple] = []
    spawn_levels: list[tuple] = []

    print("=== Goal vs 盤面（官方 JSON）===\n")
    print(f"{'Lv':>4} {'Goal':>6} {'family':>16} {'goal':>8} {'board':>8} {'語意':>12} spawn")
    print("-" * 72)

    for p in sorted(OFF.glob("Level_*.json"), key=lambda x: int(x.stem.split("_")[1])):
        d = json.loads(p.read_text(encoding="utf-8"))
        n = d["Number"]
        bc = count_board(d)
        spawn = has_obstacle_spawn(d) or has_fill_spawner(d)
        if spawn:
            kinds = []
            if has_obstacle_spawn(d):
                kinds.append("障礙生成")
            if has_fill_spawner(d):
                kinds.append("FillType1")
            spawn_levels.append((n, ", ".join(kinds)))

        for g in d.get("Goals", []):
            gid = g["Goal"]
            cnt = g["Count"]
            fam = GOAL_ID_TO_FAMILY.get(gid, "?")
            if fam == "WaterChiller":
                b = bc.get("WaterChiller", 0)
                kind = "HP 總和"
            elif fam == "BeverageChiller":
                b = bc.get("BeverageChiller", 0)
                kind = "HP 總和"
            elif fam == "Stamp":
                b = bc.get("Stamp", 0)
                kind = "蓋章次數"
            else:
                b = bc.get(fam, 0)
                kind = "instance 數"

            if fam == "Stamp" or spawn:
                tag = "（動態）"
            elif cnt == b:
                tag = ""
            else:
                tag = " MISMATCH"
                mismatch_static.append((n, fam, cnt, b, kind))

            if tag or fam == "Stamp":
                print(
                    f"{n:4d} {gid:6d} {fam:>16} {cnt:8d} {b:8d} {kind:>12}"
                    f" {'Y' if spawn else '':>5}{tag}"
                )

    print("\n=== 有生成/落下機制的關卡 ===\n")
    for n, kinds in spawn_levels:
        print(f"  L{n:3d}: {kinds}")
    print(f"\n共 {len(spawn_levels)} 關")

    print(f"\n=== 靜態關卡 goal ≠ 盤面 ({len(mismatch_static)} 筆) ===\n")
    for row in mismatch_static:
        print(f"  L{row[0]:3d} {row[1]:16s} goal={row[2]} board={row[3]} ({row[4]})")


if __name__ == "__main__":
    main()
