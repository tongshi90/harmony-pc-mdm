"""
数据库初始化 / 调试数据灌入脚本。

用法（在项目根目录执行）：

1) 重置为初始状态（仅保留 admin 管理员，其余表清空）
   .\\.venv\\Scripts\\python.exe db_init.py
   # 或
   python db_init.py

2) 重置后灌入业务联调 Demo 数据（各业务表均有关联样例）
   .\\.venv\\Scripts\\python.exe db_init.py --demo
   # 或
   python db_init.py --demo

说明：
- 建议先停止服务（Ctrl+C）再执行，避免 SQLite 文件被占用。
- 执行完成后可再启动 .\\start.ps1。
- 服务启动时的 bootstrap 不再自动灌入调试数据，避免覆盖本脚本结果。

关于表结构（重要）：
- 本脚本不写死 DDL。建表通过 SQLAlchemy 模型（app/models/*）注册到 Base.metadata，
  再调用 Base.metadata.create_all()——与服务启动时 bootstrap 同源。
- create_all 只会「新建缺失的表」，不会自动改已有表的列（增删改字段需 bootstrap
  里的迁移逻辑，或删库后重建）。
- 清空数据时优先按 _CLEAR_ORDER，并自动附带清空 Base.metadata 中尚未列入的表，
  因此后续新增模型并在本文件 import 后，一般可正常初始化；若有外键依赖顺序问题，
  把新表名补进 _CLEAR_ORDER 更稳妥。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

# 保证以脚本方式运行时可导入 app 包
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import DATA_DIR, settings
from app.database import Base, SessionLocal, engine
from app.enums.menu import MenuCode
from app.services.role_service import ensure_system_roles
from app.models import (  # noqa: F401 — 注册全部模型供 create_all / 清空
    AppBase,
    AppVersion,
    Device,
    DeviceAppInstalled,
    DevicePolicyCurrent,
    DevicePolicyExpected,
    InitialPolicy,
    InitialPolicyItem,
    PolicyDeviceTask,
    PolicyTask,
    PolicyTaskItem,
    SysDepartment,
    SysMember,
    SysMqttConfig,
    SysOpLog,
    SysRole,
    SysRoleMenu,
    User,
    UserToken,
)
from app.utils.policy_summary import build_policy_item_summary
from app.utils.security import hash_password
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

# 清空顺序：先子表后父表（未列入的模型表也会在 _clear_all_tables 末尾补清）
_CLEAR_ORDER = [
    "t_policy_device_task",
    "t_policy_task_item",
    "t_policy_task",
    "t_device_app_installed",
    "t_device_policy_expected",
    "t_device_policy_current",
    "t_device",
    "t_sys_member",
    "t_sys_department",
    "t_initial_policy_item",
    "t_initial_policy",
    "t_app_version",
    "t_app_base",
    "t_mdm_app_version",
    "t_sys_op_log",
    "t_sys_role_menu",
    "t_sys_role",
    "t_sys_mqtt_config",
    "t_user_tokens",
    "t_user",
]


def _ensure_schema() -> None:
    """按当前 ORM 模型建缺失表（不改已有表结构）。"""
    Base.metadata.create_all(bind=engine)


def _clear_all_tables() -> None:
    with engine.begin() as conn:
        # SQLite：关闭外键约束以便批量清空
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        existing = set(
            conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ).scalars()
        )
        ordered = list(_CLEAR_ORDER)
        for tname in Base.metadata.tables.keys():
            if tname not in ordered:
                ordered.append(tname)
        for name in ordered:
            if name in existing:
                conn.execute(text(f'DELETE FROM "{name}"'))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def _seed_admin(db: Session) -> User:
    now = local_now()
    admin = User(
        id=snowflake_id(),
        name=settings.default_admin_name,
        phone=None,
        email=None,
        username=settings.default_admin_username,
        password=hash_password(settings.default_admin_password),
        status=1,
        is_delete=0,
        is_admin=1,
        role_id=None,
    )
    db.add(admin)
    db.flush()
    return admin


def _ensure_demo_hap() -> dict:
    """准备联调用占位 .hap（各 Demo 版本可共用同一文件）."""
    dest_dir = DATA_DIR / "uploads" / "demo"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "seed.hap"
    if not dest.is_file():
        # 优先复用已有调试包；否则写一段占位字节
        candidates = sorted((DATA_DIR / "uploads" / "apps").rglob("*.hap")) if (DATA_DIR / "uploads" / "apps").is_dir() else []
        if candidates:
            dest.write_bytes(candidates[0].read_bytes())
        else:
            dest.write_bytes(b"MDM-DEMO-HAP-PLACEHOLDER\n")
    raw = dest.read_bytes()
    rel = dest.relative_to(DATA_DIR).as_posix()
    return {
        "file_name": dest.name,
        "file_path": rel,
        "file_size": len(raw),
        "file_md5": hashlib.md5(raw).hexdigest(),
    }


def reset_to_initial() -> None:
    """仅保留 admin，其它表为空。"""
    _ensure_schema()
    _clear_all_tables()
    db = SessionLocal()
    try:
        _seed_admin(db)
        db.commit()
        print(
            f"[ok] 已重置数据库：仅保留管理员 "
            f"{settings.default_admin_username} / {settings.default_admin_password}"
        )
    finally:
        db.close()


# 规模化 Demo：姓名池（姓 + 名），用于生成约数百人员
_SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻")
_GIVEN = [
    "明", "芳", "华", "强", "磊", "洋", "勇", "艳", "杰", "娜", "超", "秀英", "霞", "平", "刚",
    "桂英", "建华", "文", "辉", "力", "静", "丽", "敏", "军", "涛", "伟", "鹏", "婷", "鑫", "宇",
    "悦", "凯", "浩", "博", "雪", "倩", "宁", "翔", "晨", "阳", "丹", "璐", "峰", "航", "琳",
]


def _seed_org_scale(
    db: Session,
    *,
    now,
    pol_default_id: int,
    pol_rd_id: int,
    pol_sales_id: int,
) -> dict:
    """灌入类似中型企业的分组树、数百人员及设备绑定关系.

    Returns:
        统计与样例设备，供后续安装包 / 快照引用。
    """
    rng = random.Random(20261013)

    def add_dept(
        *,
        parent: SysDepartment | None,
        name: str,
        desc: str | None = None,
        policy_id: int | None = None,
    ) -> SysDepartment:
        path = name if parent is None else f"{parent.path}/{name}"
        row = SysDepartment(
            id=snowflake_id(),
            parent_id=parent.id if parent else None,
            name=name,
            path=path,
            description=desc,
            initial_policy_id=policy_id,
            status=1,
            create_time=now,
            update_time=now,
        )
        db.add(row)
        db.flush()
        return row

    hq = add_dept(parent=None, name="总部", desc="组织根节点", policy_id=pol_default_id)

    # 一级部门 + 叶子组 + 目标人数（合计约 420 人）
    org_plan: list[tuple[str, int | None, list[tuple[str, int]]]] = [
        (
            "销售部",
            pol_sales_id,
            [("销售一部", 42), ("销售二部", 38), ("销售三部", 36), ("大客户组", 28)],
        ),
        (
            "研发中心",
            pol_rd_id,
            [
                ("后端组", 48),
                ("前端组", 40),
                ("测试组", 32),
                ("基础架构组", 24),
                ("移动端组", 28),
            ],
        ),
        ("市场部", pol_default_id, [("品牌组", 18), ("增长组", 22)]),
        ("财务部", pol_default_id, [("核算组", 16), ("资金组", 12)]),
        ("人力资源部", pol_default_id, [("招聘组", 14), ("员工关系组", 12)]),
        (
            "客户成功部",
            pol_default_id,
            [("华东区", 26), ("华南区", 24), ("华北区", 22)],
        ),
        ("产品中心", pol_default_id, [("产品一组", 20), ("产品二组", 18)]),
        ("运维与安全", pol_default_id, [("基础运维", 16), ("安全合规", 14)]),
    ]

    leaf_depts: list[tuple[SysDepartment, int, str]] = []  # (dept, headcount, line)
    for l1_name, policy_id, children in org_plan:
        l1 = add_dept(parent=hq, name=l1_name, policy_id=policy_id)
        line = "sales" if l1_name == "销售部" else ("rd" if l1_name == "研发中心" else "other")
        for child_name, count in children:
            leaf = add_dept(parent=l1, name=child_name)
            leaf_depts.append((leaf, count, line))

    # 密码只哈希一次（bcrypt 很慢，数百人复用同一哈希）
    member_pwd = hash_password("Abc@1234")

    members: list[SysMember] = []
    sales_members: list[SysMember] = []
    rd_members: list[SysMember] = []
    emp_seq = 20180001
    used_names: set[str] = set()

    def next_name() -> str:
        for _ in range(2000):
            n = rng.choice(_SURNAMES) + rng.choice(_GIVEN)
            if n not in used_names:
                used_names.add(n)
                return n
        n = f"员工{emp_seq}"
        used_names.add(n)
        return n

    for leaf, count, line in leaf_depts:
        for i in range(count):
            emp_seq += 1
            name = next_name()
            account = f"u{emp_seq}"
            member = SysMember(
                id=snowflake_id(),
                department_id=leaf.id,
                name=name,
                employee_id=f"E{emp_seq}",
                account=account,
                password=member_pwd,
                status=1 if rng.random() > 0.03 else 0,  # 约 3% 禁用
                is_delete=0,
                create_time=now,
                update_time=now,
            )
            db.add(member)
            members.append(member)
            if line == "sales":
                sales_members.append(member)
            elif line == "rd":
                rd_members.append(member)
        if len(members) % 80 == 0:
            db.flush()

    db.flush()

    # 固定几位「具名」人员，方便肉眼辨认与联调
    if sales_members:
        sales_members[0].name = "张明"
        sales_members[0].account = "zhang.ming"
        sales_members[0].employee_id = "E20190315"
        sales_members[0].status = 1
    if len(rd_members) >= 2:
        rd_members[0].name = "李芳"
        rd_members[0].account = "li.fang"
        rd_members[0].employee_id = "E20180642"
        rd_members[0].status = 1
        rd_members[1].name = "陈新"
        rd_members[1].account = "chen.xin"
        rd_members[1].employee_id = "E20260901"
        rd_members[1].status = 1
    db.flush()

    vendors = [
        ("Lenovo", "ThinkPad T14 Gen4", "Gen4"),
        ("Dell", "Latitude 5440", "5440-Pro"),
        ("HP", "EliteBook 840 G10", "840-Std"),
        ("Huawei", "MateBook 14", "2024"),
        ("Honor", "MagicBook Pro", "16"),
    ]

    def make_device(
        *,
        sn: str,
        member: SysMember | None,
        name_hint: str,
        online: bool,
        idx: int,
    ) -> Device:
        vendor, model, model_ver = vendors[idx % len(vendors)]
        prefix = {"Lenovo": "LN", "Dell": "DL", "HP": "HP", "Huawei": "HW", "Honor": "HN"}[vendor]
        bound = member is not None
        subnet_c = 10 + (idx % 40)
        host = 20 + (idx % 200)
        return Device(
            id=snowflake_id(),
            sn=sn,
            device_name=name_hint,
            model=model,
            model_version=model_ver,
            vendor=vendor,
            serial_number=f"{prefix}{100000 + idx}",
            imei=f"8601{100000000 + idx:09d}"[:15],
            member_id=member.id if member else None,
            bind_status=1 if bound else 0,
            status=1 if online else 2,
            is_compliant=1,
            policy_diff_count=0,
            # 演示数据已灌入完整基本信息，视为已完成首次同步
            basic_info_synced=1,
            activate_time=now if bound else None,
            online_time=now if online else None,
            os="Windows 11 Pro" if idx % 5 else "Windows 10 Pro",
            os_build="26100.1742" if idx % 5 else "19045.4780",
            cpu="Intel Core i5-1345U" if idx % 2 == 0 else "Intel Core i7-1365U",
            memory="16 GB",
            disk="512 GB SSD",
            gpu="Intel Iris Xe",
            bios_version=f"1.{10 + (idx % 40)}",
            hostname=f"PC-{prefix}-{idx:04d}",
            ip=f"10.12.{subnet_c}.{host}",
            mac=":".join(f"{(idx * (k + 3)) % 256:02X}" for k in range(6)),
            subnet="255.255.255.0",
            gateway=f"10.12.{subnet_c}.1",
            dns="10.12.0.53",
            agent_version="3.2.1-build.428" if online else "3.1.0-build.310",
            mqtt_client_id=f"mdm-pc-{sn}",
            create_time=now,
            update_time=now,
        )

    devices: list[Device] = []
    bound_devices: list[Device] = []
    # 一人一设备：约 88% 启用人员绑定 1 台，其余未绑定；库存机另计
    sn_seq = 1
    for member in members:
        if member.status != 1:
            continue
        if rng.random() < 0.12:
            continue  # 未绑定
        sn = f"PC-DEMO-{sn_seq:05d}"
        sn_seq += 1
        online = rng.random() > 0.18
        d = make_device(
            sn=sn,
            member=member,
            name_hint=f"{member.name}的电脑",
            online=online,
            idx=sn_seq,
        )
        db.add(d)
        devices.append(d)
        bound_devices.append(d)
        if sn_seq % 100 == 0:
            db.flush()

    # 库存未绑定设备约 35 台
    idle_devices: list[Device] = []
    for j in range(35):
        sn = f"PC-IDLE-{j + 1:03d}"
        d = make_device(
            sn=sn,
            member=None,
            name_hint=f"备用机-{j + 1:02d}",
            online=False,
            idx=9000 + j,
        )
        # 固定三台经典 SN，方便文档/口头联调
        if j == 0:
            d.sn = "PC-HP-20240604512"
            d.device_name = "备用机-未绑定"
            d.mqtt_client_id = f"mdm-pc-{d.sn}"
        db.add(d)
        devices.append(d)
        idle_devices.append(d)

    db.flush()

    # 具名样例设备 SN（覆盖前几台绑定机）
    sample_sales = bound_devices[0] if bound_devices else idle_devices[0]
    sample_rd = bound_devices[1] if len(bound_devices) > 1 else sample_sales
    if sales_members:
        for d in bound_devices:
            if d.member_id == sales_members[0].id:
                sample_sales = d
                d.sn = "PC-LN-20240800127"
                d.device_name = f"销售-{sales_members[0].name}"
                d.mqtt_client_id = f"mdm-pc-{d.sn}"
                d.status = 1
                d.online_time = now
                break
    if rd_members:
        for d in bound_devices:
            if d.member_id == rd_members[0].id:
                sample_rd = d
                d.sn = "PC-DL-20240708934"
                d.device_name = f"研发-{rd_members[0].name}"
                d.mqtt_client_id = f"mdm-pc-{d.sn}"
                d.status = 1
                d.online_time = now
                break
    sample_idle = idle_devices[0]
    db.flush()

    dept_count = 1 + sum(1 + len(children) for _, _, children in org_plan)
    return {
        "dept_count": dept_count,
        "member_count": len(members),
        "device_count": len(devices),
        "bound_count": len(bound_devices),
        "idle_count": len(idle_devices),
        "sample_sales_device": sample_sales,
        "sample_rd_device": sample_rd,
        "sample_idle_device": sample_idle,
        "sample_bound_devices": bound_devices,
    }


def seed_demo() -> None:
    """清空后灌入全量联调数据（表间关联齐全）。"""
    _ensure_schema()
    _clear_all_tables()
    db = SessionLocal()
    try:
        now = local_now()
        admin = _seed_admin(db)

        # ---------- 角色 / 菜单（含三个系统角色 + Demo 自定义角色）----------
        ensure_system_roles(db)
        roles: dict[str, SysRole] = {
            r.role_code: r
            for r in db.query(SysRole).filter(SysRole.is_system == 1).all()
        }
        custom_role_defs = [
            (
                "运维工程师",
                "operator",
                "Demo 自定义角色：设备、成员、应用与策略下发",
                [
                    MenuCode.DASHBOARD.value,
                    MenuCode.DEVICE.value,
                    MenuCode.MEMBER_GROUP.value,
                    MenuCode.MEMBER.value,
                    MenuCode.APP.value,
                    MenuCode.POLICY_DISPATCH.value,
                ],
            ),
            ("只读观察员", "viewer", "Demo 自定义角色：仅数据看板", [MenuCode.DASHBOARD.value]),
        ]
        for name, code, desc, menus in custom_role_defs:
            role = SysRole(
                id=snowflake_id(),
                role_name=name,
                role_code=code,
                description=desc,
                status=1,
                is_system=0,
                create_time=now,
                update_time=now,
            )
            db.add(role)
            db.flush()
            roles[code] = role
            for menu in menus:
                db.add(
                    SysRoleMenu(
                        id=snowflake_id(),
                        role_id=role.id,
                        menu_code=menu,
                        create_time=now,
                    )
                )

        # 普通管理员（绑定安全保密管理员系统角色，便于联调）
        ops_user = User(
            id=snowflake_id(),
            name="王建国",
            phone="13800138001",
            email="wang.jianguo@corp.internal",
            username="wangjg",
            password=hash_password("12345678"),
            status=1,
            is_delete=0,
            is_admin=0,
            role_id=roles["sec_confidential"].id,
        )
        db.add(ops_user)
        db.flush()

        # ---------- MQTT ----------
        db.add(
            SysMqttConfig(
                id=snowflake_id(),
                host="192.168.18.77",
                port=1883,
                tls=0,
                username=None,
                password=None,
                client_id_prefix="mdm-",
                keep_alive=60,
                qos=1,
                clean_session=1,
                api_port=settings.mqtt_api_port,
                api_username=settings.mqtt_api_username,
                api_password=settings.mqtt_api_password,
                update_time=now,
            )
        )

        # ---------- 初始策略模板 ----------
        pol_default = InitialPolicy(
            id=snowflake_id(),
            name="全员默认初始策略",
            description="分组未单独指定时使用的基线策略",
            is_default=1,
            create_time=now,
            update_time=now,
        )
        pol_rd = InitialPolicy(
            id=snowflake_id(),
            name="研发中心初始策略",
            description="研发条线：密码与 WiFi 基线",
            is_default=0,
            create_time=now,
            update_time=now,
        )
        pol_sales = InitialPolicy(
            id=snowflake_id(),
            name="销售条线初始策略",
            description="销售条线：基础办公网络配置",
            is_default=0,
            create_time=now,
            update_time=now,
        )
        db.add_all([pol_default, pol_rd, pol_sales])
        db.flush()

        def add_policy_items(policy_id: int, items: list[tuple[str, dict, int]]) -> None:
            for code, param, sort in items:
                db.add(
                    InitialPolicyItem(
                        id=snowflake_id(),
                        policy_id=policy_id,
                        policy_code=code,
                        param_json=json.dumps(param, ensure_ascii=False),
                        summary=build_policy_item_summary(code, param),
                        sort_order=sort,
                        create_time=now,
                        update_time=now,
                    )
                )

        add_policy_items(
            pol_default.id,
            [
                (
                    "WIFI_SET",
                    {
                        "ssid": "CORP-OFFICE",
                        "securityType": "WIFI_SEC_TYPE_SAE",
                        "preSharedKey": "corp-office-demo",
                    },
                    1,
                ),
                (
                    "PSW_MANAGEMENT",
                    {
                        "complexityRegex": "^[A-Za-z0-9]{8,18}$",
                        "validityPeriod": 30,
                        "additionalDescription": "密码需含字母数字，8-18位",
                    },
                    2,
                ),
                ("USB_MANAGEMENT", {"usbPolicy": "READ_ONLY"}, 3),
            ],
        )
        add_policy_items(
            pol_rd.id,
            [
                (
                    "WIFI_SET",
                    {
                        "ssid": "CORP-RD",
                        "securityType": "WIFI_SEC_TYPE_SAE",
                        "preSharedKey": "corp-rd-demo",
                    },
                    1,
                ),
                (
                    "PSW_MANAGEMENT",
                    {
                        "complexityRegex": "^[A-Za-z0-9]{10,20}$",
                        "validityPeriod": 30,
                        "additionalDescription": "研发环境密码至少10位",
                    },
                    2,
                ),
                ("LOCATION_POLICY", {"policyType": "DISALLOW"}, 3),
            ],
        )
        add_policy_items(
            pol_sales.id,
            [
                (
                    "WIFI_SET",
                    {
                        "ssid": "CORP-OFFICE",
                        "securityType": "WIFI_SEC_TYPE_SAE",
                        "preSharedKey": "corp-office-demo",
                    },
                    1,
                ),
                (
                    "PSW_MANAGEMENT",
                    {
                        "complexityRegex": "^[A-Za-z0-9]{8,18}$",
                        "validityPeriod": 30,
                    },
                    2,
                ),
            ],
        )

        # ---------- 成员分组 / 人员 / 设备（规模化 Demo，约数百人） ----------
        org_stats = _seed_org_scale(
            db,
            now=now,
            pol_default_id=pol_default.id,
            pol_rd_id=pol_rd.id,
            pol_sales_id=pol_sales.id,
        )

        # ---------- 应用仓库 ----------
        demo_hap = _ensure_demo_hap()
        apps_spec = [
            {
                "app_name": "企业邮箱",
                "app_code": "corp.mail",
                "app_id": "com.corp.mail",
                "bundle_name": "com.corp.mail",
                "description": "企业邮箱客户端",
                "versions": [
                    ("1.0.0", "100"),
                    ("1.1.0", "110"),
                ],
            },
            {
                "app_name": "办公套件",
                "app_code": "corp.office",
                "app_id": "com.corp.office",
                "bundle_name": "com.corp.office",
                "description": "文档与表格办公套件",
                "versions": [
                    ("2.0.0", "200"),
                    ("2.1.0", "210"),
                ],
            },
            {
                "app_name": "即时通讯",
                "app_code": "corp.im",
                "app_id": "com.corp.im",
                "bundle_name": "com.corp.im",
                "description": "企业内部 IM",
                "versions": [
                    ("3.0.0", "300"),
                    ("3.0.1", "301"),
                ],
            },
        ]
        app_rows: list[tuple[AppBase, list[AppVersion]]] = []
        for spec in apps_spec:
            app = AppBase(
                id=snowflake_id(),
                app_name=spec["app_name"],
                app_code=spec["app_code"],
                app_id=spec["app_id"],
                bundle_name=spec["bundle_name"],
                description=spec["description"],
                status=1,
                create_time=now,
                update_time=now,
            )
            db.add(app)
            db.flush()
            vers: list[AppVersion] = []
            for vname, vcode in spec["versions"]:
                ver = AppVersion(
                    id=snowflake_id(),
                    app_id=app.id,
                    version_name=vname,
                    version_code=vcode,
                    file_name=demo_hap["file_name"],
                    file_path=demo_hap["file_path"],
                    file_size=demo_hap["file_size"],
                    file_md5=demo_hap["file_md5"],
                    status=2,
                    publish_time=now,
                    create_time=now,
                    update_time=now,
                )
                db.add(ver)
                vers.append(ver)
            db.flush()
            app_rows.append((app, vers))

        # ---------- 设备已安装应用（抽样一批，避免全量过重） ----------
        d_sales = org_stats["sample_sales_device"]
        d_rd = org_stats["sample_rd_device"]
        d_idle = org_stats["sample_idle_device"]
        sample_bound: list[Device] = org_stats["sample_bound_devices"]

        install_plan = [
            (d_sales, [(0, 1, 1), (1, 0, 1)]),
            (d_rd, [(0, 1, 1), (1, 1, 1), (2, 0, 2)]),
            (d_idle, [(0, 0, 1)]),
        ]
        for device, plans in install_plan:
            for app_idx, ver_idx, itype in plans:
                app, vers = app_rows[app_idx]
                ver = vers[ver_idx]
                db.add(
                    DeviceAppInstalled(
                        id=snowflake_id(),
                        device_id=device.id,
                        app_id=app.id,
                        app_version_id=ver.id,
                        install_type=itype,
                        install_time=now,
                        create_time=now,
                    )
                )
        # 再给约 80 台已绑定设备随机装 1~3 个应用
        rng = random.Random(20261013)
        for device in sample_bound[3:83]:
            picks = rng.sample(range(len(app_rows)), k=rng.randint(1, min(3, len(app_rows))))
            for app_idx in picks:
                app, vers = app_rows[app_idx]
                ver = vers[rng.randrange(len(vers))]
                db.add(
                    DeviceAppInstalled(
                        id=snowflake_id(),
                        device_id=device.id,
                        app_id=app.id,
                        app_version_id=ver.id,
                        install_type=1 if rng.random() < 0.7 else 2,
                        install_time=now,
                        create_time=now,
                    )
                )

        # ---------- 设备策略快照（样例机故意制造差异） ----------
        def put_snapshot(sn: str, code: str, expected: dict, current: dict) -> None:
            db.add(
                DevicePolicyExpected(
                    id=snowflake_id(),
                    device_sn=sn,
                    policy_code=code,
                    param_json=json.dumps(expected, ensure_ascii=False),
                    create_time=now,
                    update_time=now,
                )
            )
            db.add(
                DevicePolicyCurrent(
                    id=snowflake_id(),
                    device_sn=sn,
                    policy_code=code,
                    param_json=json.dumps(current, ensure_ascii=False),
                    create_time=now,
                    update_time=now,
                )
            )

        put_snapshot(
            d_sales.sn,
            "WIFI_SET",
            {
                "ssid": "CORP-OFFICE",
                "securityType": "WIFI_SEC_TYPE_SAE",
                "preSharedKey": "corp-office-demo",
            },
            {
                "ssid": "CORP-OFFICE",
                "securityType": "WIFI_SEC_TYPE_SAE",
                "preSharedKey": "corp-office-demo",
            },
        )
        put_snapshot(
            d_sales.sn,
            "PSW_MANAGEMENT",
            {
                "complexityRegex": "^[A-Za-z0-9]{8,18}$",
                "validityPeriod": 2592000000,
                "additionalDescription": "密码需含字母数字，8-18位",
            },
            {
                "complexityRegex": "^[A-Za-z0-9]{8,18}$",
                "validityPeriod": 2592000000,
                "additionalDescription": "密码需含字母数字，8-18位",
            },
        )
        put_snapshot(
            d_rd.sn,
            "WIFI_SET",
            {
                "ssid": "CORP-RD",
                "securityType": "WIFI_SEC_TYPE_SAE",
                "preSharedKey": "corp-rd-demo",
            },
            {
                "ssid": "CORP-GUEST",
                "securityType": "WIFI_SEC_TYPE_OPEN",
            },
        )
        put_snapshot(
            d_rd.sn,
            "PSW_MANAGEMENT",
            {
                "complexityRegex": "^[A-Za-z0-9]{10,20}$",
                "validityPeriod": 2592000000,
            },
            {
                "complexityRegex": "^[A-Za-z0-9]{6,18}$",
                "validityPeriod": 2592000000,
            },
        )
        put_snapshot(
            d_idle.sn,
            "WIFI_SET",
            {
                "ssid": "CORP-OFFICE",
                "securityType": "WIFI_SEC_TYPE_SAE",
                "preSharedKey": "corp-office-demo",
            },
            {
                "ssid": "CORP-OFFICE",
                "securityType": "WIFI_SEC_TYPE_SAE",
                "preSharedKey": "corp-office-demo",
            },
        )

        # ---------- 操作日志 ----------
        for module, action, path, success in (
            ("授权认证", "登录", "/platform/auth/login", 1),
            ("成员分组", "新建分组", "/platform/member-group/groups", 1),
            ("人员管理", "录入成员", "/platform/member", 1),
            ("应用管理", "新建应用", "/platform/app", 1),
        ):
            db.add(
                SysOpLog(
                    id=snowflake_id(),
                    user_id=admin.id,
                    username=admin.username,
                    user_name=admin.name,
                    module=module,
                    action=action,
                    method="POST",
                    path=path,
                    query_params=None,
                    request_body=None,
                    success=success,
                    response_code=0,
                    response_message="",
                    response_body='{"code":0}',
                    client_ip="127.0.0.1",
                    user_agent="db_init/demo",
                    duration_ms=12,
                    create_time=now,
                )
            )

        db.commit()
        print("[ok] 已重置并灌入 Demo 联调数据")
        print(f"  管理员: {settings.default_admin_username} / {settings.default_admin_password}")
        print("  普通账号: wangjg / 12345678（运维工程师）")
        print(
            f"  组织规模: 分组 {org_stats['dept_count']} · 人员 {org_stats['member_count']} · "
            f"设备 {org_stats['device_count']}（已绑定 {org_stats['bound_count']} / "
            f"未绑定 {org_stats['idle_count']}）"
        )
        print(
            f"  快照样例: {d_sales.sn}（销售一致）/ {d_rd.sn}（研发有差异）/ "
            f"{d_idle.sn}（未绑定）"
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="数据库初始化：默认清空仅保留 admin；加 --demo 灌入联调数据"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="清空后写入全量业务 Demo 数据（含表间关联）",
    )
    args = parser.parse_args()
    if args.demo:
        seed_demo()
    else:
        reset_to_initial()


if __name__ == "__main__":
    main()
