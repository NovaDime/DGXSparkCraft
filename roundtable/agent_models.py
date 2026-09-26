"""Public model labels and private, persisted role routing. No credential exports."""
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from .skills import ROLE_SPECS
from .cloud_models import CloudModels, CloudError

REF = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./:-]+")

class ModelRoutes:
    def __init__(self, settings):
        self.settings = settings
        self.path = settings.data_dir / "agent-models.json"
        self.routes = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.cloud = CloudModels(settings.data_dir)

    def catalog(self):
        path = self.settings.data_dir / "openclaw" / "openclaw.json"
        config = json.loads(path.read_text()) if path.exists() else {}
        models = {m["id"]: m["name"] + " · " + m["model"] for m in self.cloud.public()}
        for provider, data in config.get("models", {}).get("providers", {}).items():
            for model in data.get("models", []):
                ref = provider + "/" + model["id"]
                if REF.fullmatch(ref) and "text" in model.get("input", ["text"]):
                    models[ref] = model.get("name", model["id"])
        defaults = {}
        entries = config.get("agents", {}).get("entries", {})
        for role in ROLE_SPECS:
            value = entries.get(self.settings.agent_ids[role["id"]], {}).get("model", config.get("agents", {}).get("defaults", {}).get("model", {}))
            defaults[role["id"]] = value.get("primary") if isinstance(value, dict) else value
        return models, defaults

    def snapshot(self):
        models, defaults = self.catalog()
        return {r["id"]: self.routes.get(r["id"]) or defaults.get(r["id"]) for r in ROLE_SPECS}

    def public(self):
        models, defaults = self.catalog()
        return {"models": [{"id": k, "name": v} for k, v in models.items()],
                "roles": [{**r, "agent_id": self.settings.agent_ids[r["id"]], "model": self.routes.get(r["id"]) or defaults.get(r["id"]) or "Gateway 默认模型", "override": self.routes.get(r["id"], "")} for r in ROLE_SPECS],
                "mode": self.settings.provider_mode, "cloud_models": self.cloud.public()}

    def set(self, role, model):
        if role not in self.settings.agent_ids:
            raise ValueError("角色不存在")
        if model and model not in self.catalog()[0]:
            raise ValueError("请选择已接入的本地或云端文本模型")
        routes = {**self.routes, role: model}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(routes, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)
        self.routes = routes

class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model: str

def create_agent_router():
    router = APIRouter()
    @router.post("/api/cloud-models")
    async def add_cloud(request: Request):
        # Do not let validation errors echo a submitted API key.
        try:
            key = request.app.state.model_routes.cloud.add(await request.json())
        except (ValueError, TypeError):
            raise HTTPException(422, "云端配置无效。请检查必填项、HTTPS 基础地址和模型 ID；密钥不要填入其他字段。") from None
        return {"id": key, **request.app.state.model_routes.public()}
    @router.post("/api/cloud-models/{key}/check")
    async def check_cloud(key: str, request: Request):
        try:
            await request.app.state.model_routes.cloud.generate("cloud/" + key, instructions="只回复 OK", prompt="连接测试", max_tokens=64, timeout=30)
        except CloudError as exc:
            return {"ok":False,"message":str(exc)}
        return {"ok":True,"message":"文本生成连接成功。实际圆桌结构化评审能力仍需任务验证。"}
    @router.get("/api/agents")
    async def agents(request: Request):
        return request.app.state.model_routes.public()
    @router.post("/api/agents/{role}/model")
    async def select(role: str, body: Selection, request: Request):
        try:
            request.app.state.model_routes.set(role, body.model)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return request.app.state.model_routes.public()
    return router
