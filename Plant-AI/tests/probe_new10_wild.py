"""补充探测：备胎候选（替换不足的品种）+ 各候选的 GBIF 野外照可得量。

为什么要查野外量
----------------
训练同时喂 `data/plants/`（野外）与 `data/plants_indoor/`（室内）。train30.py 的注释
写明：**两个域都参与，避免模型把「域」当成类别的捷径**。若新增的类只有室内照，
模型可能学会「这类只在室内出现」这种无关特征，反而干扰。

但本批候选多是栽培观赏植物（空气凤梨/非洲堇/果子蔓/蟹爪兰），野外照可能很稀。
所以先量出来，据此决定：野外够就采两域，不够就只采室内并向用户说明。
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

INAT = "https://api.inaturalist.org/v1/observations"
GBIF = "https://api.gbif.org/v1/occurrence/search"
MATCH = "https://api.gbif.org/v1/species/match"
UA = "PlantCare-CourseProject/1.0 (educational, non-commercial)"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
LIC = "cc0,cc-by,cc-by-nc"


def get(url, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def inat_captive(taxon):
    p = {"taxon_name": taxon, "photos": "true", "photo_license": LIC,
         "per_page": 1, "captive": "true"}
    try:
        return get(f"{INAT}?{urllib.parse.urlencode(p)}").get("total_results", 0)
    except Exception as e:
        return f"失败({str(e)[:30]})"


def gbif_wild(taxon):
    """GBIF 上 iNat 来源的野外照总数（与 fetch_wild_gbif.py 同口径）。"""
    try:
        m = get(f"{MATCH}?{urllib.parse.urlencode({'name': taxon, 'kingdom': 'Plantae'})}")
        key = m.get("usageKey")
        if not key:
            return f"未匹配({m.get('matchType')})"
        q = urllib.parse.urlencode({"taxonKey": key, "mediaType": "StillImage", "limit": 1})
        return get(f"{GBIF}?{q}").get("count", 0)
    except Exception as e:
        return f"失败({str(e)[:30]})"


# 首选里数据不足/偏少的，用这些替换
BACKUP = {
    "鹿角蕨":  "Platycerium bifurcatum",
    "网纹草":  "Fittonia albivenis",
    "吊竹梅":  "Tradescantia zebrina",
    "平安树":  "Cinnamomum kotoense",
    "熊童子":  "Cotyledon tomentosa",
}

# 首选里已确认可用的，补查野外量
CONFIRMED = {
    "仙人球":   "Echinopsis tubiflora",
    "蟹爪兰":   "Schlumbergera truncata",
    "一叶兰":   "Aspidistra elatior",
    "幸福树":   "Radermachera sinica",
    "观音竹":   "Bambusa multiplex",
    "天竺葵":   "Pelargonium hortorum",
    "空气凤梨": "Tillandsia ionantha",
    "非洲堇":   "Streptocarpus ionanthus",
    "果子蔓":   "Guzmania lingulata",
}


def main():
    print("=" * 92)
    print("A. 备胎（用于替换数据不足的品种）")
    print("=" * 92)
    print(f"{'品种':10s} {'学名':28s} {'iNat室内':>10s} {'GBIF野外':>10s}")
    print("-" * 92)
    for label, taxon in BACKUP.items():
        print(f"{label:10s} {taxon:28s} {str(inat_captive(taxon)):>10s} {str(gbif_wild(taxon)):>10s}")
        time.sleep(1.0)

    print()
    print("=" * 92)
    print("B. 已确认候选的野外量（决定能否双域训练）")
    print("=" * 92)
    print(f"{'品种':10s} {'学名':28s} {'iNat室内':>10s} {'GBIF野外':>10s}  判定")
    print("-" * 92)
    for label, taxon in CONFIRMED.items():
        ic, gw = inat_captive(taxon), gbif_wild(taxon)
        if isinstance(gw, int):
            v = "双域可采" if gw >= 150 else ("野外偏少" if gw >= 60 else "仅室内")
        else:
            v = "野外查询失败"
        print(f"{label:10s} {taxon:28s} {str(ic):>10s} {str(gw):>10s}  {v}")
        time.sleep(1.0)

    print()
    print("注：iNat室内 = captive 栽培照；GBIF野外 = iNat 来源 research-grade 野外照。")
    print("    采集成功率 50~70%，故 >=300 才稳妥，>=150 可勉强。")


if __name__ == "__main__":
    main()
