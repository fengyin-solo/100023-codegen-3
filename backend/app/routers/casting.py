"""角色选角接口：维护角色与候选，覆盖安排试镜、取消试镜、确认定角、更换演员等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.casting import (
    ACTION_CANCEL,
    ACTION_CONFIRM,
    ACTION_REPLACE,
    ACTION_SCHEDULE,
    DEFAULT_OPERATOR,
    CastingService,
)

router = APIRouter(prefix="/api/casting", tags=["角色选角"])

service = CastingService()

LIST_FIELDS = ["角色编号", "角色名称", "角色类型", "候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]
STATUSES = ["待试镜", "试镜中", "已定角", "已取消"]
ACTIONS = [ACTION_SCHEDULE, ACTION_CANCEL, ACTION_CONFIRM, ACTION_REPLACE]


def _operator(payload: EntryPayload) -> str:
    return str(payload.values.get("operator") or "").strip() or DEFAULT_OPERATOR


@router.get("/tracking")
def tracking_view() -> dict[str, Any]:
    """定角追踪视图：按 待试镜/试镜中/已定角/已取消 分列，随列表数据同步。"""
    return service.tracking_view()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按角色编号或角色名称检索"),
    status: str | None = Query(default=None, description="待试镜、试镜中、已定角、已取消"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按角色编号/名称与状态过滤角色选角列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不在可选范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出角色选角清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "casting", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条角色明细（含流转记录）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"角色 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条角色，缺字段时说明原因而不是静默丢弃。"""
    operator = _operator(payload)
    entry, missing = service.create_entry(payload.values, operator)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="角色已登记", entry=entry)


@router.patch("/{entry_id}/candidates", response_model=ActionResult)
def update_candidates(entry_id: int, payload: EntryPayload) -> ActionResult:
    """调整候选演员；已定角角色需走更换演员，避免覆盖已定角结果。"""
    candidates = str(payload.values.get("候选演员") or "").strip()
    entry, message = service.update_candidates(
        entry_id,
        candidates,
        note=payload.remark,
        operator=_operator(payload),
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条角色执行状态动作；重复的终态动作幂等处理，不产生第二条结果。"""
    action = str(payload.values.get("action") or "").strip()
    if action not in ACTIONS:
        return ActionResult(
            ok=False,
            message=f"动作「{action}」不属于角色选角可执行范围，可选：{'、'.join(ACTIONS)}",
        )
    entry, message, changed = service.run_action(
        entry_id, action, operator=_operator(payload), values=payload.values
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
