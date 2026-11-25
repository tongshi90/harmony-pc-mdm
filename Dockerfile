# Harmony PC MDM 云侧 · 生产镜像
# Python 3.10+ · FastAPI · SQLite · 内嵌 lightrag/
#
# 构建：
#   docker build -t harmony-pc-mdm:latest .
# 推荐完整闭环（本服务 + EMQX）：
#   docker compose up -d --build
#
# 单容器也可启动；无 Broker 时 MQTT 相关能力不可用，需自行配置
# MDM_MQTT_HOST / MDM_MQTT_API_*，以及知识库用的 MDM_RAG_SILICONFLOW_API_KEY。

FROM python:3.10-slim

WORKDIR /app

# 编译 cryptography 等；运行时保留常用字体/本地化无关的最小集
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 业务 + 前端 + 内嵌 RAG 引擎（缺 lightrag/ 则知识库无法工作）
COPY app ./app
COPY web ./web
COPY lightrag ./lightrag

# 运行时数据目录（建议用 volume 挂载 /app/data）
RUN mkdir -p \
    /app/data/uploads \
    /app/data/rag/upload \
    /app/data/rag/lightrag/inputs

# 保证从仓库根导入本仓 lightrag 包
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MDM_DEBUG=false \
    MDM_DATABASE_URL=sqlite:////app/data/mdm.db

EXPOSE 8080

# 启动时 bootstrap.init_db()：建表 + 默认 admin；MQTT 可从 MDM_MQTT_* 种子写入空库
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
