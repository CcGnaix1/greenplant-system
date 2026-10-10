"""采集训练图。

数据来源：GBIF 的 occurrence API 取图片 id，再从 iNaturalist 的 S3 取图。

为什么绕这一圈而不是直接用 iNaturalist API —— 实测本机到国际站点被限速：
  * iNat observations API：74 张图/页，一页约 120 秒   (~21 KB/s)
  * GBIF occurrence API  ：100 条观察/次，一次约 26 秒  (~25 KB/s)
  * GBIF 一次能给 147 个不重复图片 id，iNat 只给 74 个 → API 耗时差约 5 倍
图片本身都来自 iNat（S3 上的 inaturalist-open-data），质量与许可一致。

下载侧：并发能把聚合带宽从 25 KB/s 提到 ~120 KB/s（每 IP 上限），
故用 24 线程；取 medium(约 500px) 而非 original(1.4MB)，够 224×224 训练用。

用法:
    python fetch_inat.py                      # 每类 150 张
    python fetch_inat.py --per-class 80 --workers 24

注：「多肉植物」「兰花」业务上是**类别**而非物种，各用几个常见代表种覆盖。
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "plants"

GBIF = "https://api.gbif.org/v1/occurrence/search"
S3 = "https://inaturalist-open-data.s3.amazonaws.com/photos"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # 本机无 certifi；只读公开图片，风险可控

# 前端标签 → 候选学名
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
    # 必须用新学名：旧名 Schefflera arboricola 在 GBIF 的图全来自 Flickr/博物馆，
    # 没有 iNat 来源；Heptapleurum arboricola 有 1359 条 iNat 记录
    "鹅掌柴":   ["Heptapleurum arboricola"],
}


def get_json(url: str, retries: int = 3) -> dict:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                print(f"    放弃: {e}")
                return {}
            time.sleep(5)
    return {}


def collect_ids(taxon: str, want: int) -> list[str]:
    """取该物种在 iNat 上的图片 id 列表。"""
    ids: dict[str, None] = {}
    offset = 0
    while len(ids) < want and offset < 600:
        q = urllib.parse.urlencode({
            "scientificName": taxon,
            "mediaType": "StillImage",
            "limit": 100,
            "offset": offset,
        })
        d = get_json(f"{GBIF}?{q}")
        results = d.get("results", [])
        if not results:
            break
        for occ in results:
            for m in occ.get("media", []):
                u = m.get("identifier") or ""
                # 只取 iNat 来源：社区鉴定、质量稳定；其它来源（Flickr 等）参差
                if "inaturalist-open-data.s3" in u and "/photos/" in u:
                    pid = u.split("/photos/")[1].split("/")[0]
                    if pid.isdigit():
                        ids[pid] = None
        offset += 100
        if d.get("endOfRecords"):
            break
        time.sleep(0.5)
    return list(ids)[:want]


def fetch_image(pid: str, dest: Path, size: str = "medium") -> int:
    """下单一尺寸；失败回退 small。返回字节数，0 表示失败。"""
    for sz in (size, "small", "original"):
        try:
            req = urllib.request.Request(f"{S3}/{pid}/{sz}.jpg", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=150, help="每个前端标签的目标张数")
    ap.add_argument("--workers", type=int, default=24, help="并发下载线程数")
    ap.add_argument("--size", type=str, default="medium", help="图片尺寸 medium/small/large")
    args = ap.parse_args()

    print(f"目标: {len(SPECIES)} 类 x {args.per_class} 张, 尺寸={args.size}, 并发={args.workers}")
    print(f"输出: {DATA_DIR}\n")

    manifest = {}
    total = 0
    for label, taxa in SPECIES.items():
        out_dir = DATA_DIR / label
        out_dir.mkdir(parents=True, exist_ok=True)
        have = len([f for f in os.listdir(out_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
        need = max(0, args.per_class - have)
        print(f"[{label}] 已有 {have}，目标 {args.per_class}，还需 {need}（{len(taxa)} 个物种）")
        if need == 0:
            manifest[label] = have
            total += have
            continue

        per_taxon = max(1, need // len(taxa) + 1)
        jobs: list[tuple[str, Path]] = []
        for taxon in taxa:
            for pid in collect_ids(taxon, per_taxon):
                if have + len(jobs) >= args.per_class:
                    break
                dest = out_dir / f"{taxon.replace(' ', '_')}_{pid}.jpg"
                if not dest.exists():
                    jobs.append((pid, dest))
            if have + len(jobs) >= args.per_class:
                break

        got = 0
        if jobs:
            print(f"    下载 {len(jobs)} 张 ...")
            done = 0
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futs = {pool.submit(fetch_image, pid, dest, args.size): dest for pid, dest in jobs}
                for fut in as_completed(futs):
                    done += 1
                    if fut.result():
                        got += 1
                    if done % 50 == 0:
                        print(f"      进度 {done}/{len(jobs)}，成功 {got}")
        final = len([f for f in os.listdir(out_dir)
                     if f.lower().endswith((".jpg", ".jpeg", ".png"))])
        manifest[label] = final
        total += final
        print(f"[{label}] 完成，共 {final} 张\n")

    print("=" * 52)
    for k, v in manifest.items():
        print(f"  {k:10s} {v} 张")
    print(f"  {'合计':10s} {total} 张")
    (ROOT / "data" / "fetch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
