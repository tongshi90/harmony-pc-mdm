from fastapi import APIRouter

from app.api import (
    app_pkg,
    auth,
    dashboard,
    device,
    initial_policy,
    mdm_app,
    member,
    member_group,
    platform,
    policy_dispatch,
)

# 云侧管理台接口统一前缀 /platform；对外设备侧白名单接口预留 /api/
api_router = APIRouter(prefix="/platform")
api_router.include_router(auth.router, prefix="/auth", tags=["授权认证"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["数据看板"])
api_router.include_router(platform.router, prefix="/platform", tags=["平台基础管理"])
api_router.include_router(mdm_app.router, prefix="/platform", tags=["平台基础管理-MDM应用"])
api_router.include_router(
    mdm_app.public_router, tags=["MDM应用-安装包下载"]
)
api_router.include_router(app_pkg.router, prefix="/app", tags=["应用管理"])
api_router.include_router(
    app_pkg.public_router, prefix="/app", tags=["应用管理-安装包下载"]
)
api_router.include_router(
    member_group.router, prefix="/member-group", tags=["成员分组"]
)
api_router.include_router(
    initial_policy.router, prefix="/member-group", tags=["初始策略"]
)
api_router.include_router(member.router, prefix="/member", tags=["人员管理"])
api_router.include_router(device.router, prefix="/device", tags=["设备管理"])
api_router.include_router(
    policy_dispatch.router, prefix="/policy", tags=["策略下发"]
)
