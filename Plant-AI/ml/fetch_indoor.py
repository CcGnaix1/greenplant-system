"""采集「栽培/室内」绿植照，补足训练数据与真实使用场景的域差距。

为什么需要这个脚本
------------------
现有 2708 张训练图全部来自 iNaturalist 的**野外**观察照（见 fetch_inat.py），
而用户实际拍的是室内盆栽。实测同一株绿萝：
    野外照 -> 绿萝 0.83~0.89（对）
    室内照 -> 栀子花 0.46（错）
所以「置信度低、识别错」的根因是**数据域不匹配**，不是训练轮数不够。
（对照：训练集已过拟合，最后一轮 train_acc 0.9986 vs val_acc 0.9059）

为什么不复用 fetch_inat.py
--------------------------
它走 GBIF，而 GBIF 收录的是 iNat 的 research-grade 子集；
被标记 captive/cultivated 的观察是 casual 等级，**根本不会被发布**，
所以走 GBIF 取栽培照实测 captive 占比恒为 0（抽样 5400 条验证过）。
必须改走 iNat 官方 observations API，它支持 captive=true 筛选，
且经实测本机访问很快（1~2 秒/次），当初绕开它的限速理由已不成立。

用法:
    python fetch_indoor.py                      # 每类 200 张
    python fetch_indoor.py --per-class 100
    python fetch_indoor.py --only 绿萝 虎皮兰     # 只补指定类别

输出:
    data/plants_indoor/<品种>/<照片id>.jpg
    data/plants_indoor/manifest.jsonl           # 每张图的许可与署名（合规留痕）
"""

import argparse
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "plants_indoor"

API = "https://api.inaturalist.org/v1/observations"
S3 = "https://inaturalist-open-data.s3.amazonaws.com/photos"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"
# 只用可商用的宽松许可里头最宽的三档；NC 也收，本实训为教学非商业用途
LICENSES = "cc0,cc-by,cc-by-nc"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 与 fetch_inat.py 的 SPECIES 保持一致，否则类别与模型输出对不上
SPECIES = {
    "龟背竹":   ["Monstera deliciosa"],
    "绿萝":     ["Epipremnum aureum"],
    "虎皮兰":   ["Dracaena trifasciata"],
    "多肉植物": ["Echeveria elegans", "Crassula ovata", "Haworthia fasciata", "Kalanchoe blossfeldiana"],
    "发财树":   ["Pachira aquatica"],
    "兰花":     ["Phalaenopsis aphrodite", "Cymbidium goeringii", "Dendrobium nobile"],
    "吊兰":     ["Chlorophytum comosum"],
    "琴叶榕":   ["Ficus lyrata"],
    "橡皮树":   ["Ficus elastica"],
    "常春藤":   ["Hedera helix"],
    "白掌":     ["Spathiphyllum wallisii"],
    "文竹":     ["Asparagus setaceus"],
    "富贵竹":   ["Dracaena sanderiana"],
    "铜钱草":   ["Hydrocotyle verticillata"],
    "薄荷":     ["Mentha spicata"],
    "迷迭香":   ["Salvia rosmarinus"],
    "栀子花":   ["Gardenia jasminoides"],
    "茉莉花":   ["Jasminum sambac"],
    "袖珍椰子": ["Chamaedorea elegans"],
    "鹅掌柴":   ["Heptapleurum arboricola"],
}


def get_json(url: str, retries: int = 3) -> dict:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                print(f"    放弃: {e}")
                return {}
            time.sleep(4)
    return {}


def collect_photos(taxon: str, want: int, max_pages: int = 6) -> list[dict]:
    """取该物种 captive 观察里的照片。

    用 id_below 翻页而不是 page：iNat 在翻页期间若有新观察插入，
    page 分页会重复或漏掉记录，id_below 以 id 为游标则稳定。
    """
    photos: dict[int, dict] = {}
    id_below = None
    for _ in range(max_pages):
        params = {
            "taxon_name": taxon,
            "captive": "true",          # 关键：只要栽培/圈养，这才是贴近室内的那一域
            "photos": "true",
            "photo_license": LICENSES,
            "per_page": 200,
            "order_by": "id",
            "order": "desc",
        }
        if id_below:
            params["id_below"] = id_below
        d = get_json(f"{API}?{urllib.parse.urlencode(params)}")
        results = d.get("results", [])
        if not results:
            break
        for obs in results:
            for p in obs.get("photos") or []:
                pid = p.get("id")
                if isinstance(pid, int) and pid not in photos:
                    photos[pid] = {
                        "id": pid,
                        "license": p.get("license_code"),
                        "attribution": p.get("attribution"),
                        "observation": obs.get("uri"),
                        "taxon": taxon,
                    }
        id_below = results[-1].get("id")
        if len(photos) >= want or not id_below:
            break
        time.sleep(0.5)   # 对公共 API 客气一点
    return list(photos.values())[:want]


def fetch_image(pid: int, dest: Path, size: str = "medium") -> int:
    """下载单张；medium 失败依次回退 small/original。返回字节数，0 表示失败。"""
    for sz in (size, "small", "original"):
        try:
            req = urllib.request.Request(f"{S3}/{pid}/{sz}.jpg", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
                data = r.read()
            if len(data) < 3000:      # 过小的多半是占位图或损坏
                continue
            dest.write_bytes(data)
            return len(data)
        except Exception:  # noqa: BLE001
            continue
    dest.unlink(missing_ok=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description="采集 captive(栽培/室内) 绿植照")
    ap.add_argument("--per-class", type=int, default=200, help="每类目标张数")
    ap.add_argument("--workers", type=int, default=24, help="并发下载线程数")
    ap.add_argument("--size", type=str, default="medium")
    ap.add_argument("--only", nargs="*", default=None, help="只采指定类别")
    args = ap.parse_args()

    targets = {k: v for k, v in SPECIES.items() if not args.only or k in args.only}
    if not targets:
        raise SystemExit(f"--only 里的类别都不在清单中: {args.only}")

    print(f"目标: {len(targets)} 类 x {args.per_class} 张 (captive 栽培照), 并发={args.workers}")
    print(f"输出: {DATA_DIR}\n")

    manifest_path = DATA_DIR / "manifest.jsonl"
    manifest_lines: list[str] = []
    summary: dict[str, int] = {}
    total_new = 0

    for label, taxa in targets.items():
        out_dir = DATA_DIR / label
        out_dir.mkdir(parents=True, exist_ok=True)
        have = len([f for f in out_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")])
        need = max(0, args.per_class - have)
        print(f"[{label}] 已有 {have}，目标 {args.per_class}，还需 {need}（{len(taxa)} 个物种）")

        if need:
            cands: list[dict] = []
            per_taxon = max(1, need // len(taxa) + 1)
            for taxon in taxa:
                got = collect_photos(taxon, per_taxon)
                cands.extend(got)
                print(f"    候选 {taxon:26s} {len(got)} 张")
            # 跨物种去重（多肉/兰花是多个代表种凑一类）
            seen: set[int] = set()
            jobs: list[tuple[dict, Path]] = []
            for c in cands:
                pid = c["id"]
                if pid in seen:
                    continue
                seen.add(pid)
                dest = out_dir / f"{pid}.jpg"
                if dest.exists():
                    continue
                if have + len(jobs) >= args.per_class:
                    break
                jobs.append((c, dest))

            got_n = 0
            if jobs:
                print(f"    下载 {len(jobs)} 张 ...")
                done = 0
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futs = {pool.submit(fetch_image, c["id"], dest, args.size): (c, dest)
                            for c, dest in jobs}
                    for fut in as_completed(futs):
                        c, dest = futs[fut]
                        done += 1
                        if fut.result():
                            got_n += 1
                            manifest_lines.append(json.dumps({
                                "file": f"{label}/{dest.name}",
                                "label": label,
                                "photo_id": c["id"],
                                "license": c["license"],
                                "attribution": c["attribution"],
                                "observation": c["observation"],
                                "source": "iNaturalist (captive/cultivated)",
                            }, ensure_ascii=False))
                        if done % 100 == 0:
                            print(f"      进度 {done}/{len(jobs)}，成功 {got_n}")
            total_new += got_n

        final = len([f for f in out_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")])
        summary[label] = final
        print(f"[{label}] 完成，共 {final} 张\n")

    if manifest_lines:
        with open(manifest_path, "a", encoding="utf-8") as f:
            f.write("\n".join(manifest_lines) + "\n")

    print("=" * 52)
    for k, v in summary.items():
        print(f"  {k:10s} {v} 张")
    print(f"  {'本次新增':10s} {total_new} 张")
    print(f"  {'合计':10s} {sum(summary.values())} 张")
    print(f"\n许可/署名清单: {manifest_path}")


if __name__ == "__main__":
    main()
