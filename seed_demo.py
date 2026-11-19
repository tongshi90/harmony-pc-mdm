"""
灌入本地联调基础演示数据（成员分组 / 人员 / 设备 / 应用仓库）。

依赖：已有 data/mdm.db（或首次运行时自动 bootstrap 建库 + admin）。
不会删除现有业务数据；若检测到演示标记「演示科技」分组已存在则跳过（可用 --force 强制再灌，
会跳过已存在的同名 SN / 工号 / 账号 / app_code，只补缺失项）。

用法（建议先停服务或确认库未被占用）：

  .\\.venv\\Scripts\\python.exe seed_demo.py
  .\\.venv\\Scripts\\python.exe seed_demo.py -y

演示人员默认密码：Pass1234（bcrypt 存储；设备绑定接口仍传明文）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 演示数据标记：用该顶级分组是否存在判断是否已灌过
DEMO_ROOT_NAME = "演示科技"
DEMO_MEMBER_PASSWORD = "Pass1234"


def _confirm(skip: bool) -> bool:
    if skip:
        return True
    tip = (
        f"将向当前库写入演示数据（分组「{DEMO_ROOT_NAME}」等）。\n"
        "已存在的同名 SN / 工号 / 账号 / 应用编码会跳过。继续？[y/N] "
    )
    try:
        return input(tip).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def seed(*, force: bool = False) -> dict[str, int]:
    from app.bootstrap import init_db
    from app.database import SessionLocal
    from app.models.app_pkg import AppBase, AppVersion
    from app.models.department import SysDepartment, SysMember
    from app.models.device import Device
    from app.utils.security import hash_password
    from app.utils.snowflake import snowflake_id
    from app.utils.timeutil import now as local_now

    init_db()
    db = SessionLocal()
    stats = {
        "departments": 0,
        "members": 0,
        "devices": 0,
        "apps": 0,
        "app_versions": 0,
        "skipped": 0,
    }
    try:
        now = local_now()
        root = (
            db.query(SysDepartment)
            .filter(SysDepartment.name == DEMO_ROOT_NAME)
            .first()
        )
        if root and not force:
            print(
                f"已检测到分组「{DEMO_ROOT_NAME}」，视为演示数据已存在。"
                "如需补缺请加 --force。"
            )
            return stats

        # —— 成员分组（树）——
        def ensure_dept(
            name: str, *, parent_id: int | None, description: str = ""
        ) -> SysDepartment:
            nonlocal stats
            row = db.query(SysDepartment).filter(SysDepartment.name == name).first()
            if row:
                stats["skipped"] += 1
                return row
            path = name
            if parent_id:
                parent = db.query(SysDepartment).filter(SysDepartment.id == parent_id).first()
                if not parent:
                    raise RuntimeError(f"父分组不存在: {parent_id}")
                path = f"{parent.path}/{name}"
            row = SysDepartment(
                id=snowflake_id(),
                parent_id=parent_id,
                name=name,
                path=path,
                description=description or None,
                initial_policy_id=None,
                status=1,
                create_time=now,
                update_time=now,
            )
            db.add(row)
            db.flush()
            stats["departments"] += 1
            return row

        root = ensure_dept(DEMO_ROOT_NAME, parent_id=None, description="联调演示根机构")
        dept_rd = ensure_dept("研发中心", parent_id=root.id, description="研发")
        dept_fe = ensure_dept("前端组", parent_id=dept_rd.id)
        dept_be = ensure_dept("后端组", parent_id=dept_rd.id)
        dept_ops = ensure_dept("运维部", parent_id=root.id)
        dept_hr = ensure_dept("综合部", parent_id=root.id)

        # —— 人员 ——
        pwd_hash = hash_password(DEMO_MEMBER_PASSWORD)

        def ensure_member(
            *,
            name: str,
            employee_id: str,
            account: str,
            department_id: int,
        ) -> SysMember | None:
            nonlocal stats
            exists = (
                db.query(SysMember)
                .filter(
                    (SysMember.employee_id == employee_id)
                    | (SysMember.account == account)
                )
                .first()
            )
            if exists:
                stats["skipped"] += 1
                return exists if int(exists.is_delete or 0) == 0 else None
            row = SysMember(
                id=snowflake_id(),
                department_id=department_id,
                name=name,
                employee_id=employee_id,
                account=account,
                password=pwd_hash,
                status=1,
                is_delete=0,
                create_time=now,
                update_time=now,
            )
            db.add(row)
            db.flush()
            stats["members"] += 1
            return row

        members_spec = [
            ("张三", "E10001", "zhangsan", dept_fe.id),
            ("李四", "E10002", "lisi", dept_fe.id),
            ("王五", "E10003", "wangwu", dept_be.id),
            ("赵六", "E10004", "zhaoliu", dept_be.id),
            ("钱七", "E10005", "qianqi", dept_ops.id),
            ("孙八", "E10006", "sunba", dept_ops.id),
            ("周九", "E10007", "zhoujiu", dept_hr.id),
            ("吴十", "E10008", "wushi", dept_hr.id),
        ]
        members: list[SysMember] = []
        for name, eid, acc, did in members_spec:
            m = ensure_member(
                name=name, employee_id=eid, account=acc, department_id=did
            )
            if m:
                members.append(m)

        # —— 设备（部分绑定、部分仅预登记）——
        def ensure_device(
            sn: str,
            *,
            member: SysMember | None = None,
            online: bool = False,
            with_basic: bool = False,
            index: int = 0,
        ) -> None:
            nonlocal stats
            sn = (sn or "").strip().upper()
            if db.query(Device.id).filter(Device.sn == sn).first():
                stats["skipped"] += 1
                return
            bound = member is not None
            row = Device(
                id=snowflake_id(),
                sn=sn,
                device_name=f"演示PC-{index:02d}" if with_basic else None,
                model="HUAWEI Qingyun W515" if with_basic else None,
                model_version="1.0" if with_basic else None,
                vendor="HUAWEI" if with_basic else None,
                serial_number=sn if with_basic else None,
                imei=None,
                member_id=member.id if member else None,
                bind_status=1 if bound else 0,
                status=1 if online else 2,
                is_compliant=1,
                policy_diff_count=0,
                activate_time=now if bound else None,
                online_time=now if online else None,
                basic_info_synced=1 if with_basic else 0,
                os="HarmonyOS PC 5.0" if with_basic else None,
                os_build="5.0.0.100" if with_basic else None,
                cpu="Kirin 9000C" if with_basic else None,
                memory="16 GB" if with_basic else None,
                disk="512 GB SSD" if with_basic else None,
                hostname=f"demo-pc-{index:02d}" if with_basic else None,
                ip=f"10.10.{(index // 10) + 1}.{10 + index}" if with_basic else None,
                mac=f"00:1A:2B:3C:4D:{index:02X}" if with_basic else None,
                agent_version="1.0.0" if with_basic else None,
                mqtt_client_id=sn if with_basic else None,
                remark="seed_demo" if with_basic else None,
                create_time=now,
                update_time=now,
            )
            db.add(row)
            stats["devices"] += 1

        # 已绑定 + 有基本信息
        for i, m in enumerate(members[:6], start=1):
            ensure_device(
                f"DEMO-SN-{i:04d}",
                member=m,
                online=(i % 2 == 1),
                with_basic=True,
                index=i,
            )
        # 未绑定预登记
        for i in range(7, 11):
            ensure_device(f"DEMO-SN-{i:04d}", member=None, online=False, with_basic=False, index=i)

        # —— 应用仓库（无真实 HAP，仅元数据；发布态便于联调列表展示）——
        apps_spec = [
            {
                "app_name": "企业办公套件",
                "app_code": "demo_office",
                "app_id": "com.demo.office",
                "bundle_name": "com.demo.office",
                "description": "演示用办公应用",
                "versions": [
                    ("1.0.0", "100", 2),
                    ("1.1.0", "110", 2),
                ],
            },
            {
                "app_name": "安全浏览器",
                "app_code": "demo_browser",
                "app_id": "com.demo.browser",
                "bundle_name": "com.demo.browser",
                "description": "演示用浏览器",
                "versions": [
                    ("2.0.0", "200", 2),
                    ("2.0.1", "201", 0),  # 草稿
                ],
            },
            {
                "app_name": "远程协助",
                "app_code": "demo_remote",
                "app_id": "com.demo.remote",
                "bundle_name": "com.demo.remote",
                "description": "演示用远程协助",
                "versions": [
                    ("3.0.0", "300", 2),
                ],
            },
        ]

        for spec in apps_spec:
            app = db.query(AppBase).filter(AppBase.app_code == spec["app_code"]).first()
            if not app:
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
                stats["apps"] += 1
            else:
                stats["skipped"] += 1

            for ver_name, ver_code, status in spec["versions"]:
                exists_ver = (
                    db.query(AppVersion)
                    .filter(
                        AppVersion.app_id == app.id,
                        AppVersion.version_code == ver_code,
                    )
                    .first()
                )
                if exists_ver:
                    stats["skipped"] += 1
                    continue
                db.add(
                    AppVersion(
                        id=snowflake_id(),
                        app_id=app.id,
                        version_name=ver_name,
                        version_code=ver_code,
                        file_name=None,
                        file_path=None,
                        file_size=None,
                        file_md5=None,
                        status=int(status),
                        publish_time=now if int(status) == 2 else None,
                        create_time=now,
                        update_time=now,
                    )
                )
                stats["app_versions"] += 1

        db.commit()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="灌入 MDM 联调演示数据")
    parser.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使已有「演示科技」分组也继续补缺（已存在键跳过）",
    )
    args = parser.parse_args()
    if not _confirm(args.yes):
        print("已取消")
        return 1

    print("正在写入演示数据…")
    stats = seed(force=bool(args.force))
    print(
        "完成："
        f"分组 +{stats['departments']}，"
        f"人员 +{stats['members']}，"
        f"设备 +{stats['devices']}，"
        f"应用 +{stats['apps']}，"
        f"应用版本 +{stats['app_versions']}，"
        f"跳过 {stats['skipped']}"
    )
    print(f"人员默认密码：{DEMO_MEMBER_PASSWORD}")
    print("设备 SN 示例：DEMO-SN-0001 … DEMO-SN-0010（前 6 台已绑定）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
