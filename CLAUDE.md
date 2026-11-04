# Harmony PC MDM 云侧项目

企业 PC 终端管控云平台：管理台配置与策略下发，设备侧 Agent 通过 HTTP + MQTT 与云侧交互。

**仓库根目录即本目录。** 本地访问：**http://localhost:8080** · Swagger：**http://localhost:8080/docs**

当前阶段：登录鉴权、平台基础管理（含 MDM 版本）、应用仓库、成员/分组/初始策略、设备管理、策略下发、设备侧协议接口均已接通真实 API；数据看板等少数入口仍为占位。临时方案与待办见根目录 `待办.txt`。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+ · FastAPI · SQLAlchemy · SQLite |
| 前端 | 静态 HTML / CSS / JS（无构建，由 FastAPI 托管） |
| 管理台鉴权 | JWT + `t_user_tokens`；管理员密码传输 RSA-OAEP，存储 bcrypt |
| 设备侧接口 | `/api/*` 白名单，默认不鉴权、不记操作日志（内网部署约定） |
| 主键 | 雪花算法 |
| 消息 | MQTT（策略拉取、快照催报、解绑、远程控制等） |

字段与端云协议可参考根目录《云侧开发文档-待完善.docx》《端云协议.docx》；**以代码与本文件为准**。

---

## 本地启动

### 环境要求

- Windows（PowerShell）
- Python 3.10+

### 方式一：一键脚本（推荐）

```powershell
cd F:\harmony-pc-mdm
.\start.ps1
```

`start.ps1` 会先清理占用 8080 的旧进程，再用 uvicorn `--reload` 启动（监视 `app/`）。

| 改什么 | 如何生效 |
|--------|----------|
| `app/` 后端 Python | 保存后自动重载 |
| `web/` 前端静态文件 | 浏览器 **Ctrl+F5** 强制刷新 |
| `requirements.txt` | 重新 `pip install -r requirements.txt` 后重启 |

建议只开一个 `.\start.ps1` 终端。若怀疑僵尸进程：该终端 `Ctrl+C` 后再执行一次 `.\start.ps1`。

### 方式二：手动命令

```powershell
cd F:\harmony-pc-mdm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
# 或
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload --reload-dir app
```

### 默认管理员

| 账号 | 密码 |
|------|------|
| `admin` | `12345678` |

首次启动会自动：创建 `data/mdm.db`、生成 RSA 密钥对（`data/rsa_*.pem`）、写入默认管理员与预置角色。MDM Agent 包名由配置 `MDM_AGENT_BUNDLE_NAME`（默认 `com.huawei.mdm.demo`）提供，管理台只维护版本仓库。

### 重置本地数据

```powershell
# 先停止服务
Remove-Item F:\harmony-pc-mdm\data\mdm.db -ErrorAction SilentlyContinue
python run.py
```

演示/清空数据也可用根目录 `db_init.py`（`--demo` 灌入演示数据）。

### 停止服务

运行 `run.py` / `start.ps1` 的终端按 `Ctrl+C`。

---

## 项目结构

```
harmony-pc-mdm/
├── app/                      # FastAPI 后端
│   ├── api/                  # 路由（管理台 /platform + 设备侧 /api）
│   ├── models/               # ORM
│   ├── schemas/              # 请求响应模型
│   ├── services/             # 业务逻辑
│   ├── mqtt/                 # MQTT 发布
│   ├── middleware/           # 鉴权、操作日志
│   ├── enums/                # 菜单等枚举
│   ├── utils/                # 雪花、JWT、RSA、密码哈希、时间
│   ├── bootstrap.py          # 建表与种子
│   ├── config.py             # MDM_ 环境变量
│   ├── database.py
│   ├── deps.py
│   └── main.py               # 入口：挂载 API + 静态前端
├── web/                      # 前端（自 Demo 迁移，逐步接真 API）
│   ├── login.html
│   ├── index.html            # 数据看板（占位）
│   ├── pages/
│   └── assets/js/            # api.js · layout.js · utils.js · pages/
├── data/                     # SQLite、RSA、上传包（勿提交密钥/库）
├── docs/                     # 测试业务规则等
├── db_init.py                # 清库 / Demo 种子
├── requirements.txt
├── run.py
├── start.ps1
├── 待办.txt
└── CLAUDE.md                 # 本文件
```

---

## 页面入口（管理台）

| 路径 | 模块 | 数据来源 |
|------|------|----------|
| `/login.html` | 登录 | 真实 API |
| `/index.html` | 数据看板 | 占位 |
| `/pages/platform/users.html` | 平台基础管理（管理员 / 角色 / **MDM 版本** / MQTT·日志配置 / 操作日志） | 真实 API |
| `/pages/platform/user-form.html` | 新建/编辑管理员 | 真实 API |
| `/pages/apps/apps.html` 等 | 应用仓库、版本、批量安装/卸载 | 真实 API |
| `/pages/members/groups.html` | 成员分组 | 真实 API |
| `/pages/members/members.html` | 人员管理（含导入） | 真实 API |
| `/pages/members/initial-policy*.html` | 初始策略模板 | 真实 API |
| `/pages/devices/devices.html` | 设备列表（预登记、合规筛选、重试策略拉取） | 真实 API |
| `/pages/devices/device-detail.html` | 设备详情（基本信息/快照/已装应用/轨迹；催设备上报、解绑、远程控制） | 真实 API |
| `/pages/scenes/scene-dispatch*.html` | 策略下发（列表/创建/详情） | 真实 API |

旧 Demo 路径（`/pages/dispatch/*`、`commands`、`scenes/scenes.html`、`settings`、`device-form` 等）仅为轻量重定向到上述真实页，不再加载 Demo 脚本。未登录访问业务页会跳转 `/login.html`。

---

## 接口前缀与鉴权约定

| 前缀 | 用途 | 鉴权 | 操作日志 |
|------|------|------|----------|
| `/platform/*` | 云侧管理台 | 默认需登录 + 菜单前缀权限 | 写操作默认记；GET 默认不记 |
| `/api/*` | 设备侧协议 | **不鉴权** | **不记** |
| `/openapi/*` | 企业对接（如业务卡片上报） | **不鉴权**（白名单；后续可加签） | **不记** |

### `/platform` 免登录白名单

- `POST /platform/auth/login`
- `GET /platform/auth/public-key`
- `GET /platform/health`
- `GET /platform/app/{id}/versions/{vid}/package`（应用包直链）
- `GET /platform/app/{id}/icon`（图标直链）
- `GET /platform/mdm-app/versions/{vid}/package`（MDM 包直链）

需登录但不校验菜单：`/platform/auth/*`（如 `/me`、改密、退出）。

### 操作日志约定

- **默认记录**：`POST/PUT/PATCH/DELETE`（成功/失败均记）
- **查询不记**：普通 GET；需记时加 `@audit_log`（如导出 CSV、导入模板下载）
- **永不记录**：`/api/*`、`/openapi/*`、health、public-key、`/me`、`@no_audit`
- 密码等敏感字段入库前脱敏为 `******`
- 内置 `admin`（`is_admin=1`）可查全部日志；其他人仅本人

统一响应：

```json
{ "code": 0, "message": "", "data": {} }
```

`code=0` 成功（`message` 为空）；失败时 `message` 为原因。

---

## 固定菜单与权限

定义在 `app/enums/menu.py`：

| 菜单（侧栏/登录默认顺序） | Code | 接口前缀 |
|------|------|----------|
| 数据看板 | `dashboard` | `/platform/dashboard` |
| 设备管理 | `device` | `/platform/device` |
| 人员管理 | `member` | `/platform/member` |
| 成员分组 | `member_group` | `/platform/member-group` |
| 应用管理 | `app` | `/platform/app` |
| 策略下发 | `policy_dispatch` | `/platform/policy` |
| 平台基础管理 | `platform` | `/platform/platform` |

说明：策略能力内置在 `policy-commands.js`，通过「策略下发 / 初始策略」配置，不另设「策略管理」菜单。MDM Agent 版本管理挂在「平台基础管理」Tab，不进应用仓库。

权限机制：

1. 角色绑定 `menu_codes`（`t_sys_role_menu`）
2. 普通用户绑 `role_id`；内置 `admin` 超级管理员全权限、不绑角色、不出现在管理员列表
3. `GET /platform/auth/me` 返回 `menu_codes` / `menus`，前端渲染侧栏
4. `AuthGuardMiddleware` 校验登录；菜单路径按最长前缀鉴权；失败统一 **HTTP 401**

---

## 已实现 API（摘要）

### 授权 `/platform/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/public-key` | RSA 公钥（免登录） |
| POST | `/login` | 登录 |
| POST | `/logout` | 退出 |
| GET | `/me` | 当前用户与菜单 |
| PUT | `/password` | 修改密码（RSA 传密） |

### 平台基础管理 `/platform/platform`

管理员、角色、菜单枚举、MQTT、日志保留配置、操作日志；以及 **MDM 版本**（无应用信息表，Bundle Name 见 `MDM_AGENT_BUNDLE_NAME`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/mdm-app/versions` | 版本列表 / 新建草稿 |
| GET/PUT/DELETE | `/mdm-app/versions/{id}` | 版本详情 / 编辑发布 / 删除 |
| POST | `/mdm-app/versions/{id}/package` | 上传 HAP |

公开下载：`GET /platform/mdm-app/versions/{id}/package`

### 应用管理 `/platform/app`

应用 CRUD、图标、版本、HAP 上传、安装覆盖统计、按分组批量安装/卸载（写 `APP_MANAGEMENT` 预期并发 `STRATEGY_PULL`）。

### 成员分组 / 初始策略 `/platform/member-group`

分组树 CRUD；初始策略模板 CRUD（分组绑定模板；无全局默认时未绑分组可不套用）。

### 人员 `/platform/member`

成员 CRUD、分组树只读、Excel 导入模板与导入。成员密码：**管理台录入时 RSA 传输 + bcrypt 存储**；**设备绑定接口明文传密码**（临时方案，见 `待办.txt`【3】）。

### 设备 `/platform/device`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/` · `/batch` | 列表 / 预登记 SN / 批量登记 |
| GET/DELETE | `/{sn}` | 详情 / 删除未绑定设备 |
| GET | `/{sn}/snapshot` · `/apps` · `/locations` | 快照对比、已装应用、轨迹 |
| POST | `/{sn}/strategy-pull` | 不合规设备补发 `STRATEGY_PULL` |
| POST | `/{sn}/snapshot-report` | 催设备上报（MQTT `SNAPSHOT_REPORT`） |
| POST | `/{sn}/unbind` | **管理员解绑**（需登录；设备侧不再提供解绑） |
| POST | `/{sn}/control` | 远程控制 reboot / shutDown / lockScreen / DISK_ERASURE |

### 策略下发 `/platform/policy`

选人、任务创建与列表/详情、设备明细、`device-sync` 对齐查询。

### 企业对接 `/openapi/*`（免鉴权，暂无签名）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/openapi/approval/report` | 企业上报审批整单状态；拆主表 `t_biz_card` + 步骤副表 `t_biz_card_step` 按 bizId 覆盖 |

校验失败业务码 `40001`（HTTP 200）；服务异常 `50001`（HTTP 500）。不做人员存在性校验；云→企业补偿查询与 PC 触达另立事项。

### 设备侧业务卡片 `/api/biz-card/*`（免鉴权）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/biz-card/todos?sn=` | 待我审核（节点 PENDING） |
| GET | `/api/biz-card/mine?sn=` | 我的提交（审批中 + 近 7 天终态） |
| GET | `/api/biz-card/detail?sn=&bizId=` | 单条详情（完整步骤） |

落库后 MQTT 催拉（见 `待办.txt`【7】）：`BIZ_CARD_PULL` + `bizType=mySubmission|pendingReview`；未绑定跳过该路。

### 设备侧 `/api/*`（免鉴权）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/strategy/get` | 拉预期策略快照 |
| POST | `/api/report/snapshot` | 上报基本信息 + 已装应用 + 当前策略快照 |
| POST | `/api/report/location` | 位置上报 |
| GET | `/api/app/list` | 应用市场列表 |
| GET | `/api/mdm/getInfo` | MDM 最新已发布版本（含下载 URL、`bundleSize` 单位 KB） |
| POST | `/api/device/bind` | 成员绑定（密码**明文**，临时） |

完整列表以 Swagger 为准。

---

## MQTT 通知类型（云 → 端）

| type | 说明 |
|------|------|
| `STRATEGY_PULL` | 催设备拉预期策略 |
| `SNAPSHOT_REPORT` | 催设备完整上报（基本信息 / 已装应用 / 策略快照） |
| `DEVICE_UNBINDING` | 解绑通知（管理台解绑后下发） |
| `DEVICE_CONTROL` | 远程控制（`controlType`: reboot / shutDown / lockScreen / DISK_ERASURE） |
| `BIZ_CARD_PULL` | 业务卡片催拉（`bizType`: `mySubmission` / `pendingReview`） |

Topic 按设备 SN 路由（见 `app/mqtt`）。Broker 配置在平台基础管理 · 系统配置；EMQX 管理端账号仅环境变量 / 配置文件（`MDM_MQTT_API_*`）。

---

## 主要数据表

| 表名 | 说明 |
|------|------|
| `t_user` / `t_user_tokens` | 管理员与会话 |
| `t_sys_role` / `t_sys_role_menu` | 角色与菜单 |
| `t_sys_mqtt_config` / `t_sys_log_config` | MQTT、操作日志保留天数 |
| `t_sys_op_log` | 操作审计 |
| `t_app_base` / `t_app_version` | 应用仓库与版本包 |
| `t_mdm_app_version` | MDM Agent 版本仓库（与应用仓库分离；包名走配置） |
| `t_sys_department` / `t_sys_member` | 成员分组与人员 |
| `t_initial_policy` / `t_initial_policy_item` | 初始策略模板 |
| `t_device` / `t_device_app_installed` | 设备与已装应用 |
| `t_device_location_log` | 位置轨迹 |
| `t_device_policy_expected` / `t_device_policy_current` | 预期 / 当前策略快照 |
| `t_policy_task` / `t_policy_task_item` / `t_policy_device_task` | 策略下发任务 |

设备合规：`t_device.is_compliant`、`policy_diff_count`（预期 vs 当前快照，含 `APP_MANAGEMENT` 与已装应用比对）。

---

## 前端约定

| 文件 | 说明 |
|------|------|
| `web/assets/js/api.js` | Token、RSA（管理台密码）、`MDMApi` |
| `web/assets/js/layout.js` | 布局、登录校验、侧栏 |
| `web/assets/js/utils.js` | 工具与 `routes`；跳转用 `MDMUtils.href(routeKey, query)` |
| `web/assets/js/pages/*.js` | 各页逻辑 |

新增 HTML 页需在 `utils.js` 之后、`layout.js` 之前引入 `api.js`。改前端后强制刷新即可。

---

## 后端约定

- 新管理台接口：`app/api/` 增加路由，在 `app/api/__init__.py` 注册到 `/platform`
- 新设备侧接口：独立 router，在 `main.py` 挂到 `/api`
- 新表：`app/models/` 定义，启动时 `bootstrap.init_db()` → `create_all`
- 配置前缀：`MDM_`（见 `app/config.py`）
- 管理台密码类字段：前端 RSA 加密再提交；绑定接口除外（明文临时方案）
- 删除管理员：逻辑删除（`is_delete=1`）；系统管理员不可删

---

## 常用调试

```powershell
curl http://localhost:8080/platform/health
curl http://localhost:8080/api/mdm/getInfo
start http://localhost:8080/docs
```

开发推荐 `.\start.ps1`。改 `app/` 自动重载；改 `web/` 浏览器强制刷新。
