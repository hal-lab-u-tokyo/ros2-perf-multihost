#!/bin/bash
set -e

# ホスト名リスト（Dockerfilesディレクトリと一致させる）
HOSTS=("pi0" "pi1" "pi2")  # 必要に応じて編集

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILES_DIR="${REPO_DIR}/Dockerfiles"

for HOST in "${HOSTS[@]}"; do
  HOST_DOCKERFILES_DIR="${DOCKERFILES_DIR}/${HOST}"
  REMOTE_DIR="~/docker_build_${HOST}"

  echo "=== Copy Dockerfile dir to ${HOST} ==="
  ssh "${HOST}" "rm -rf ${REMOTE_DIR}"
  scp -r "${HOST_DOCKERFILES_DIR}" "${HOST}:${REMOTE_DIR}"

  echo "=== Remove old image on ${HOST} ==="
  ssh "${HOST}" "docker rmi -f ros2_perf_${HOST}:latest || true"

  echo "=== Build image on ${HOST} ==="
  ssh "${HOST}" "docker build --platform=linux/arm64 --no-cache -t ros2_perf_${HOST}:latest -f ${REMOTE_DIR}/Dockerfile ${REMOTE_DIR}"

  echo "=== Clean up Dockerfile dir on ${HOST} ==="
  ssh "${HOST}" "rm -rf ${REMOTE_DIR}"
done

echo "=== All host-specific Docker images built on each host ==="