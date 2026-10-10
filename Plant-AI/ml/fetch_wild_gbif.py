"""野外照采集（走 GBIF）—— 补 10 个新类的野外数据。

为什么不复用 fetch_plants.py 的 wild 模式：
该模式走 iNat 官方 API，而 iNat 现在对本机**限速**：一条 per_page=200 的查询
实测要 245 秒（此前仅 1~2 秒）。GBIF 未受影响（1.6~2.0 秒），
且 GBIF 收录的就是 iNat 的 research-grade 野外观察，图源与许可是同一批。

分工：
    GBIF（本脚本）  -> 野外照，写入 data/plants/
    iNat 官方 API   -> 栽培/室内照，写入 data/plants_indoor/（fetch_plants.py）

去重同 fetch_plants.py：按 photo id，而不是文件名 —— 两代脚本命名规则不同，
只比文件名会让同一张照片重复入库，进而可能一份进训练集、一份进验证集。
"""

import argparse
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECIES_FILE = Path(__file__).resolve().parent / "species.json"
GBIF = "https://api.gbif.org/v1/occurrence/search"
MATCH = "https://api.gbif.org/v1/species/match"
S3 = "https://inaturalist-open-data.s3.amazonaws.com/photos"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"
OUT_DIR = ROOT / "data" / "plants"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

EXTS = (".jpg", ".jpeg", ".png", ".webp")
TRAILING_ID = re.compile(r"_(\d{6,})\.\w+$|^(\d{6,})\.\w+$")


def get_json(url, timeout=180, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                print(f"    放弃: {str(e)[:70]}")
                return {}
            time.sleep(4)
    return {}


def existing_ids(out_dir: Path) -> set:
    ids = set()
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


def collect_ids(taxon: str, want: int, skip: set, max_pages: int = 4) -> list:
    """取该物种在 GBIF 上的图（photo id 形如 iNat 的 S3 路径数字）。"""
    m = get_json(f"{MATCH}?{urllib.parse.urlencode({'name': taxon, 'kingdom': 'Plantae'})}")
    key = m.get("usageKey")
    if not key:
        print(f"    {taxon}: GBIF 未匹配到 taxonKey（matchType={m.get('matchType')}）")
        return []

    ids: dict = {}
    offset = 0
    for _ in range(max_pages):
        q = urllib.parse.urlencode({
            "taxonKey": key, "mediaType": "StillImage",
            "limit": 300, "offset": offset,
        })
        d = get_json(f"{GBIF}?{q}")
        results = d.get("results", [])
        if not results:
            break
        for occ in results:
            for media in occ.get("media", []):
                u = media.get("identifier") or ""
                # 只取 iNat 来源（社区鉴定、质量稳定）；Flickr 等来源参差
                if "inaturalist-open-data.s3" in u and "/photos/" in u:
                    pid = u.split("/photos/")[1].split("/")[0]
                    if pid.isdigit():
                        p = int(pid)
                        if p not in skip:
                            ids[p] = None
        offset += 300
        if d.get("endOfRecords") or len(ids) >= want:
            break
        time.sleep(0.3)
    return list(ids)[:want]


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
    ap = argparse.ArgumentParser(description="野外照采集（GBIF）")
    ap.add_argument("--per-class", type=int, default=200)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    species = json.loads(SPECIES_FILE.read_text(encoding="utf-8"))["classes"]
    targets = {k: v for k, v in species.items() if not args.only or k in args.only}
    if not targets:
        raise SystemExit(f"--only 不在 species.json 中: {args.only}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skip = existing_ids(OUT_DIR)
    print(f"野外采集（GBIF）: {len(targets)} 类 x {args.per_class} 张")
    print(f"输出: {OUT_DIR}   已有 photo id {len(skip)} 个（将跳过）\n")

    manifest = OUT_DIR / "manifest.jsonl"
    lines, summary, total_new = [], {}, 0

    for label, taxa in targets.items():
        out_dir = OUT_DIR / label
        out_dir.mkdir(parents=True, exist_ok=True)
        have = len([f for f in out_dir.iterdir() if f.name.lower().endswith(EXTS)])
        need = max(0, args.per_class - have)
        print(f"[{label}] 已有 {have}，目标 {args.per_class}，还需 {need}（{len(taxa)} 个物种）")

        if need:
            cands = []
            per = max(1, need // len(taxa) + 1)
            for taxon in taxa:
                got = collect_ids(taxon, per, skip)
                cands.extend(got)
                print(f"    候选 {taxon:28s} {len(got)} 张")
            seen, jobs = set(), []
            for pid in cands:
                if pid in seen:
                    continue
                seen.add(pid)
                dest = out_dir / f"{pid}.jpg"
                if dest.exists() or have + len(jobs) >= args.per_class:
                    if have + len(jobs) >= args.per_class:
                        break
                    continue
                jobs.append((pid, dest))

            got_n = 0
            if jobs:
                print(f"    下载 {len(jobs)} 张 ...")
                done = 0
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futs = {pool.submit(fetch_image, pid, dest): (pid, dest) for pid, dest in jobs}
                    for fut in as_completed(futs):
                        pid, dest = futs[fut]
                        done += 1
                        if fut.result():
                            got_n += 1
                            lines.append(json.dumps({
                                "file": f"{label}/{dest.name}", "label": label,
                                "photo_id": pid,
                                "observation": f"https://www.inaturalist.org/photos/{pid}",
                                "source": "iNaturalist via GBIF (research-grade / wild)",
                                "license": "见 iNat 照片页",
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


if __name__ == "__main__":
    main()
