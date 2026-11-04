"""固定菜单枚举：菜单名、Code、接口路径前缀、前端路由等."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class MenuCode(str, Enum):
    """固定菜单 Code（写入 t_sys_role_menu.menu_code）；顺序与侧栏/登录默认页一致."""

    DASHBOARD = "dashboard"
    DEVICE = "device"
    MEMBER = "member"
    MEMBER_GROUP = "member_group"
    APP = "app"
    POLICY_DISPATCH = "policy_dispatch"
    PLATFORM = "platform"


@dataclass(frozen=True)
class MenuItem:
    code: str
    name: str
    api_prefix: str  # 该菜单下接口统一前缀，如 /platform/app
    nav_id: str  # 前端导航高亮 id
    href: str  # 前端入口路径
    group: str  # 侧栏分组
    sort: int
    # False：不出现在侧栏 / 角色权限勾选；菜单 Code、页面与接口仍保留（可直链调试）
    visible: bool = True


# 平台固定菜单（不允许前端动态增删）；sort 决定侧栏/角色勾选/登录默认页顺序
_MENU_ITEMS: tuple[MenuItem, ...] = (
    MenuItem(
        code=MenuCode.DASHBOARD.value,
        name="数据看板",
        api_prefix="/platform/dashboard",
        nav_id="dashboard",
        href="/index.html",
        group="运营监控",
        sort=10,
    ),
    MenuItem(
        code=MenuCode.DEVICE.value,
        name="设备管理",
        api_prefix="/platform/device",
        nav_id="device",
        href="/pages/devices/devices.html",
        group="终端资源",
        sort=20,
    ),
    MenuItem(
        code=MenuCode.MEMBER.value,
        name="人员管理",
        api_prefix="/platform/member",
        nav_id="member",
        href="/pages/members/members.html",
        group="组织人员",
        sort=30,
    ),
    MenuItem(
        code=MenuCode.MEMBER_GROUP.value,
        name="成员分组",
        api_prefix="/platform/member-group",
        nav_id="member_group",
        href="/pages/members/groups.html",
        group="组织人员",
        sort=40,
    ),
    MenuItem(
        code=MenuCode.APP.value,
        name="应用管理",
        api_prefix="/platform/app",
        nav_id="app",
        href="/pages/apps/apps.html",
        group="终端资源",
        sort=50,
    ),
    MenuItem(
        code=MenuCode.POLICY_DISPATCH.value,
        name="策略记录",
        api_prefix="/platform/policy",
        nav_id="policy_dispatch",
        href="/pages/scenes/scene-dispatch.html",
        group="策略中心",
        sort=60,
    ),
    MenuItem(
        code=MenuCode.PLATFORM.value,
        name="平台基础管理",
        api_prefix="/platform/platform",
        nav_id="platform",
        href="/pages/platform/users.html",
        group="平台管理",
        sort=70,
    ),
)

_MENU_BY_CODE: dict[str, MenuItem] = {m.code: m for m in _MENU_ITEMS}


def list_menus(*, include_hidden: bool = True) -> list[MenuItem]:
    items = _MENU_ITEMS if include_hidden else tuple(m for m in _MENU_ITEMS if m.visible)
    return sorted(items, key=lambda m: m.sort)


def get_menu(code: str | MenuCode) -> MenuItem | None:
    key = code.value if isinstance(code, MenuCode) else code
    return _MENU_BY_CODE.get(key)


def all_menu_codes(*, include_hidden: bool = True) -> list[str]:
    return [m.code for m in list_menus(include_hidden=include_hidden)]


def match_menu_by_path(path: str) -> MenuItem | None:
    """根据请求路径匹配所属菜单（最长前缀优先）."""
    matched: MenuItem | None = None
    best = -1
    for item in _MENU_ITEMS:
        prefix = item.api_prefix.rstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            if len(prefix) > best:
                matched = item
                best = len(prefix)
    return matched


def menu_to_dict(item: MenuItem) -> dict:
    return asdict(item)
