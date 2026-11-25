#!/usr/bin/env bash
# Harmony PC MDM · Linux 服务器 Docker 启动（推荐走 compose 闭环）
# 用法：
#   ./docker-start.sh              # docker compose up -d --build
#   ./docker-start.sh single       # 仅跑 MDM 单容器（需已有镜像；MQTT 需自备 Broker）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

MODE="${1:-compose}"
IMAGE_NAME="${IMAGE_NAME:-harmony-pc-mdm:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-harmony-pc-mdm}"
HOST_PORT="${HOST_PORT:-8080}"
DATA_DIR="${DATA_DIR:-${ROOT}/data-docker}"

if [[ "${MODE}" == "compose" ]]; then
  echo "启动完整闭环（MDM + EMQX）..."
  docker compose up -d --build
  echo "已启动。"
  echo "  管理台: http://<服务器IP>:8080  （admin / Ab12345678，仅首次空库）"
  echo "  EMQX:   http://<服务器IP>:18083 （admin / Nv7Kq2Rm9Xp4Tw6B）"
  echo "日志: docker compose logs -f mdm"
  exit 0
fi

mkdir -p "${DATA_DIR}/uploads" "${DATA_DIR}/rag/upload" "${DATA_DIR}/rag/lightrag/inputs"

if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "移除已有容器: ${CONTAINER_NAME}"
  docker rm -f "${CONTAINER_NAME}" >/dev/null
fi

echo "启动单容器 ${CONTAINER_NAME}"
echo "  镜像: ${IMAGE_NAME}"
echo "  端口: ${HOST_PORT} -> 8080"
echo "  数据: ${DATA_DIR} -> /app/data"
echo "  提示: 单容器不含 EMQX；请设置 MDM_MQTT_HOST / MDM_MQTT_API_* 指向可用 Broker"

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "${HOST_PORT}:8080" \
  -v "${DATA_DIR}:/app/data" \
  -e MDM_DATABASE_URL=sqlite:////app/data/mdm.db \
  -e "MDM_MQTT_HOST=${MDM_MQTT_HOST:-}" \
  -e "MDM_MQTT_PORT=${MDM_MQTT_PORT:-1883}" \
  -e "MDM_MQTT_API_HOST=${MDM_MQTT_API_HOST:-}" \
  -e "MDM_MQTT_API_PORT=${MDM_MQTT_API_PORT:-18083}" \
  -e "MDM_MQTT_API_USERNAME=${MDM_MQTT_API_USERNAME:-admin}" \
  -e "MDM_MQTT_API_PASSWORD=${MDM_MQTT_API_PASSWORD:-Nv7Kq2Rm9Xp4Tw6B}" \
  -e "MDM_RAG_SILICONFLOW_API_KEY=${MDM_RAG_SILICONFLOW_API_KEY:-}" \
  "${IMAGE_NAME}"

echo "已启动。访问 http://<服务器IP>:${HOST_PORT}"
echo "默认账号 admin / Ab12345678（首次无库时由 init_db 自动创建）"
echo "日志: docker logs -f ${CONTAINER_NAME}"
