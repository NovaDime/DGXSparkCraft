from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace

import httpx

from roundtable.providers import (
    DeterministicProvider, OpenClawProvider, ProviderError, create_provider,
    parse_generation, validate_generation,
)


TOKEN = "secret-test-token-never-show"


def settings(**overrides):
    return SimpleNamespace(**{
        "provider_mode": "openclaw", "openclaw_base_url": "http://127.0.0.1:18789",
        "openclaw_token": TOKEN, "openclaw_model": "openclaw",
        "request_timeout_seconds": 180, "simulation_delay_seconds": 0,
        "max_context_chars": 24000, **overrides,
    })


def role(role_id="planner"):
    return {"id": role_id, "name": role_id, "title": "审阅者", "description": "检查本专业问题",
            "skill_id": role_id + "-skill", "skill_content": "检查目标与验收边界。", "agent_id": role_id + "-agent"}


def context(**overrides):
    return {"meeting_id": "meeting-1", "round": 1, "phase": "review", "topic": "传送玩法",
            "constraints": "不生图", "proposal": "固定提案", "issues": [], "round_reviews": [],
            "all_approve": False, **overrides}


def opinion(**overrides):
    return {"summary": "建议完整", "stance": "approve", "proposal": "固定提案", "concerns": [],
            "recommendations": [], "resolved_issue_ids": [], "skill_ids": ["planner-skill"], **overrides}


def envelope(text=None, **overrides):
    return {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text if text is not None else json.dumps(opinion(), ensure_ascii=False)}]}],
            "usage": {"input_tokens": 123, "output_tokens": 45}, **overrides}


class ParsingTests(unittest.TestCase):
    def test_plain_and_single_fenced_json_are_accepted(self):
        raw = json.dumps(opinion(), ensure_ascii=False)
        for text in (raw, "\n" + raw + "\n", "```json\n" + raw + "\n```"):
            with self.subTest(text=text[:12]):
                result = parse_generation(text)
                self.assertEqual(result["stance"], "approve")
                self.assertEqual(result["usage"], {"input_tokens": None, "output_tokens": None})

    def test_no_greedy_json_extraction(self):
        raw = json.dumps(opinion())
        cases = ["解释：" + raw, raw + "\n后记", raw + raw, "```json\n" + raw + "\n```\n结语",
                 "[]", "null", "{", '"text"', raw.replace('"summary": "', '"summary": NaN, "x": "')]
        for text in cases:
            with self.subTest(text=text[:30]), self.assertRaises(ProviderError):
                parse_generation(text)

    def test_duplicate_keys_are_rejected(self):
        raw = json.dumps(opinion())
        raw = raw[:-1] + ', "stance": "revise"}'
        with self.assertRaises(ProviderError):
            parse_generation(raw)

    def test_strict_structure_and_no_contradictory_approval(self):
        cases = [opinion(summary=""), opinion(summary=1), opinion(stance="yes"), opinion(proposal=None),
                 opinion(concerns={}), opinion(recommendations="do it"), opinion(skill_ids=[4]),
                 opinion(resolved_issue_ids=[None]), opinion(extra="not allowed"),
                 opinion(concerns=[{"title": "问题", "detail": "证据", "severity": "major"}]),
                 opinion(stance="revise", concerns=[{"title": "问题", "detail": "证据", "severity": []}]),
                 opinion(stance="revise", concerns=[{"title": "问题", "detail": "证据", "severity": "critical"}])]
        missing = opinion()
        del missing["summary"]
        cases.append(missing)
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ProviderError):
                validate_generation(payload)

    def test_host_can_preserve_proposal_with_empty_string(self):
        self.assertEqual(validate_generation(opinion(proposal=""))["proposal"], "")


class OpenClawTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.aclose()

    def provider(self, handler, **overrides):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.clients.append(client)
        return OpenClawProvider(settings(**overrides), client=client)

    async def test_actual_responses_request_and_authoritative_usage(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=envelope(json.dumps(opinion(usage={"input_tokens": 999999, "output_tokens": 999999}))))

        provider = self.provider(handler)
        result = await provider.generate(role=role(), context=context())
        request = seen[0]
        body = json.loads(request.content)
        self.assertEqual(str(request.url), "http://127.0.0.1:18789/v1/responses")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(body["model"], "openclaw/planner-agent")
        self.assertIs(body["stream"], False)
        self.assertEqual(body["max_output_tokens"], 4096)
        self.assertIn("recommendations 必须是数组", body["instructions"])
        self.assertNotIn(TOKEN, request.content.decode())
        self.assertIn("检查目标与验收边界", body["input"])
        self.assertIn("固定提案", body["input"])
        self.assertNotIn("previous_response_id", body)
        self.assertEqual(result["usage"], {"input_tokens": 123, "output_tokens": 45})

    async def test_token_budget_blocks_request_before_network(self):
        calls=[]
        provider=self.provider(lambda request: calls.append(request))
        with self.assertRaises(ProviderError) as caught:
            await provider.generate(role=role(),context=context(remaining_token_budget=1))
        self.assertEqual(caught.exception.code,"token_budget")
        self.assertEqual(calls,[])

    async def test_protocol_repair_is_charged_against_token_budget(self):
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(200,json=envelope("invalid json"))
        provider=self.provider(handler)
        with self.assertRaises(ProviderError) as caught:
            await provider.generate(role=role(),context=context(remaining_token_budget=35000))
        self.assertEqual(caught.exception.code,"token_budget")
        self.assertEqual(len(calls),1)
        self.assertGreater(caught.exception.budget_tokens,0)

    async def test_backend_model_override_preserves_agent_target(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=envelope())
        provider = self.provider(handler)
        await provider.generate(role={**role(), "model_ref": "local/two"}, context=context())
        self.assertEqual(seen[0].headers["x-openclaw-model"], "local/two")
        self.assertEqual(json.loads(seen[0].content)["model"], "openclaw/planner-agent")

    async def test_opening_request_requires_a_nonempty_initial_proposal(self):
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=envelope())
        provider = self.provider(handler)
        await provider.generate(role=role(), context=context(phase="opening", proposal=""))
        self.assertIn("opening 阶段", seen[0]["instructions"])
        self.assertIn("proposal 必须为非空字符串", seen[0]["instructions"])

    async def test_bounded_protocol_repairs_wrong_role_and_field_shapes(self):
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            if len(calls) == 1:
                result = opinion(skill_ids=["modsdk-feasibility"], resolved_issue_ids=["I001", "I002"])
            elif len(calls) == 2:
                result = opinion(skill_ids=["planner-skill"], resolved_issue_ids=["I001"], recommendations=[{"bad": "shape"}])
            else:
                result = opinion(skill_ids=["planner-skill"], resolved_issue_ids=["I001"])
            return httpx.Response(200, json=envelope(json.dumps(result, ensure_ascii=False)))
        provider = self.provider(handler)
        issues = [
            {"id": "I001", "owner_role_id": "planner", "status": "open"},
            {"id": "I002", "owner_role_id": "engineer", "status": "open"},
        ]
        result = await provider.generate(role=role(), context=context(issues=issues))
        self.assertEqual(result["skill_ids"], ["planner-skill"])
        self.assertEqual(result["resolved_issue_ids"], ["I001"])
        self.assertEqual(len(calls), 3)
        self.assertIn("上一响应未通过严格协议校验", calls[1]["instructions"])
        self.assertIn('resolved_issue_ids 只能是 [] 或 ["I001"]', calls[1]["instructions"])
        self.assertIn("上一响应未通过严格协议校验", calls[2]["instructions"])

    async def test_configurable_output_budget(self):
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=envelope())
        provider = self.provider(handler, max_output_tokens=1024)
        await provider.generate(role=role(), context=context())
        self.assertEqual(seen[0]["max_output_tokens"], 1024)

    async def test_final_message_after_progress_is_used(self):
        payload = envelope()
        payload["output"].insert(0, {"type": "message", "role": "assistant", "status": "completed",
                                     "content": [{"type": "output_text", "text": "正在检查数值。"}]})
        provider = self.provider(lambda request: httpx.Response(200, json=payload))
        result = await provider.generate(role=role(), context=context())
        self.assertEqual(result["summary"], "建议完整")

    async def test_invalid_final_message_cannot_fall_back_to_earlier_json(self):
        for final_text, final_status in (("最后还需要补充", "completed"), (json.dumps(opinion()), "incomplete")):
            payload = envelope()
            payload["output"].append({"type": "message", "role": "assistant", "status": final_status,
                                      "content": [{"type": "output_text", "text": final_text}]})
            provider = self.provider(lambda request: httpx.Response(200, json=payload))
            with self.assertRaises(ProviderError):
                await provider.generate(role=role(), context=context())

    async def test_user_scope_isolated_by_meeting_role_round_phase(self):
        users = []

        def handler(request):
            body = json.loads(request.content)
            users.append(body["user"])
            return httpx.Response(200, json=envelope(json.dumps(opinion(skill_ids=[]))))

        provider = self.provider(handler)
        await provider.generate(role=role(), context=context())
        await provider.generate(role=role(), context=context(meeting_id="meeting-2"))
        await provider.generate(role=role("balance"), context=context())
        await provider.generate(role=role(), context=context(round=2))
        await provider.generate(role=role(), context=context(phase="synthesis"))
        await provider.generate(role=role(), context=context())
        self.assertEqual(len(set(users[:5])), 5)
        self.assertEqual(users[0], users[-1])

    async def test_http_failures_are_safe_and_do_not_fallback(self):
        for status, code in [(401, "unauthorized"), (403, "forbidden"), (429, "rate_limited"),
                             (500, "upstream_error"), (503, "upstream_error"), (400, "http_error"), (404, "http_error")]:
            with self.subTest(status=status):
                provider = self.provider(lambda request: httpx.Response(status, text=TOKEN + " private-body"))
                with self.assertRaises(ProviderError) as caught:
                    await provider.generate(role=role(), context=context())
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(TOKEN, str(caught.exception))
                self.assertNotIn("private-body", str(caught.exception))
                self.assertEqual(provider.mode, "openclaw")
                check = await provider.check()
                self.assertFalse(check["ok"])
                self.assertNotIn(TOKEN, json.dumps(check))

    async def test_timeout_and_network_errors_are_safe(self):
        for error_type, code in [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection")]:
            with self.subTest(error=error_type):
                def handler(request):
                    raise error_type(TOKEN + " private-url", request=request)
                provider = self.provider(handler)
                with self.assertRaises(ProviderError) as caught:
                    await provider.generate(role=role(), context=context())
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(TOKEN, str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                check = await provider.check()
                self.assertFalse(check["ok"])
                self.assertNotIn(TOKEN, json.dumps(check))

    async def test_redirect_is_not_followed(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(307, headers={"Location": "https://unexpected.example/collect"})
        provider = self.provider(handler)
        with self.assertRaises(ProviderError):
            await provider.generate(role=role(), context=context())
        self.assertEqual(len(calls), 1)

    async def test_failed_or_incomplete_envelopes_cannot_approve(self):
        partial = envelope()
        partial["output"][0]["status"] = "incomplete"
        payloads = [envelope(status="incomplete"), envelope(status="failed"), envelope(status="in_progress"),
                    envelope(error={"message": TOKEN}), envelope(status=None), partial]
        for payload in payloads:
            with self.subTest(payload=payload):
                provider = self.provider(lambda request: httpx.Response(200, json=payload))
                with self.assertRaises(ProviderError) as caught:
                    await provider.generate(role=role(), context=context())
                self.assertEqual(caught.exception.code, "incomplete_response")
                self.assertNotIn(TOKEN, str(caught.exception))

    async def test_only_assistant_output_text_is_used(self):
        payloads = [envelope(output=[]), envelope(output_text=json.dumps(opinion()), output=[]),
                    envelope(output=[{"type": "message", "role": "user", "content": [{"type": "output_text", "text": json.dumps(opinion())}]}]),
                    envelope(output=[{"type": "function_call", "name": "do_something", "arguments": TOKEN}]),
                    envelope(output=[{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": TOKEN}]}])]
        for payload in payloads:
            with self.subTest(payload=payload):
                provider = self.provider(lambda request: httpx.Response(200, json=payload))
                with self.assertRaises(ProviderError) as caught:
                    await provider.generate(role=role(), context=context())
                self.assertNotIn(TOKEN, str(caught.exception))

    async def test_invalid_json_never_leaks_body(self):
        for body in (TOKEN, json.dumps(envelope(TOKEN)), json.dumps(envelope("prefix " + json.dumps(opinion())))):
            provider = self.provider(lambda request: httpx.Response(200, text=body))
            with self.assertRaises(ProviderError) as caught:
                await provider.generate(role=role(), context=context())
            self.assertNotIn(TOKEN, str(caught.exception))

    async def test_unknown_skills_and_other_owners_issues_rejected(self):
        issues = [{"id": "issue-1", "owner_role_id": "balance", "status": "open"}]
        for result in (opinion(skill_ids=["invented-tool"]), opinion(resolved_issue_ids=["unknown"]), opinion(resolved_issue_ids=["issue-1"])):
            provider = self.provider(lambda request: httpx.Response(200, json=envelope(json.dumps(result))))
            with self.assertRaises(ProviderError):
                await provider.generate(role=role(), context=context(issues=issues))

    async def test_own_open_issue_can_be_closed(self):
        issues = [{"id": "issue-1", "owner_role_id": "planner", "status": "open"}]
        provider = self.provider(lambda request: httpx.Response(200, json=envelope(json.dumps(opinion(resolved_issue_ids=["issue-1"])))))
        result = await provider.generate(role=role(), context=context(issues=issues))
        self.assertEqual(result["resolved_issue_ids"], ["issue-1"])

    async def test_unreported_or_invalid_usage_stays_unknown(self):
        for usage in (None, {}, {"input_tokens": -1, "output_tokens": True}, {"input_tokens": "5", "output_tokens": 2.5}):
            provider = self.provider(lambda request: httpx.Response(200, json=envelope(usage=usage)))
            result = await provider.generate(role=role(), context=context())
            self.assertEqual(result["usage"], {"input_tokens": None, "output_tokens": None})

    async def test_oversize_context_stops_before_http_without_mutating_input(self):
        seen = []
        provider = self.provider(lambda request: seen.append(request), max_context_chars=100)
        payload = context()
        original = copy.deepcopy(payload)
        with self.assertRaises(ProviderError) as caught:
            await provider.generate(role=role(), context=payload)
        self.assertEqual(caught.exception.code, "context_limit")
        self.assertEqual(seen, [])
        self.assertEqual(payload, original)

    async def test_check_is_connectivity_only(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"data": [{"id": "openclaw"}]})
        provider = self.provider(handler)
        result = await provider.check()
        self.assertTrue(result["ok"])
        self.assertFalse(result["inference_verified"])
        self.assertEqual(seen[0].method, "GET")
        self.assertEqual(seen[0].url.path, "/v1/models")

    async def test_check_rejects_html_and_wrong_json_shape(self):
        for body in ("<html>" + TOKEN + "</html>", "[]", "{}"):
            provider = self.provider(lambda request: httpx.Response(200, text=body))
            result = await provider.check()
            self.assertFalse(result["ok"])
            self.assertNotIn(TOKEN, json.dumps(result))

    async def test_client_ownership(self):
        provider = self.provider(lambda request: httpx.Response(200, json={"data": []}))
        await provider.aclose()
        self.assertFalse(self.clients[-1].is_closed)
        owned = OpenClawProvider(settings())
        await owned.aclose()
        self.assertTrue(owned._client.is_closed)

    async def test_configuration_rejects_credentials_in_url_and_invalid_agent_id(self):
        for url in ("http://user:pass@example.com", "http://localhost?token=" + TOKEN, "http://localhost/#" + TOKEN):
            with self.assertRaises(ProviderError) as caught:
                OpenClawProvider(settings(openclaw_base_url=url))
            self.assertNotIn(TOKEN, str(caught.exception))
        provider = self.provider(lambda request: self.fail("must not call server"))
        invalid_role = role()
        invalid_role["agent_id"] = "bad/agent"
        with self.assertRaises(ProviderError):
            await provider.generate(role=invalid_role, context=context())


class SimulationTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeatable_two_round_fixture_preserves_final_reviewed_proposal(self):
        provider = DeterministicProvider(delay_seconds=0)
        opened = await provider.generate(role=role("host"), context=context(phase="opening", proposal=""))
        reviews = []
        issues = []
        for role_id in ("planner", "balance", "engineer", "reviewer"):
            review = await provider.generate(role=role(role_id), context=context(proposal=opened["proposal"]))
            repeat = await provider.generate(role=role(role_id), context=context(proposal=opened["proposal"]))
            self.assertEqual(review, repeat)
            self.assertEqual(review["stance"], "revise")
            self.assertIn("模拟", review["summary"])
            reviews.append(review)
            issues.append({"id": role_id + "-issue", "owner_role_id": role_id, "status": "open"})
        revised = await provider.generate(role=role("host"), context=context(phase="synthesis", proposal=opened["proposal"], round_reviews=reviews, issues=issues))
        self.assertNotEqual(revised["proposal"], opened["proposal"])
        for role_id in ("planner", "balance", "engineer", "reviewer"):
            review = await provider.generate(role=role(role_id), context=context(round=2, proposal=revised["proposal"], issues=issues))
            self.assertEqual(review["stance"], "approve")
            self.assertEqual(review["resolved_issue_ids"], [role_id + "-issue"])
        final = await provider.generate(role=role("host"), context=context(round=2, phase="synthesis", proposal=revised["proposal"], all_approve=True))
        self.assertEqual(final["stance"], "approve")
        self.assertEqual(final["proposal"], revised["proposal"])
        self.assertEqual(final["usage"], {"input_tokens": None, "output_tokens": None})
        self.assertIn("模拟", (await provider.check())["message"])
        await provider.aclose()

    async def test_factory_modes_are_explicit(self):
        simulated = create_provider(settings(provider_mode="simulation"))
        self.assertIsInstance(simulated, DeterministicProvider)
        real = create_provider(settings())
        self.assertIsInstance(real, OpenClawProvider)
        await real.aclose()
        with self.assertRaises(ProviderError):
            create_provider(settings(provider_mode="automatic"))


if __name__ == "__main__":
    unittest.main()
