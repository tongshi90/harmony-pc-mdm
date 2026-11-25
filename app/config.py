from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"


class Settings(BaseSettings):
    app_name: str = "企业终端管理云平台"
    debug: bool = True
    database_url: str = f"sqlite:///{(DATA_DIR / 'mdm.db').as_posix()}"
    secret_key: str = "harmony-pc-mdm-dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 12
    algorithm: str = "HS256"
    # 默认超级管理员用户名/显示名（首次初始化写入；密码不以明文进配置，见 bootstrap 种子哈希）
    default_admin_username: str = "admin"
    default_admin_name: str = "系统管理员"
    snowflake_worker_id: int = 1
    snowflake_datacenter_id: int = 1
    # 业务 MQTT Broker（可选种子）：库内 host 为空时，启动用下列环境变量写入
    # 环境变量：MDM_MQTT_HOST / MDM_MQTT_PORT / MDM_MQTT_USERNAME / MDM_MQTT_PASSWORD
    # Docker Compose 闭环示例：MDM_MQTT_HOST=emqx
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    # EMQX 管理端（Dashboard / 在线查询 REST API）——仅配置文件 / 启动环境变量，平台侧不可改
    # 环境变量：MDM_MQTT_API_HOST / MDM_MQTT_API_PORT / MDM_MQTT_API_USERNAME / MDM_MQTT_API_PASSWORD
    # mqtt_api_host 为空时回落业务 MQTT 的 host（t_sys_mqtt_config.host）
    mqtt_api_host: str = ""
    mqtt_api_port: int = 18083
    mqtt_api_username: str = "admin"
    mqtt_api_password: str = "Nv7Kq2Rm9Xp4Tw6B"
    # 设备在线状态全量同步周期（秒）；定时任务与策略下发共用 sync_device_online_status
    device_online_sync_interval_seconds: int = 30
    # 启动后延迟多久跑首轮同步（秒），避开与 MQTT 建连抢时机
    device_online_sync_startup_delay_seconds: int = 30
    # 设备拉取策略后，等待回执的超时（分钟）；超时仅影响展示，查询时落库为失败
    strategy_execute_timeout_minutes: int = 30
    # MDM Agent 包名（端侧 getInfo.bundleName；管理台只维护版本，包名走配置）
    # 环境变量：MDM_AGENT_BUNDLE_NAME
    agent_bundle_name: str = "com.huawei.mdm.demo"

    # ==================================================================
    # RAG 知识库（模块：app/rag/；引擎：仓库根 lightrag/）
    # 环境变量统一前缀 MDM_（字段名大写，例如 rag_chat_model → MDM_RAG_CHAT_MODEL）
    # 当前默认均指向硅基流动 SiliconFlow；改 URL/Key/模型名即可换兼容服务
    # 未配置 API Key 时：仍可建库/上传，向量化与提问会失败并提示配置
    # ==================================================================

    # ---- 在线模型（共用 Key + 各环节 URL/模型名）----
    # 共用 API Key：Embedding / Rerank / Chat 生成 / 问题改写拆分 / 图片 VL
    # 环境变量：MDM_RAG_SILICONFLOW_API_KEY
    rag_siliconflow_api_key: str = "sk-peeqhweinlldybquwghxeylhydqqscjrkzxrxnznboqfbgpm"

    # 【提问 · 生成答案】主 Chat
    # 环节：根据检索上下文生成最终回答（管理台 / 设备侧）
    # 环境变量：MDM_RAG_CHAT_URL / MDM_RAG_CHAT_MODEL
    # 引擎侧会把 chat URL 推导为 OpenAI 兼容 base（去掉 /chat/completions → …/v1）
    rag_chat_url: str = "https://api.siliconflow.cn/v1/chat/completions"
    rag_chat_model: str = "Qwen/Qwen2.5-72B-Instruct"
    rag_chat_timeout: int = 60
    rag_chat_max_tokens: int = 4096
    rag_chat_temperature: float = 0.5

    # 【入库 · 向量化】Embedding（编辑切片重向量化共用）
    # 环节：把文字段转为向量写入本地；检索时本地算相似度，不再调在线模型
    # 环境变量：MDM_RAG_EMBEDDING_URL / MDM_RAG_EMBEDDING_MODEL
    # 更换 embedding 模型或维度后，需清空 data/rag/lightrag 并重新入库
    rag_embedding_url: str = "https://api.siliconflow.cn/v1/embeddings"
    rag_embedding_model: str = "Qwen/Qwen3-Embedding-4B"
    rag_embedding_timeout: int = 90
    rag_embedding_batch_size: int = 10
    rag_embedding_dim: int = 2560
    rag_embedding_max_tokens: int = 8192

    # 【提问 · 重排序】Rerank
    # 环节：多库检索合并后，按与问题相关性重排，再取 TopK 送生成
    # 注意：此处为完整 rerank 接口 URL（不是 …/v1 base）
    # 环境变量：MDM_RAG_RERANK_URL / MDM_RAG_RERANK_MODEL
    rag_rerank_url: str = "https://api.siliconflow.cn/v1/rerank"
    rag_rerank_model: str = "Qwen/Qwen3-Reranker-0.6B"
    rag_rerank_timeout: int = 30

    # 【提问 · 问题改写 / 问题拆分】轻量 Chat
    # 环节：有对话历史时改写为可独立检索的问句；复合问题拆成子问题
    # URL 复用 rag_chat_url；仅模型名与超时/温度单独配置
    # 环境变量：MDM_RAG_TEXT_SPLITTER_MODEL
    rag_text_splitter_model: str = "Qwen/Qwen2.5-7B-Instruct"
    rag_text_splitter_timeout: int = 60
    rag_text_splitter_temperature: float = 0.3

    # 【入库 · 图片转写】多模态 VL
    # 环节：PDF / Word / PPT 插图 → 文字，供后续切分与向量化
    # URL 默认与主 Chat 相同（硅基流动 chat/completions）；模型为视觉模型
    # 环境变量：MDM_RAG_VL_URL / MDM_RAG_VL_MODEL
    # 未单独配置 VL URL 时回落 rag_chat_url
    rag_vl_url: str = ""
    rag_vl_model: str = "Qwen/Qwen3-VL-8B-Instruct"
    rag_vl_timeout: int = 90
    rag_vl_max_tokens: int = 1200

    # ---- RAG 业务参数（非模型厂商）----
    # 本地存储：默认 data/rag/；可改为绝对路径或相对 data/ 的子路径
    rag_data_dir: str = "rag"
    rag_upload_dir: str = ""  # 空则 data/rag/upload
    rag_lightrag_dir: str = ""  # 空则 data/rag/lightrag（按知识库 workspace 分目录）
    # 单文件上传上限（字节），默认 32MB
    rag_max_upload_bytes: int = 32 * 1024 * 1024
    # 入库切分器：split_v2（Plan A/B + 尺寸治理）| rag_project（旧 TitleDetector）
    # 环境变量：MDM_RAG_SPLITTER；切换后已入库文件需重切
    rag_splitter: str = "split_v2"
    # 单文件入库超时（秒）：从 worker 正式开始解析起算，排队等待不计；默认 2 小时
    rag_ingest_timeout_seconds: int = 7200
    # 入库超时巡检间隔（秒）
    rag_ingest_timeout_check_interval_seconds: int = 300
    # 生成上下文预算（粗估 token≈字数/2）：单块上限 / 全部参考合计上限
    # 父章过大时按命中片居中截窗，不再整本塞进 LLM
    rag_gen_chunk_max_tokens: int = 2500
    rag_gen_total_max_tokens: int = 8000

    class Config:
        env_prefix = "MDM_"


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
