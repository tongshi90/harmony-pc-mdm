from __future__ import annotations

import logging
import time

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import (  # noqa: F401 — 注册全部模型供 create_all
    AppBase,
    AppVersion,
    BizCard,
    BizCardStep,
    Device,
    DeviceAppInstalled,
    DeviceLocationLog,
    DevicePolicyCurrent,
    DevicePolicyExpected,
    InitialPolicy,
    InitialPolicyItem,
    MdmAppVersion,
    PolicyDeviceTask,
    PolicyTask,
    PolicyTaskItem,
    RagAskMessage,
    RagAskSession,
    RagFile,
    RagKnowledgeBase,
    SysDepartment,
    SysMember,
    SysLogConfig,
    SysMqttConfig,
    SysOpLog,
    SysRole,
    SysRoleMenu,
    User,
    UserToken,
)
from app.utils.snowflake import snowflake_id

logger = logging.getLogger("mdm.bootstrap")

# 内置 admin 首次种子密码的 bcrypt 哈希（仅不存在时 INSERT；已有用户永不改密）。
# 对应明文仅见项目文档本地调试说明，不写入 Settings / 环境变量。
_DEFAULT_ADMIN_PASSWORD_HASH = (
    "$2b$12$IiiQ6yMr4YIbvA9pvFXLPuPrErMeKPTvtsWnN2uFruqo5Qtbr4GOe"
)


def init_db() -> None:
    """建表 + 确保内置 admin 存在。

    调试/演示数据请用根目录脚本：
      python seed_demo.py        # 灌入分组/人员/设备/应用演示数据
    服务启动不再自动灌入业务 Demo，避免覆盖手动重置结果。

    SQLite 在 uvicorn --reload / 旧进程未退出时可能短暂 database is locked，做有限重试。
    """
    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            migrate_flags = _migrate_schema()
            Base.metadata.create_all(bind=engine)
            db = SessionLocal()
            try:
                _seed_default_admin(db)
                from app.services.role_service import ensure_system_roles

                ensure_system_roles(db)
                _backfill_policy_summaries(db)
                if migrate_flags.get("backfill_compliance"):
                    _backfill_device_compliance(db)
            finally:
                db.close()
            return
        except OperationalError as exc:
            last_exc = exc
            msg = str(exc).lower()
            if "locked" not in msg and "busy" not in msg:
                raise
            logger.warning(
                "init_db 数据库忙（第 %s 次），0.8s 后重试: %s",
                attempt,
                exc,
            )
            time.sleep(0.8)
    assert last_exc is not None
    raise last_exc


def _rebuild_tables_without_ddl_comments(table_names: tuple[str, ...]) -> None:
    """若已有表的 sqlite_master DDL 不含 /* 列注释，则删表由 create_all 重建.

    调试阶段可接受策略下发历史丢失；用于把 model comment 写进 DDL。
    """
    with engine.begin() as conn:
        for name in table_names:
            row = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"
                ),
                {"n": name},
            ).fetchone()
            if row is None:
                continue
            ddl = row[0] or ""
            if "/*" in ddl:
                continue
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))


def _rebuild_policy_dispatch_tables_if_obsolete() -> None:
    """策略变更日志三表：缺 op_type / 仍含旧状态列则重建.

    调试阶段直接删表由 create_all 重建（会清空变更历史）。
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    need_rebuild = False
    if "t_policy_task" in tables:
        cols = {c["name"] for c in insp.get_columns("t_policy_task")}
        if "op_type" not in cols:
            need_rebuild = True
        if {"status", "target_type", "success_count"} & cols:
            need_rebuild = True
    if "t_policy_device_task" in tables:
        cols = {c["name"] for c in insp.get_columns("t_policy_device_task")}
        if {"status", "error_msg", "sent_at"} & cols or "employee_id" not in cols:
            need_rebuild = True
    if not need_rebuild:
        return
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_policy_device_task"))
        conn.execute(text("DROP TABLE IF EXISTS t_policy_task_item"))
        conn.execute(text("DROP TABLE IF EXISTS t_policy_task"))


def _migrate_mdm_drop_app_table() -> None:
    """去掉 t_mdm_app；版本表去掉 mdm_app_id（保留已有版本行）."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        if "t_mdm_app" in tables:
            conn.execute(text("DROP TABLE IF EXISTS t_mdm_app"))
        if "t_mdm_app_version" not in tables:
            return
        cols = {c["name"] for c in insp.get_columns("t_mdm_app_version")}
        if "mdm_app_id" not in cols:
            return
        conn.execute(text("DROP TABLE IF EXISTS t_mdm_app_version__new"))
        conn.execute(
            text(
                """
                CREATE TABLE t_mdm_app_version__new (
                    id BIGINT NOT NULL PRIMARY KEY,
                    version_name VARCHAR(64) NOT NULL,
                    version_code VARCHAR(20) NOT NULL,
                    file_name VARCHAR(255),
                    file_path VARCHAR(512),
                    file_size BIGINT,
                    file_md5 VARCHAR(64),
                    status INTEGER NOT NULL DEFAULT 0,
                    publish_time DATETIME,
                    create_time DATETIME,
                    update_time DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO t_mdm_app_version__new (
                    id, version_name, version_code, file_name, file_path,
                    file_size, file_md5, status, publish_time, create_time, update_time
                )
                SELECT
                    id, version_name, version_code, file_name, file_path,
                    file_size, file_md5, status, publish_time, create_time, update_time
                FROM t_mdm_app_version
                """
            )
        )
        conn.execute(text("DROP TABLE t_mdm_app_version"))
        conn.execute(text("ALTER TABLE t_mdm_app_version__new RENAME TO t_mdm_app_version"))


def _migrate_schema() -> dict[str, bool]:
    """兼容已有 SQLite：补充列 / 清理已下线表. 返回需后续回填的标志."""
    flags: dict[str, bool] = {}
    _migrate_mdm_drop_app_table()
    _rebuild_policy_dispatch_tables_if_obsolete()
    # 先子表后父表，便于带注释重建
    _rebuild_tables_without_ddl_comments(
        (
            "t_policy_device_task",
            "t_policy_task_item",
            "t_policy_task",
        )
    )
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "t_app_version_expression" in tables:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS t_app_version_expression"))
    # 设备策略快照：若仍含已下线列则重建（调试阶段不保留旧数据）
    _obsolete_snapshot_cols = {
        "protocol_key",
        "report_time",
        "update_by",
        "update_by_name",
        "update_scene",
        "task_code",
        "task_id",
    }
    for tname in ("t_device_policy_expected", "t_device_policy_current"):
        if tname not in tables:
            continue
        cols = {c["name"] for c in insp.get_columns(tname)}
        if cols & _obsolete_snapshot_cols:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {tname}"))
    if "t_app_base" in tables:
        app_cols = {c["name"] for c in insp.get_columns("t_app_base")}
        with engine.begin() as conn:
            if "app_id" not in app_cols:
                conn.execute(text("ALTER TABLE t_app_base ADD COLUMN app_id VARCHAR(128)"))
            if "bundle_name" not in app_cols:
                conn.execute(
                    text("ALTER TABLE t_app_base ADD COLUMN bundle_name VARCHAR(128)")
                )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_t_app_base_app_id "
                    "ON t_app_base (app_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_t_app_base_bundle_name "
                    "ON t_app_base (bundle_name)"
                )
            )
        # 存量数据：从旧版版本 package_name / app_code 回填（列删除前）
        ver_cols = (
            {c["name"] for c in insp.get_columns("t_app_version")}
            if "t_app_version" in tables
            else set()
        )
        with engine.begin() as conn:
            if "package_name" in ver_cols:
                order_by = (
                    "ORDER BY v.is_initial DESC, v.id DESC"
                    if "is_initial" in ver_cols
                    else "ORDER BY v.id DESC"
                )
                conn.execute(
                    text(
                        f"""
                        UPDATE t_app_base
                        SET bundle_name = (
                            SELECT v.package_name FROM t_app_version v
                            WHERE v.app_id = t_app_base.id
                              AND v.package_name IS NOT NULL
                              AND TRIM(v.package_name) != ''
                            {order_by}
                            LIMIT 1
                        )
                        WHERE bundle_name IS NULL OR TRIM(bundle_name) = ''
                        """
                    )
                )
            conn.execute(
                text(
                    """
                    UPDATE t_app_base
                    SET app_id = COALESCE(NULLIF(TRIM(bundle_name), ''), app_code)
                    WHERE app_id IS NULL OR TRIM(app_id) = ''
                    """
                )
            )
    # 应用版本不再维护 is_initial / package_name（包名统一在应用 Bundle Name）
    if "t_app_version" in tables:
        ver_cols = {c["name"] for c in insp.get_columns("t_app_version")}
        if {"is_initial", "package_name"} & ver_cols:
            with engine.begin() as conn:
                if "is_initial" in ver_cols:
                    conn.execute(text("ALTER TABLE t_app_version DROP COLUMN is_initial"))
                if "package_name" in ver_cols:
                    conn.execute(text("ALTER TABLE t_app_version DROP COLUMN package_name"))
    # 成员表：核心字段调整为 姓名/工号/账号/密码/分组（调试阶段无业务数据则重建）
    if "t_sys_member" in tables:
        member_cols = {c["name"] for c in insp.get_columns("t_sys_member")}
        if "password" not in member_cols or "phone" in member_cols or "email" in member_cols:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS t_sys_member"))
            tables.discard("t_sys_member")
    # 设备表：补充详情基本信息列（调试阶段缺关键列则重建）
    if "t_device" in tables:
        device_cols = {c["name"] for c in insp.get_columns("t_device")}
        need_cols = {"vendor", "agent_version", "imei", "member_id"}
        if not need_cols.issubset(device_cols):
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS t_device_app_installed"))
                conn.execute(text("DROP TABLE IF EXISTS t_device"))
            tables.discard("t_device")
            tables.discard("t_device_app_installed")
    # 策略项 / 任务：摘要列（列表直接返回，避免前端组装）
    if "t_initial_policy_item" in tables:
        ip_cols = {c["name"] for c in insp.get_columns("t_initial_policy_item")}
        if "summary" not in ip_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE t_initial_policy_item ADD COLUMN summary VARCHAR(512)")
                )
    if "t_policy_task_item" in tables:
        pti_cols = {c["name"] for c in insp.get_columns("t_policy_task_item")}
        if "summary" not in pti_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE t_policy_task_item ADD COLUMN summary VARCHAR(512)")
                )
    if "t_policy_task" in tables:
        pt_cols = {c["name"] for c in insp.get_columns("t_policy_task")}
        with engine.begin() as conn:
            if "policy_summary" not in pt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_policy_task ADD COLUMN policy_summary VARCHAR(1024)"
                    )
                )
            if "op_type" not in pt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_policy_task ADD COLUMN op_type "
                        "VARCHAR(32) NOT NULL DEFAULT 'dispatch'"
                    )
                )
            if "source_id" not in pt_cols:
                conn.execute(
                    text("ALTER TABLE t_policy_task ADD COLUMN source_id BIGINT")
                )
            if "ext_json" not in pt_cols:
                conn.execute(
                    text("ALTER TABLE t_policy_task ADD COLUMN ext_json TEXT")
                )
    if "t_policy_device_task" in tables:
        pdt_cols = {c["name"] for c in insp.get_columns("t_policy_device_task")}
        with engine.begin() as conn:
            if "employee_id" not in pdt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_policy_device_task ADD COLUMN employee_id VARCHAR(64)"
                    )
                )
            if "department_id" not in pdt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_policy_device_task ADD COLUMN department_id BIGINT"
                    )
                )
            if "department_path" not in pdt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_policy_device_task "
                        "ADD COLUMN department_path VARCHAR(512)"
                    )
                )
    # MQTT 管理端（Dashboard / REST API）配置列
    if "t_sys_mqtt_config" in tables:
        mqtt_cols = {c["name"] for c in insp.get_columns("t_sys_mqtt_config")}
        with engine.begin() as conn:
            if "api_port" not in mqtt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_sys_mqtt_config ADD COLUMN api_port INTEGER DEFAULT 18083"
                    )
                )
            if "api_username" not in mqtt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_sys_mqtt_config ADD COLUMN api_username VARCHAR(128)"
                    )
                )
            if "api_password" not in mqtt_cols:
                conn.execute(
                    text(
                        "ALTER TABLE t_sys_mqtt_config ADD COLUMN api_password VARCHAR(255)"
                    )
                )
    if "t_sys_role" in tables:
        role_cols = {c["name"] for c in insp.get_columns("t_sys_role")}
        if "is_system" not in role_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE t_sys_role ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0"
                    )
                )
    if "t_device" in tables:
        device_cols = {c["name"] for c in insp.get_columns("t_device")}
        if "pending_disk_erasure" not in device_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE t_device ADD COLUMN pending_disk_erasure "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
        if "is_compliant" not in device_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE t_device ADD COLUMN is_compliant "
                        "INTEGER NOT NULL DEFAULT 1"
                    )
                )
            flags["backfill_compliance"] = True
        if "policy_diff_count" not in device_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE t_device ADD COLUMN policy_diff_count "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
            # 新列时若合规字段已存在，仍需按快照回填差异数
            flags["backfill_compliance"] = True
        if "basic_info_synced" not in device_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE t_device ADD COLUMN basic_info_synced "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
                # 兼容旧库：原先靠关键列推断「已同步」的设备，回填为已同步，避免再次覆盖
                conn.execute(
                    text(
                        """
                        UPDATE t_device SET basic_info_synced = 1
                        WHERE COALESCE(TRIM(model), '') != ''
                           OR COALESCE(TRIM(os), '') != ''
                           OR COALESCE(TRIM(cpu), '') != ''
                           OR COALESCE(TRIM(hostname), '') != ''
                           OR COALESCE(TRIM(mac), '') != ''
                        """
                    )
                )
        if "expected_mdm_version_id" not in device_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE t_device ADD COLUMN expected_mdm_version_id BIGINT"
                    )
                )
    # RAG 文件：正式解析开始时间（超时兜底用；排队阶段为空）
    if "t_rag_file" in tables:
        rag_file_cols = {c["name"] for c in insp.get_columns("t_rag_file")}
        if "parse_start_time" not in rag_file_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE t_rag_file ADD COLUMN parse_start_time DATETIME"
                    )
                )

    if "t_user" not in tables:
        return flags
    cols = {c["name"] for c in insp.get_columns("t_user")}
    if "role_id" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE t_user ADD COLUMN role_id BIGINT"))
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_t_user_role_id ON t_user (role_id)")
            )
    return flags


def _legacy_password_param(param: dict) -> dict:
    """旧 PASSWORD_POLICY 字段 → PSW_MANAGEMENT."""
    if not isinstance(param, dict):
        return {}
    if "complexityRegex" in param or "validityPeriod" in param or "additionalDescription" in param:
        return param
    min_len = 8
    try:
        min_len = int(param.get("passwordMinLength") or 8)
    except (TypeError, ValueError):
        min_len = 8
    min_len = max(4, min(min_len, 32))
    return {
        "complexityRegex": f"^[A-Za-z0-9]{{{min_len},18}}$",
        "validityPeriod": 30,
        "additionalDescription": f"密码至少{min_len}位，建议含字母与数字",
    }


def _backfill_device_compliance(db: Session) -> None:
    """新增 is_compliant 列后，按现有快照全量重算一次."""
    from app.models.device import Device
    from app.services import device_snapshot_service

    sns = [r.sn for r in db.query(Device.sn).all() if r.sn]
    for sn in sns:
        device_snapshot_service.refresh_device_compliance(db, sn, commit=False)
    if sns:
        db.commit()
        logger.info("已回填设备合规字段：%s 台", len(sns))


def _backfill_policy_summaries(db: Session) -> None:
    """归一化历史 Code、回填摘要；任务聚合摘要一并补齐."""
    import json

    from app.utils.policy_summary import (
        aggregate_policy_summaries,
        build_policy_item_summary,
        make_app_name_resolver,
        normalize_param_for_expected,
    )

    resolve = make_app_name_resolver(db)
    changed = False

    def _param(raw: str | None) -> dict:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _normalize_item(row, *, dumps: bool = True) -> bool:
        nonlocal changed
        touched = False
        code = (row.policy_code or "").strip()
        param = _param(row.param_json)
        if code == "PASSWORD_POLICY":
            row.policy_code = "PSW_MANAGEMENT"
            param = _legacy_password_param(param)
            if dumps:
                row.param_json = json.dumps(param, ensure_ascii=False, separators=(",", ":"))
            touched = True
        summary = build_policy_item_summary(
            row.policy_code, param, resolve_app_name=resolve
        )
        if (row.summary or "").strip() != summary:
            row.summary = summary
            touched = True
        if touched:
            changed = True
        return touched

    for row in db.query(InitialPolicyItem).all():
        _normalize_item(row)

    for row in db.query(PolicyTaskItem).all():
        _normalize_item(row)

    # 设备快照中的旧 Code 一并归一，避免详情页同样错位
    for model in (DevicePolicyExpected, DevicePolicyCurrent):
        for row in db.query(model).filter(model.policy_code == "PASSWORD_POLICY").all():
            row.policy_code = "PSW_MANAGEMENT"
            param = _legacy_password_param(_param(row.param_json))
            row.param_json = json.dumps(param, ensure_ascii=False, separators=(",", ":"))
            changed = True

    # 预期快照：密码有效期天→毫秒；应用配置名单字符串→{appId,appName}
    resolve_apps = make_app_name_resolver(db)
    for row in db.query(DevicePolicyExpected).filter(
        DevicePolicyExpected.policy_code.in_(
            ("PSW_MANAGEMENT", "PASSWORD_POLICY", "APP_CONFIG_MANAGEMENT")
        )
    ).all():
        raw = _param(row.param_json)
        fixed = normalize_param_for_expected(
            row.policy_code, raw, resolve_app_name=resolve_apps
        )
        if fixed != raw:
            row.param_json = json.dumps(fixed, ensure_ascii=False, separators=(",", ":"))
            changed = True

    for task in db.query(PolicyTask).all():
        items = (
            db.query(PolicyTaskItem)
            .filter(PolicyTaskItem.task_id == task.id)
            .order_by(PolicyTaskItem.sort_order.asc(), PolicyTaskItem.id.asc())
            .all()
        )
        summaries = [(it.summary or "").strip() for it in items]
        agg = aggregate_policy_summaries(summaries)
        if (task.policy_summary or "").strip() != agg:
            task.policy_summary = agg
            changed = True

    if changed:
        db.commit()


def _seed_default_admin(db: Session) -> None:
    """内置 admin：全权限、不绑角色；仅首次创建写入密码哈希，之后不改密."""
    exists = (
        db.query(User)
        .filter(User.username == settings.default_admin_username, User.is_delete == 0)
        .first()
    )
    if exists:
        exists.name = settings.default_admin_name
        exists.status = 1
        exists.is_delete = 0
        exists.is_admin = 1
        exists.role_id = None  # 不受角色限制
        db.commit()
        return
    db.add(
        User(
            id=snowflake_id(),
            name=settings.default_admin_name,
            phone=None,
            email=None,
            username=settings.default_admin_username,
            password=_DEFAULT_ADMIN_PASSWORD_HASH,
            status=1,
            is_delete=0,
            is_admin=1,
            role_id=None,
        )
    )
    db.commit()
