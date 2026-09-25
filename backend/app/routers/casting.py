"""角色选角接口：维护角色，覆盖试镜排期、定角确认、候选调整与定角追踪视图。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.casting import CastingService

router = APIRouter(prefix="/api/casting", tags=["角色选角"])

service = CastingService()

LIST_FIELDS = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]
STATUSES = ["待试镜", "试镜中", "已定角", "已换角"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按角色编号检索"),
    status: str | None = Query(default=None, description="待试镜、试镜中、已定角、已换角"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按角色编号与状态过滤角色选角列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/tracking", response_model=dict)
def tracking_view(
    keyword: str | None = Query(default=None, description="按角色编号检索"),
    status: str | None = Query(default=None, description="待试镜、试镜中、已定角、已换角"),
) -> dict[str, Any]:
    """定角追踪视图：每个角色的候选名单、试镜排期、定角记录与流转时间线。"""
    items = service.tracking(keyword=keyword, status=status)
    return {"items": items, "total": len(items)}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出角色选角清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "casting", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条角色明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"角色 {entry_id} 不存在或已归档")
    return entry


@router.get("/{entry_id}/tracking", response_model=dict)
def entry_tracking(entry_id: int) -> dict[str, Any]:
    """单个角色的定角追踪详情：候选名单、试镜排期、定角记录与流转时间线。"""
    item = service.tracking_one(entry_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"角色 {entry_id} 不存在或已归档")
    return item


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条角色，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="角色已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条角色执行安排试镜、取消试镜、确认定角、更换演员、调整候选。

    状态只能沿 待试镜 → 试镜中 → 已定角 流转，越级或不合法的动作会被拦下并说明原因；
    重复确认定角、重复取消试镜不会产生第二条结果。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
