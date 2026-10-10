"""校验推理服务里的 TTA 实现是否复现离线量到的增益（0.9170 → 0.9235）。

为什么要单独校验
----------------
离线实验（tests/eval_tta.py）里的变换是自己写的，生产代码在 `service/recognizer.py`
里又实现了一遍。两份实现只要有一点不一致（resize 尺寸、是否翻转、softmax 的轴），
增益就可能消失甚至变负，而 **/health 是看不出来的**。所以这里直接调生产类。

为什么测试集从 JSON 读、而不是用 stratified_split 现算
------------------------------------------------------
`stratified_split` 的随机数状态依赖**类的数量与顺序**（整个数据集共用一个 generator）。
一旦数据集新增了 12 个类目录，原有 30 类的切分就全变了 —— 现算出来的 test 集
与 320 模型当初评估的那 1072 张**不是同一批图**，指标不可比。

所以这里直接读 `results/error_analysis_indoor.json` 里记录的 1072 条测试项：
那就是 320 模型评估时用的同一批图（同 SEED、同数据集组成），可直接对比 0.9170/0.9235。
标签映射也改用模型自己的 labels.json，而不是已经变成 42 类的 PlantDataset。
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path("C:/Plant/plant-ai")
TEST_JSON = Path("C:/Plant/tests/results/error_analysis_indoor.json")
sys.path.insert(0, str(ROOT / "service"))

import recognizer                                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EXPECT_TTA = 0.9235
EXPECT_SINGLE = 0.9170


def main():
    print("=" * 76)
    print("生产 TTA 实现校验")
    print("=" * 76)

    items = json.loads(TEST_JSON.read_text(encoding="utf-8"))["items"]
    labels = json.loads((ROOT / "output" / "labels.json").read_text(encoding="utf-8"))
    name2idx = {x["name"]: i for i, x in enumerate(labels)}
    print(f"测试集 {len(items)} 张（取自 {TEST_JSON.name}，与 320 模型评估同一批）")
    print(f"模型 {len(labels)} 类")

    unmapped = {it["true"] for it in items if it["true"] not in name2idx}
    if unmapped:
        raise SystemExit(f"[错误] 测试集里有模型不认识的类: {unmapped}")

    rec = recognizer.PlantRecognizer()
    if rec.session is None:
        raise SystemExit("模型未加载（session 为空），无法校验")
    sess = rec.session
    size = recognizer.SPECIES_IMAGE_SIZE
    base_r = int(size * 1.14)

    def tfs_for(tta: bool):
        if tta:
            return [recognizer.build_val_transform_from_r(int(base_r * s), size)
                    for s in recognizer.TTA_SCALES]
        return [recognizer.build_val_transform(size)]

    def run(tta: bool):
        from PIL import Image
        tfs = tfs_for(tta)
        ok = 0
        for it in items:
            img = np.array(Image.open(it["image"]).convert("RGB"))
            x = np.stack([tf(image=img)["image"].numpy() for tf in tfs]).astype(np.float32)
            logits = sess.run(None, {"input": x})[0]
            probs = np.mean([recognizer._softmax(r) for r in logits], axis=0)
            ok += int(int(probs.argmax()) == name2idx[it["true"]])
        return ok / len(items)

    single, tta = run(False), run(True)

    print(f"\n{'模式':12s} {'实测':>8s} {'离线参照':>9s} {'差':>9s}")
    print("-" * 76)
    print(f"{'单视角':12s} {single:8.4f} {EXPECT_SINGLE:9.4f} {single - EXPECT_SINGLE:+9.4f}")
    print(f"{'TTA(3视角)':12s} {tta:8.4f} {EXPECT_TTA:9.4f} {tta - EXPECT_TTA:+9.4f}")
    print(f"\nTTA 增益: {tta - single:+.4f}")

    ok = True
    if abs(single - EXPECT_SINGLE) > 0.005:
        print(f"\n[警告] 单视角与离线差 {abs(single - EXPECT_SINGLE):.4f} —— 基准路径也漂了")
        ok = False
    if abs(tta - EXPECT_TTA) > 0.005:
        print(f"\n[警告] TTA 与离线差 {abs(tta - EXPECT_TTA):.4f} —— 生产实现与实验不一致")
        ok = False
    if tta <= single:
        print(f"\n[失败] TTA 无增益（{tta:.4f} <= {single:.4f}），不该开启")
        ok = False
    print("\n" + ("通过：生产 TTA 与离线一致" if ok else "未通过：请检查实现"))

    # 耗时：TTA 的代价要如实告知（批量 3 视角是一次推理，不是三次调用）
    from PIL import Image
    img = np.array(Image.open(items[0]["image"]).convert("RGB"))
    print()
    for label, tta_on in (("单视角", False), ("TTA(3视角)", True)):
        x = np.stack([tf(image=img)["image"].numpy() for tf in tfs_for(tta_on)]).astype(np.float32)
        for _ in range(3):
            sess.run(None, {"input": x})
        t0 = time.time()
        for _ in range(30):
            sess.run(None, {"input": x})
        print(f"  {label:12s} 单张推理 {1000 * (time.time() - t0) / 30:6.1f} ms")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
