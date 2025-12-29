#!/bin/bash
set -e

# ホスト名リスト（Dockerfilesディレクトリと一致させる）
HOSTS=("pi0" "pi1" "pi2")  # 必要に応じて編集

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILES_DIR="${REPO_DIR}/Dockerfiles"

for HOST in "${HOSTS[@]}"; do
  IMAGE_NAME="ros2_perf_${HOST}"
  IMAGE_TAG="latest"
  IMAGE_FILE="${IMAGE_NAME}.tar"
  DOCKERFILE_PATH="${DOCKERFILES_DIR}/${HOST}/Dockerfile"

  echo "=== Building image for ${HOST} ==="
  docker build --platform=linux/arm64 -t ${IMAGE_NAME}:${IMAGE_TAG} -f "${DOCKERFILE_PATH}" "${DOCKERFILES_DIR}/${HOST}"

  echo "=== Saving image for ${HOST} ==="
  docker save -o "${IMAGE_FILE}" "${IMAGE_NAME}:${IMAGE_TAG}"

  echo "=== Copying image to ${HOST} ==="
  scp "${IMAGE_FILE}" "${HOST}:~/"

  echo "=== Loading image on ${HOST} ==="
  ssh "${HOST}" "docker load -i ~/${IMAGE_FILE} && rm ~/${IMAGE_FILE}"

  rm "${IMAGE_FILE}"
done

echo "=== All host-specific Docker images distributed ==="