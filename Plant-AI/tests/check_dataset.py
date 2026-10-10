"""校验 30 类数据集完整性：两侧目录集合一致、无空类、计数。"""

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AI = Path("C:/Plant/plant-ai")
EXTS = (".jpg", ".jpeg", ".png", ".webp")
OLD20 = ["兰花", "发财树", "吊兰", "多肉植物", "富贵竹", "常春藤", "文竹", "栀子花",
         "橡皮树", "琴叶榕", "白掌", "绿萝", "茉莉花", "薄荷", "虎皮兰", "袖珍椰子",
         "迷迭香", "铜钱草", "鹅掌柴", "龟背竹"]

species = json.loads((AI / "ml" / "species.json").read_text(encoding="utf-8"))["classes"]


def scan(root):
    out = {}
    for sub in sorted(root.iterdir()):
        if sub.is_dir():
            out[sub.name] = len([f for f in sub.iterdir() if f.name.lower().endswith(EXTS)])
    return out


def main():
    wild = scan(AI / "data" / "plants")
    indoor = scan(AI / "data" / "plants_indoor")

    print(f"species.json 声明: {len(species)} 类")
    print(f"野外目录: {len(wild)} 类，{sum(wild.values())} 张")
    print(f"室内目录: {len(indoor)} 类，{sum(indoor.values())} 张")
    print()

    ok = True
    for name, d in (("野外", wild), ("室内", indoor)):
        missing = set(species) - set(d)
        extra = set(d) - set(species)
        if missing:
            print(f"[错误] {name} 缺少类别: {sorted(missing)}")
            ok = False
        if extra:
            print(f"[错误] {name} 多出类别: {sorted(extra)}")
            ok = False
        empty = [k for k, v in d.items() if v == 0]
        if empty:
            print(f"[错误] {name} 有空类别: {empty}")
            ok = False

    if wild.keys() == indoor.keys():
        print("两侧类别集合一致（标签顺序不会错位）")
    else:
        print("[错误] 两侧类别集合不一致")
        ok = False

    print(f"\n{'类别':<10s} {'野外':>6s} {'室内':>6s}   {'':<4s}")
    print("-" * 34)
    for c in sorted(species):
        tag = "" if c in OLD20 else "  ←新增"
        w, i = wild.get(c, 0), indoor.get(c, 0)
        warn = "  ⚠偏少" if min(w, i) < 100 else ""
        print(f"{c:<10s} {w:6d} {i:6d}{tag}{warn}")

    print("-" * 34)
    print(f"{'合计':<10s} {sum(wild.values()):6d} {sum(indoor.values()):6d}")
    print()
    print("校验通过，可以开始训练" if ok else "存在错误，训练前必须修复")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
