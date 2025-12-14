#!/usr/bin/env bash
set -euo pipefail

# ホストPC上で実行する前提
# 使い方:
#   cd parse_json
#   bash copy_artifacts_to_rpis.sh
#
# 前提:
# - 各Raspberry Piにsshでパスワードなし接続可能 (pi0, pi1, pi2, pi3)
# - 各Raspberry Piに ~/ros2-perf-multihost-v2 ディレクトリが存在

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKERFILES_DIR="${REPO_DIR}/Dockerfiles"
HOST_SCRIPTS_DIR="${REPO_DIR}/host_scripts"

# 配布対象ホスト（必要に応じて編集）
HOSTS=("pi0" "pi1" "pi2" "pi3")

# リモート側の受け取り先
REMOTE_BASE="~/ros2-perf-multihost-v2"
REMOTE_DOCKERFILES_DIR="${REMOTE_BASE}/Dockerfiles"
REMOTE_HOST_SCRIPTS_DIR="${REMOTE_BASE}/host_scripts"

echo "=== Checking local artifacts exist ==="
if [[ ! -d "${DOCKERFILES_DIR}" ]]; then
  echo "ERROR: ${DOCKERFILES_DIR} not found. First generate Dockerfiles via parse_json/generate_dockerfiles.py."
  exit 1
fi
if [[ ! -d "${HOST_SCRIPTS_DIR}" ]]; then
  echo "ERROR: ${HOST_SCRIPTS_DIR} not found. First generate host scripts via parse_json/generate_scripts.py or generate_dockerfiles.py."
  exit 1
fi

for host in "${HOSTS[@]}"; do
  echo "=== Copying artifacts to ${host} ==="
  ssh "${host}" "mkdir -p ${REMOTE_DOCKERFILES_DIR} ${REMOTE_HOST_SCRIPTS_DIR}"

  # Dockerfiles はホスト毎のディレクトリ単位でコピー
  # 存在するホストのみコピー（無い場合はスキップ）
  for dfdir in "${DOCKERFILES_DIR}"/*; do
    dfname="$(basename "${dfdir}")"
    if [[ -d "${dfdir}" ]]; then
      echo " -> Dockerfiles/${dfname} -> ${host}:${REMOTE_DOCKERFILES_DIR}/${dfname}"
      scp -r "${dfdir}" "${host}:${REMOTE_DOCKERFILES_DIR}/"
    fi
  done

  # host_scripts はディレクトリごとコピー
  echo " -> host_scripts/* -> ${host}:${REMOTE_HOST_SCRIPTS_DIR}/"
  scp -r "${HOST_SCRIPTS_DIR}/"* "${host}:${REMOTE_HOST_SCRIPTS_DIR}/" || true

  # 実行権限の付与
  ssh "${host}" "chmod +x ${REMOTE_HOST_SCRIPTS_DIR}/*.sh || true"

  echo "=== Done for ${host} ==="
done

echo "=== All copies finished ==="