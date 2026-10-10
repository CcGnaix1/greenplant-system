"""确认 iNat API 返回的 photos 结构与可下载 URL 格式（写采集脚本前必须搞清）。"""

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
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    q = urllib.parse.urlencode({
        "taxon_name": "Epipremnum aureum", "captive": "true", "photos": "true",
        "photo_license": "cc0,cc-by,cc-by-nc", "per_page": 3,
        "order_by": "votes", "order": "desc",
    })
    d = get_json(f"{API}?{q}")
    res = d.get("results", [])
    print(f"返回 {len(res)} 条观察\n")

    for i, r in enumerate(res[:2]):
        print(f"--- 观察 #{i+1}  id={r.get('id')}  quality={r.get('quality_grade')}  captive={r.get('captive')}")
        print(f"    观察页面: {r.get('uri')}")
        photos = r.get("photos") or []
        print(f"    照片数: {len(photos)}")
        for p in photos[:2]:
            print("    照片字段:", json.dumps({k: v for k, v in p.items()
                                              if k in ('id', 'url', 'license_code', 'attribution', 'original_dimensions')},
                                             ensure_ascii=False)[:220])

    # 实际试下载一张 medium 尺寸，确认 URL 模板可用
    print("\n=== 试下载 medium 尺寸 ===")
    for p in (res[0].get("photos") or [])[:1]:
        for tmpl in ("url", "medium_url"):
            u = p.get(tmpl)
            if not u:
                continue
            # iNat 的 url 字段带 square.jpg，换尺寸就是换文件名
            for size in ("medium", "small", "large", "square"):
                cand = u.replace("square.", f"{size}.").replace("small.", f"{size}.").replace("medium.", f"{size}.")
                try:
                    t0 = time.time()
                    req = urllib.request.Request(cand, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                        data = r.read()
                    print(f"  [OK] {tmpl}->{size}: {len(data)} bytes  ({time.time()-t0:.1f}s)  {cand[:88]}")
                except Exception as e:
                    print(f"  [FAIL] {tmpl}->{size}: {str(e)[:60]}  {cand[:88]}")

    print("\n=== per_page 上限测试 ===")
    for n in (100, 200, 300):
        q = urllib.parse.urlencode({"taxon_name": "Epipremnum aureum", "captive": "true",
                                    "photos": "true", "per_page": n})
        try:
            d = get_json(f"{API}?{q}", timeout=120)
            print(f"  请求 per_page={n} -> 实际返回 {len(d.get('results', []))} 条")
        except Exception as e:
            print(f"  请求 per_page={n} -> 失败 {str(e)[:60]}")


if __name__ == "__main__":
    main()
