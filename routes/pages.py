from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .deps import RouteDeps


def get_router(deps: RouteDeps) -> APIRouter:
    router = APIRouter(tags=["pages"])

    @router.get("/student", response_class=HTMLResponse)
    async def student_page():
        return deps.load_ui_page("student.html")

    @router.get("/admin", response_class=HTMLResponse)
    async def admin_page():
        return deps.load_ui_page("admin.html")

    @router.get("/", response_class=HTMLResponse)
    async def root():
        return deps.load_ui_page("index.html")

    return router
