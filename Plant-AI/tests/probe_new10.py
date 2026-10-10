"""探测「加 10 类」候选品种在 iNat 上的数据可得量。

为什么要先探测
------------
扩类的成本几乎全在采集上（每类需 ~200 张室内 + ~100~200 张野外），而 iNat 的
可用量在品种之间差异极大 —— 有些冷门品种全网只有几十张（见 `fetch_*` 那批踩坑记录：
龙血树用旧学名时 GBIF 仅 14 条、0 张 iNat 图）。采不到就白花时间，所以先探数。

排除与现有类重叠的品种
--------------------
`多肉植物` 这一类是把 4 个物种合并成一类的（Echeveria elegans / Crassula ovata /
Haworthia fasciata / Kalanchoe blossomed-floriana）。所以：
    * 玉树   = Crassula ovata        → **已在 多肉植物 里**，不能单列
    * 长寿花 = Kalanchoe blossomed   → **已在 多肉植物 里**，不能单列
这两个若单列会和现有类重叠、互相打架，已换成不重叠的候选。
同理 `兰花` 已合并 3 个物种（蝴蝶兰/春兰/石斛），故不再单独加兰科品种。

判据：captive（栽培）+ 带照片 + 开放许可 >= 300 视为充足。
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
LIC = "cc0,cc-by,cc-by-nc"

# 首选候选：与现有 30 类无重叠
CANDIDATES = {
    "仙人球":   "Echinopsis tubiflora",
    "蟹爪兰":   "Schlumbergera truncata",
    "铁线蕨":   "Adiantum raddianum",
    "一叶兰":   "Aspidistra elatior",
    "幸福树":   "Radermachera sinica",
    "观音竹":   "Bambusa multiplex",
    "天竺葵":   "Pelargonium hortorum",
    "空气凤梨": "Tillandsia ionantha",
    "非洲堇":   "Streptocarpus ionanthus",
    "果子蔓":   "Guzmania lingulata",
}

# 备胎：首选里有数据不足时替换
BACKUP = {
    "平安树":  "Cinnamomum kotoense",
    "鹿角蕨":  "Platycerium bifurcatum",
    "网纹草":  "Fittonia albivenis",
    "吊竹梅":  "Tradescantia zebrina",
    "熊童子":  "Cotyledon tomentosa",
    "常夏石竹": "Dianthus plumarius",
}


def count(taxon, captive=True):
    p = {"taxon_name": taxon, "photos": "true", "photo_license": LIC, "per_page": 1}
    if captive:
        p["captive"] = "true"
    try:
        req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(p)}",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("total_results", 0)
    except Exception as e:
        return f"失败({str(e)[:40]})"


def verdict(n):
    if not isinstance(n, int):
        return "查询失败"
    if n >= 300:
        return "充足"
    if n >= 150:
        return "偏少(可勉强)"
    return "不足(需换品种)"


def main():
    ap_argv = sys.argv[1:]
    pool = dict(CANDIDATES)
    if "--backup" in ap_argv:
        pool = dict(BACKUP)

    print("=" * 88)
    print("候选品种 iNat 可得量（captive 栽培 + 带照片 + 开放许可）")
    print("=" * 88)
    print(f"{'品种':10s} {'学名':30s} {'可得':>8s}  判定")
    print("-" * 88)
    good, bad = [], []
    for label, taxon in pool.items():
        n = count(taxon)
        print(f"{label:10s} {taxon:30s} {str(n):>8s}  {verdict(n)}")
        (good if isinstance(n, int) and n >= 150 else bad).append(label)
        time.sleep(1.0)

    print()
    print(f"可用（>=150）: {good}")
    if bad:
        print(f"不足/失败  : {bad}   ← 需从备胎里换")
    print("\n注：这是 captive/栽培 的量（对应室内照）。野外照另走 GBIF。")
    print("    采集还要按 photo id 去重，且成功率常只有 50~70%，故 >=300 才稳妥。")


if __name__ == "__main__":
    main()
