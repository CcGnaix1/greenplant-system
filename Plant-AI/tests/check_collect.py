"""查看两条采集线的实时进度。"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

NEW = ["金钱树", "万年青", "龙血树", "红掌", "鹤望兰", "竹芋", "芦荟", "豆瓣绿", "波斯顿蕨", "散尾葵"]
WEAK = ["常春藤", "栀子花", "富贵竹", "袖珍椰子", "龟背竹", "多肉植物"]
WILD = Path("C:/Plant/plant-ai/data/plants")
INDOOR = Path("C:/Plant/plant-ai/data/plants_indoor")
EXTS = (".jpg", ".jpeg", ".png")


def cnt(base, c):
    d = base / c
    if not d.exists():
        return 0
    return len([f for f in d.iterdir() if f.suffix.lower() in EXTS])


print(f"{'类别':<10s} {'野外':>6s} {'室内':>6s}   目标")
print("-" * 40)
for c in NEW:
    print(f"{c:<10s} {cnt(WILD, c):6d} {cnt(INDOOR, c):6d}   野外200/室内200")
print("-" * 40)
for c in WEAK:
    print(f"{c:<10s} {'—':>6s} {cnt(INDOOR, c):6d}   室内400")

w = sum(cnt(WILD, c) for c in NEW)
i = sum(cnt(INDOOR, c) for c in NEW) + sum(cnt(INDOOR, c) for c in WEAK)
print("-" * 40)
print(f"新类野外 {w}/2000   新类+弱类室内 {i}/3200")

for name in ("collect_wild", "collect_indoor"):
    p = Path(f"C:/Plant/plant-ai/logs/{name}.log")
    if p.exists():
        t = p.read_text(encoding="utf-8", errors="replace")
        done = "DONE" in t
        print(f"\n{name}: {'已完成' if done else '进行中'}")
