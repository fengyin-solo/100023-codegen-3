"""角色选角业务规则：试镜排期、定角流转、候选调整与审计留痕都收在这里。

状态机：
    待试镜 --安排试镜--> 试镜中 --确认定角--> 已定角
                          \--取消试镜--> 已取消
    已定角/试镜中 --更换演员--> 试镜中（旧定角结果只留在流转记录里，不产生两个当前结果）

所有状态变更都追加一条流转记录（动作、前后状态、操作人、时间、备注），
重复执行终态动作按幂等处理，只回显既有结果，不重复留痕。
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "casting"
REQUIRED_FIELDS = ["角色编号", "角色名称", "角色类型"]
OPTIONAL_FIELDS = ["候选演员", "试镜日期", "片酬区间", "角色说明"]

STATUS_PENDING = "待试镜"
STATUS_AUDITION = "试镜中"
STATUS_CAST = "已定角"
STATUS_CANCELLED = "已取消"
STATUS_ORDER = [STATUS_PENDING, STATUS_AUDITION, STATUS_CAST, STATUS_CANCELLED]

ACTION_SCHEDULE = "安排试镜"
ACTION_CONFIRM = "确认定角"
ACTION_CANCEL = "取消试镜"
ACTION_REPLACE = "更换演员"
ACTION_ADJUST = "调整候选"

DEFAULT_OPERATOR = "值班管理员"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class CastingService:
    def __init__(self) -> None:
        # 种子数据来自通用样例，这里补齐选角追踪需要的字段，保证既有定角记录继续可读。
        rows = store.rows(MODULE)
        if rows and any("status_logs" in row for row in rows):
            return
        for row in rows:
                row.setdefault("候选演员", "")
                row.setdefault("试镜日期", None)
                row.setdefault("片酬区间", "")
                row.setdefault("角色说明", "")
                logs: list[dict[str, Any]] = [
                    {"action": "登记角色", "from": None, "to": STATUS_PENDING,
                     "operator": "系统初始化", "time": None, "note": "既有数据迁移"}
                ]
                status = row.get("status", STATUS_PENDING)
                if status in (STATUS_AUDITION, STATUS_CAST, STATUS_CANCELLED):
                    logs.append({"action": ACTION_SCHEDULE, "from": STATUS_PENDING,
                                 "to": STATUS_AUDITION, "operator": "系统初始化",
                                 "time": None, "note": "既有试镜安排"})
                if status == STATUS_CAST:
                    row.setdefault("定角演员", row.get("候选演员") or None)
                    row.setdefault("定角时间", None)
                    logs.append({"action": ACTION_CONFIRM, "from": STATUS_AUDITION,
                                 "to": STATUS_CAST, "operator": "系统初始化",
                                 "time": None,
                                 "note": f"定角演员：{row.get('定角演员') or '未记录'}"})
                else:
                    row.setdefault("定角演员", None)
                    row.setdefault("定角时间", None)
                    if status == STATUS_CANCELLED:
                        logs.append({"action": ACTION_CANCEL, "from": STATUS_AUDITION,
                                     "to": STATUS_CANCELLED, "operator": "系统初始化",
                                     "time": None, "note": "既有取消记录"})
                row["status_logs"] = logs
                row["pending"] = status in (STATUS_PENDING, STATUS_AUDITION)
                row["abnormal"] = status == STATUS_CANCELLED

    # ---------- 读取 ----------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            key = keyword.strip()
            rows = [
                row for row in rows
                if key in str(row.get("角色编号", "")) or key in str(row.get("角色名称", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [deepcopy(row) for row in rows[start:start + size]], total

    def tracking_view(self) -> dict[str, Any]:
        """定角追踪视图：按状态分列，附最新一条流转记录用于看板展示。"""
        rows = store.rows(MODULE)
        columns: list[dict[str, Any]] = []
        for name in STATUS_ORDER:
            cards = []
            for row in rows:
                if row.get("status") != name:
                    continue
                latest = row.get("status_logs", [])[-1] if row.get("status_logs") else None
                cards.append({
                    "id": row["id"],
                    "角色编号": row.get("角色编号"),
                    "角色名称": row.get("角色名称"),
                    "角色类型": row.get("角色类型"),
                    "候选演员": row.get("候选演员"),
                    "试镜日期": row.get("试镜日期"),
                    "定角演员": row.get("定角演员"),
                    "定角时间": row.get("定角时间"),
                    "最新进展": latest,
                })
            columns.append({"status": name, "count": len(cards), "cards": cards})
        return {
            "columns": columns,
            "total": len(rows),
            "cast_total": sum(1 for row in rows if row.get("status") == STATUS_CAST),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return deepcopy(row) if row is not None else None

    # ---------- 写入 ----------

    def create_entry(
        self, values: dict[str, Any], operator: str | None = None
    ) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            entry[field] = str(values.get(field) or "").strip() or None
        entry["status"] = STATUS_PENDING
        entry["定角演员"] = None
        entry["定角时间"] = None
        entry["pending"] = True
        entry["abnormal"] = False
        entry["status_logs"] = [{
            "action": "登记角色", "from": None, "to": STATUS_PENDING,
            "operator": operator or DEFAULT_OPERATOR, "time": _now(), "note": None,
        }]
        rows.append(entry)
        return deepcopy(entry), []

    def update_candidates(
        self,
        entry_id: int,
        candidates: str,
        *,
        note: str | None = None,
        operator: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """调整候选演员：未定角角色可改，列表与追踪视图读的是同一份数据，天然同步。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"角色 {entry_id} 不存在或已归档"
        candidates = candidates.strip()
        if not candidates:
            return None, "候选演员不能为空，至少保留一位候选人"
        if entry.get("status") == STATUS_CAST:
            return None, "角色已定角，调整人选请使用「更换演员」，避免覆盖已定角结果"
        before = entry.get("候选演员")
        entry["候选演员"] = candidates
        self._append_log(entry, ACTION_ADJUST, entry["status"], entry["status"],
                         operator, f"候选演员：{before or '（空）'} → {candidates}"
                         + (f"；{note}" if note else ""))
        return deepcopy(entry), "候选演员已调整，选角列表与追踪视图同步更新"

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        operator: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行状态动作。返回 (记录, 说明, 是否真正发生状态变更)。

        终态动作重复触发时第三个返回值为 False：只回显既有结果，不追加第二条记录。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"角色 {entry_id} 不存在或已归档", False
        values = values or {}
        actor = operator or DEFAULT_OPERATOR
        status = entry.get("status")

        if action == ACTION_SCHEDULE:
            return self._schedule(entry, values, actor)
        if action == ACTION_CONFIRM:
            return self._confirm(entry, values, actor)
        if action == ACTION_CANCEL:
            return self._cancel(entry, values, actor)
        if action == ACTION_REPLACE:
            return self._replace(entry, values, actor)
        return None, f"动作「{action}」不属于角色选角可执行范围", False

    # ---------- 具体动作 ----------

    def _schedule(
        self, entry: dict[str, Any], values: dict[str, Any], actor: str
    ) -> tuple[dict[str, Any], str, bool]:
        status = entry["status"]
        if status == STATUS_AUDITION:
            return deepcopy(entry), "试镜已在安排中，未重复创建试镜记录", False
        if status == STATUS_CAST:
            return None, "角色已定角，不能重复安排试镜；如需换人请使用「更换演员」", False
        audition_date = str(values.get("试镜日期") or entry.get("试镜日期") or "").strip() or None
        if audition_date:
            entry["试镜日期"] = audition_date
        candidates = str(values.get("候选演员") or "").strip()
        if candidates:
            entry["候选演员"] = candidates
        note = f"试镜日期：{audition_date}" if audition_date else None
        self._change_status(entry, STATUS_AUDITION, ACTION_SCHEDULE, actor, note)
        return deepcopy(entry), "已安排试镜，角色进入试镜中", True

    def _confirm(
        self, entry: dict[str, Any], values: dict[str, Any], actor: str
    ) -> tuple[dict[str, Any] | None, str, bool]:
        status = entry["status"]
        if status == STATUS_CAST:
            # 幂等：已定角再次确认只回显，绝不留下第二条定角结果。
            return deepcopy(entry), (
                f"角色已定角（{entry.get('定角演员') or '演员未记录'}），未重复记录定角结果"
            ), False
        if status != STATUS_AUDITION:
            return None, f"当前状态为「{status}」，试镜中角色才能确认定角", False
        chosen = str(values.get("定角演员") or "").strip()
        if not chosen:
            chosen = self._first_candidate(str(entry.get("候选演员") or ""))
        if not chosen:
            return None, "候选演员为空，无法确认定角；请先调整候选演员", False
        entry["定角演员"] = chosen
        entry["定角时间"] = _now()
        entry["签约状态"] = str(values.get("签约状态") or "待签约")
        self._change_status(entry, STATUS_CAST, ACTION_CONFIRM, actor, f"定角演员：{chosen}")
        return deepcopy(entry), f"已定角：{chosen}", True

    def _cancel(
        self, entry: dict[str, Any], values: dict[str, Any], actor: str
    ) -> tuple[dict[str, Any] | None, str, bool]:
        status = entry["status"]
        if status == STATUS_CANCELLED:
            return deepcopy(entry), "试镜已取消，未重复记录取消结果", False
        if status == STATUS_CAST:
            return None, "角色已定角，不能取消试镜；如需换人请使用「更换演员」", False
        if status == STATUS_PENDING:
            return None, "角色尚未安排试镜，没有可取消的试镜", False
        reason = str(values.get("note") or values.get("取消原因") or "").strip()
        self._change_status(entry, STATUS_CANCELLED, ACTION_CANCEL, actor, reason or None)
        return deepcopy(entry), "试镜已取消", True

    def _replace(
        self, entry: dict[str, Any], values: dict[str, Any], actor: str
    ) -> tuple[dict[str, Any] | None, str, bool]:
        status = entry["status"]
        if status not in (STATUS_AUDITION, STATUS_CAST):
            return None, f"当前状态为「{status}」，没有可更换的试镜或定角人选", False
        new_actor = str(values.get("候选演员") or values.get("定角演员") or "").strip()
        if not new_actor:
            return None, "请填写新的候选演员后再更换", False
        old = entry.get("定角演员") or self._first_candidate(str(entry.get("候选演员") or ""))
        entry["候选演员"] = new_actor
        was_cast = status == STATUS_CAST
        if was_cast:
            # 回到试镜中，旧定角结果只保存在流转记录里，当前结果唯一。
            entry["定角演员"] = None
            entry["定角时间"] = None
            entry["签约状态"] = None
            self._change_status(entry, STATUS_AUDITION, ACTION_REPLACE, actor,
                                f"更换演员：{old or '原人选'} → {new_actor}，重新进入试镜")
            return deepcopy(entry), f"已撤下原人选（{old or '未记录'}），{new_actor} 进入试镜", True
        self._append_log(entry, ACTION_REPLACE, STATUS_AUDITION, STATUS_AUDITION, actor,
                         f"更换候选人：{old or '原人选'} → {new_actor}")
        return deepcopy(entry), f"候选演员已更换为 {new_actor}", True

    # ---------- 辅助 ----------

    @staticmethod
    def _first_candidate(candidates: str) -> str:
        for token in candidates.replace("，", ",").replace("、", ",").replace(";", ",").split(","):
            token = token.strip()
            if token:
                return token
        return ""

    def _change_status(
        self, entry: dict[str, Any], target: str, action: str, actor: str, note: str | None
    ) -> None:
        before = entry.get("status")
        entry["status"] = target
        entry["pending"] = target in (STATUS_PENDING, STATUS_AUDITION)
        entry["abnormal"] = target == STATUS_CANCELLED
        self._append_log(entry, action, before, target, actor, note)

    @staticmethod
    def _append_log(
        entry: dict[str, Any],
        action: str,
        before: str | None,
        target: str,
        actor: str,
        note: str | None,
    ) -> None:
        entry.setdefault("status_logs", []).append({
            "action": action,
            "from": before,
            "to": target,
            "operator": actor,
            "time": _now(),
            "note": note,
        })
