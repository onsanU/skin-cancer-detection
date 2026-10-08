#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成演示兜底存档 —— 真跑一遍现场要执行的操作，把输出存成 txt
现场服务挂了时，直接念存档内容

更新: 包含集成推理 + 7 类类型参考
"""
import json
import os
import subprocess
import time

PROJ = "/mnt/d/Project/JXprojiect/Hermes-project/project/皮肤癌图像系统"
OUT = os.path.join(PROJ, "交付文件", "演示存档")
BASE = "http://127.0.0.1:8000"
TEST_DATA = os.path.join(PROJ, "dataset", "processed_v2_full", "test")


def sh(cmd, timeout=90):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def w(name, content):
    """清理工具输出中的控制字符后写入"""
    cleaned = "".join(ch for ch in content if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(cleaned)
    print(f"  {name}  ({len(cleaned)} 字符)")


os.makedirs(OUT, exist_ok=True)
lines = []
lines.append("=" * 78)
lines.append("皮肤癌图像检测系统 —— 演示存档")
lines.append(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
lines.append("=" * 78)
lines.append("")


def step(n, title, content):
    lines.append("-" * 78)
    lines.append(f"【步骤 {n}】{title}")
    lines.append("-" * 78)
    lines.append(content.rstrip())
    lines.append("")


print("生成演示存档...")

# ---- 1. 健康检查 ----
out = sh(f'curl -s --max-time 20 {BASE}/api/health')
w("health.txt", out)
try:
    d = json.loads(out)
    m = d["model"]
    step(1, "服务健康检查", f"""status      : {d.get('status')}
模型就绪    : {m.get('ready')}
推理后端    : {m.get('backend')}
集成模式    : {m.get('ensemble')}（{m.get('ensemble_size')} 个模型）
集成成员    : {', '.join(m.get('ensemble_members', []))}
默认阈值    : {m.get('default_threshold')}
设备        : {m.get('device')}
模型加载耗时: {m.get('load_time_s')}s""")
except Exception as e:
    step(1, "服务健康检查", f"(解析失败: {e})\n{out[:400]}")

# ---- 2. 模型信息（含 7 类）----
out = sh(f'curl -s --max-time 20 {BASE}/api/model/info')
w("model_info.txt", out)
try:
    d = json.loads(out)
    m, t = d["model"], d.get("type_model", {})
    step(2, "模型信息", f"""【主模型】{m.get('arch')}
  后端      : {m.get('backend')}
  集成      : {m.get('ensemble')}（{m.get('ensemble_size')} 个）
  输入尺寸  : {m.get('img_size')}
  默认阈值  : {m.get('default_threshold')}

【7 类类型模型（辅助）】
  就绪      : {t.get('ready')}
  后端      : {t.get('backend')}
  类别数    : {t.get('num_classes')}
  加载耗时  : {t.get('load_time_s')}s""")
except Exception as e:
    step(2, "模型信息", f"(解析失败: {e})\n{out[:400]}")

# ---- 3. 7 类定义 ----
out = sh(f'curl -s --max-time 20 {BASE}/api/model/types')
w("types.txt", out)
try:
    d = json.loads(out)
    rows = "\n".join(f"  {c['code']:<7} {c['name']:<16} [{c['group']}]"
                     for c in d["classes"])
    step(3, "七类病变类型定义", f"""类别数量  : {len(d['classes'])}
模型准确率: {d['model_accuracy']}

{rows}

免责声明:
  {d.get('disclaimer', '')}""")
except Exception as e:
    step(3, "七类病变类型定义", f"(解析失败: {e})")

# ---- 4. 阈值预设 ----
out = sh(f'curl -s --max-time 20 {BASE}/api/thresholds')
w("thresholds.txt", out)
try:
    d = json.loads(out)
    rows = []
    for k, v in d.get("presets", {}).items():
        rows.append(f"  {v.get('name', k):<10} 阈值={v.get('value'):<5}  {v.get('desc', '')}")
    if rows:
        rows.append(f"\n  默认阈值: {d.get('default')}")
        rows.append(f"  说明    : {d.get('note', '')}")
    step(4, "工作模式（阈值预设）", "\n".join(rows) if rows else out[:300])
except Exception as e:
    step(4, "工作模式", f"(解析失败: {e})")

# ---- 5. 真实检测（良性样本，展示集成+7类）----
tokens = {}
for folder, label_cn in [("benign", "良性样本"), ("malignant", "恶性样本")]:
    files = sh(f'ls "{TEST_DATA}/{folder}"/*.jpg 2>/dev/null | head -1').strip()
    if not files:
        continue
    img = files.split("\n")[0]
    name = os.path.basename(img)

    # 注册：返回体里直接带 token，用它即可（避免再次登录）
    # 注意：curl 命令必须单行，多行 f-string 会把 -o 参数切断
    uname = f"demo_{int(time.time())}"
    reg_cmd = (f'curl -s --max-time 20 -X POST {BASE}/api/auth/register '
               f'-H "Content-Type: application/json" '
               f'-d \'{{"username":"{uname}","password":"Demo123456","email":"{uname}@demo.com"}}\' '
               f'-o /tmp/demo_reg.json')
    sh(reg_cmd)
    token = ""
    try:
        with open("/tmp/demo_reg.json", encoding="utf-8") as f:
            token = json.load(f).get("token", "")
    except Exception:
        pass

    # 若注册未带回 token，则登录获取（字段名为 token，非 access_token）
    if not token:
        login_cmd = (f'curl -s --max-time 20 -X POST {BASE}/api/auth/login '
                     f'-H "Content-Type: application/json" '
                     f'-d \'{{"username":"{uname}","password":"Demo123456"}}\' '
                     f'-o /tmp/demo_login.json')
        sh(login_cmd)
        try:
            with open("/tmp/demo_login.json", encoding="utf-8") as f:
                token = json.load(f).get("token", "")
        except Exception:
            pass

    hdr = f'-H "Authorization: Bearer {token}"' if token else ""
    out = sh(f'curl -s --max-time 60 -X POST {BASE}/api/predict '
             f'{hdr} -F "file=@{img}" -F "note=演示存档"')
    w(f"detect_{folder}.txt", out)

    try:
        d = json.loads(out)
        r = d["result"]
        tr = d.get("type_reference") or {}
        topk = tr.get("topk", [])
        gs = tr.get("group_sum", {})

        body = f"""文件      : {name}
主结论    : {r['label_cn']}（{r['label']}）
置信度    : {r['probability']:.4f}
恶性概率  : {r['malignant_prob']:.4f}
良性概率  : {r['benign_prob']:.4f}
判定阈值  : {r['threshold']}
推理模式  : {r.get('mode', '单模型')}
推理耗时  : {r['infer_ms']}ms
记录 ID   : {d.get('record_id')}"""

        if topk:
            body += "\n\n类型参考（仅供参考）:\n"
            for i, t in enumerate(topk, 1):
                body += f"  {i}. {t['name']:<16} {t['prob']*100:>5.1f}%  [{t['group']}]\n"
            body += f"\n分组汇总: 良性={gs.get('benign', 0)*100:.1f}%  " \
                    f"恶性={gs.get('malignant', 0)*100:.1f}%"
            body += f"\n\n⚠️ {tr.get('disclaimer', '')}"

        adv = d.get("advice", {})
        if adv:
            body += f"\n\n健康建议: {adv.get('title', '')}\n  {adv.get('text', '')}"

        step(5 if folder == "benign" else 6,
             f"真实检测演示 —— {label_cn}", body)
    except Exception as e:
        step(5 if folder == "benign" else 6, f"检测 {label_cn}", f"(解析失败: {e})\n{out[:400]}")

# ---- 7. 阈值对比（同一样本不同阈值）----
files = sh(f'ls "{TEST_DATA}/malignant"/*.jpg 2>/dev/null | head -1').strip()
if files:
    img = files.split("\n")[0]
    name = os.path.basename(img)
    rows = []
    for thr, label in [(0.28, "筛查模式"), (0.51, "平衡模式（默认）")]:
        out = sh(f'curl -s --max-time 60 -X POST {BASE}/api/predict '
                 f'-F "file=@{img}" -F "threshold={thr}"')
        try:
            d = json.loads(out)
            r = d["result"]
            rows.append(f"  阈值 {thr}（{label:<10}）: {r['label_cn']}  "
                        f"恶性概率={r['malignant_prob']:.4f}  置信度={r['probability']:.4f}")
        except Exception as e:
            rows.append(f"  阈值 {thr}: 解析失败 {e}")

    step(7, "阈值对比演示（同一样本）",
         f"样本: {name}（真实标签：恶性）\n\n" + "\n".join(rows) +
         "\n\n说明：同一张图在不同阈值下可得到不同判定。\n"
         "      筛查模式牺牲少量准确率以降低漏诊率，符合医疗筛查原则。")

w("demo_output.txt", "\n".join(lines))

# ---- INDEX ----
idx = ["演示存档索引", "=" * 60, "",
       "本目录包含系统真实运行的输出记录，服务故障时可直接使用。", ""]
for fn in sorted(os.listdir(OUT)):
    if fn == "INDEX.txt":
        continue
    size = os.path.getsize(os.path.join(OUT, fn))
    idx.append(f"  {fn:<24} {size:>7} 字节")
idx += ["", "主要文件说明：", "  demo_output.txt    完整演示流程（7 个步骤，推荐阅读）",
        "  health.txt         服务健康检查原始响应",
        "  model_info.txt     模型信息（集成 + 7类）",
        "  types.txt          七类病变类型定义",
        "  thresholds.txt     工作模式阈值预设",
        "  detect_benign.txt  良性样本检测原始响应",
        "  detect_malignant.txt 恶性样本检测原始响应"]
w("INDEX.txt", "\n".join(idx))

print("\n演示存档生成完成")
print(f"输出目录: {OUT}")
