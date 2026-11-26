# 应用商店调试 · 签名工具目录

本目录对应 hm-appstore 的 `cert-dir-private`（`/data/sign/`）。

当前范围：**证书管理**（CSR 签发 / 上传 cer）、**Profile**、以及 **模式 2 hapResign**（解包 + 平台密钥重签）。

## 已内置（OpenHarmony 公开调试版）

来源：[openharmony/developtools_hapsigner](https://github.com/openharmony/developtools_hapsigner) 仓库 `dist/`。

| 文件 | 用途 |
|------|------|
| `hap-sign-tool.jar` | 官方签名工具（生成 Profile p7b） |
| `OpenHarmony.p12` | 密钥库（CSR 签发、Profile 签名；口令 `123456`） |
| `OpenHarmonyProfileRelease.pem` | Profile 签名证书链 |
| `openvalley.pem` | 模式 2 用**应用证书**（公钥）；配对私钥在 `OpenHarmony.p12` 别名 `openvalley`，口令 `123456`（本机随机生成的调试自签证，非企业正式链） |

以上为**社区/本地调试材料**，与线上企业机不一定一致。

## 可选

| 文件 | 用途 |
|------|------|
| `root.cer` | CSR 签发后追加的 Root CA；缺省用内置默认 |

本机还需可用的 `java` / `keytool`（可用 `MDM_STORE_JAVA_BIN`、`MDM_STORE_KEYTOOL_BIN` 指定路径）。

管理台「应用商店调试」页顶部会显示工具是否就绪。
