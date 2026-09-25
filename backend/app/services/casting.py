"""角色选角业务规则：试镜排期、定角追踪、状态流转与幂等约束都收在这里。

状态机：待试镜 → 试镜中 → 已定角（已定角可再「更换演员」进入已换角）。
每次状态变更都会写入「流转记录」（时间 + 操作人）；确认定角与取消试镜做了幂等处理，
重复提交不会留下第二条定角记录或取消记录。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "casting"
REQUIRED_FIELDS = ["角色编号", "角色名称", "角色类型"]
OPTIONAL_FIELDS = ["候选演员", "试镜日期", "片酬区间", "签约状态", "角色说明"]

STATUS_PENDING = "待试镜"
STATUS_AUDITIONING = "试镜中"
STATUS_CAST = "已定角"
STATUS_REPLACED = "已换角"
STATUS_ORDER = [STATUS_PENDING, STATUS_AUDITIONING, STATUS_CAST, STATUS_REPLACED]
TERMINAL_STATUSES = {STATUS_CAST, STATUS_REPLACED}

AUDITION_OPEN = "已排期"
AUDITION_CANCELED = "已取消"
AUDITION_PICKED = "已入选"

ACTION_NAMES = ["安排试镜", "取消试镜", "确认定角", "更换演员", "调整候选"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _split_candidates(raw: Any) -> list[str]:
    """把「、，,/」分隔的候选文本或名单数组整理成去重后的有序名单。"""
    if isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        text = str(raw or "")
        for sep in ("、", "，", ",", "/", ";", "；"):
            text = text.replace(sep, " ")
        parts = text.split()
    names: list[str] = []
    for part in parts:
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def _operator_of(values: dict[str, Any]) -> str:
    return str(values.get("操作人") or values.get("operator") or "").strip() or "未署名"


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """补齐历史数据缺少的追踪字段；已定角的老记录补一份可读的定角记录。"""
    candidates = entry.get("候选演员列表")
    if not isinstance(candidates, list):
        candidates = _split_candidates(entry.get("候选演员"))
        entry["候选演员列表"] = candidates
    entry.setdefault("试镜排期", [])
    entry.setdefault("流转记录", [])
    entry.setdefault("定角记录", None)
    entry.setdefault("定角演员", None)
    if entry.get("status") == STATUS_CAST and not entry["定角记录"]:
        actor = candidates[0] if candidates else str(entry.get("候选演员") or "").strip() or "未记录"
        entry["定角演员"] = actor
        entry["定角记录"] = {
            "演员": actor,
            "时间": None,
            "操作人": "历史数据",
            "备注": "历史定角记录，原始时间与操作人未留存",
        }
    return entry


def _sync_candidate_text(entry: dict[str, Any]) -> None:
    entry["候选演员"] = "、".join(entry["候选演员列表"])


def _refresh_flags(entry: dict[str, Any]) -> None:
    entry["pending"] = entry.get("status") not in TERMINAL_STATUSES
    entry["abnormal"] = entry.get("status") == STATUS_REPLACED


def _record(
    entry: dict[str, Any],
    *,
    action: str,
    operator: str,
    from_status: str | None,
    to_status: str,
    note: str = "",
) -> None:
    entry["流转记录"].append({
        "时间": _now(),
        "操作人": operator,
        "动作": action,
        "从状态": from_status,
        "到状态": to_status,
        "说明": note,
    })


def _next_audition_id(entry: dict[str, Any]) -> int:
    return max((int(item.get("id", 0)) for item in entry["试镜排期"]), default=0) + 1


class CastingService:
    def __init__(self) -> None:
        for row in store.rows(MODULE):
            _normalize(row)

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [_normalize(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("角色编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _normalize(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            if values.get(field) not in (None, ""):
                entry[field] = values.get(field)
        entry["status"] = STATUS_PENDING
        entry["候选演员列表"] = _split_candidates(values.get("候选演员列表") or values.get("候选演员"))
        _sync_candidate_text(entry)
        entry["试镜排期"] = []
        entry["定角记录"] = None
        entry["定角演员"] = None
        entry["流转记录"] = []
        _refresh_flags(entry)
        _record(
            entry,
            action="登记角色",
            operator=_operator_of(values),
            from_status=None,
            to_status=STATUS_PENDING,
            note="角色登记，进入待试镜",
        )
        rows.append(entry)
        return entry, []

    def tracking(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """定角追踪视图：与选角列表同一份数据，口径一致的筛选。"""
        rows = [_normalize(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("角色编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return [self._tracking_item(row) for row in rows]

    def tracking_one(self, entry_id: int) -> dict[str, Any] | None:
        entry = self.get_entry(entry_id)
        return self._tracking_item(entry) if entry is not None else None

    @staticmethod
    def _tracking_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "角色编号": row.get("角色编号"),
            "角色名称": row.get("角色名称"),
            "角色类型": row.get("角色类型"),
            "角色说明": row.get("角色说明"),
            "status": row.get("status"),
            "候选演员列表": list(row.get("候选演员列表", [])),
            "试镜排期": [dict(item) for item in row.get("试镜排期", [])],
            "定角演员": row.get("定角演员"),
            "定角记录": dict(row["定角记录"]) if row.get("定角记录") else None,
            "流转记录": [dict(item) for item in row.get("流转记录", [])],
        }

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"角色 {entry_id} 不存在或已归档"
        _normalize(entry)
        handlers = {
            "安排试镜": self._schedule_audition,
            "取消试镜": self._cancel_audition,
            "确认定角": self._confirm_casting,
            "更换演员": self._replace_actor,
            "调整候选": self._adjust_candidates,
        }
        handler = handlers.get(action)
        if handler is None:
            return None, f"动作「{action}」不属于角色选角可执行范围"
        return handler(entry, values or {})

    def _schedule_audition(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] not in (STATUS_PENDING, STATUS_AUDITIONING):
            return None, f"角色当前为「{entry['status']}」，不能再安排试镜"
        actor = str(values.get("演员") or values.get("actor") or "").strip()
        date = str(values.get("试镜日期") or values.get("date") or "").strip()
        if not actor:
            return None, "安排试镜需要填写演员姓名"
        if not date:
            return None, "安排试镜需要填写试镜日期"
        for session in entry["试镜排期"]:
            if session.get("状态") == AUDITION_OPEN and session.get("演员") == actor and session.get("试镜日期") == date:
                return entry, f"「{actor}」{date} 的试镜已排期，未重复创建"
        operator = _operator_of(values)
        entry["试镜排期"].append({
            "id": _next_audition_id(entry),
            "演员": actor,
            "试镜日期": date,
            "状态": AUDITION_OPEN,
            "操作人": operator,
            "排期时间": _now(),
            "取消时间": None,
            "取消人": None,
        })
        if actor not in entry["候选演员列表"]:
            entry["候选演员列表"].append(actor)
            _sync_candidate_text(entry)
        previous = entry["status"]
        entry["status"] = STATUS_AUDITIONING
        entry["试镜日期"] = date
        _refresh_flags(entry)
        _record(
            entry,
            action="安排试镜",
            operator=operator,
            from_status=previous,
            to_status=STATUS_AUDITIONING,
            note=f"「{actor}」试镜日期 {date}",
        )
        return entry, f"已为「{actor}」安排 {date} 试镜"

    def _cancel_audition(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        actor = str(values.get("演员") or values.get("actor") or "").strip()
        open_sessions = [item for item in entry["试镜排期"] if item.get("状态") == AUDITION_OPEN]
        targets = [item for item in open_sessions if not actor or item.get("演员") == actor]
        if not targets:
            canceled = [
                item for item in entry["试镜排期"]
                if item.get("状态") == AUDITION_CANCELED and (not actor or item.get("演员") == actor)
            ]
            if canceled:
                return entry, "试镜此前已取消，未重复处理"
            hint = f"「{actor}」" if actor else ""
            return None, f"没有{hint}进行中的试镜安排可取消"
        if entry["status"] != STATUS_AUDITIONING:
            return None, f"角色当前为「{entry['status']}」，不能取消试镜"
        operator = _operator_of(values)
        now = _now()
        names: list[str] = []
        for session in targets:
            session["状态"] = AUDITION_CANCELED
            session["取消时间"] = now
            session["取消人"] = operator
            names.append(str(session.get("演员")))
        remaining = [item for item in entry["试镜排期"] if item.get("状态") == AUDITION_OPEN]
        previous = entry["status"]
        if not remaining:
            entry["status"] = STATUS_PENDING
        _refresh_flags(entry)
        _record(
            entry,
            action="取消试镜",
            operator=operator,
            from_status=previous,
            to_status=entry["status"],
            note=f"取消「{'、'.join(names)}」的试镜",
        )
        return entry, f"已取消「{'、'.join(names)}」的试镜"

    def _confirm_casting(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        actor = str(values.get("演员") or values.get("actor") or "").strip()
        if not actor:
            return None, "确认定角需要填写定角演员"
        record = entry.get("定角记录")
        if entry["status"] == STATUS_CAST and record:
            if record.get("演员") == actor:
                return entry, f"角色已由「{actor}」定角，重复确认未产生新记录"
            return None, f"角色已定为「{record.get('演员')}」，如需改选请走「更换演员」"
        if entry["status"] != STATUS_AUDITIONING:
            return None, f"角色当前为「{entry['status']}」，需先安排试镜再确认定角"
        candidates = entry["候选演员列表"]
        if candidates and actor not in candidates:
            return None, f"「{actor}」不在候选名单里，请先「调整候选」"
        operator = _operator_of(values)
        now = _now()
        for session in entry["试镜排期"]:
            if session.get("状态") != AUDITION_OPEN:
                continue
            if session.get("演员") == actor:
                session["状态"] = AUDITION_PICKED
            else:
                session["状态"] = AUDITION_CANCELED
                session["取消时间"] = now
                session["取消人"] = operator
        previous = entry["status"]
        entry["status"] = STATUS_CAST
        entry["定角演员"] = actor
        entry["定角记录"] = {"演员": actor, "时间": now, "操作人": operator, "备注": "试镜通过，确认定角"}
        entry["签约状态"] = "待签约"
        _refresh_flags(entry)
        _record(
            entry,
            action="确认定角",
            operator=operator,
            from_status=previous,
            to_status=STATUS_CAST,
            note=f"定角演员「{actor}」，其余进行中试镜同步取消",
        )
        return entry, f"角色已定为「{actor}」"

    def _replace_actor(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != STATUS_CAST:
            return None, f"角色当前为「{entry['status']}」，只有已定角的角色才能更换演员"
        new_actor = str(values.get("新演员") or values.get("演员") or "").strip()
        if not new_actor:
            return None, "更换演员需要填写新演员姓名"
        record = entry.get("定角记录") or {}
        old_actor = str(record.get("演员") or entry.get("定角演员") or "").strip()
        if old_actor and new_actor == old_actor:
            return entry, f"「{new_actor}」已是当前定角演员，未重复更换"
        operator = _operator_of(values)
        now = _now()
        entry["status"] = STATUS_REPLACED
        entry["定角演员"] = new_actor
        entry["定角记录"] = {
            "演员": new_actor,
            "时间": now,
            "操作人": operator,
            "备注": f"换角：原定「{old_actor or '未记录'}」",
        }
        entry["签约状态"] = "待签约"
        if new_actor not in entry["候选演员列表"]:
            entry["候选演员列表"].append(new_actor)
            _sync_candidate_text(entry)
        _refresh_flags(entry)
        _record(
            entry,
            action="更换演员",
            operator=operator,
            from_status=STATUS_CAST,
            to_status=STATUS_REPLACED,
            note=f"「{old_actor or '未记录'}」更换为「{new_actor}」",
        )
        return entry, f"角色已由「{old_actor or '未记录'}」更换为「{new_actor}」"

    def _adjust_candidates(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] in TERMINAL_STATUSES:
            return None, f"角色当前为「{entry['status']}」，候选名单已锁定"
        raw = values.get("候选演员列表")
        if raw is None:
            raw = values.get("候选演员")
        candidates = _split_candidates(raw)
        if not candidates:
            return None, "调整候选需要给出至少一名候选演员"
        before = list(entry["候选演员列表"])
        if candidates == before:
            return entry, "候选名单没有变化，未重复调整"
        operator = _operator_of(values)
        entry["候选演员列表"] = candidates
        _sync_candidate_text(entry)
        _record(
            entry,
            action="调整候选",
            operator=operator,
            from_status=entry["status"],
            to_status=entry["status"],
            note=f"候选演员：{'、'.join(before) or '（空）'} → {'、'.join(candidates)}",
        )
        return entry, f"候选演员已调整为：{'、'.join(candidates)}"
