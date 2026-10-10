"""生成「品种×症状」专属建议的 SQL（42 品种 × 6 症状 = 252 条）。

设计
----
写进 `symptom_dict`，用新增的 `knowledge_id` 区分：
    knowledge_id IS NULL   → 通用建议（原有 10 条，兜底）
    knowledge_id IS NOT NULL → 该品种专属建议
查询侧「品种专属优先、通用兜底」，见 FrontService.lookupSymptomAdvice。

knowledge_id 用**子查询按品种名解析**，不硬编码 id —— 品种 id 依赖插入顺序，
硬编码会在库重建后错位。

用法:
    PYTHONUTF8=1 python -u gen_species_advice.py            # 写到 db/species_advice_data.sql
    PYTHONUTF8=1 python -u gen_species_advice.py --check    # 只校验覆盖度，不写文件
"""

import argparse
import json
import sys
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))

from advice_part1 import ADVICE as A1            # noqa: E402
from advice_part2 import ADVICE as A2            # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SPECIES_FILE = ML_DIR / "species.json"
SPECIES_IDS = ML_DIR.parent / "data" / "species_ids.json"
OUT_SQL = ML_DIR.parent.parent / "绿植智能养护系统" / "plant-manage" / "db" / "species_advice_data.sql"

# 症状码 → (展示名, 分类, 排序)。前 5 个与 symptom_dict 通用行的口径一致；
# healthy 是新码（通用字典里原本没有「健康」文案，因为健康不出病害建议）。
CODES = ["healthy", "leaf_spot_brown", "spider_mite", "leaf_spot_white",
         "rust", "yellowing_whole"]
META = {
    "healthy":         ("健康",       "保健",   10),
    "leaf_spot_brown": ("叶斑(褐色)", "病斑",    0),
    "spider_mite":     ("红蜘蛛",     "虫害",    8),
    "leaf_spot_white": ("叶斑(白色)", "病斑",    2),
    "rust":            ("锈病",       "病斑",    9),
    "yellowing_whole": ("黄化(全叶)", "生理性",  3),
}


def sql_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def plain(s: str) -> str:
    """去掉 markdown 加粗记号。

    小程序是纯文本渲染（diagnose.wxml 用的是 {{report.cause}}，不走 markdown），
    正文里写 **xxx** 会原样显示出星号。强调改用「」——与库里原有文案的写法一致。
    """
    return s.replace("**", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验覆盖度")
    ap.add_argument("--out", default=str(OUT_SQL))
    args = ap.parse_args()

    advice = {}
    for d in (A1, A2):
        for k, v in d.items():
            if k in advice:
                raise SystemExit(f"[错误] 品种重复: {k}")
            advice[k] = v

    species = list(json.loads(SPECIES_FILE.read_text(encoding="utf-8"))["classes"].keys())

    # ---------- 校验 ----------
    print("=" * 74)
    print("覆盖度校验")
    print("=" * 74)
    problems = []
    missing_in_advice = [s for s in species if s not in advice]
    extra_in_advice = [s for s in advice if s not in species]
    if missing_in_advice:
        problems.append(f"这些品种没写建议: {missing_in_advice}")
    if extra_in_advice:
        problems.append(f"建议里有 species.json 之外的品种: {extra_in_advice}")

    for sp, m in advice.items():
        miss = [c for c in CODES if c not in m]
        if miss:
            problems.append(f"{sp} 缺症状码: {miss}")
        for c, v in m.items():
            if c not in CODES:
                problems.append(f"{sp} 有未知症状码: {c}")
            elif (not isinstance(v, (tuple, list))) or len(v) != 3 or not all(v):
                problems.append(f"{sp}.{c} 字段不完整（应为 3 段非空）")

    total = len(species) * len(CODES)
    print(f"  species.json 品种数   : {len(species)}")
    print(f"  已写建议的品种数      : {len(advice)}")
    print(f"  应覆盖条目            : {len(species)} x {len(CODES)} = {total}")
    print(f"  实际条目              : {sum(len(m) for m in advice.values())}")

    if species_ids_ok := SPECIES_IDS.is_file():
        ids = json.loads(SPECIES_IDS.read_text(encoding="utf-8"))
        no_id = [s for s in species if s not in ids]
        print(f"  species_ids.json 覆盖 : {'齐全' if not no_id else f'缺 {no_id}'}")
        if no_id:
            problems.append(f"species_ids.json 缺映射: {no_id}")
    else:
        print(f"  species_ids.json      : 不存在 {SPECIES_IDS}")

    if problems:
        print("\n[校验失败]")
        for p in problems:
            print("  *", p)
        raise SystemExit(1)
    print("\n[校验通过] 覆盖完整")

    if args.check:
        return

    # ---------- 生成 SQL ----------
    lines = [
        "-- =============================================================================",
        "-- 品种×症状 专属建议（自动生成，请勿手改 —— 改 ml/advice_part1.py / advice_part2.py）",
        f"-- 生成器：ml/gen_species_advice.py    覆盖 {len(species)} 品种 × {len(CODES)} 症状 = {total} 条",
        "-- 依赖：先跑 db/species_advice_schema.sql（加 knowledge_id 列与 (code, knowledge_id) 唯一键）",
        "-- 幂等：INSERT ... ON DUPLICATE KEY UPDATE，可重复执行",
        "-- =============================================================================",
        "",
        "INSERT INTO `symptom_dict`",
        "  (`code`, `knowledge_id`, `label`, `category`, `sort_order`,",
        "   `cause_analysis`, `urgent_action`, `long_term_advice`)",
        "VALUES",
    ]
    rows = []
    for sp in species:
        kid = f"(SELECT `knowledge_id` FROM `plant_knowledge` WHERE `plant_name` = '{sql_escape(sp)}')"
        for c in CODES:
            label, cat, order = META[c]
            cause, urgent, long = (plain(x) for x in advice[sp][c])
            rows.append(
                f"  ('{c}', {kid}, '{sql_escape(label)}', '{cat}', {order},\n"
                f"   '{sql_escape(cause)}',\n"
                f"   '{sql_escape(urgent)}',\n"
                f"   '{sql_escape(long)}')"
            )
    lines.append(",\n".join(rows))
    lines += [
        "AS new_adv",
        "ON DUPLICATE KEY UPDATE",
        "  `label`            = new_adv.`label`,",
        "  `category`         = new_adv.`category`,",
        "  `sort_order`       = new_adv.`sort_order`,",
        "  `cause_analysis`   = new_adv.`cause_analysis`,",
        "  `urgent_action`    = new_adv.`urgent_action`,",
        "  `long_term_advice` = new_adv.`long_term_advice`;",
        "",
        "SELECT COUNT(*) AS 品种专属条数 FROM `symptom_dict` WHERE `knowledge_id` IS NOT NULL;",
        "",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n已写 {out}（{total} 条）")


if __name__ == "__main__":
    main()
