from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent


def read_env(path: Path) -> dict[str, str]:
    """Read literal key=value settings; never evaluate or export shell expressions."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f".env 第 {number} 行格式无效，应为 KEY=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    provider_mode: str = "simulation"
    openclaw_base_url: str = "http://127.0.0.1:18789"
    openclaw_token: str = field(default="", repr=False)
    openclaw_model: str = "openclaw"
    request_timeout_seconds: float = 180
    simulation_delay_seconds: float = 0.35
    max_context_chars: int = 24000
    max_output_tokens: int = 4096
    data_dir: Path = ROOT / "data"
    skills_dir: Path = ROOT / "skills"
    examples_path: Path = ROOT / "examples" / "topics.json"
    agent_ids: dict[str, str] = field(default_factory=lambda: {
        role: role for role in ("host", "planner", "balance", "engineer", "audio", "art", "reviewer")
    })
    max_queued_meetings: int = 10
    coding_agent_id: str = "coder"

    def __post_init__(self):
        if self.provider_mode not in {"simulation", "openclaw"}:
            raise ValueError("ROUNDTABLE_PROVIDER 必须是 simulation 或 openclaw")
        url = urlsplit(self.openclaw_base_url)
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError("OPENCLAW_BASE_URL 必须是 http(s) 地址")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("模型地址不能包含凭证、查询参数或片段；凭证请放 OPENCLAW_TOKEN")
        if not 1 <= self.request_timeout_seconds <= 900:
            raise ValueError("请求超时必须在 1 至 900 秒之间")
        if not 0 <= self.simulation_delay_seconds <= 5:
            raise ValueError("模拟延迟必须在 0 至 5 秒之间")
        if not 8000 <= self.max_context_chars <= 128000:
            raise ValueError("上下文字符预算必须在 8000 至 128000 之间")
        if not 512 <= self.max_output_tokens <= 8192:
            raise ValueError("单次输出 token 预算必须在 512 至 8192 之间")
        if set(self.agent_ids) != {"host", "planner", "balance", "engineer", "audio", "art", "reviewer"}:
            raise ValueError("必须为七个圆桌角色分别配置 Agent ID")
        if len(set(self.agent_ids.values())) != 7:
            raise ValueError("七个角色必须使用不同的 OpenClaw Agent ID，以保持专业会话独立")
        for value in self.agent_ids.values():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
                raise ValueError("OpenClaw Agent ID 仅支持字母、数字、下划线和连字符")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", self.coding_agent_id) or self.coding_agent_id in self.agent_ids.values():
            raise ValueError("编码 Agent 必须使用独立且有效的 ID")

    @classmethod
    def from_env(cls, path: Path | None = None) -> "Settings":
        source = {**read_env(path or ROOT / ".env"), **os.environ}
        data_dir = Path(source.get("ROUNDTABLE_DATA_DIR", str(ROOT / "data")))
        if not data_dir.is_absolute():
            data_dir = ROOT / data_dir
        return cls(
            provider_mode=source.get("ROUNDTABLE_PROVIDER", "simulation"),
            openclaw_base_url=source.get("OPENCLAW_BASE_URL", "http://127.0.0.1:18789").rstrip("/"),
            openclaw_token=source.get("OPENCLAW_TOKEN", ""),
            openclaw_model=source.get("OPENCLAW_MODEL", "openclaw"),
            request_timeout_seconds=float(source.get("ROUNDTABLE_REQUEST_TIMEOUT", "180")),
            simulation_delay_seconds=float(source.get("ROUNDTABLE_SIMULATION_DELAY", "0.35")),
            max_context_chars=int(source.get("ROUNDTABLE_MAX_CONTEXT_CHARS", "24000")),
            max_output_tokens=int(source.get("ROUNDTABLE_MAX_OUTPUT_TOKENS", "4096")),
            coding_agent_id=source.get("OPENCLAW_AGENT_CODER", "coder"),
            data_dir=data_dir.resolve(),
            agent_ids={role: source.get(f"OPENCLAW_AGENT_{role.upper()}", role)
                       for role in ("host", "planner", "balance", "engineer", "audio", "art", "reviewer")},
        )

    def provider_info(self) -> dict:
        parts = urlsplit(self.openclaw_base_url)
        return {
            "mode": self.provider_mode,
            "configured": self.provider_mode == "openclaw",
            "model": self.openclaw_model if self.provider_mode == "openclaw" else "规则模拟 · 非 AI 推理",
            "base_url": urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")),
        }
