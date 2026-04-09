from __future__ import annotations

from fastapi import FastAPI

from . import admin, auth, exam, pages, ws
from .deps import RouteDeps


def register_routes(app: FastAPI, deps: RouteDeps) -> None:
    app.include_router(auth.get_router(deps))
    app.include_router(exam.get_router(deps))
    app.include_router(admin.get_router(deps))
    app.include_router(ws.get_router(deps))
    app.include_router(pages.get_router(deps))


__all__ = ["RouteDeps", "register_routes"]
