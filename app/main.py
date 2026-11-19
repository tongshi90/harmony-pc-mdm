from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.api import api_router
from app.api.device_app import router as device_app_router
from app.api.device_bind import router as device_bind_router
from app.api.device_biz_card import router as device_biz_card_router
from app.api.device_mdm import router as device_mdm_router
from app.api.device_rag import router as device_rag_router
from app.api.device_report import router as device_report_router
from app.api.device_strategy import router as device_strategy_router
from app.api.openapi_approval import router as openapi_approval_router
from app.bootstrap import init_db
from app.config import BASE_DIR, WEB_DIR, settings
from app.database import SessionLocal
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.auth_guard import AuthGuardMiddleware
from app.schemas.common import fail
from app.services import mqtt_service
from app.services.device_online_sync_scheduler import (
    start_device_online_sync_scheduler,
    stop_device_online_sync_scheduler,
)
from app.services.op_log_purge_scheduler import (
    start_op_log_purge_scheduler,
    stop_op_log_purge_scheduler,
)
from app.rag.ingest_watchdog import start_ingest_watchdog, stop_ingest_watchdog
from app.utils.crypto import get_public_key_pem


def _ensure_mdm_console_logging() -> None:
    """保证 mdm.* 业务日志输出到控制台（uvicorn 默认不一定挂载自定义 logger）."""
    mdm = logging.getLogger("mdm")
    mdm.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in mdm.handlers):
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        mdm.addHandler(handler)
    # 子 logger 继承；避免再经 root 重复打印
    mdm.propagate = False


app = FastAPI(title=settings.app_name, version="0.1.0")
# 后添加的中间件更靠外：Audit 包裹 Auth，便于拿到 user_id 并记录成功/失败
app.add_middleware(AuthGuardMiddleware)
app.add_middleware(AuditLogMiddleware)

# 对外设备侧白名单接口（/api/*，AuthGuard 已放行）
app.include_router(device_strategy_router, prefix="/api")
app.include_router(device_report_router, prefix="/api")
app.include_router(device_app_router, prefix="/api")
app.include_router(device_bind_router, prefix="/api")
app.include_router(device_mdm_router, prefix="/api")
app.include_router(device_biz_card_router, prefix="/api")
app.include_router(device_rag_router, prefix="/api")
# 企业对接 OpenAPI（/openapi/*，非 /platform 前缀，AuthGuard 自然放行；暂无签名）
app.include_router(openapi_approval_router, prefix="/openapi")


@app.on_event("startup")
def on_startup() -> None:
    _ensure_mdm_console_logging()
    init_db()
    get_public_key_pem()
    # MQTT：有配置则后台连接；失败不影响服务启动
    db = SessionLocal()
    try:
        mqtt_service.startup_connect(db)
    finally:
        db.close()
    # 设备在线：定时全量校准（与策略下发共用 sync_device_online_status）
    start_device_online_sync_scheduler()
    # 操作日志：每天本地 01:00 清理过期 t_sys_op_log
    start_op_log_purge_scheduler()
    # RAG：重启后恢复 parsing 队列 + 入库超时巡检（从正式解析起算）
    try:
        from app.rag.service import resume_interrupted_ingests

        resume_interrupted_ingests()
    except Exception:
        logging.getLogger("mdm.rag").exception("RAG 启动恢复入库失败（不影响服务启动）")
    start_ingest_watchdog()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_device_online_sync_scheduler()
    stop_op_log_purge_scheduler()
    stop_ingest_watchdog()


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(status_code=exc.status_code, content=fail(detail, code=exc.status_code))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=fail("参数校验失败", code=422, data=exc.errors()))


app.include_router(api_router)


@app.get("/platform/health")
def health():
    return {"code": 0, "message": "ok", "data": {"app": settings.app_name}}


if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")
    app.mount("/pages", StaticFiles(directory=str(WEB_DIR / "pages"), html=True), name="pages")


@app.get("/")
async def index():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(fail("前端未部署", 404))
    return FileResponse(index_file)


@app.get("/login.html")
async def login_page():
    login_file = WEB_DIR / "login.html"
    if not login_file.exists():
        raise HTTPException(status_code=404, detail="登录页不存在")
    return FileResponse(login_file)


@app.get("/{path:path}")
async def spa_fallback(path: str):
    """兼容静态 html 直链访问."""
    if path.startswith("api/") or path.startswith("platform/"):
        raise HTTPException(status_code=404, detail="接口不存在")
    candidate = WEB_DIR / path
    if candidate.is_file():
        return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="页面不存在")
