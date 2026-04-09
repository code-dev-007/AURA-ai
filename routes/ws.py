from __future__ import annotations

import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .deps import RouteDeps


def get_router(deps: RouteDeps) -> APIRouter:
    router = APIRouter(tags=["ws"])

    @router.websocket("/ws/{student_id}")
    async def student_ws(websocket: WebSocket, student_id: str):
        await websocket.accept()
        deps.student_ws_map[student_id] = websocket
        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                db = next(deps.get_db())
                res = await deps.pipeline(
                    student_id,
                    data.get("event", "unknown"),
                    data.get("details", ""),
                    data.get("timestamp", time.time()),
                    db,
                )
                await websocket.send_json({"status": "ok", "score": res.get("total_score", 0)})
        except WebSocketDisconnect:
            deps.student_ws_map.pop(student_id, None)

    @router.websocket("/ws/admin/live")
    async def admin_ws(websocket: WebSocket):
        await websocket.accept()
        deps.admin_ws_list.append(websocket)
        try:
            await websocket.send_json({"type": "connected", "msg": "Admin live connected"})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            if websocket in deps.admin_ws_list:
                deps.admin_ws_list.remove(websocket)

    return router
