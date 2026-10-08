#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检测历史记录路由"""

import csv
import io
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import config, database
from ..routers.auth import get_current_user

router = APIRouter(prefix="/api/records", tags=["历史记录"])


def _row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "filename": r["filename"],
        "label": r["label"],
        "label_cn": r["label_cn"],
        "probability": r["probability"],
        "malignant_prob": r["malignant_prob"],
        "benign_prob": r["benign_prob"],
        "threshold": r["threshold"],
        "infer_ms": r["infer_ms"],
        "note": r["note"],
        "created_at": r["created_at"],
        "image_url": f"/api/image/{os.path.basename(r['stored_path'])}",
    }


@router.get("", summary="检测历史列表")
def list_records(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    label: Optional[str] = Query(None, description="筛选: benign / malignant"),
    user=Depends(get_current_user),
):
    if label and label not in config.CLASSES:
        raise HTTPException(400, f"label 必须是 {config.CLASSES} 之一")
    rows = database.list_records(user["id"], limit, offset, label)
    total = database.count_records(user["id"], label)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_row_to_dict(r) for r in rows],
    }


@router.get("/stats", summary="检测统计")
def stats(user=Depends(get_current_user)):
    return database.stats(user["id"])


@router.get("/export", summary="导出检测记录（CSV）")
def export_csv(user=Depends(get_current_user)):
    rows = database.list_records(user["id"], limit=10000, offset=0)

    buf = io.StringIO()
    buf.write("\ufeff")          # BOM，Excel 打开中文不乱码
    w = csv.writer(buf)
    w.writerow(["ID", "文件名", "检测结果", "置信度", "恶性概率", "良性概率",
                "判定阈值", "推理耗时(ms)", "备注", "检测时间"])
    for r in rows:
        w.writerow([r["id"], r["filename"], r["label_cn"], f"{r['probability']:.4f}",
                    f"{r['malignant_prob']:.4f}", f"{r['benign_prob']:.4f}",
                    r["threshold"], f"{r['infer_ms']:.1f}", r["note"], r["created_at"]])
    buf.seek(0)

    fname = f"skin_cancer_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{record_id}", summary="单条记录详情")
def get_record(record_id: int, user=Depends(get_current_user)):
    r = database.get_record(record_id, user["id"])
    if not r:
        raise HTTPException(404, "记录不存在")
    d = _row_to_dict(r)
    d["advice"] = config.ADVICE[r["label"]]
    d["disclaimer"] = config.DISCLAIMER
    return d


@router.delete("/{record_id}", summary="删除记录")
def delete_record(record_id: int, user=Depends(get_current_user)):
    r = database.get_record(record_id, user["id"])
    if not r:
        raise HTTPException(404, "记录不存在")
    # 同时删除磁盘上的图片
    try:
        if os.path.isfile(r["stored_path"]):
            os.remove(r["stored_path"])
    except Exception:
        pass
    ok = database.delete_record(record_id, user["id"])
    return {"message": "删除成功" if ok else "删除失败", "id": record_id}
