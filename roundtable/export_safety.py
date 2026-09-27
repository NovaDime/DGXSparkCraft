"""Screen generated archives, including reports, before publication."""
import re
from .audio_generation import StepAudio
from .cloud_models import CloudModels
from .art_models import ArtConnection


def check_export(settings, payloads):
    secrets = [settings.openclaw_token, StepAudio(settings.data_dir).config()["api_key"]]
    secrets.extend(v["api_key"] for v in CloudModels(settings.data_dir).read().values())
    secrets.append(ArtConnection(settings.data_dir).read().get("api_key", ""))
    for payload in payloads:
        if any(secret and secret.encode() in payload for secret in secrets) or re.search(
                rb"(?:sk-[a-zA-Z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY)", payload):
            raise ValueError("产物或报告包含疑似凭证，已阻止导出。")
