"""探测两件事，用来决定「多搜集数据」该往哪采：

A. 现有 20 类里那几个弱类（召回<0.80），iNat 还有多少 captive 图可采 —— 决定能不能靠加量补救
B. 常见的室内植物里，**不在现有 20 类**的，数据可得量有多少 —— 决定能不能扩类

背景：当前模型的错误分析显示
  * 弱类：常春藤 0.767、栀子花 0.767、富贵竹 0.800、袖珍椰子 0.800、龟背竹 0.800
  * 高置信度错误仅 16/596，模型校准尚可，主要短板是这几类
  * 更根本的限制是**闭集分类**：拍到 20 类之外的植物会被自信地误判成某一类
"""

import json
import ssl
import ssl as _ssl
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

# A. 现有弱类
WEAK = {
    "常春藤": "Hedera helix",
    "栀子花": "Gardenia jasminoides",
    "富贵竹": "Dracaena sanderiana",
    "袖珍椰子": "Chamaedorea elegans",
    "龟背竹": "Monstera deliciosa",
}

# B. 中国家庭/花市常见、但不在现有 20 类里的候选
NEW = {
    "金钱树": "Zamioculcas zamiifolia",
    "万年青": "Aglaonema commutatum",
    "红掌":   "Anthurium andraeanum",
    "幸福树": "Radermachera sinica",
    "芦荟":   "Aloe vera",
    "散尾葵": "Dypsis lutescens",
    "龙血树": "Dracaena marginata",
    "竹芋":   "Goeppertia zebrina",
    "豆瓣绿": "Peperomia obtusifolia",
    "铁线蕨": "Adiantum raddianum",
    "波斯顿蕨": "Nephrolepis exaltata",
    "鹤望兰": "Strelitzia reginae",
}


def count(taxon, captive=True):
    p = {"taxon_name": taxon, "photos": "true", "photo_license": LIC, "per_page": 1}
    if captive:
        p["captive"] = "true"
    try:
        req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(p)}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("total_results", 0)
    except Exception as e:
        return f"失败({str(e)[:30]})"


def main():
    print("=" * 84)
    print("A. 现有弱类还能补多少（captive + 带照片 + 开放许可）")
    print("=" * 84)
    for label, taxon in WEAK.items():
        n = count(taxon)
        extra = n - 200 if isinstance(n, int) else 0
        print(f"  {label:10s} {taxon:28s} 可得 {n:>7}   已采 200   可再补约 {extra}")
        time.sleep(0.4)

    print()
    print("=" * 84)
    print("B. 不在现有 20 类里的常见植物（若要扩类，这些是可选项）")
    print("=" * 84)
    for label, taxon in NEW.items():
        n = count(taxon)
        ok = "充足" if isinstance(n, int) and n >= 300 else ("偏少" if isinstance(n, int) and n >= 100 else "不足")
        print(f"  {label:10s} {taxon:28s} 可得 {n:>7}   {ok}")
        time.sleep(0.4)

    print()
    print("说明：iNat captive 数据越多，越能支撑「加量」或「扩类」。")
    print("      扩类还需同步 plant_knowledge 表与 species_ids.json，并重新训练。")


if __name__ == "__main__":
    main()
