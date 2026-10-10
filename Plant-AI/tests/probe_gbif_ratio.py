"""测量各品种 iNat「圈养/栽培(captive)」观察的占比，判断室内数据够不够用。

上一支探测脚本发现 GBIF 记录里带字段
    http://unknown.org/captive_cultivated  (取值 wild / captive)
但 GBIF 不支持按它做 URL 筛选，只能在客户端过滤。
所以这里抽样若干页，统计 captive 占比，再乘以总量估算可采集张数。
"""

import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GBIF = "https://api.gbif.org/v1/occurrence/search"
SPECIES_API = "https://api.gbif.org/v1/species/match"
CAPTIVE_FIELD = "http://unknown.org/captive_cultivated"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 挑几类代表：你在用的那几张图对应的品种 + 几个易混的
PROBE = {
    "绿萝": ["Epipremnum aureum"],
    "龟背竹": ["Monstera deliciosa"],
    "橡皮树": ["Ficus elastica"],
    "栀子花": ["Gardenia jasminoides"],
    "虎皮兰": ["Dracaena trifasciata"],
    "袖珍椰子": ["Chamaedorea elegans"],
}

PAGES = 3          # 每物种抽几页
PAGE = 300         # GBIF 单页上限
IMGS_PER_REC = 1.2  # 经验值：一条观察平均带的图片数（用于估算可下载张数）


def get_json(url, timeout=180):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def taxon_key(name):
    d = get_json(f"{SPECIES_API}?{urllib.parse.urlencode({'name': name, 'kingdom': 'Plantae'})}")
    return d.get("usageKey"), d.get("matchType")


def probe(label, taxa):
    rows = []
    for taxon in taxa:
        key, mt = taxon_key(taxon)
        if not key:
            rows.append((taxon, mt, 0, 0, 0, 0))
            continue
        total = get_json(f"{GBIF}?{urllib.parse.urlencode({'taxonKey': key, 'limit': 0})}").get("count", 0)
        cap, wild, other, imgs = 0, 0, 0, 0
        for p in range(PAGES):
            q = urllib.parse.urlencode({
                "taxonKey": key, "mediaType": "StillImage",
                "limit": PAGE, "offset": p * PAGE,
            })
            d = get_json(f"{GBIF}?{q}")
            res = d.get("results", [])
            if not res:
                break
            for r in res:
                v = r.get(CAPTIVE_FIELD)
                if v == "captive":
                    cap += 1
                elif v == "wild":
                    wild += 1
                else:
                    other += 1
                for m in r.get("media", []):
                    u = m.get("identifier") or ""
                    if "inaturalist-open-data.s3" in u and "/photos/" in u:
                        imgs += 1
            if d.get("endOfRecords"):
                break
            time.sleep(0.3)
        rows.append((taxon, mt, total, cap, wild, other))
        print(f"  {label:8s} {taxon:26s} 总记录={total:6d}  抽样{cap+wild+other:4d}条: "
              f"captive={cap:4d} wild={wild:4d} 空={other:4d}")
    return rows


def main():
    print("=" * 88)
    print("各品种 iNat captive(圈养/栽培) 占比探测")
    print("=" * 88)
    print(f"每物种抽样 {PAGES} 页 x {PAGE} 条\n")

    for label, taxa in PROBE.items():
        probe(label, taxa)

    print()
    print("说明：captive 判定基于 iNat 的「captive/cultivated」标记，")
    print("      包含室内盆栽、花园栽培、温室、苗圃等 —— 比野外照更接近你的使用场景，")
    print("      但不全是室内。占比高才有采集价值。")


if __name__ == "__main__":
    main()
