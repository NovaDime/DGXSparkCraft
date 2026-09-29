"""HTTP API for explicit repository import and reviewed experience memory."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.concurrency import run_in_threadpool

from .knowledge import MAX_UPLOAD_BYTES


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=4096)
    name: str | None = Field(default=None, min_length=1, max_length=120)


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    accepted: StrictBool = False
    evidence: str | dict | None = None


class LearningSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int | None = Field(default=None, ge=1)
    enabled: StrictBool | None = None


class ReviewFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: StrictBool
    evidence: str | dict | None = None


async def _call(function, *args, **kwargs):
    try:
        return await run_in_threadpool(function, *args, **kwargs)
    except KeyError:
        raise HTTPException(404, "代码库不存在。") from None
    except (ValueError, FileNotFoundError, PermissionError) as exc:
        raise HTTPException(400, str(exc)) from None
    except OSError:
        raise HTTPException(400, "无法读取该目录或文件，请确认权限和文件状态。") from None


def create_knowledge_router() -> APIRouter:
    router = APIRouter(prefix="/api/repositories", tags=["repositories"])

    @router.get("")
    async def repositories(request: Request):
        return await _call(request.app.state.knowledge.list)

    @router.post("/import", status_code=201)
    async def import_repository(body: ImportRequest, request: Request):
        item = await _call(request.app.state.knowledge.import_path, body.path, body.name)
        request.app.state.skill_learning.schedule(item["id"])
        return item

    @router.post("/upload", status_code=201)
    async def upload_repository(request: Request, name: str = Query("uploaded-repository", min_length=1, max_length=120)):
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "ZIP 上传不得超过 20 MiB。")
            payload.extend(chunk)
        item = await _call(request.app.state.knowledge.import_zip, bytes(payload), name)
        request.app.state.skill_learning.schedule(item["id"])
        return item

    @router.get("/{repository_id}")
    async def repository_detail(repository_id: str, request: Request):
        item = await _call(request.app.state.knowledge.get, repository_id)
        if item is None:
            raise HTTPException(404, "代码库不存在。")
        return item

    @router.post("/{repository_id}/reindex")
    async def reindex_repository(repository_id: str, request: Request):
        item = await _call(request.app.state.knowledge.reindex, repository_id)
        request.app.state.skill_learning.schedule(item["id"])
        return item

    @router.get("/{repository_id}/skill-learning")
    async def learning_status(repository_id: str, request: Request):
        try: return request.app.state.skill_learning.detail(repository_id)
        except KeyError: raise HTTPException(404, "代码库不存在") from None

    @router.post("/{repository_id}/skill-learning")
    async def learn_repository(repository_id: str, request: Request):
        try: return request.app.state.skill_learning.schedule(repository_id, force=True)
        except KeyError: raise HTTPException(404, "代码库不存在") from None

    @router.patch("/{repository_id}/skill-learning")
    async def select_learning(repository_id: str, body: LearningSelection, request: Request):
        try: return request.app.state.skill_learning.select(repository_id, **body.model_dump())
        except KeyError: raise HTTPException(404, "代码库不存在") from None
        except ValueError: raise HTTPException(400, "学习版本不存在") from None

    @router.get("/{repository_id}/skill-learning/download")
    async def download_learning(repository_id: str, request: Request):
        from fastapi.responses import FileResponse
        learning=request.app.state.skill_learning
        try: item=learning.state(repository_id)
        except KeyError: raise HTTPException(404, "代码库不存在") from None
        if not item['active_version']: raise HTTPException(404, "尚未生成学习版本")
        return FileResponse(learning.root/repository_id/f'v{item["active_version"]}.md',filename='repository-skill-supplement.md',media_type='text/markdown')

    @router.get("/{repository_id}/search")
    async def search_repository(repository_id: str, request: Request,
                                q: str = Query(..., min_length=1, max_length=4000),
                                limit: int = Query(6, ge=1, le=20)):
        return await _call(request.app.state.knowledge.search, repository_id, q, limit)

    @router.get("/{repository_id}/feedback")
    async def repository_feedback(repository_id: str, request: Request):
        return await _call(request.app.state.knowledge.feedback, repository_id)

    @router.post("/{repository_id}/feedback", status_code=201)
    async def create_feedback(repository_id: str, body: FeedbackRequest, request: Request):
        return await _call(request.app.state.knowledge.add_feedback, repository_id, **body.model_dump())

    @router.patch("/{repository_id}/feedback/{feedback_id}")
    async def review_feedback(repository_id: str, feedback_id: str, body: ReviewFeedbackRequest, request: Request):
        return await _call(request.app.state.knowledge.review_feedback, repository_id, feedback_id, **body.model_dump())

    return router
