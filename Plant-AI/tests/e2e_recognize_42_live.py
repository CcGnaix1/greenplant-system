"""线上识别率抽查：走「Spring /species/recognize」全链路，核对返回品种与真值。

离线评估（eval_recognize_42.py）测的是 ONNX 层；这里确认**运行中的服务**——
Spring 转发、FastAPI 的 320 预处理、TTA、labels.json 的 knowledgeId 映射——都对得上。
用室内测试集（未参与训练）前 N 张，避免「记忆分」。
"""

import argparse
import json
import sys
import urllib.request
import uuid
from pathlib import Path

ROOT = Path("C:/Plant/plant-ai")
sys.path.insert(0, str(ROOT / "ml"))
from dataset import PlantDataset              # noqa: E402
from train30 import stratified_split          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://127.0.0.1:8000/api"
SEED = 42


def login():
    body = json.dumps({"phone": "13800000001", "password": "123456"}).encode("utf-8")
    req = urllib.request.Request(BASE + "/auth/login", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["data"]["token"]


def post_image(token, path: Path):
    boundary = "----eval" + uuid.uuid4().hex
    data = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(BASE + "/species/recognize", data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": "Bearer " + token,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="抽查张数")
    args = ap.parse_args()

    labels = json.loads((ROOT / "output" / "labels.json").read_text(encoding="utf-8"))
    kid2name = {l["knowledge_id"]: l["name"] for l in labels}

    ds = PlantDataset(str(ROOT / "data" / "plants_indoor"))
    _, _, test_i = stratified_split(ds, (0.70, 0.15, 0.15), SEED)
    print(f"室内测试集 {len(test_i)} 张，抽查前 {args.n} 张")

    token = login()
    hit = 0
    for i in test_i[:args.n]:
        p, lab = ds.samples[i]
        true_name = labels[lab]["name"]
        resp = post_image(token, Path(p))
        d = resp.get("data") or {}
        cand = (d.get("candidates") or [{}])[0]
        got_id = cand.get("knowledgeId")
        got = kid2name.get(got_id, cand.get("species"))
        ok = got == true_name
        hit += int(ok)
        print(f"  {'OK ' if ok else 'NG '} 真值={true_name:8s} 预测={got:8s} "
              f"conf={cand.get('confidence')} isMock={d.get('isMock')}")
    print(f"\n线上命中 {hit}/{args.n} = {hit / args.n:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
