"""探测 iNaturalist 官方 observations API 能否取到 captive(栽培/室内)照片。

背景：GBIF 收录的是 iNat 的 research-grade 子集，而 RS 等级**排除**了
被标记为 captive/cultivated 的观察，所以走 GBIF 拿不到室内盆栽照（实测 captive=0）。
iNat 官方 API 支持 captive=true 筛选，可能能拿到 —— 本脚本验证这一点。

现有 fetch_inat.py 当初绕开 iNat API 是因为本机到国际站点被限速
（docstring 记载约 21 KB/s），但若 GBIF 拿不到目标数据，慢也值得。
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

API = "https://api.inaturalist.org/v1/observations"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get_json(url, timeout=120):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d, time.time() - t0, None
    except Exception as e:
        return {}, time.time() - t0, str(e)


def probe(label, params, show_fields=False):
    q = urllib.parse.urlencode(params)
    d, dt, err = get_json(f"{API}?{q}")
    if err:
        print(f"  {label:44s} 失败: {err[:50]}  ({dt:.1f}s)")
        return None
    n = d.get("total_results")
    got = len(d.get("results", []))
    print(f"  {label:44s} total={n} 本次返回={got}  ({dt:.1f}s)")
    if show_fields and got:
        r = d["results"][0]
        print(f"     记录字段: {sorted(r.keys())[:22]}")
        print(f"     captive 字段值 = {r.get('captive')}, quality_grade = {r.get('quality_grade')}")
    return n


def main():
    print("=" * 84)
    print("iNaturalist 官方 API 可达性与 captive 筛选探测")
    print("=" * 84)

    print("\n[1] 连通性")
    probe("绿萝 全部观察", {"taxon_name": "Epipremnum aureum", "per_page": 1})

    print("\n[2] captive 筛选（这是关键）")
    probe("绿萝 captive=true（栽培/室内）", {"taxon_name": "Epipremnum aureum", "captive": "true", "per_page": 1})
    probe("绿萝 captive=false（野外）", {"taxon_name": "Epipremnum aureum", "captive": "false", "per_page": 1})

    print("\n[3] captive + 仅要带照片 + 有可用许可")
    probe("绿萝 captive=true + photos + 开放许可",
          {"taxon_name": "Epipremnum aureum", "captive": "true", "photos": "true",
           "photo_license": "cc0,cc-by,cc-by-nc", "per_page": 1}, show_fields=True)

    print("\n[4] 各品种 captive 可得量（估算可采集张数）")
    for name in ["Epipremnum aureum", "Monstera deliciosa", "Ficus elastica",
                 "Gardenia jasminoides", "Dracaena trifasciata", "Chamaedorea elegans"]:
        probe(f"  {name} captive+photos", {
            "taxon_name": name, "captive": "true", "photos": "true",
            "photo_license": "cc0,cc-by,cc-by-nc", "per_page": 1,
        })
        time.sleep(0.5)

    print("\n说明：若 total_results 可观（每类数百以上），则改造 fetch 脚本走 iNat API 可行；")
    print("      若为 0 或极少，说明 iNat 上这些观赏植物的栽培照本来就少，此路也不通。")


if __name__ == "__main__":
    main()
