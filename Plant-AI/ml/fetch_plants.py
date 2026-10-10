"""通用绿植图采集器：既能采「室内(栽培)」也能采「野外」照，类别读 species.json。

与两位前辈的关系
----------------
- `fetch_inat.py` 是第一代：走 GBIF 取 iNat 的图，只能拿到**野外**照
  （GBIF 收的是 research-grade 子集，栽培观察是 casual 级，不会被发布）。
- `fetch_indoor.py` 是第二代：走 iNat 官方 API 的 `captive=true`，专采室内照。
- 本脚本是第三代：把两者合并，`--domain` 切换，类别清单从 `species.json` 读，
  避免类别散落在多个脚本里各写一份而漂移。

用法:
    # 采室内(栽培)照（默认），写入 data/plants_indoor/
    python fetch_plants.py --per-class 400 --only 金钱树 万年青

    # 采野外照，写入 data/plants/
    python fetch_plants.py --domain wild --per-class 200 --only 金钱树

    # 弱类加量（已存在的照片 id 会自动跳过，可反复续跑）
    python fetch_plants.py --per-class 400 --only 常春藤 栀子花 富贵竹

去重（重要）
------------
按 iNat 的 photo id 去重，而不是按文件名。第一代脚本的文件名是
`<学名>_<photoId>.jpg`，本脚本写的是 `<photoId>.jpg` —— 只比文件名会让
同一张照片以两个名字各存一份，进而可能一份进训练集、一份进验证集，
**验证准确率会虚高**。所以这里从所有既有文件名里提取尾部数字做黑名单。
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECIES_FILE = Path(__file__).resolve().parent / "species.json"
API = "https://api.inaturalist.org/v1/observations"
S3 = "https://inaturalist-open-data.s3.amazonaws.com/photos"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"
LICENSES = "cc0,cc-by,cc-by-nc"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

OUT_DIRS = {"indoor": ROOT / "data" / "plants_indoor", "wild": ROOT / "data" / "plants"}
EXTS = (".jpg", ".jpeg", ".png", ".webp")
TRAILING_ID = re.compile(r"_(\d{6,})\.\w+$|^(\d{6,})\.\w+$")


def get_json(url, retries=2, timeout=600):
    """取 JSON。

    timeout 必须给足：iNat 在限速状态下，一条 per_page=200 的查询实测要 245 秒。
    早先这里写 120 秒，导致每条请求都超时→重试→看起来像卡死，
    实际是超时阈值比真实响应时间还短。
    """
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"    [重试 {i + 1}/{retries}] {str(e)[:70]}")
            if i == retries - 1:
                print(f"    放弃: {e}")
                return {}
            time.sleep(5)
    return {}


def existing_ids(out_dir: Path) -> set[int]:
    """扫出该目录下已有图片的 photo id，用于去重（跨两代命名规则）。"""
    ids: set[int] = set()
    if not out_dir.exists():
        return ids
    for sub in out_dir.iterdir():
        if not sub.is_dir():
            continue
        for f in sub.iterdir():
            if not f.name.lower().endswith(EXTS):
                continue
            m = TRAILING_ID.search(f.name)
            if m:
                ids.add(int(m.group(1) or m.group(2)))
    return ids


def min_id_in(class_dir: Path) -> int | None:
    """取某个类别目录里已有照片的最小 id，用作翻页起点（加量场景省一页）。"""
    lo = None
    if not class_dir.exists():
        return None
    for f in class_dir.iterdir():
        if not f.name.lower().endswith(EXTS):
            continue
        m = TRAILING_ID.search(f.name)
        if m:
            v = int(m.group(1) or m.group(2))
            lo = v if lo is None else min(lo, v)
    return lo


def collect(taxon: str, want: int, captive: bool, skip: set[int],
            start_below: int | None = None, max_pages: int = 8) -> list[dict]:
    """取该物种的照片。

    用 id_below 翻页而非 page：翻页期间若有新观察插入，page 分页会重复或漏记录。

    start_below 用于「加量」场景：某类的最新 N 张已经采过，若仍从最新开始翻，
    第一页会全是已采的、被 skip 掉，白白多花一次请求（限速下一条要 245 秒）。
    传入该类已有照片的最小 id，就能直接从它之下开始，跳过整页空转。
    """
    photos: dict[int, dict] = {}
    id_below = start_below
    for _ in range(max_pages):
        params = {
            "taxon_name": taxon,
            "photos": "true",
            "photo_license": LICENSES,
            "per_page": 200,
            "order_by": "id",
            "order": "desc",
        }
        params["captive"] = "true" if captive else "false"
        if id_below:
            params["id_below"] = id_below
        d = get_json(f"{API}?{urllib.parse.urlencode(params)}")
        results = d.get("results", [])
        if not results:
            break
        for obs in results:
            for p in obs.get("photos") or []:
                pid = p.get("id")
                if isinstance(pid, int) and pid not in photos and pid not in skip:
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
        time.sleep(0.4)
    return list(photos.values())[:want]


def fetch_image(pid: int, dest: Path, size="medium") -> int:
    for sz in (size, "small", "original"):
        try:
            req = urllib.request.Request(f"{S3}/{pid}/{sz}.jpg", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
                data = r.read()
            if len(data) < 3000:
                continue
            dest.write_bytes(data)
            return len(data)
        except Exception:  # noqa: BLE001
            continue
    dest.unlink(missing_ok=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description="绿植图采集（室内/野外）")
    ap.add_argument("--domain", choices=["indoor", "wild"], default="indoor")
    ap.add_argument("--per-class", type=int, default=300)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--size", default="medium")
    ap.add_argument("--only", nargs="*", default=None, help="只采指定类别")
    ap.add_argument("--out", default=None, help="覆盖输出目录")
    args = ap.parse_args()

    species = json.loads(SPECIES_FILE.read_text(encoding="utf-8"))["classes"]
    targets = {k: v for k, v in species.items() if not args.only or k in args.only}
    if not targets:
        raise SystemExit(f"--only 里的类别不在 species.json 中: {args.only}")

    out_root = Path(args.out) if args.out else OUT_DIRS[args.domain]
    captive = args.domain == "indoor"
    print(f"域: {args.domain}（captive={captive}） 目标 {len(targets)} 类 x {args.per_class} 张")
    print(f"输出: {out_root}")
    skip = existing_ids(out_root)
    print(f"已有 photo id {len(skip)} 个，将跳过（跨命名规则去重）\n")

    manifest = out_root / "manifest.jsonl"
    lines, summary, total_new = [], {}, 0

    for label, taxa in targets.items():
        out_dir = out_root / label
        out_dir.mkdir(parents=True, exist_ok=True)
        have = len([f for f in out_dir.iterdir() if f.name.lower().endswith(EXTS)])
        need = max(0, args.per_class - have)
        print(f"[{label}] 已有 {have}，目标 {args.per_class}，还需 {need}（{len(taxa)} 个物种）")

        if need:
            cands: list[dict] = []
            per = max(1, need // len(taxa) + 1)
            # 该类已采过就从其最小 id 之下开始翻，避免第一页全是已采的被 skip 掉
            start_below = min_id_in(out_dir)
            for taxon in taxa:
                got = collect(taxon, per, captive, skip, start_below=start_below)
                cands.extend(got)
                print(f"    候选 {taxon:28s} {len(got)} 张")
            seen: set[int] = set()
            jobs = []
            for c in cands:
                if c["id"] in seen:
                    continue
                seen.add(c["id"])
                dest = out_dir / f"{c['id']}.jpg"
                if dest.exists() or have + len(jobs) >= args.per_class:
                    if have + len(jobs) >= args.per_class:
                        break
                    continue
                jobs.append((c, dest))

            got_n = 0
            if jobs:
                print(f"    下载 {len(jobs)} 张 ...")
                done = 0
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futs = {pool.submit(fetch_image, c["id"], dest, args.size): (c, dest) for c, dest in jobs}
                    for fut in as_completed(futs):
                        c, dest = futs[fut]
                        done += 1
                        if fut.result():
                            got_n += 1
                            lines.append(json.dumps({
                                "file": f"{label}/{dest.name}", "label": label,
                                "photo_id": c["id"], "license": c["license"],
                                "attribution": c["attribution"], "observation": c["observation"],
                                "source": f"iNaturalist ({'captive/cultivated' if captive else 'wild'})",
                            }, ensure_ascii=False))
                        if done % 100 == 0:
                            print(f"      进度 {done}/{len(jobs)}，成功 {got_n}")
            total_new += got_n

        final = len([f for f in out_dir.iterdir() if f.name.lower().endswith(EXTS)])
        summary[label] = final
        print(f"[{label}] 完成，共 {final} 张\n")

    if lines:
        with open(manifest, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    print("=" * 52)
    for k, v in summary.items():
        print(f"  {k:10s} {v} 张")
    print(f"  {'本次新增':10s} {total_new} 张")
    print(f"\n许可清单: {manifest}")


if __name__ == "__main__":
    main()
