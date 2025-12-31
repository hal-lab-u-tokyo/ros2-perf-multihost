#!/bin/bash
set -euo pipefail

# ホスト名リスト（必要に応じて編集）
HOSTS=("pi0" "pi1" "pi2")

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for HOST in "${HOSTS[@]}"; do
  REMOTE_DIR="~/ros2_perf_build_${HOST}"
  REMOTE_LOG="${REMOTE_DIR}/build_${HOST}.log"
  LOCAL_LOG="./build_${HOST}.log"

  echo "=== Sync project to ${HOST}:${REMOTE_DIR} ==="
  ssh "${HOST}" "rm -rf ${REMOTE_DIR} && mkdir -p ${REMOTE_DIR}"
  rsync -az --delete --exclude='.git' "${REPO_DIR}/" "${HOST}:${REMOTE_DIR}/"

  echo "=== Remove old image on ${HOST} ==="
  ssh "${HOST}" "docker rmi -f ros2_perf_${HOST}:latest || true" || true

  echo "=== Start remote build on ${HOST} (streaming output) ==="
  # Run build on remote host, tee output to remote log, and stream it locally.
  # Use bash -lc to ensure PIPESTATUS is available on remote side.
  ssh "${HOST}" bash -lc "set -o pipefail; cd ${REMOTE_DIR}; \
    if [ -f Dockerfiles/${HOST}/Dockerfile ]; then \
      docker build --platform=linux/arm64 --no-cache -t ros2_perf_${HOST}:latest -f Dockerfiles/${HOST}/Dockerfile . 2>&1 | tee ${REMOTE_LOG}; \
      exit \${PIPESTATUS[0]}; \
    else \
      echo 'No Dockerfile for ${HOST} at Dockerfiles/${HOST}/Dockerfile' | tee ${REMOTE_LOG}; exit 2; \
    fi" 2>&1 | tee "${LOCAL_LOG}"

  SSH_EXIT=${PIPESTATUS[0]:-0}
  if [ "${SSH_EXIT}" -ne 0 ]; then
    echo "=== Remote build on ${HOST} failed (exit ${SSH_EXIT}) ==="
  else
    echo "=== Remote build on ${HOST} finished OK ==="
  fi

  echo "=== Fetch remote build log from ${HOST} ==="
  scp "${HOST}:${REMOTE_LOG}" "${LOCAL_LOG}.remote" || echo "failed to fetch remote log for ${HOST}"

  echo "=== Clean up remote build dir on ${HOST} ==="
  ssh "${HOST}" "rm -rf ${REMOTE_DIR}" || true
done

echo "=== All host-specific Docker image builds requested/completed ==="