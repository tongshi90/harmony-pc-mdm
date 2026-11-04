# Harmony PC MDM 云侧 · 生产镜像
# Python 3.10+ · FastAPI · SQLite（数据目录建议挂载 volume）

FROM python:3.10-slim

WORKDIR /app

# 系统依赖（cryptography / bcrypt 等可能需要）
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

# 应用代码（不含本地 data 库文件，由 volume / 启动时 bootstrap 创建）
COPY app ./app
COPY web ./web

RUN mkdir -p /app/data/uploads

ENV PYTHONUNBUFFERED=1 \
    MDM_DEBUG=false \
    MDM_DATABASE_URL=sqlite:////app/data/mdm.db

EXPOSE 8080

# 启动时 app.bootstrap.init_db() 会：建表 + 写入默认 admin（无 Demo 调试数据）
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
