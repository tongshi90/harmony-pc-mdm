#!/usr/bin/env bash
# Harmony PC MDM · Linux 服务器 Docker 启动脚本
# 数据目录挂载：宿主机 /home/p40/ts/harmony-pc-mdm → 容器 /app/data
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-harmony-pc-mdm:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-harmony-pc-mdm}"
HOST_PORT="${HOST_PORT:-8080}"
# 宿主机持久化目录（SQLite、RSA、上传包等）
DATA_DIR="${DATA_DIR:-/home/p40/ts/harmony-pc-mdm}"

mkdir -p "${DATA_DIR}/uploads"

# 已存在同名容器则先移除（可改为 docker start 复用）
if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "移除已有容器: ${CONTAINER_NAME}"
  docker rm -f "${CONTAINER_NAME}" >/dev/null
fi

echo "启动 ${CONTAINER_NAME}"
echo "  镜像: ${IMAGE_NAME}"
echo "  端口: ${HOST_PORT} -> 8080"
echo "  数据: ${DATA_DIR} -> /app/data"

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "${HOST_PORT}:8080" \
  -v "${DATA_DIR}:/app/data" \
  "${IMAGE_NAME}"

echo "已启动。访问 http://<服务器IP>:${HOST_PORT}"
echo "默认账号 admin / 12345678（首次无库时由 init_db 自动创建）"
echo "日志: docker logs -f ${CONTAINER_NAME}"
