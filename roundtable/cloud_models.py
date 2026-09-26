"""OpenAI-compatible cloud text models; secrets stay in private local storage."""
import json
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

class CloudError(ValueError):
    pass

class CloudModels:
    def __init__(self, data_dir):
        self.folder = data_dir / "private"
        self.path = self.folder / "cloud-models.json"

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def public(self):
        return [{"id": key, "name": item["name"], "model": item["model"], "base_url": item["base_url"], "configured": bool(item["api_key"]), "kind": "cloud"} for key, item in self.read().items()]

    def add(self, body):
        if not isinstance(body, dict) or set(body) != {"name", "model", "base_url", "api_key"}:
            raise CloudError("请填写名称、API 地址、模型 ID 和密钥")
        if any(not isinstance(v, str) or not v.strip() for v in body.values()):
            raise CloudError("所有配置字段都必须填写")
        values = {k:v.strip() for k,v in body.items()}
        if len(values["name"]) > 80 or len(values["api_key"]) > 4096 or re.search(r"[\r\n\x00-\x1f]", values["api_key"]):
            raise CloudError("名称或密钥格式无效")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,199}", values["model"]):
            raise CloudError("模型 ID 格式无效")
        url = urlsplit(values["base_url"])
        if len(values["base_url"]) > 500 or url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise CloudError("请填写不含凭证与查询参数的 HTTPS API 基础地址，例如 https://api.stepfun.com/v1")
        if any(values["api_key"] in values[k] for k in ("name", "model", "base_url")):
            raise CloudError("不要在公开配置字段中填写密钥")
        values["base_url"] = values["base_url"].rstrip("/")
        key = "cloud/" + uuid4().hex
        data = self.read(); data[key] = values
        self.folder.mkdir(parents=True, exist_ok=True); self.folder.chmod(0o700)
        temp = self.path.with_suffix(".tmp")
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle, ensure_ascii=False)
        temp.replace(self.path)
        return key

    async def generate(self, key, *, instructions, prompt, max_tokens=4096, timeout=180, client=None):
        item = self.read().get(key)
        if not item:
            raise CloudError("云端模型配置不存在，请重新选择")
        owns = client is None
        client = client or httpx.AsyncClient(follow_redirects=False, trust_env=False)
        try:
            async with client.stream("POST", item["base_url"] + "/chat/completions", headers={"Authorization": "Bearer " + item["api_key"]}, json={"model":item["model"], "messages":[{"role":"system","content":instructions},{"role":"user","content":prompt}], "max_tokens":max_tokens, "stream":False}, timeout=timeout, follow_redirects=False) as response:
                if response.status_code in (401,403): raise CloudError("云端鉴权失败，请检查密钥与模型权限")
                if response.status_code == 429: raise CloudError("云端额度不足或请求限流，请检查服务账户")
                if not 200 <= response.status_code < 300: raise CloudError(f"云端请求失败（HTTP {response.status_code}），请检查 API 地址和模型 ID")
                chunks=[]; total=0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > 4 * 1024 * 1024: raise CloudError("云端响应超过大小限制")
                    chunks.append(chunk)
            data = json.loads(b"".join(chunks)); choice = data["choices"][0]; message = choice["message"]
            if choice.get("finish_reason") != "stop" or message.get("tool_calls") or message.get("function_call"):
                raise CloudError("云端输出未完整结束或请求了工具，未采纳部分结果")
            text = message["content"]
            if not isinstance(text, str) or not text.strip(): raise CloudError("云端没有返回文本")
            text = text.replace(item["api_key"], "[REDACTED]")
            usage = data.get("usage") or {}
            return text, {"input_tokens":usage.get("prompt_tokens"),"output_tokens":usage.get("completion_tokens")}
        except CloudError:
            raise
        except httpx.TimeoutException:
            raise CloudError("云端请求超时，未自动重试") from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise CloudError("云端连接或响应格式异常，请确认支持 Chat Completions 接口") from None
        finally:
            if owns: await client.aclose()
