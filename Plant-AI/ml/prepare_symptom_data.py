"""把 PlantVillage 的 38 个『作物+病害』标签重映射成少数几个『症状大类』，生成索引。

为什么要重映射
--------------
公开病害数据集全按「作物+病害」标注（Apple___Apple_scab、Tomato___Late_blight…），
覆盖的是 14 种粮食作物，与本项目要服务的 30 种观叶绿植零重叠。直接训这种模型，
用户拍绿萝只会得到「番茄晚疫病」这种无意义输出。

但**症状的外观是跨物种通用的**：叶斑在绿萝上是叶斑，在龟背竹上也是叶斑。
所以把 38 个作物病害标签按「表现出的症状」归并成 6 类，模型学到的就是可迁移的
症状特征，再配上已有的 symptom_dict 文案，就能给任意品种出建议。

为什么用索引 CSV 而不是复制成 ImageFolder 目录
--------------------------------------------
45k 张图复制一份要多占 ~2GB，且复制后两边容易不同步。
索引只记录 (路径, 症状, split)，训练时按索引读原图，零冗余。

为什么用官方 split 而不是自己随机切
----------------------------------
PlantVillage 同一片叶子常有多张照片，随机切会让同一叶片同时进训练与验证，
指标虚高。这里用数据集自带的 splits/color_{train,test}.txt（Mohanty 论文那套）。
脚本仍会打印「同名文件同时出现在两侧」的数量，便于判断泄漏程度。
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
TAXONOMY = ML_DIR / "symptom_taxonomy.json"
DEFAULT_RAW = ROOT / "data" / "raw" / "plantvillage"
OUT_CSV = ROOT / "data" / "symptoms_index.csv"
OUT_STATS = ROOT / "data" / "symptoms_stats.json"

# raw/<variant>/<PV 类别>/<文件名>，variant ∈ color|grayscale|segmented
LINE_RE = re.compile(r"^raw/([^/]+)/([^/]+)/(.+\.(?:JPG|jpg|jpeg|png))$")


def load_taxonomy(path: Path) -> dict:
    tax = json.loads(path.read_text(encoding="utf-8"))
    if set(tax["symptoms"]) != set(tax["labels"]):
        raise SystemExit("[错误] symptoms 与 labels 的键不一致")
    missing = set(tax["mapping"]) - set(tax["mapping"])
    if missing:
        raise SystemExit(f"[错误] {missing}")
    bad = {pv: s for pv, s in tax["mapping"].items() if s not in tax["symptoms"]}
    if bad:
        raise SystemExit(f"[错误] 映射到了未声明的症状类: {bad}")
    if tax.get("_pv_class_count") != len(tax["mapping"]):
        raise SystemExit(
            f"[错误] taxonomy 声明 {tax.get('_pv_class_count')} 个 PV 类，"
            f"实际 mapping 有 {len(tax['mapping'])} 个"
        )
    return tax


def read_split(split_file: Path, variant: str) -> list[tuple[Path, str]]:
    """返回 [(相对路径, PV 类别)]，只保留指定 variant。"""
    out, skipped = [], 0
    for line in split_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            skipped += 1
            continue
        v, pv, _ = m.groups()
        if v != variant:
            continue
        out.append((Path(line), pv))
    if skipped:
        print(f"    [警告] {split_file.name} 有 {skipped} 行格式不匹配，已跳过")
    return out


def main():
    ap = argparse.ArgumentParser(description="PlantVillage → 症状大类索引")
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW), help="解压后的 PlantVillage 根目录")
    ap.add_argument("--variant", default="color", choices=["color", "segmented", "grayscale"],
                    help="用哪种图片（默认 color，即原图）")
    ap.add_argument("--taxonomy", default=str(TAXONOMY))
    ap.add_argument("--out", default=str(OUT_CSV))
    args = ap.parse_args()

    raw = Path(args.raw_dir)
    tax = load_taxonomy(Path(args.taxonomy))
    mapping, symptoms = tax["mapping"], tax["symptoms"]

    print("=" * 78)
    print("PlantVillage → 症状大类")
    print("=" * 78)
    print(f"原始目录: {raw}")
    print(f"变体    : {args.variant}")
    print(f"症状类  : {len(symptoms)} 类 {symptoms}\n")

    # ---------- 1. 磁盘上的 PV 类是否都被映射 ----------
    color_root = raw / "raw" / args.variant
    if not color_root.is_dir():
        # 兼容解压后直接是 color/ 的情况
        alt = raw / args.variant
        if alt.is_dir():
            color_root = alt
        else:
            raise SystemExit(f"[错误] 找不到图片目录: {color_root}（也不存在 {alt}）")

    on_disk = sorted(d.name for d in color_root.iterdir() if d.is_dir())
    unmapped = [d for d in on_disk if d not in mapping]
    if unmapped:
        print(f"[错误] 磁盘上有 {len(unmapped)} 个目录未在 taxonomy.mapping 中:")
        for d in unmapped:
            print(f"    {d}")
        raise SystemExit(1)
    not_on_disk = [k for k in mapping if k not in on_disk]
    if not_on_disk:
        print(f"[警告] taxonomy 里有 {len(not_on_disk)} 个类磁盘上不存在: {not_on_disk}")
    print(f"磁盘 PV 类: {len(on_disk)} 个，全部已被映射 ✅")

    # ---------- 2. 官方 split ----------
    rows, per_split = [], defaultdict(Counter)
    missing_files = 0
    seen_name = defaultdict(set)
    for split in ("train", "test"):
        sf = raw / "splits" / f"{args.variant}_{split}.txt"
        if not sf.is_file():
            raise SystemExit(f"[错误] 缺少 split 文件: {sf}")
        entries = read_split(sf, args.variant)
        for rel, pv in entries:
            sym = mapping[pv]
            full = (raw / rel) if (raw / rel).is_file() else (color_root / pv / rel.name)
            if not full.is_file():
                missing_files += 1
                continue
            key = f"{pv}/{rel.name}"
            seen_name[key].add(split)
            rows.append((str(full.resolve()), sym, split))
            per_split[split][sym] += 1
        print(f"{split:5s}: {len(entries)} 行 → 落地 {sum(per_split[split].values())} 张")

    if missing_files:
        print(f"[警告] {missing_files} 条 split 记录在磁盘上找不到文件（已跳过）")

    # 同名文件同时出现在 train 与 test → 潜在泄漏
    leaked = sum(1 for v in seen_name.values() if len(v) > 1)
    if leaked:
        print(f"[警告] {leaked} 个同名文件同时出现在 train/test（同叶多照，指标可能偏高）")

    # ---------- 3. 写索引 ----------
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("path,symptom,split\n")
        for p, s, sp in rows:
            # 路径含逗号时用引号包住（Windows 用户名/目录名可能出现）
            f.write(f'"{p}",{s},{sp}\n')

    # ---------- 4. 汇总 ----------
    all_counts = Counter(s for _, s, _ in rows)
    print("\n" + "-" * 78)
    print(f"{'症状类':16s} {'train':>8s} {'test':>8s} {'合计':>8s}  占均比")
    print("-" * 78)
    total = len(rows)
    for s in sorted(symptoms, key=lambda x: -all_counts.get(x, 0)):
        tr, te = per_split["train"].get(s, 0), per_split["test"].get(s, 0)
        if tr + te == 0:
            print(f"{s:16s} {'0':>8s} {'0':>8s} {'0':>8s}  ⚠ 空类")
            continue
        ratio = (tr + te) / total
        print(f"{s:16s} {tr:>8d} {te:>8d} {tr + te:>8d}  {ratio:6.1%}")
    print("-" * 78)
    print(f"{'合计':16s} {sum(per_split['train'].values()):>8d} "
          f"{sum(per_split['test'].values()):>8d} {total:>8d}")

    empty = [s for s in symptoms if all_counts.get(s, 0) == 0]
    if empty:
        raise SystemExit(f"\n[错误] 有空症状类，无法训练: {empty}")
    imax, imin = max(all_counts.values()), min(all_counts.values())
    print(f"\n不均衡比: 最大/最小 = {imax}/{imin} = {imax / imin:.1f} : 1"
          f"{'（需类权重）' if imax / imin > 3 else ''}")

    Path(OUT_STATS if args.out == str(OUT_CSV) else str(Path(args.out).with_suffix(".stats.json"))).write_text(
        json.dumps({
            "variant": args.variant,
            "symptoms": symptoms,
            "labels": tax["labels"],
            "dict_code": tax["dict_code"],
            "counts": {s: {"train": per_split["train"].get(s, 0),
                           "test": per_split["test"].get(s, 0)} for s in symptoms},
            "total": total,
            "same_name_both_splits": leaked,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n索引已写出: {out}")
    print(f"统计已写出: {OUT_STATS}")


if __name__ == "__main__":
    main()
