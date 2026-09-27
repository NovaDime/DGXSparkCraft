from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings
from .engine import QueueFullError, RoundtableEngine
from .models import DEFAULT_ROUNDS, MAX_ROUNDS, MIN_ROUNDS, MeetingRequest
from .providers import create_provider
from .reporting import render_report
from .skills import ROLE_SPECS, SkillCatalog
from .storage import MeetingStore
from .knowledge import KnowledgeStore
from .knowledge_api import create_knowledge_router
from .development import DevelopmentEngine, create_development_router
from .agent_models import ModelRoutes, create_agent_router
from .delivery import DeliveryEngine, create_delivery_router

STATIC_DIR = Path(__file__).parent / "static"


class DataDirectoryLock:
    """Prevent two workers from independently driving the same meeting database."""
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.file = (directory / ".server.lock").open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            import os
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            self.file.close()
            raise RuntimeError("该数据目录已有运行实例。请使用单 worker，或关闭之前的服务。") from None

    def close(self):
        self.file.close()


def create_app(settings: Settings | None = None, provider=None) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        instance_lock = DataDirectoryLock(config.data_dir)
        store = None
        engine = None
        knowledge = None
        development = None
        delivery = None
        official = None
        official_sync = None
        try:
            catalog = SkillCatalog(config.skills_dir)
            catalog.all()  # Fail startup early if the project's professional skills are missing.
            model_provider = provider or create_provider(config)
            store = MeetingStore(config.data_dir / "meetings.sqlite3")
            engine = RoundtableEngine(config, store, model_provider, catalog)
            app.state.model_routes = ModelRoutes(config)
            engine.model_routes = app.state.model_routes
            engine.recover()
            from .official_knowledge import OfficialKnowledge
            official = OfficialKnowledge(config.data_dir)
            app.state.official_knowledge = official
            engine.official_knowledge = official
            knowledge = KnowledgeStore(config.data_dir / "knowledge")
            engine.knowledge = knowledge
            development = DevelopmentEngine(config, model_provider, knowledge, store, catalog, engine._lane)
            development.official_knowledge = official
            app.state.settings = config
            app.state.store = store
            app.state.engine = engine
            app.state.provider = model_provider
            app.state.catalog = catalog
            app.state.knowledge = knowledge
            app.state.development = development
            delivery = DeliveryEngine(config, development, store, model_provider, app.state.model_routes)
            app.state.delivery = delivery
            if provider is None and config.provider_mode != "simulation" and not official.meta_path.exists():
                import asyncio
                official_sync = asyncio.create_task(official.sync())
            yield
        finally:
            if official_sync:
                official_sync.cancel()
                import asyncio
                await asyncio.gather(official_sync, return_exceptions=True)
            if delivery:
                await delivery.close()
            if development:
                await development.close()
            if engine:
                await engine.close()
            if store:
                store.close()
            if knowledge:
                knowledge.close()
            if official:
                official.close()
            instance_lock.close()

    app = FastAPI(title="UGC AI 圆桌", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            expected = urlsplit(str(request.base_url))
            if origin:
                incoming = urlsplit(origin)
                if (incoming.scheme, incoming.netloc) != (expected.scheme, expected.netloc):
                    return JSONResponse({"detail": "仅允许当前本地页面发起操作。"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "不接受跨站请求。"}, status_code=403)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "无效的请求长度。"}, status_code=400)
            maximum = 20 * 1024 * 1024 if request.url.path == "/api/repositories/upload" else 65536
            if length > maximum:
                return JSONResponse({"detail": "请求过大，请缩短议题和约束。"}, status_code=413)
            if request.url.path != "/api/repositories/upload":
                # Enforce limits for chunked requests too, before JSON parsing.
                size = 0
                chunks = []
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > maximum:
                        return JSONResponse({"detail": "请求过大。"}, status_code=413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": __version__, "provider_mode": config.provider_mode}

    @app.get("/api/meta")
    async def metadata(request: Request):
        examples = json.loads(config.examples_path.read_text(encoding="utf-8")) if config.examples_path.exists() else []
        skills = request.app.state.catalog.all()
        return {"app_name": "UGC AI 圆桌", "version": __version__, "provider": config.provider_info(),
                "roles": ROLE_SPECS, "examples": examples,
                "limits": {"max_rounds_min": MIN_ROUNDS, "max_rounds_default": DEFAULT_ROUNDS,
                           "max_rounds_max": MAX_ROUNDS},
                "skills": [{key: item[key] for key in ("id", "name", "description")} for item in skills]}

    @app.get("/api/skills/{skill_id}")
    async def skill(skill_id: str, request: Request):
        try:
            return request.app.state.catalog.get(skill_id)
        except KeyError:
            raise HTTPException(404, "未找到该 Skill") from None

    @app.post("/api/provider/check")
    async def provider_check(request: Request):
        return await request.app.state.provider.check()

    @app.get("/api/meetings")
    async def meetings(request: Request, deleted: bool = False):
        return request.app.state.store.summaries(deleted)

    @app.post("/api/meetings/{meeting_id}/visibility")
    async def meeting_visibility(meeting_id: str, request: Request, deleted: bool = True):
        store = request.app.state.store
        item = store.get(meeting_id)
        if not item: raise HTTPException(404, "会议不存在")
        if item["status"] in {"queued", "running"}: raise HTTPException(409, "请先停止会议再删除")
        item["deleted"] = deleted
        store.save(item)
        return {"ok": True}

    @app.post("/api/meetings", status_code=201)
    async def create_meeting(body: MeetingRequest, request: Request):
        try:
            return request.app.state.engine.create(body)
        except QueueFullError as exc:
            raise HTTPException(429, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/meetings/{meeting_id}")
    async def meeting_detail(meeting_id: str, request: Request):
        meeting = request.app.state.store.get(meeting_id)
        if not meeting:
            raise HTTPException(404, "会议不存在")
        return meeting

    @app.post("/api/meetings/{meeting_id}/cancel")
    async def cancel_meeting(meeting_id: str, request: Request):
        meeting = request.app.state.engine.cancel(meeting_id)
        if not meeting:
            raise HTTPException(404, "会议不存在")
        return meeting

    @app.get("/api/meetings/{meeting_id}/export")
    async def export(meeting_id: str, request: Request, format: str = Query("markdown", pattern="^(markdown|json)$")):
        meeting = request.app.state.store.get(meeting_id)
        if not meeting:
            raise HTTPException(404, "会议不存在")
        extension = "md" if format == "markdown" else "json"
        content = render_report(meeting) if format == "markdown" else json.dumps(meeting, ensure_ascii=False, indent=2)
        # Filename comes from stored UUID, never from the topic or a filesystem request path.
        return Response(content, media_type="text/markdown" if format == "markdown" else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="roundtable-{meeting["id"]}.{extension}"'})

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/studio")
    async def studio():
        return FileResponse(STATIC_DIR / "studio.html")

    from .official_knowledge import create_official_router
    app.include_router(create_official_router())
    from .documents import create_document_router
    app.include_router(create_document_router())
    app.include_router(create_knowledge_router())
    app.include_router(create_agent_router())
    app.include_router(create_development_router())
    app.include_router(create_delivery_router())

    app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
    return app
