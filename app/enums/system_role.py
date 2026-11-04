"""内置系统角色：不可删除 / 编辑 / 禁用 / 改权限；仅启动引导维护."""

from __future__ import annotations

from dataclasses import dataclass

from app.enums.menu import MenuCode, all_menu_codes


@dataclass(frozen=True)
class SystemRoleDef:
    role_code: str
    role_name: str
    description: str
    menu_codes: tuple[str, ...]


# 安全保密管理员：业务侧人员/设备/应用/策略管控（不含平台账号与审计配置）
_SEC_CONFIDENTIAL_MENUS = (
    MenuCode.DASHBOARD.value,
    MenuCode.DEVICE.value,
    MenuCode.MEMBER.value,
    MenuCode.MEMBER_GROUP.value,
    MenuCode.APP.value,
    MenuCode.POLICY_DISPATCH.value,
)

# 安全审计员：看板 + 平台基础管理（含操作日志；菜单粒度后续可再拆）
_SEC_AUDITOR_MENUS = (
    MenuCode.DASHBOARD.value,
    MenuCode.PLATFORM.value,
)


def system_role_defs() -> tuple[SystemRoleDef, ...]:
    """商用初始化内置的三个系统角色（菜单可后续再调）."""
    return (
        SystemRoleDef(
            role_code="system_admin",
            role_name="系统管理员",
            description="系统角色：拥有全部菜单操作权限",
            menu_codes=tuple(all_menu_codes(include_hidden=True)),
        ),
        SystemRoleDef(
            role_code="sec_confidential",
            role_name="安全保密管理员",
            description="系统角色：人员/设备/应用与策略下发等业务安全管控（菜单可后续调整）",
            menu_codes=_SEC_CONFIDENTIAL_MENUS,
        ),
        SystemRoleDef(
            role_code="sec_auditor",
            role_name="安全审计员",
            description="系统角色：数据看板与平台审计相关能力（菜单可后续调整）",
            menu_codes=_SEC_AUDITOR_MENUS,
        ),
    )


SYSTEM_ROLE_CODES: frozenset[str] = frozenset(d.role_code for d in system_role_defs())
