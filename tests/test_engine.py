from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from roundtable.config import Settings
from roundtable.engine import QueueFullError, RoundtableEngine
from roundtable.models import MeetingRequest
from roundtable.skills import ROLE_SPECS, SkillCatalog
from roundtable.storage import MeetingStore


def make_skills(root: Path):
    for role in ROLE_SPECS:
        folder = root / role["skill_id"]
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {role['skill_id']}\ndescription: A bounded review skill.\n---\nReview only your professional domain.\n", encoding="utf-8")


def answer(**overrides):
    return {"summary": "专业评审意见", "stance": "approve", "proposal": "", "concerns": [],
            "recommendations": [], "resolved_issue_ids": [], "skill_ids": [], "usage": {}, **overrides}


class ScriptedProvider:
    def __init__(self, behavior=None, delay=0):
        self.behavior = behavior
        self.delay = delay
        self.calls = []
        self.active = 0
        self.peak = 0
        self.entered = asyncio.Event()

    async def generate(self, *, role, context):
        self.calls.append((role["id"], context))
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.entered.set()
        try:
            await asyncio.sleep(self.delay)
            if self.behavior:
                result = self.behavior(role, context)
                if result is not None:
                    return result
            return answer(proposal="首版方案" if context["phase"] == "opening" else "")
        finally:
            self.active -= 1

    async def check(self):
        return {"ok": True, "mode": "simulation", "message": "测试夹具"}

    async def aclose(self):
        pass


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_skills(self.root / "skills")
        self.settings = Settings(data_dir=self.root, skills_dir=self.root / "skills", simulation_delay_seconds=0)
        self.store = MeetingStore(self.root / "test.sqlite3")
        self.engine = None

    async def asyncTearDown(self):
        if self.engine:
            await self.engine.close()
        self.store.close()
        self.tmp.cleanup()

    def setup_engine(self, provider):
        self.engine = RoundtableEngine(self.settings, self.store, provider, SkillCatalog(self.settings.skills_dir))
        return self.engine

    async def run_meeting(self, provider, **kwargs):
        engine = self.setup_engine(provider)
        created = engine.create(MeetingRequest(topic="采集奖励与重复领奖评审", **kwargs))
        await engine.wait_idle()
        return self.store.get(created["id"])

    async def test_order_and_shared_draft(self):
        provider = ScriptedProvider()
        meeting = await self.run_meeting(provider)
        self.assertEqual(meeting["status"], "completed")
        self.assertEqual(meeting["current_round"], 3)
        self.assertEqual([role for role, context in provider.calls],
                         ["host"] + ["planner", "balance", "engineer", "reviewer", "host"] * 3)
        self.assertEqual({context["proposal"] for _, context in provider.calls if context["phase"] == "review"}, {"首版方案"})
        self.assertIsNone(meeting["metrics"]["input_tokens"])
        self.assertIn("规则模拟", meeting["final_report"])
        self.assertTrue(all(turn["skill_sha256"] for turn in meeting["turns"]))

    async def test_fourth_round_when_third_round_raises_issue(self):
        def behavior(role, context):
            if role["id"] == "planner" and context["round"] == 3:
                return answer(stance="revise", concerns=[{"title": "第三轮新问题", "detail": "需要再核验", "severity": "major"}])
            if role["id"] == "planner" and context["round"] == 4:
                return answer(resolved_issue_ids=[context["issues"][0]["id"]])
        provider = ScriptedProvider(behavior)
        meeting = await self.run_meeting(provider, max_rounds=4)
        self.assertEqual(meeting["status"], "completed")
        self.assertEqual(meeting["current_round"], 4)
        self.assertEqual(len(provider.calls), 21)
        self.assertEqual(meeting["issues"][0]["status"], "resolved")

    async def test_four_round_limit_keeps_unresolved_issue(self):
        def behavior(role, context):
            if role["id"] == "planner" and context["round"] == 1:
                return answer(stance="revise", concerns=[{"title": "未解决问题", "detail": "仍需人工判断", "severity": "major"}])
        provider = ScriptedProvider(behavior)
        meeting = await self.run_meeting(provider, max_rounds=4)
        self.assertEqual(meeting["status"], "needs_review")
        self.assertEqual(meeting["current_round"], 4)
        self.assertEqual(len(provider.calls), 21)
        self.assertEqual(meeting["issues"][0]["status"], "open")

    async def test_explicit_owner_resolution_and_second_round(self):
        def behavior(role, context):
            if role["id"] == "engineer" and context["round"] == 1:
                return answer(stance="revise", concerns=[{"title": "重复领奖", "detail": "缺少幂等检查", "severity": "major"}])
            if role["id"] == "engineer" and context["round"] == 2:
                return answer(summary="第二版引入领取流水唯一键，方案层面已回应。", resolved_issue_ids=[context["issues"][0]["id"]])
            if context["phase"] == "synthesis" and context["round"] == 1:
                return answer(stance="revise", proposal="第二版：服务端校验与领取流水唯一键。")
        meeting = await self.run_meeting(ScriptedProvider(behavior))
        self.assertEqual(meeting["status"], "completed")
        self.assertEqual(meeting["current_round"], 3)
        self.assertEqual(meeting["issues"][0]["status"], "resolved")
        self.assertEqual(meeting["issues"][0]["resolved_round"], 2)
        self.assertIn("唯一键", meeting["issues"][0]["resolution"])

    async def test_host_cannot_override_open_objections(self):
        def behavior(role, context):
            if role["id"] == "planner" and context["round"] == 1:
                return answer(stance="revise", concerns=[{"title": "目标不明", "detail": "玩家目的未定义", "severity": "minor"}])
        meeting = await self.run_meeting(ScriptedProvider(behavior), max_rounds=3)
        self.assertEqual(meeting["status"], "needs_review")
        self.assertEqual(meeting["issues"][0]["status"], "open")

    async def test_foreign_resolution_is_ignored(self):
        def behavior(role, context):
            if role["id"] == "engineer" and context["round"] == 1:
                return answer(stance="revise", concerns=[{"title": "状态冲突", "detail": "多人同时领取", "severity": "blocker"}])
            if role["id"] == "reviewer":
                return answer(resolved_issue_ids=["I001"])
        meeting = await self.run_meeting(ScriptedProvider(behavior), max_rounds=3)
        self.assertEqual(meeting["status"], "needs_review")
        self.assertEqual(meeting["issues"][0]["status"], "open")
        self.assertTrue(any(event["type"] == "resolution_ignored" for event in meeting["events"]))

    async def test_final_draft_change_requires_re_review(self):
        def behavior(role, context):
            if context["phase"] == "synthesis":
                return answer(proposal=context["proposal"] + " 新增未经审阅的规则。")
        meeting = await self.run_meeting(ScriptedProvider(behavior), max_rounds=3)
        self.assertEqual(meeting["status"], "needs_review")
        self.assertTrue(any(event["type"] == "draft_changed" for event in meeting["events"]))

    async def test_revision_vote_alone_prevents_consensus(self):
        def behavior(role, context):
            if role["id"] == "balance":
                return answer(stance="revise", summary="需要进一步提供收益范围。")
        meeting = await self.run_meeting(ScriptedProvider(behavior), max_rounds=3)
        self.assertEqual(meeting["status"], "needs_review")

    async def test_serial_inference_across_multiple_meetings(self):
        provider = ScriptedProvider(delay=0.002)
        engine = self.setup_engine(provider)
        meetings = [engine.create(MeetingRequest(topic=f"测试会议 {number}")) for number in range(3)]
        await engine.wait_idle()
        self.assertEqual(provider.peak, 1)
        self.assertTrue(all(self.store.get(item["id"])["status"] == "completed" for item in meetings))

    async def test_cancel_queued_and_running_preserves_status(self):
        provider = ScriptedProvider(delay=60)
        engine = self.setup_engine(provider)
        first = engine.create(MeetingRequest(topic="第一场等待响应"))
        second = engine.create(MeetingRequest(topic="第二场等待排队"))
        await provider.entered.wait()
        engine.cancel(second["id"])
        engine.cancel(first["id"])
        await engine.wait_idle()
        self.assertEqual(self.store.get(first["id"])["status"], "cancelled")
        self.assertEqual(self.store.get(second["id"])["status"], "cancelled")
        self.assertEqual(len(provider.calls), 1)

    async def test_recovery_never_replays_old_model_calls(self):
        engine = self.setup_engine(ScriptedProvider())
        meeting = engine.create(MeetingRequest(topic="中断恢复测试"))
        engine.cancel(meeting["id"])
        await engine.wait_idle()
        snapshot = self.store.get(meeting["id"])
        snapshot["status"] = "running"
        self.store.save(snapshot)
        self.assertEqual(engine.recover(), 1)
        self.assertEqual(self.store.get(meeting["id"])["status"], "interrupted")

    async def test_invalid_response_does_not_approve(self):
        meeting = await self.run_meeting(ScriptedProvider(lambda *_: {"summary": "invalid"}))
        self.assertEqual(meeting["status"], "failed")

    async def test_unknown_exception_does_not_leak_secret(self):
        def behavior(*_):
            raise RuntimeError("Authorization: Bearer confidential-token")
        meeting = await self.run_meeting(ScriptedProvider(behavior))
        self.assertEqual(meeting["status"], "failed")
        self.assertNotIn("confidential-token", str(meeting))

    async def test_queue_is_bounded(self):
        provider = ScriptedProvider(delay=60)
        engine = self.setup_engine(provider)
        for index in range(self.settings.max_queued_meetings):
            engine.create(MeetingRequest(topic=f"有界排队会议 {index}"))
        with self.assertRaises(QueueFullError):
            engine.create(MeetingRequest(topic="超出上限的会议"))
