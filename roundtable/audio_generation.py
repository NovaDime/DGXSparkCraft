"""StepFun text-to-audio adapter. Credentials never enter plans or artifacts."""
import io
import json
import os
import re
import wave

import httpx


class AudioError(ValueError):
    pass


class StepAudio:
    def __init__(self, data_dir):
        self.path = data_dir / "private" / "stepaudio.json"

    def config(self):
        value = json.loads(self.path.read_text()) if self.path.exists() else {}
        return {"api_key": os.environ.get("STEPFUN_API_KEY") or value.get("api_key", ""),
                "endpoint": value.get("endpoint", "https://api.stepfun.com/v1/audio/generate"),
                "model": value.get("model", "stepaudio-3-gen-preview")}

    def public(self):
        c = self.config()
        return {"configured": bool(c["api_key"]), "endpoint": c["endpoint"], "model": c["model"]}

    def save(self, body):
        if not isinstance(body, dict) or set(body) != {"api_key", "endpoint", "model"}:
            raise AudioError("请填写 StepFun 密钥、区域接口和模型 ID。")
        if not all(isinstance(v, str) for v in body.values()):
            raise AudioError("音频连接字段必须为文本。")
        value = {k: v.strip() for k, v in body.items()}
        if not 8 <= len(value["api_key"]) <= 4096 or re.search(r"[\x00-\x20]", value["api_key"]):
            raise AudioError("密钥格式不正确。")
        if value["endpoint"] not in {"https://api.stepfun.com/v1/audio/generate", "https://api.stepfun.ai/v1/audio/generate"}:
            raise AudioError("请选择 StepFun 官方音频生成接口。")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}", value["model"]) or value["api_key"] in value["model"]:
            raise AudioError("模型 ID 格式无效。")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        temp = self.path.with_suffix(".tmp")
        with os.fdopen(os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle)
        temp.replace(self.path)
        return self.public()

    @staticmethod
    def payload(asset, model):
        data = {"model": model, "task": "text_to_audio", "response_format": "wav",
                "sample_rate": 24000, "stream_format": "audio", "return_url": False,
                "instruction": asset["direction"]}
        if asset["kind"] == "npc":
            data["roles"] = [{"name": "NPC", "description": asset["voice"]}]
            data["scripts"] = [{"speaker": "NPC", "text": asset["text"]}]
        else:
            data["scripts"] = [{"text": "[" + asset["text"] + "]"}]
        return data

    @staticmethod
    def validate_wav(data):
        try:
            with wave.open(io.BytesIO(data), "rb") as audio:
                frames, rate, channels, width = audio.getnframes(), audio.getframerate(), audio.getnchannels(), audio.getsampwidth()
                duration = frames / rate
                if not .05 <= duration <= 120 or channels not in (1, 2) or width not in (1, 2, 3, 4):
                    raise ValueError()
                samples = audio.readframes(frames)
                if len(samples) != frames * channels * width or not any(samples):
                    raise ValueError()
                return {"seconds": round(duration, 3), "sample_rate": rate, "channels": channels}
        except (wave.Error, EOFError, ValueError, ZeroDivisionError):
            raise AudioError("未收到完整有效的非空 PCM WAV 音频；没有采用响应内容。") from None

    async def generate(self, asset, expected, client=None):
        config = self.config()
        if not config["api_key"]:
            raise AudioError("尚未配置 StepFun 音频密钥，请在审核面板保存连接后重试。")
        if any(config[k] != expected[k] for k in ("model", "endpoint")):
            raise AudioError("音频接口或模型已变更，请重新审核执行计划。")
        owned = client is None
        client = client or httpx.AsyncClient(trust_env=False, follow_redirects=False)
        try:
            async with client.stream("POST", config["endpoint"], headers={"Authorization": "Bearer " + config["api_key"]},
                                     json=self.payload(asset, config["model"]), timeout=240, follow_redirects=False) as response:
                if response.status_code in (401, 403):
                    raise AudioError("StepFun 鉴权失败，请检查密钥及音频模型权限。")
                if not 200 <= response.status_code < 300:
                    raise AudioError(f"StepFun 音频请求失败（HTTP {response.status_code}）；没有自动重试。")
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 24 * 1024 * 1024:
                        raise AudioError("音频响应超过 24 MiB 限制。")
                    chunks.append(chunk)
            data = b"".join(chunks)
            return data, self.validate_wav(data)
        except httpx.HTTPError:
            raise AudioError("音频请求连接异常或超时；上游可能已经计费，请确认后手动重试。") from None
        finally:
            if owned:
                await client.aclose()

    @staticmethod
    def game_audio(wav):
        """Normalize to mono OGG/Vorbis, without invoking generated programs."""
        try:
            import soundfile as sf
            samples, rate = sf.read(io.BytesIO(wav), always_2d=True)
            output = io.BytesIO()
            sf.write(output, samples.mean(axis=1), rate, format="OGG", subtype="VORBIS", compression_level=1.0)
            encoded = output.getvalue()
            with sf.SoundFile(io.BytesIO(encoded)) as check:
                if check.format != "OGG" or check.subtype != "VORBIS" or check.frames <= 0:
                    raise ValueError()
            return encoded
        except (ImportError, OSError, ValueError):
            raise AudioError("OGG/Vorbis 转换失败，请安装 requirements.txt 中的 soundfile 及系统 libsndfile。") from None
