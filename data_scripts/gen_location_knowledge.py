#!/usr/bin/env python3
"""
生成「部位知识提示」数据 —— 从 HAM10000 真实统计各部位的病变构成

用途：结果页展示「该部位常见的病变类型」，作为科普参考（不参与判定）

输出：backend/app/data/location_knowledge.json
"""
import csv
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "dataset/HAM10000_raw/HAM10000_metadata.csv")
OUT = os.path.join(ROOT, "backend/app/data/location_knowledge.json")

DX_CN = {
    "mel": "黑色素瘤", "nv": "黑色素细胞痣", "bcc": "基底细胞癌",
    "bkl": "良性角化", "akiec": "光化性角化", "df": "皮肤纤维瘤",
    "vasc": "血管性病变",
}
DX_BIN = {"mel": "malignant", "bcc": "malignant", "akiec": "malignant",
          "nv": "benign", "bkl": "benign", "df": "benign", "vasc": "benign"}

# 前端部位 → HAM localization
SITE_MAP = {
    "face":    ("面部 / 耳 / 鼻", ["face", "ear", "nose"]),
    "scalp":   ("头皮 / 颈部",    ["scalp", "neck"]),
    "trunk":   ("躯干 / 胸 / 腹 / 背", ["trunk", "chest", "abdomen", "back"]),
    "arm":     ("上肢 / 手",      ["upper extremity", "hand", "acral"]),
    "leg":     ("下肢 / 足",      ["lower extremity", "foot"]),
    "genital": ("生殖器部位",     ["genital"]),
    "unknown": ("未指定 / 其它",  ["unknown"]),
}


def main():
    rows = list(csv.DictReader(open(META, encoding="utf-8-sig")))
    print(f"元数据: {len(rows)} 条")

    # 按部位聚合
    agg = defaultdict(lambda: {"n": 0, "mal": 0, "dx": Counter()})
    for r in rows:
        raw = (r.get("localization") or "unknown").strip().lower()
        dx = (r.get("dx") or "").strip()
        if dx not in DX_BIN:
            continue
        bucket = "unknown"
        for front, (_, raws) in SITE_MAP.items():
            if raw in raws:
                bucket = front
                break
        a = agg[bucket]
        a["n"] += 1
        a["dx"][dx] += 1
        if DX_BIN[dx] == "malignant":
            a["mal"] += 1

    out = {}
    print()
    print(f"{'部位':<20}{'样本':>7}{'恶性占比':>10}   主要病变类型(top3)")
    print("-" * 90)
    for front, (label, _) in SITE_MAP.items():
        a = agg.get(front)
        if not a or a["n"] == 0:
            continue
        pct_mal = a["mal"] / a["n"]
        top3 = a["dx"].most_common(3)
        top3_list = [{"dx": k, "name": DX_CN[k], "n": v,
                      "pct": round(v / a["n"], 4),
                      "group": DX_BIN[k]} for k, v in top3]
        # 该部位最高发的恶性类型
        mal_dx = [(k, v) for k, v in a["dx"].items() if DX_BIN[k] == "malignant"]
        top_mal = max(mal_dx, key=lambda kv: kv[1]) if mal_dx else None

        out[front] = {
            "label": label,
            "n": a["n"],
            "malignant_pct": round(pct_mal, 4),
            "top_types": top3_list,
            "top_malignant": ({"dx": top_mal[0], "name": DX_CN[top_mal[0]]}
                              if top_mal else None),
        }
        top3_str = ", ".join(f"{DX_CN[k]}({v/a['n']*100:.0f}%)" for k, v in top3)
        print(f"{label:<20}{a['n']:>7}{pct_mal*100:>9.1f}%   {top3_str}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {
        "source": "HAM10000 数据集统计",
        "note": "各部位病变构成比例的参考数据，仅用于科普提示，不参与判定",
        "sites": out,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print()
    print(f"已保存: {OUT}")


if __name__ == "__main__":
    main()
