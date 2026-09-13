from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .config import Settings
from .models import AgentResult, MeetingRequest, TERMINAL_STATUSES
from .reporting import render_report
from .skills import SkillCatalog
from .storage import MeetingStore

logger = logging.getLogger(__name__)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class QueueFullError(Exception):
    pass


class RoundtableEngine:
    """One global inference lane, immutable drafts per review round, explicit consensus."""
    def __init__(self, settings: Settings, store: MeetingStore, provider, catalog: SkillCatalog):
        self.settings = settings
        self.store = store
        self.provider = provider
        self.catalog = catalog
        self._lane = asyncio.Semaphore(1)
        self._tasks: dict[str, asyncio.Task] = {}
        self._states: dict[str, dict] = {}
        self._closing = False

    def recover(self) -> int:
        recovered = 0
        for meeting in self.store.all():
            if meeting["status"] in {"queued", "running"}:
                self._finish(meeting, "interrupted", "上次服务已中断。已保留发言和方案，请新建议题重新评审。")
                recovered += 1
        return recovered

    def create(self, request: MeetingRequest) -> dict:
        if self._closing or len(self._tasks) >= self.settings.max_queued_meetings:
            raise QueueFullError("当前会议队列已满，请等待已有会议结束。")
        stamp = now()
        meeting = {
            "id": uuid4().hex, "topic": request.topic, "constraints": request.constraints,
            "max_rounds": request.max_rounds, "include_reviewer": request.include_reviewer,
            "provider_mode": self.settings.provider_mode, "status": "queued",
            "created_at": stamp, "updated_at": stamp, "current_round": 0,
            "proposal": "", "final_report": "", "error": None,
            "turns": [], "issues": [], "events": [], "active_role_id": None,
            "metrics": {"turn_count": 0, "total_elapsed_ms": 0, "input_tokens": None, "output_tokens": None},
            "schema_version": 1,
        }
        self._event(meeting, "queued", "已加入圆桌队列；每次仅运行一场会议。")
        self._states[meeting["id"]] = meeting
        task = asyncio.create_task(self._run(meeting), name=f"meeting-{meeting['id']}")
        self._tasks[meeting["id"]] = task
        task.add_done_callback(lambda done, meeting_id=meeting["id"]: self._discard(meeting_id, done))
        return self.store.get(meeting["id"])

    def _discard(self, meeting_id: str, task: asyncio.Task) -> None:
        self._tasks.pop(meeting_id, None)
        self._states.pop(meeting_id, None)
        if not task.cancelled():
            error = task.exception()
            if error:
                logger.error("Meeting task failed outside its error boundary: %s", type(error).__name__)

    def cancel(self, meeting_id: str) -> dict | None:
        meeting = self._states.get(meeting_id) or self.store.get(meeting_id)
        if meeting is None:
            return None
        if meeting["status"] not in TERMINAL_STATUSES:
            self._finish(meeting, "cancelled", "用户停止会议；已保留停止前的发言与未解决分歧。")
            if task := self._tasks.get(meeting_id):
                task.cancel()
        return self.store.get(meeting_id)

    async def close(self) -> None:
        self._closing = True
        tasks = list(self._tasks.values())
        for meeting in list(self._states.values()):
            if meeting["status"] not in TERMINAL_STATUSES:
                self._finish(meeting, "interrupted", "服务正在关闭，已保留会议记录。")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.provider.aclose()

    async def wait_idle(self) -> None:
        """Join submitted tasks, also used by deterministic integration tests."""
        await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    def _event(self, meeting: dict, kind: str, message: str, **extra) -> None:
        meeting["updated_at"] = now()
        meeting["events"].append({"id": len(meeting["events"]) + 1, "type": kind,
                                  "message": message, "created_at": meeting["updated_at"], **extra})
        self.store.save(meeting)

    def _finish(self, meeting: dict, status: str, explanation: str) -> None:
        meeting["status"] = status
        meeting["active_role_id"] = None
        if status in {"failed", "interrupted", "cancelled", "needs_review"}:
            meeting["error"] = explanation
        meeting["final_report"] = render_report(meeting, transcript=False)
        self._event(meeting, status, explanation)

    def _apply_issues(self, meeting: dict, role_id: str, result: AgentResult) -> None:
        # Resolution rights stay with the specialist who raised the issue.
        for issue_id in result.resolved_issue_ids:
            issue = next((item for item in meeting["issues"] if item["id"] == issue_id), None)
            if issue and issue["owner_role_id"] == role_id and issue["status"] == "open":
                issue.update(status="resolved", resolution=result.summary, resolved_round=meeting["current_round"])
            else:
                self._event(meeting, "resolution_ignored", f"未接受 {role_id} 对 {issue_id} 的关闭：仅提出者可复核自己的未解决问题。", role_id=role_id)
        for concern in result.concerns:
            duplicate = next((issue for issue in meeting["issues"]
                              if issue["owner_role_id"] == role_id and issue["title"] == concern.title and issue["status"] == "open"), None)
            if duplicate:
                duplicate.update(detail=concern.detail, severity=concern.severity)
            else:
                meeting["issues"].append({
                    "id": f"I{len(meeting['issues']) + 1:03d}", "owner_role_id": role_id,
                    **concern.model_dump(), "status": "open", "created_round": meeting["current_round"],
                    "resolution": "", "resolved_round": None,
                })

    async def _turn(self, meeting: dict, role_id: str, phase: str, reviews: list[dict], all_approve: bool = False) -> AgentResult:
        role = self.catalog.role(role_id, self.settings.agent_ids)
        meeting["active_role_id"] = role_id
        self._event(meeting, "turn_started", f"{role['name']}开始{'整理议题' if phase == 'opening' else '汇总讨论' if phase == 'synthesis' else '评审'}。",
                    role_id=role_id, round=meeting["current_round"])
        context = {
            "meeting_id": meeting["id"], "round": meeting["current_round"], "phase": phase,
            "topic": meeting["topic"], "constraints": meeting["constraints"], "proposal": meeting["proposal"],
            "issues": [{key: item[key] for key in ("id", "owner_role_id", "title", "detail", "severity", "status")}
                       for item in meeting["issues"] if item["status"] == "open"],
            "round_reviews": reviews,
            "previous_summary": next((turn["summary"] for turn in reversed(meeting["turns"]) if turn["role_id"] == "host"), ""),
            "all_approve": all_approve,
        }
        started = time.perf_counter()
        async with asyncio.timeout(self.settings.request_timeout_seconds + 5):
            raw = await self.provider.generate(role=role, context=context)
        result = AgentResult.model_validate(raw)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        turn = {
            "id": len(meeting["turns"]) + 1, "round": meeting["current_round"], "role_id": role_id,
            "role_name": role["name"], "phase": phase, **result.model_dump(exclude={"usage"}),
            "provided_skill_id": role["skill_id"], "skill_sha256": role["skill_sha256"],
            "reference_sha256": role["reference_sha256"],
            "elapsed_ms": elapsed_ms, "created_at": now(),
        }
        meeting["turns"].append(turn)
        meeting["metrics"]["turn_count"] = len(meeting["turns"])
        meeting["metrics"]["total_elapsed_ms"] += elapsed_ms
        for key in ("input_tokens", "output_tokens"):
            value = result.usage.get(key)
            # Unknown usage is not zero. Only sum if every completed turn reports it.
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                if len(meeting["turns"]) == 1:
                    meeting["metrics"][key] = value
                elif meeting["metrics"][key] is not None:
                    meeting["metrics"][key] += value
            else:
                meeting["metrics"][key] = None
        self._apply_issues(meeting, role_id, result)
        self._event(meeting, "turn_completed", f"{role['name']}完成发言。", role_id=role_id, round=meeting["current_round"])
        return result

    async def _run(self, meeting: dict) -> None:
        try:
            async with self._lane:
                meeting["status"] = "running"
                self._event(meeting, "started", "开始规则模拟；以下内容不属于 AI 推理。" if meeting["provider_mode"] == "simulation" else "开始 OpenClaw 模型评审。")
                opening = await self._turn(meeting, "host", "opening", [])
                if not opening.proposal:
                    raise ValueError("主持者没有提供可供评审的初始方案。")
                meeting["proposal"] = opening.proposal
                self.store.save(meeting)
                specialists = ["planner", "balance", "engineer"] + (["reviewer"] if meeting["include_reviewer"] else [])
                for round_index in range(1, meeting["max_rounds"] + 1):
                    meeting["current_round"] = round_index
                    reviewed_proposal = meeting["proposal"]
                    self._event(meeting, "round_started", f"第 {round_index} 轮：所有专业角色评审同一版方案。", round=round_index)
                    reviews: list[dict] = []
                    approved = []
                    for role_id in specialists:
                        result = await self._turn(meeting, role_id, "review", reviews)
                        approved.append(result.stance == "approve" and not result.concerns)
                        # Carry this round's relevant comments, not the entire transcript.
                        reviews.append({"role_id": role_id, **result.model_dump(exclude={"usage", "proposal"})})
                    no_open_issues = not any(item["status"] == "open" for item in meeting["issues"])
                    all_approve = all(approved) and no_open_issues
                    synthesis = await self._turn(meeting, "host", "synthesis", reviews, all_approve)
                    revised = synthesis.proposal or reviewed_proposal
                    unchanged = revised.strip() == reviewed_proposal.strip()
                    meeting["proposal"] = revised
                    no_open_issues = not any(item["status"] == "open" for item in meeting["issues"])
                    if all_approve and synthesis.stance == "approve" and no_open_issues and unchanged:
                        self._finish(meeting, "completed", "模拟流程收敛；需要真实模型进一步验证。" if meeting["provider_mode"] == "simulation" else "各专业角色已认可同一版方案，当前已登记分歧全部关闭。")
                        return
                    if all_approve and not unchanged:
                        self._event(meeting, "draft_changed", "主管修改了已审阅方案，需要下一轮重新评审，不能直接视为共识。")
                    self._event(meeting, "round_completed", "仍有分歧、保留意见或新修订，继续评审。", round=round_index)
                self._finish(meeting, "needs_review", "已达到轮数上限。当前方案及所有保留意见已保存，尚未达成共识。")
        except asyncio.CancelledError:
            if meeting["status"] not in TERMINAL_STATUSES:
                self._finish(meeting, "interrupted", "执行被中断；已保留完成的发言。")
            raise
        except Exception as exc:
            # Never persist raw HTTP bodies, credentials, tracebacks or third-party exception text.
            from .providers import ProviderError
            if isinstance(exc, ProviderError):
                message = str(exc)
            elif isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
                message = "本次角色调用超时，会议已停止。请检查模型服务并调整请求超时。"
            elif isinstance(exc, ValidationError):
                message = "模型返回的评审结构不完整或不合法，会议已停止；未将其视作通过。"
            elif isinstance(exc, FileNotFoundError):
                message = "缺少项目 Skill 或参考资料，请检查项目文件是否完整。"
            elif isinstance(exc, ValueError):
                message = "返回内容无法形成有效评审方案，请检查模型结构化输出。"
            else:
                message = f"圆桌执行遇到内部错误（{type(exc).__name__}），已保留已有记录。"
            logger.warning("Meeting %s stopped: %s", meeting["id"], type(exc).__name__)
            self._finish(meeting, "failed", message)
