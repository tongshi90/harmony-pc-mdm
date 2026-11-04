# Harmony PC MDM（云侧）

基于 Demo 原型迁移的企业 PC 终端管控云平台。当前阶段：

- 前端页面整体迁入，作为操作界面
- FastAPI + SQLite 实现登录 / 退出 / 修改密码 / 管理员管理
- 其余业务页暂保持静态 Demo 数据

## 技术栈

- 后端：Python 3.10+ · FastAPI · SQLAlchemy · SQLite
- 前端：静态 HTML/CSS/JS（由 FastAPI 托管）
- 鉴权：JWT + `t_user_tokens` · 密码传输 RSA-OAEP · 密码存储 bcrypt
- 主键：雪花算法

## 快速启动

```powershell
cd F:\harmony-pc-mdm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

浏览器访问：http://localhost:8080

默认超级管理员（天然全权限、不绑角色、不出现在管理员列表）：

| 账号 | 密码 |
|------|------|
| `admin` | `12345678` |

## 目录结构

```
harmony-pc-mdm/
├── app/                 # FastAPI 后端
│   ├── api/             # 接口路由
│   ├── models/          # 数据表（对齐云侧文档）
│   ├── schemas/         # 请求/响应模型
│   ├── services/        # 业务逻辑
│   ├── utils/           # 雪花ID / 加解密 / JWT
│   ├── bootstrap.py     # 建表与种子数据
│   └── main.py
├── web/                 # 前端页面（自 Demo 迁移）
├── data/                # SQLite 与 RSA 密钥（运行时生成）
├── requirements.txt
└── run.py
```

## 接口前缀

- 云侧管理台：`/platform/*`（需登录）
- 对外设备侧白名单：`/api/*`（交互文档约定，默认不鉴权）

## 已实现接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/platform/auth/public-key` | 获取 RSA 公钥 |
| POST | `/platform/auth/login` | 登录 |
| POST | `/platform/auth/logout` | 退出 |
| GET | `/platform/auth/me` | 当前用户（含角色与菜单权限） |
| PUT | `/platform/auth/password` | 修改密码（旧密码校验） |
| GET | `/platform/platform/menus` | 固定菜单枚举 |
| GET/POST | `/platform/platform/admins` | 管理员列表 / 新建 |
| GET/PUT/DELETE | `/platform/platform/admins/{id}` | 详情 / 编辑 / 逻辑删除 |
| PUT | `/platform/platform/admins/{id}/status` | 启用/禁用 |
| POST | `/platform/platform/admins/{id}/reset-password` | 重置密码 |
| GET/POST | `/platform/platform/roles` | 角色列表 / 新建 |
| GET/PUT/DELETE | `/platform/platform/roles/{id}` | 详情 / 编辑（含菜单权限） / 删除 |
| PUT | `/platform/platform/roles/{id}/status` | 启用/禁用 |

统一响应：`{ "code": 0, "message": "", "data": {} }`。授权失败 HTTP **401** → 前端跳转登录。

## 数据表（本阶段）

对齐《云侧开发文档-待完善.docx》：

- `t_user`：管理员账号（含 `role_id`）
- `t_user_tokens`：登录会话
- `t_sys_role` / `t_sys_role_menu`：角色与菜单权限

固定菜单枚举见 `app/enums/menu.py`（看板 / 平台 / 产品 / 应用 / 成员分组 / 人员 / 设备 / 策略下发）。

## 使用说明

1. 未登录或 401 会跳转 `/login.html`
2. 右上角人名下拉：修改密码 / 退出登录
3. 侧栏菜单按登录用户权限动态显示
4. 「平台基础管理」中管理员、角色权限已对接真实接口；操作日志仍为静态 Demo
