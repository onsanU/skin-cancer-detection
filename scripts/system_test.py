#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统测试脚本 —— 自动化收集测试证据
================================================================
覆盖:
  1. 接口功能测试（14 个接口全覆盖）
  2. 模型性能测试（测试集 213 张完整推理）
  3. 边界与异常测试（格式/大小/权限/越权）
  4. 并发性能测试（多线程请求）
  5. 前端构建验证

输出: docs/test_report_data.json（供测试报告引用）
"""

import concurrent.futures
import json
import os
import statistics
import subprocess
import sys
import time

import requests

BASE = "http://127.0.0.1:8000"
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _resolve_test_data():
    """测试集路径：优先 WSL 本地盘（训练用副本），回退项目内 D 盘数据"""
    cands = [
        os.path.expanduser("~/skin_cancer_data/processed_v2_full/test"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "dataset", "processed_v2_full", "test"),
    ]
    for c in cands:
        if os.path.isdir(c):
            return c
    return cands[1]


TEST_DATA = _resolve_test_data()

R = {"api": [], "model": {}, "boundary": [], "concurrency": {}, "summary": {}}


def rec(category, name, passed, detail="", ms=None):
    """记录测试结果。model 类为单条 dict，其余为列表累加。"""
    item = {"name": name, "passed": passed, "detail": detail, "ms": round(ms, 1) if ms else None}
    if category == "model":
        R["model"].setdefault("checks", []).append(item)
    else:
        R.setdefault(category, []).append(item)
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def timed(fn):
    """执行并计时，返回 (结果, 毫秒, 异常信息)。requests 的 4xx 不会抛异常。"""
    t0 = time.time()
    res = None
    err = None
    try:
        res = fn()
    except Exception as ex:
        err = f"{type(ex).__name__}: {ex}"
    return res, (time.time() - t0) * 1000, err


# ==================== 1. 接口功能测试 ====================
def test_api():
    print("\n" + "=" * 70)
    print("1. 接口功能测试")
    print("=" * 70)
    s = requests.Session()
    uname = f"test_{int(time.time())}"

    # 1.1 健康检查
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/health", timeout=10))
    ok = r and r.status_code == 200 and r.json().get("status") == "ok"
    rec("api", "GET /api/health 健康检查", ok, f"model.ready={r.json()['model']['ready']}" if ok else str(e), ms)

    # 1.2 服务信息
    r, ms, e = timed(lambda: s.get(f"{BASE}/", timeout=10))
    rec("api", "GET / 服务信息", r is not None and r.status_code == 200, "", ms)

    # 1.3 注册
    r, ms, e = timed(lambda: s.post(f"{BASE}/api/auth/register", json={
        "username": uname, "email": f"{uname}@example.com",
        "password": "test123456", "full_name": "测试用户"}, timeout=15))
    ok = r and r.status_code == 200 and "token" in r.json()
    token = r.json()["token"] if ok else None
    rec("api", "POST /api/auth/register 注册", ok, f"user_id={r.json()['user']['id']}" if ok else str(e), ms)

    # 1.4 重复注册（应失败）
    r, ms, e = timed(lambda: s.post(f"{BASE}/api/auth/register", json={
        "username": uname, "email": f"{uname}@example.com", "password": "test123456"}, timeout=15))
    rec("api", "POST /api/auth/register 重复注册拦截", r is not None and r.status_code == 400, f"HTTP {r.status_code}", ms)

    # 1.5 登录
    r, ms, e = timed(lambda: s.post(f"{BASE}/api/auth/login", json={
        "username": uname, "password": "test123456"}, timeout=15))
    ok = r and r.status_code == 200 and "token" in r.json()
    if ok:
        token = r.json()["token"]
    rec("api", "POST /api/auth/login 登录", ok, "", ms)

    # 1.6 错误密码
    r, ms, e = timed(lambda: s.post(f"{BASE}/api/auth/login", json={
        "username": uname, "password": "wrongpass"}, timeout=15))
    rec("api", "POST /api/auth/login 错误密码拦截", r is not None and r.status_code == 401, f"HTTP {r.status_code}", ms)

    H = {"Authorization": f"Bearer {token}"}

    # 1.7 当前用户
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/auth/me", headers=H, timeout=10))
    ok = r and r.status_code == 200 and "user" in r.json()
    rec("api", "GET /api/auth/me 用户信息", ok, f"stats={r.json().get('stats')}" if ok else str(e), ms)

    # 1.8 无 token 访问（应 401）
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/auth/me", timeout=10))
    rec("api", "GET /api/auth/me 无token拦截", r is not None and r.status_code == 401, f"HTTP {r.status_code}", ms)

    # 1.9 模型信息
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/model/info", timeout=10))
    ok = r and r.status_code == 200
    rec("api", "GET /api/model/info 模型信息", ok,
        f"backend={r.json()['model']['backend']}" if ok else str(e), ms)

    # 1.10 阈值预设
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/thresholds", timeout=10))
    ok = r and r.status_code == 200 and len(r.json().get("presets", {})) == 3
    rec("api", "GET /api/thresholds 阈值预设", ok, "3个预设" if ok else str(e), ms)

    # 1.10b 7 类类型定义
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/model/types", timeout=10))
    ok = r is not None and r.status_code == 200 and len(r.json().get("classes", [])) == 7
    rec("api", "GET /api/model/types 7类定义", ok,
        f"{len(r.json()['classes'])}类 模型acc={r.json().get('model_accuracy')}" if ok else str(e), ms)

    # 1.10c 集成模式确认
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/model/info", timeout=10))
    if r is not None and r.status_code == 200:
        mj = r.json().get("model", {})
        tm = r.json().get("type_model", {})
        is_ens = mj.get("ensemble", False)
        ens_n = mj.get("ensemble_size", 0)
        rec("api", "集成模式状态", True,
            f"集成={is_ens} 成员={ens_n}个 阈值={mj.get('default_threshold')}", ms)
        rec("api", "7类模型状态", tm.get("ready", False),
            f"ready={tm.get('ready')} classes={tm.get('num_classes')} "
            f"err={tm.get('load_error','') or '(无)'}", ms)
    else:
        rec("api", "集成模式状态", False, str(e), ms)
        rec("api", "7类模型状态", False, str(e), ms)

    # 1.11 图像检测（同时校验类型参考）
    img = os.path.join(TEST_DATA, "malignant", "ISIC_0024432.jpg")
    if not os.path.isfile(img):
        import glob
        cand = glob.glob(os.path.join(TEST_DATA, "malignant", "*.jpg"))
        img = cand[0] if cand else None

    if img:
        with open(img, "rb") as f:
            r, ms, e = timed(lambda: s.post(f"{BASE}/api/predict", headers=H,
                                            files={"file": ("t.jpg", f, "image/jpeg")},
                                            data={"note": "自动化测试"}, timeout=60))
        ok = r is not None and r.status_code == 200 and "result" in r.json()
        rec("api", "POST /api/predict 图像检测", ok,
            f"{r.json()['result']['label_cn']} p={r.json()['result']['probability']:.4f} "
            f"mode={r.json()['result'].get('mode','单模型')}" if ok else str(e), ms)
        rec_id = r.json().get("record_id") if ok else None

        # 类型参考信息校验
        if ok:
            tr = r.json().get("type_reference")
            if tr and tr.get("top1"):
                t1 = tr["top1"]
                n_topk = len(tr.get("topk", []))
                gs = tr.get("group_sum", {})
                rec("api", "类型参考信息返回", True,
                    f"Top1={t1['name']}({t1['prob']:.2f}) TopK={n_topk} "
                    f"良性={gs.get('benign',0):.2f}/恶性={gs.get('malignant',0):.2f}", ms)
            else:
                rec("api", "类型参考信息返回", False,
                    "未返回 type_reference（ENABLE_TYPE_PREDICT=False 时属预期）", ms)
    else:
        rec_id = None
        rec("api", "POST /api/predict 图像检测", False, "测试图未找到")

    # 1.12 历史列表
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/records?limit=5", headers=H, timeout=10))
    ok = r and r.status_code == 200 and "items" in r.json()
    rec("api", "GET /api/records 历史列表", ok, f"total={r.json().get('total')}" if ok else str(e), ms)

    # 1.13 筛选
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/records?label=malignant", headers=H, timeout=10))
    rec("api", "GET /api/records 按结果筛选", r is not None and r.status_code == 200, "", ms)

    # 1.14 统计
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/records/stats", headers=H, timeout=10))
    ok = r and r.status_code == 200 and "total" in r.json()
    rec("api", "GET /api/records/stats 统计", ok, str(r.json()) if ok else str(e), ms)

    # 1.15 单条详情
    if rec_id:
        r, ms, e = timed(lambda: s.get(f"{BASE}/api/records/{rec_id}", headers=H, timeout=10))
        ok = r and r.status_code == 200 and "advice" in r.json()
        rec("api", "GET /api/records/{id} 记录详情", ok, "含健康建议" if ok else str(e), ms)

    # 1.16 CSV 导出
    r, ms, e = timed(lambda: s.get(f"{BASE}/api/records/export", headers=H, timeout=15))
    ok = r and r.status_code == 200 and "ID" in r.text[:200]
    rec("api", "GET /api/records/export CSV导出", ok, f"{len(r.text.splitlines())}行" if ok else str(e), ms)

    # 1.17 图片访问
    if rec_id:
        r, ms, e = timed(lambda: s.get(f"{BASE}/api/records/{rec_id}", headers=H, timeout=10))
        url = r.json().get("image_url") if r is not None else None
        if url:
            r2, ms2, e2 = timed(lambda: s.get(f"{BASE}{url}", timeout=10))
            rec("api", "GET /api/image/{name} 图片访问", r2 is not None and r2.status_code == 200, "", ms2)

    # 1.18 删除记录
    if rec_id:
        r, ms, e = timed(lambda: s.delete(f"{BASE}/api/records/{rec_id}", headers=H, timeout=10))
        rec("api", "DELETE /api/records/{id} 删除记录", r is not None and r.status_code == 200, "", ms)

    return token


# ==================== 2. 边界与异常测试 ====================
def test_boundary(token):
    print("\n" + "=" * 70)
    print("2. 边界与异常测试")
    print("=" * 70)
    s = requests.Session()
    H = {"Authorization": f"Bearer {token}"}

    # 2.1 不支持的格式
    r = s.post(f"{BASE}/api/predict", headers=H,
               files={"file": ("test.txt", b"not an image", "text/plain")}, timeout=15)
    rec("boundary", "上传 .txt 文件被拒绝", r.status_code == 400, f"HTTP {r.status_code}", None)

    # 2.2 超大文件
    big = b"0" * (11 * 1024 * 1024)
    r = s.post(f"{BASE}/api/predict", headers=H,
               files={"file": ("big.jpg", big, "image/jpeg")}, timeout=60)
    rec("boundary", "上传 11MB 文件被拒绝", r.status_code == 400, f"HTTP {r.status_code}", None)

    # 2.3 路径穿越防护
    r = s.get(f"{BASE}/api/image/..%2F..%2Fskin_cancer.db", timeout=10)
    rec("boundary", "路径穿越攻击被拦截", r.status_code in (404, 400), f"HTTP {r.status_code}", None)

    # 2.4 不存在的记录
    r = s.get(f"{BASE}/api/records/999999", headers=H, timeout=10)
    rec("boundary", "查询不存在记录返回404", r.status_code == 404, f"HTTP {r.status_code}", None)

    # 2.5 非法阈值筛选
    r = s.get(f"{BASE}/api/records?label=invalid", headers=H, timeout=10)
    rec("boundary", "非法 label 参数被拒绝", r.status_code == 400, f"HTTP {r.status_code}", None)

    # 2.6 越权访问（他人记录）
    # 注册第二个用户，尝试访问第一个用户的记录
    uname2 = f"other_{int(time.time())}"
    r = s.post(f"{BASE}/api/auth/register", json={
        "username": uname2, "email": f"{uname2}@example.com", "password": "test123456"}, timeout=15)
    if r.status_code == 200:
        H2 = {"Authorization": f"Bearer {r.json()['token']}"}
        # 先给用户1创建一条记录
        img = os.path.join(TEST_DATA, "benign", "ISIC_0024325.jpg")
        if os.path.isfile(img):
            with open(img, "rb") as f:
                r1 = s.post(f"{BASE}/api/predict", headers=H,
                            files={"file": ("t.jpg", f, "image/jpeg")}, timeout=30)
            rid = r1.json().get("record_id")
            if rid:
                r2 = s.get(f"{BASE}/api/records/{rid}", headers=H2, timeout=10)
                rec("boundary", "越权访问他人记录被拦截", r2.status_code == 404, f"HTTP {r2.status_code}", None)

    # 2.7 非法邮箱格式
    r = s.post(f"{BASE}/api/auth/register", json={
        "username": "x" * 5, "email": "not-an-email", "password": "test123456"}, timeout=15)
    rec("boundary", "非法邮箱格式被拒绝", r.status_code == 422, f"HTTP {r.status_code}", None)

    # 2.8 密码过短
    r = s.post(f"{BASE}/api/auth/register", json={
        "username": f"short{int(time.time())}", "email": f"s{int(time.time())}@x.com",
        "password": "123"}, timeout=15)
    rec("boundary", "密码过短被拒绝", r.status_code == 422, f"HTTP {r.status_code}", None)

    # 2.9 阈值等效性（自动扫描找临界样本：概率落在 0.33~0.49 之间）
    import glob as _glob
    critical = None
    for p in sorted(_glob.glob(os.path.join(TEST_DATA, "malignant", "*.jpg")))[:30]:
        with open(p, "rb") as f:
            rr = s.post(f"{BASE}/api/predict", headers=H,
                        files={"file": ("t.jpg", f, "image/jpeg")}, timeout=30)
        if rr.status_code != 200:
            continue
        if 0.33 <= rr.json()["result"]["malignant_prob"] <= 0.49:
            critical = (p, rr.json()["result"]["malignant_prob"])
            break

    if critical:
        p, prob = critical
        with open(p, "rb") as f:
            rlo = s.post(f"{BASE}/api/predict", headers=H,
                         files={"file": ("t.jpg", f, "image/jpeg")},
                         data={"threshold": "0.32"}, timeout=30)
        with open(p, "rb") as f:
            rhi = s.post(f"{BASE}/api/predict", headers=H,
                         files={"file": ("t.jpg", f, "image/jpeg")},
                         data={"threshold": "0.50"}, timeout=30)
        if rlo.status_code == 200 and rhi.status_code == 200:
            lo, hi = rlo.json()["result"], rhi.json()["result"]
            differ = lo["label"] != hi["label"]
            rec("boundary", "阈值参数实际生效", differ,
                f"临界样本({prob:.4f}) 0.32→{lo['label_cn']} / 0.50→{hi['label_cn']}", None)
        else:
            rec("boundary", "阈值参数实际生效", False, f"HTTP {rlo.status_code}/{rhi.status_code}")
    else:
        # 没有临界样本时，验证阈值被记录到响应中
        img = os.path.join(TEST_DATA, "malignant", "ISIC_0024432.jpg")
        if os.path.isfile(img):
            with open(img, "rb") as f:
                rr = s.post(f"{BASE}/api/predict", headers=H,
                            files={"file": ("t.jpg", f, "image/jpeg")},
                            data={"threshold": "0.42"}, timeout=30)
            ok = rr.status_code == 200 and abs(rr.json()["result"]["threshold"] - 0.42) < 1e-6
            rec("boundary", "阈值参数被服务端采纳", ok,
                f"回显 threshold={rr.json()['result']['threshold']}" if ok else "未采纳")


# ==================== 3. 模型性能测试 ====================
def test_model():
    print("\n" + "=" * 70)
    print("3. 模型性能测试（测试集完整推理）")
    print("=" * 70)
    s = requests.Session()
    token = s.post(f"{BASE}/api/auth/register", json={
        "username": f"perf_{int(time.time())}", "email": f"perf{int(time.time())}@x.com",
        "password": "test123456"}, timeout=15).json()["token"]
    H = {"Authorization": f"Bearer {token}"}

    import glob
    samples = []
    for cls in ["benign", "malignant"]:
        for p in sorted(glob.glob(os.path.join(TEST_DATA, cls, "*.jpg"))):
            samples.append((p, cls))

    print(f"  待测样本: {len(samples)} 张")
    y_true, y_pred, latencies = [], [], []
    t0 = time.time()
    for p, cls in samples:
        with open(p, "rb") as f:
            try:
                r = s.post(f"{BASE}/api/predict", headers=H,
                           files={"file": ("t.jpg", f, "image/jpeg")}, timeout=30)
                if r.status_code == 200:
                    d = r.json()["result"]
                    y_true.append(1 if cls == "malignant" else 0)
                    y_pred.append(1 if d["label"] == "malignant" else 0)
                    latencies.append(d["infer_ms"])
            except Exception:
                continue
    elapsed = time.time() - t0

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    n = len(y_true)
    acc = (tp + tn) / n if n else 0
    rec_ = tp / (tp + fn) if (tp + fn) else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    f1 = 2 * prec * rec_ / (prec + rec_) if (prec + rec_) else 0
    spec = tn / (tn + fp) if (tn + fp) else 0

    R["model"] = {
        "samples": n, "total_time_s": round(elapsed, 1),
        "accuracy": round(acc, 4), "malignant_recall": round(rec_, 4),
        "malignant_precision": round(prec, 4), "macro_f1": round(f1, 4),
        "specificity": round(spec, 4),
        "miss_rate": round(1 - rec_, 4),
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "latency": {
            "mean": round(statistics.mean(latencies), 1) if latencies else None,
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "min": round(min(latencies), 1) if latencies else None,
            "max": round(max(latencies), 1) if latencies else None,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 1) if latencies else None,
        },
    }
    print(f"  样本数 {n} | 准确率 {acc:.4f} | 恶性召回 {rec_:.4f} | F1 {f1:.4f}")
    print(f"  混淆矩阵: TN={tn} FP={fp} FN={fn} TP={tp}")
    print(f"  延迟: 均值{statistics.mean(latencies):.1f}ms 中位{statistics.median(latencies):.1f}ms "
          f"P95={sorted(latencies)[int(len(latencies)*0.95)]:.1f}ms")
    print(f"  总耗时 {elapsed:.1f}s")
    rec("model", f"测试集 {n} 张完整推理", True,
        f"acc={acc:.4f} recall={rec_:.4f} latency={statistics.mean(latencies):.1f}ms")


# ==================== 4. 并发测试 ====================
def test_concurrency():
    print("\n" + "=" * 70)
    print("4. 并发性能测试")
    print("=" * 70)
    import glob
    imgs = sorted(glob.glob(os.path.join(TEST_DATA, "malignant", "*.jpg")))[:20]
    if not imgs:
        return

    def one(p):
        t0 = time.time()
        try:
            with open(p, "rb") as f:
                r = requests.post(f"{BASE}/api/predict",
                                  files={"file": ("t.jpg", f, "image/jpeg")}, timeout=30)
            return (r.status_code == 200, time.time() - t0)
        except Exception:
            return (False, time.time() - t0)

    for workers in [1, 4, 8]:
        # 单线程基准用同一批图
        batch = imgs * max(1, (workers * 5) // len(imgs) + 1)
        batch = batch[: workers * 5]
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(one, batch))
        elapsed = time.time() - t0
        ok = sum(1 for s, _ in results if s)
        qps = len(batch) / elapsed
        R["concurrency"][f"{workers}_threads"] = {
            "requests": len(batch), "success": ok,
            "elapsed_s": round(elapsed, 2), "qps": round(qps, 1),
            "avg_latency_ms": round(elapsed / len(batch) * 1000, 1),
        }
        print(f"  {workers} 线程: {len(batch)} 请求, 成功 {ok}, "
              f"{elapsed:.1f}s, QPS={qps:.1f}, 平均延迟={elapsed/len(batch)*1000:.0f}ms")


# ==================== 5. 前端构建 ====================
def test_frontend():
    print("\n" + "=" * 70)
    print("5. 前端构建验证")
    print("=" * 70)
    fe = os.path.join(PROJ, "frontend")
    p = subprocess.run("npm run build", shell=True, cwd=fe,
                       capture_output=True, text=True, timeout=600)
    ok = p.returncode == 0 and "built in" in p.stdout
    out = [l for l in p.stdout.splitlines() if "dist/" in l or "built in" in l]
    R["summary"]["frontend_build"] = {"passed": ok, "output": out}
    print(f"  [{'PASS' if ok else 'FAIL'}] npm run build")
    for l in out:
        print(f"    {l}")


# ==================== 主流程 ====================
def main():
    print("=" * 70)
    print("皮肤癌图像检测系统 — 自动化系统测试")
    print("=" * 70)

    try:
        token = test_api()
    except Exception as e:
        print(f"接口测试异常: {e}")
        token = None

    if token:
        try:
            test_boundary(token)
        except Exception as e:
            print(f"边界测试异常: {e}")

    try:
        test_model()
    except Exception as e:
        print(f"模型测试异常: {e}")

    try:
        test_concurrency()
    except Exception as e:
        print(f"并发测试异常: {e}")

    try:
        test_frontend()
    except Exception as e:
        print(f"前端构建异常: {e}")

    # 汇总
    api_pass = sum(1 for t in R["api"] if t["passed"])
    bd_pass = sum(1 for t in R["boundary"] if t["passed"])
    R["summary"]["api"] = {"total": len(R["api"]), "passed": api_pass}
    R["summary"]["boundary"] = {"total": len(R["boundary"]), "passed": bd_pass}

    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    print(f"  接口功能测试: {api_pass}/{len(R['api'])} 通过")
    print(f"  边界异常测试: {bd_pass}/{len(R['boundary'])} 通过")
    if R["model"]:
        m = R["model"]
        print(f"  模型性能: 准确率 {m['accuracy']:.4f}, 恶性召回 {m['malignant_recall']:.4f}, "
              f"平均延迟 {m['latency']['mean']}ms")
    print(f"  并发测试: {len(R['concurrency'])} 组")

    total = len(R["api"]) + len(R["boundary"])
    passed = api_pass + bd_pass
    print(f"\n  总计: {passed}/{total} 通过 ({passed/total*100:.1f}%)")

    # 保存
    out_path = os.path.join(PROJ, "docs", "test_report_data.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print(f"\n测试数据已保存: {out_path}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
