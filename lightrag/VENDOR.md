# Vendored LightRAG（本仓内嵌 · 已按 MDM 路径精简）

本目录为定制版 LightRAG 的 Python 包源码（含 `parser/external/rag_project` 入库切分），
从本地工程迁入 **harmony-pc-mdm**，供私有环境部署时 **无需再依赖外部 LightRAG 仓库或 editable 安装**。

- 上游项目：https://github.com/HKUDS/LightRAG（MIT，见同目录 `LICENSE`）
- 本仓用法：进程内由 `app/rag/lightrag_engine.py` 调用；启动时优先从仓库根目录加载本包
- 安装：只需 `pip install -r requirements.txt`，**不要**再执行 `pip install -e ...LightRAG...`
- 请勿单独 `pip install lightrag-hku`，以免与本目录包冲突

## 精简说明（相对上游完整包）

已移除与当前 MDM 运行时无关的部分，例如：

- `api/webui`、`api/static` 及除 `api/__init__.py` 外的 API Server
- `evaluation/`、`tools/`
- 未使用的 LLM provider、未使用的存储后端（仅保留 JsonKV / NanoVectorDB / NetworkX / JsonDocStatus）
- Native / MinerU / Docling 解析栈，以及 V/P chunker 实现
- 未使用的 LLM / 存储后端

**保留**：`rag_project` 入库、`llm/openai`、naive 检索相关核心、默认四存储、`recursive_character`（LightRAG 初始化依赖）、`api/__init__.py`（供 openai User-Agent 读取版本号）。
