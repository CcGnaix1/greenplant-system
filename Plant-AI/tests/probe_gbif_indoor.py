"""可行性探测：GBIF 能否筛出「栽培/圈养」的观察记录（即室内盆栽那一域）。

背景：现有 2708 张训练图全部来自 iNaturalist 的**野外**观察照，
而用户实际拍的是室内盆栽，两者域不匹配导致置信度只有 0.46。
iNaturalist 有「圈养/栽培 (captive/cultivated)」标记，若 GBIF 侧可筛，
就能复用现有采集管线拿到同物种、同许可、但更接近室内场景的图。

这个脚本只做查询、不下载，用来判断值不值得改造 fetch_inat.py。
"""

import json
import ssl
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GBIF = "https://api.gbif.org/v1/occurrence/search"
SPECIES = "https://api.gbif.org/v1/species/match"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get_json(url, timeout=180):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d, time.time() - t0
    except Exception as e:
        return {"_error": str(e)}, time.time() - t0


def count(label, params):
    q = urllib.parse.urlencode(params)
    d, dt = get_json(f"{GBIF}?{q}")
    if "_error" in d:
        print(f"  {label:38s} 失败: {d['_error'][:60]}  ({dt:.1f}s)")
        return None
    n = d.get("count")
    print(f"  {label:38s} count={n}  ({dt:.1f}s)")
    return n


def main():
    print("=" * 70)
    print("GBIF 栽培/圈养筛选 可行性探测")
    print("=" * 70)

    # 1. 先拿物种 taxonKey
    d, dt = get_json(f"{SPECIES}?name=Epipremnum%20aureum&kingdom=Plantae")
    key = d.get("usageKey")
    print(f"\n[1] Epipremnum aureum (绿萝) taxonKey = {key}  ({dt:.1f}s)")

    print("\n[2] 各种筛选条件下能拿到多少条（绿萝）")
    base = {"taxonKey": key, "mediaType": "StillImage", "limit": 0}
    count("无条件（现有脚本用的就是这种）", base)
    count("establishmentMeans=MANAGED", {**base, "establishmentMeans": "MANAGED"})
    count("establishmentMeans=INTRODUCED", {**base, "establishmentMeans": "INTRODUCED"})
    count("occurrenceStatus=PRESENT", {**base, "occurrenceStatus": "PRESENT"})

    # 3. 看单条记录有哪些字段可用 —— 决定还能按什么筛
    print("\n[3] 抽样一条记录，看可用字段")
    q = urllib.parse.urlencode({"taxonKey": key, "mediaType": "StillImage", "limit": 1})
    d, dt = get_json(f"{GBIF}?{q}")
    res = d.get("results", [])
    if res:
        r = res[0]
        print(f"  ({dt:.1f}s) 字段清单:")
        for k in sorted(r.keys()):
            v = r[k]
            if isinstance(v, (list, dict)):
                v = f"<{type(v).__name__} len={len(v)}>"
            s = str(v)
            print(f"    {k:34s} = {s[:60]}")

    # 4. 数据集来源分布：确认图确实来自 iNat
    print("\n[4] 前 200 条的采集来源（看是不是 iNat）")
    q = urllib.parse.urlencode({**base, "limit": 200})
    d, dt = get_json(f"{GBIF}?{q}")
    src = {}
    eman = {}
    for r in d.get("results", []):
        for m in r.get("media", []):
            u = m.get("identifier") or ""
            if "inaturalist-open-data.s3" in u:
                src["iNat"] = src.get("iNat", 0) + 1
            else:
                src["其它"] = src.get("其它", 0) + 1
        em = r.get("establishmentMeans")
        eman[str(em)] = eman.get(str(em), 0) + 1
    print(f"  ({dt:.1f}s) 图片来源: {src}")
    print(f"  establishmentMeans 分布: {eman}")


if __name__ == "__main__":
    main()
