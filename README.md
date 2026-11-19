# Harmony PC MDM（云侧）

企业 PC 终端管控云平台：管理台配置与策略下发，设备侧 Agent 通过 HTTP + MQTT 与云侧交互。

本地访问：**http://localhost:8080** · Swagger：**http://localhost:8080/docs**

当前已接通真实 API 的能力包括：登录鉴权、平台基础管理（含 MDM 版本）、应用仓库、成员/分组/初始策略、设备管理、策略下发、业务卡片对接、知识库问答（管理台 + 设备侧）、设备侧协议接口。临时方案与待办见 `待办.txt`；更完整的模块说明见 `CLAUDE.md`。

## 技术栈

- 后端：Python 3.10+ · FastAPI · SQLAlchemy · SQLite
- 前端：静态 HTML/CSS/JS（由 FastAPI 托管，无构建）
- 鉴权：JWT + `t_user_tokens` · 管理台密码 RSA-OAEP 传输 · bcrypt 存储
- 设备侧：`/api/*` 白名单，默认不鉴权（内网约定）
- 消息：MQTT · 主键：雪花算法
- 知识库：本仓内嵌 LightRAG（`lightrag/`）· SiliconFlow OpenAI 兼容接口

## 快速启动

```powershell
cd F:\harmony-pc-mdm
.\start.ps1
```

或手动：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

只需本仓 + `requirements.txt` 即可运行；**不要**再对外部 LightRAG 工程做 `pip install -e`，也勿单独安装 `lightrag-hku`（会与本仓 `lightrag/` 冲突）。

| 改什么 | 如何生效 |
|--------|----------|
| `app/` | uvicorn `--reload` 自动重载 |
| `web/` | 浏览器 Ctrl+F5 |
| `requirements.txt` | 重新 pip install 后重启 |

### 默认管理员（首次启动种子）

| 账号 | 密码 |
|------|------|
| `admin` | `Ab12345678` |

正式环境请尽快改密；登录页不再展示默认凭据。新建/改密/重置管理员密码须 **6–18 位且同时含字母与数字**。知识库提问需配置 `MDM_RAG_SILICONFLOW_API_KEY`。

可选联调灌数 / 一键恢复（非启动必需）：

```powershell
.\.venv\Scripts\python.exe db_init.py --demo
# 清库 + 删上传包/知识库文件（保留 admin、系统角色、RSA）：
.\.venv\Scripts\python.exe project_init.py -y
```

### 本地 MQTT（EMQX，闭环联调）

策略催拉、设备在线状态等依赖 MQTT。可用 Docker 起一套与本仓默认管理端账号对齐的 EMQX：

```powershell
docker run -d --name emqx --restart unless-stopped `
  -p 1883:1883 `
  -p 18083:18083 `
  -e EMQX_DASHBOARD__DEFAULT_USERNAME=admin `
  -e EMQX_DASHBOARD__DEFAULT_PASSWORD=Nv7Kq2Rm9Xp4Tw6B `
  emqx/emqx:5.8.3
```

- Dashboard：`http://localhost:18083`（账号 `admin`，密码与上、`config.py` 中 `mqtt_api_password` 一致）
- 管理台「平台基础管理 · MQTT」填写 Host（本机 `127.0.0.1`）、端口 `1883` 并保存连通
- 管理 API 默认读 `MDM_MQTT_API_*`（端口 `18083`）；若改了 Dashboard 密码，同步改环境变量或 `config.py`

## 目录结构

```
harmony-pc-mdm/
├── app/              # FastAPI 后端（api / rag / models / services …）
├── lightrag/         # 内嵌精简 LightRAG（见 lightrag/VENDOR.md）
├── web/              # 管理台静态前端
├── data/             # SQLite、RSA、RAG 数据（运行时生成，勿提交密钥/库）
├── requirements.txt
├── run.py / start.ps1
├── db_init.py        # 清库；加 --demo 灌入联调样例
├── project_init.py   # 一键恢复「刚部署」状态（库+上传+知识库文件）
├── 待办.txt
└── CLAUDE.md         # 给开发/Agent 的完整约定
```

## 接口前缀

| 前缀 | 用途 | 鉴权 |
|------|------|------|
| `/platform/*` | 管理台 | 默认需登录 + 菜单权限 |
| `/api/*` | 设备侧 | 不鉴权 |
| `/openapi/*` | 企业对接 | 不鉴权（暂无签名） |

统一响应：`{ "code": 0, "message": "", "data": {} }`。授权失败 HTTP **401** → 前端跳转登录。

菜单与权限见 `app/enums/menu.py`。接口明细以 Swagger 与 `CLAUDE.md` 为准。

## 使用说明

1. 未登录或 401 会跳转 `/login.html`
2. 侧栏菜单按登录用户 `menu_codes` 动态显示
3. 右上角：修改密码 / 退出登录
