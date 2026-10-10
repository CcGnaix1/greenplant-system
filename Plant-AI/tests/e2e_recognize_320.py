"""端到端实测：320 品种模型经「小程序 → Spring → FastAPI」全链路是否正确。

为什么要走全链路而不是只测 ONNX
------------------------------
ONNX 层的精度已经单独验过（tests/check_onnx_320_parity.py，0.9170）。
这里要确认的是**管线**：
  * Spring 的 multipart 参数名、鉴权、转发是否正常
  * FastAPI 的 320 预处理是否被真正调用（不是仍按旧代码跑 224）
  * 返回的 species / knowledgeId 与 plant_knowledge 映射是否一致

样本取自室内测试集（训练不可见），用 Python 发请求以避开 Git Bash 的中文编码坑。
用标准库 urllib 手工拼 multipart —— 该 venv 里没有 requests/httpx。
"""

import argparse
import json
import mimetypes
import sys
import urllib.request
from pathlib import Path

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))

from dataset import PlantDataset               # noqa: E402
from train30 import stratified_split           # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://127.0.0.1:8000/api"
SEED = 42


def post_json(url, payload, token=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def post_multipart(url, field, file_path, token):
    boundary = "----plant320boundary"
    ctype = mimetypes.guess_type(file_path)[0] or "image/jpeg"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="{field}"; filename="x.jpg"\r\n'.encode()
    body += f"Content-Type: {ctype}\r\n\r\n".encode()
    body += Path(file_path).read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=1, help="每个品种取几张（默认 1）")
    ap.add_argument("--phone", default="13800000001")
    ap.add_argument("--password", default="123456")
    args = ap.parse_args()

    print("=" * 78)
    print("端到端实测：320 品种模型全链路")
    print("=" * 78)

    login = post_json(f"{BASE}/auth/login", {"phone": args.phone, "password": args.password})
    token = login["data"]["token"]
    print(f"登录成功（{args.phone}）")

    ds = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    _, _, test_i = stratified_split(ds, (0.70, 0.15, 0.15), SEED)

    # 每类取前 N 张
    picked, per = [], {}
    for i in test_i:
        p, lab = ds.samples[i]
        c = ds.classes[lab]
        if per.get(c, 0) >= args.per_class:
            continue
        per[c] = per.get(c, 0) + 1
        picked.append((p, c))

    print(f"样本 {len(picked)} 张（覆盖 {len(per)} 个品种，均取自训练不可见的测试集）\n")

    ok = 0
    misses = []
    mocks = 0
    for p, true_c in picked:
        resp = post_multipart(f"{BASE}/species/recognize", "image", p, token)
        d = resp.get("data", {})
        cands = d.get("candidates", [])
        got = cands[0]["species"] if cands else None
        conf = cands[0]["confidence"] if cands else 0.0
        kid = cands[0].get("speciesId") if cands else None
        if d.get("isMock"):
            mocks += 1
        if got == true_c:
            ok += 1
        else:
            misses.append((true_c, got, conf))
        flag = "OK  " if got == true_c else "MISS"
        print(f"  {flag} 真实={true_c:8s} 预测={str(got):8s} conf={conf:<7} knowledgeId={kid}")

    print(f"\n全链路命中 {ok}/{len(picked)} = {ok / len(picked):.4f}")
    if mocks:
        print(f"[警告] 有 {mocks} 次返回 isMock=true —— 模型没加载上！")
    if misses:
        print("未命中：")
        for t, g, c in misses:
            print(f"   {t} → {g} ({c})")
    print("\n注意：这是每类 1 张的小样本抽查，用于确认**管线正确**，")
    print("      精度结论以 tests/check_onnx_320_parity.py 的 1072 张为准。")


if __name__ == "__main__":
    main()
