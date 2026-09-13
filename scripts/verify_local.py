"""Run an explicit simulation smoke check and export its inspectable evidence."""
import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roundtable.config import Settings
from roundtable.engine import RoundtableEngine
from roundtable.models import MeetingRequest
from roundtable.providers import create_provider
from roundtable.reporting import render_report
from roundtable.skills import SkillCatalog
from roundtable.storage import MeetingStore


async def verify(output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="roundtable-smoke-") as temporary:
        settings = Settings(data_dir=Path(temporary), simulation_delay_seconds=0)
        catalog = SkillCatalog(settings.skills_dir)
        store = MeetingStore(settings.data_dir / "smoke.sqlite3")
        engine = RoundtableEngine(settings, store, create_provider(settings), catalog)
        try:
            examples = json.loads(settings.examples_path.read_text(encoding="utf-8"))
            example = examples[0]
            request = MeetingRequest(topic=example["topic"], constraints=example["constraints"], max_rounds=3)
            meeting = engine.create(request)
            await engine.wait_idle()
            final = store.get(meeting["id"])
            checks = {
                "simulation_marked": final["provider_mode"] == "simulation" and "规则模拟" in final["final_report"],
                "two_round_review": final["current_round"] == 2,
                "consensus_guard_passed": final["status"] == "completed",
                "objections_were_recorded": len(final["issues"]) > 0,
                "objections_were_resolved": all(item["status"] == "resolved" for item in final["issues"]),
                "skills_fingerprinted": all(len(turn["skill_sha256"]) == 64 for turn in final["turns"]),
            }
            summary = {"ok": all(checks.values()), "mode": "simulation", "checks": checks,
                       "notice": "只验证本地调度和记录，不代表模型能力、Spark性能或游戏运行验收。",
                       "meeting_id": final["id"], "turn_count": len(final["turns"])}
            output.mkdir(parents=True, exist_ok=True)
            (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "meeting.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "meeting.md").write_text(render_report(final), encoding="utf-8")
            return summary
        finally:
            await engine.close()
            store.close()


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "local-verification")
    result = asyncio.run(verify(parser.parse_args().output))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
