"""设备模拟器 FastAPI 入口（默认端口 8081）."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from device.agent.log_store import logs
from device.agent.session import session
from device.config import WEB_DIR, settings
from device.database import init_schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title=settings.app_name, docs_url="/docs", redoc_url=None)


class ConnectIn(BaseModel):
    sn: str = Field(..., min_length=1, max_length=64)


@app.on_event("startup")
def _startup() -> None:
    init_schema()


@app.get("/sim/status")
def sim_status():
    return {"code": 0, "message": "", "data": session.status()}


@app.post("/sim/connect")
def sim_connect(body: ConnectIn):
    try:
        data = session.connect(body.sn)
        return {"code": 0, "message": "", "data": data}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sim/disconnect")
def sim_disconnect():
    data = session.disconnect()
    return {"code": 0, "message": "", "data": data}


@app.get("/sim/logs")
def sim_logs(limit: int = 100):
    return {"code": 0, "message": "", "data": logs.list(limit=limit)}


@app.get("/sim/logs/{log_id}")
def sim_log_detail(log_id: str):
    item = logs.get(log_id)
    if not item:
        raise HTTPException(status_code=404, detail="日志不存在")
    return {"code": 0, "message": "", "data": item}


# 静态页
if WEB_DIR.is_dir():
    assets = WEB_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    def index_page():
        return FileResponse(WEB_DIR / "index.html")
