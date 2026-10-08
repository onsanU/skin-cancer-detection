#!/usr/bin/env python3
"""
BCN20000 数据集下载器（走 ISIC Archive S3 官方直链）

为什么不用 Kaggle 那个 9.7GB 搬运版？
  · Kaggle 版图片名是 BCN_0000000000.jpg（改写名），
    与官方元数据的 isic_id（ISIC_0053454）【对不上】，无法打标签
  · ISIC S3 直链用的就是 isic_id 本身作为文件名 → 与元数据天然一一对应

数据源:
  · 元数据: https://www.kaggle.com/api/v1/datasets/download/manikandanrajkanna/bcn20000-metadata
            → bcn20000_metadata_2024-01-25.csv (12413 张 / 3576 病灶)
  · 图片:   https://isic-archive.s3.amazonaws.com/images/{isic_id}.jpg
            实测 HTTP 206 支持断点续传，1024x1024 JPEG 约 60-100KB

用法:
  python3 download_bcn20k.py --meta /tmp/bcn20000_metadata_2024-01-25.csv --out dataset/BCN20000_raw
  python3 download_bcn20k.py --meta ... --out ... --workers 8        # 加并发
  python3 download_bcn20k.py --meta ... --out ... --limit 100        # 先小量试水
"""
import os
import sys
import csv
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

S3_BASE = "https://isic-archive.s3.amazonaws.com/images"

_lock = threading.Lock()
_done = 0
_fail = 0
_skip = 0


def fetch_one(isic_id, outdir, retries=3, timeout=45):
    """下载单张图，返回 (isic_id, status, bytes)"""
    dst = os.path.join(outdir, f"{isic_id}.jpg")
    # 断点续传：已存在且 >1KB 就跳过
    if os.path.exists(dst) and os.path.getsize(dst) > 1024:
        return isic_id, "skip", os.path.getsize(dst)

    url = f"{S3_BASE}/{isic_id}.jpg"
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (dataset-fetch)"})
            with urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) < 1024:
                raise ValueError(f"响应太小 ({len(data)} bytes)")
            tmp = dst + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dst)          # 原子写入，避免半截文件
            return isic_id, "ok", len(data)
        except (URLError, HTTPError, ValueError, OSError) as e:
            if attempt == retries - 1:
                return isic_id, f"fail:{type(e).__name__}", 0
            time.sleep(1.5 * (attempt + 1))
    return isic_id, "fail:unknown", 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", required=True, help="元数据 CSV")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--workers", type=int, default=6, help="并发线程数（别太大，避免被限流）")
    ap.add_argument("--limit", type=int, default=0, help="只下前 N 张（0=全部，用于试水）")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    rows = list(csv.DictReader(open(args.meta, encoding="utf-8-sig")))
    ids = [(r.get("isic_id") or "").strip() for r in rows]
    ids = [i for i in ids if i]
    if args.limit > 0:
        ids = ids[:args.limit]

    total = len(ids)
    print(f"待下载: {total} 张 → {args.out}")
    print(f"并发: {args.workers} 线程")
    print("-" * 64)

    t0 = time.time()
    global _done, _fail, _skip

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, i, args.out): i for i in ids}
        for n, fut in enumerate(as_completed(futs), 1):
            iid, status, nbytes = fut.result()
            with _lock:
                if status == "ok":
                    _done += 1
                elif status == "skip":
                    _skip += 1
                else:
                    _fail += 1
                    if _fail <= 10:
                        print(f"  ❌ {iid}: {status}")
            if n % 100 == 0 or n == total:
                el = time.time() - t0
                rate = n / el if el > 0 else 0
                eta = (total - n) / rate if rate > 0 else 0
                print(f"  进度 {n}/{total} ({n/total*100:.1f}%)  "
                      f"新增{_done} 跳过{_skip} 失败{_fail}  "
                      f"{rate:.1f}张/s  ETA {eta/60:.1f}分钟")

    el = time.time() - t0
    print("-" * 64)
    print(f"完成！新增 {_done} / 跳过 {_skip} / 失败 {_fail}   耗时 {el/60:.1f} 分钟")
    # 统计实际文件
    files = [f for f in os.listdir(args.out) if f.endswith(".jpg")]
    sz = sum(os.path.getsize(os.path.join(args.out, f)) for f in files)
    print(f"目录内实际: {len(files)} 张, 合计 {sz/1024**2:.1f} MB")
    if _fail:
        print(f"\n⚠️ 有 {_fail} 张失败 —— 重跑本脚本会自动补齐（已存在的会跳过）")


if __name__ == "__main__":
    main()
