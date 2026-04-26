#!/usr/bin/env bash
set -euo pipefail

# metadata.txt を参照して、各ホスト向け exec_scripts を配布する。
# 前提:
# - 各 host_name は SSH で名前解決できる
# - リモート側に REMOTE_REPO_BASE が存在する

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_WS_DIR="performance_ws"
DEFAULT_SCENARIO="latest"
DEFAULT_REMOTE_REPO_BASE="/home/ubuntu/ros2-perf-multihost"

WS_DIR_INPUT="${DEFAULT_WS_DIR}"
SCENARIO_INPUT="${DEFAULT_SCENARIO}"
REMOTE_REPO_BASE="${DEFAULT_REMOTE_REPO_BASE}"

print_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Distribute host-specific exec scripts using values from metadata.txt.

Options:
  -s, --scenario NAME        Scenario directory under ws-dir
                             (default: ${DEFAULT_SCENARIO})
  -w, --ws-dir DIR           Workspace directory that contains scenarios
                             (default: ${DEFAULT_WS_DIR})
  -r, --remote-repo-base DIR Remote repository base directory
                             (default: ${DEFAULT_REMOTE_REPO_BASE})
  -h, --help                 Show this help message and exit

Examples:
  $(basename "$0")
  $(basename "$0") --scenario simple-fastdds
  $(basename "$0") -s simple-cyclonedds -w performance_ws -r /home/ubuntu/ros2-perf-multihost
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--scenario)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: $1 requires a value" >&2
                exit 2
            fi
            SCENARIO_INPUT="$2"
            shift 2
            ;;
        -w|--ws-dir)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: $1 requires a value" >&2
                exit 2
            fi
            WS_DIR_INPUT="$2"
            shift 2
            ;;
        -r|--remote-repo-base)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: $1 requires a value" >&2
                exit 2
            fi
            REMOTE_REPO_BASE="$2"
            shift 2
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            echo "ERROR: unknown option: $1" >&2
            echo "Use --help to see available options." >&2
            exit 2
            ;;
    esac
done

METADATA_PATH="${REPO_DIR}/${WS_DIR_INPUT}/${SCENARIO_INPUT}/metadata.txt"

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

get_metadata_value() {
    local key="$1"
    local file="$2"
    awk -v key="$key" 'index($0, key ": ") == 1 {print substr($0, length(key) + 3); exit}' "$file"
}

if [[ ! -f "${METADATA_PATH}" ]]; then
    echo "ERROR: metadata file not found: ${METADATA_PATH}" >&2
    exit 1
fi

WS_DIR="$(get_metadata_value "ws_dir" "${METADATA_PATH}")"
SCENARIO_DIR="$(get_metadata_value "scenario_dir" "${METADATA_PATH}")"
HOSTS_LINE="$(get_metadata_value "hosts" "${METADATA_PATH}")"
JSON_PATH="$(get_metadata_value "json_path" "${METADATA_PATH}")"

if [[ -z "${WS_DIR}" || -z "${SCENARIO_DIR}" || -z "${HOSTS_LINE}" ]]; then
    echo "ERROR: metadata is missing one of ws_dir/scenario_dir/hosts in ${METADATA_PATH}" >&2
    exit 1
fi

LOCAL_RUN_DIR="${REPO_DIR}/${WS_DIR}/${SCENARIO_DIR}"
LOCAL_EXEC_DIR="${LOCAL_RUN_DIR}/exec_scripts"

if [[ ! -d "${LOCAL_EXEC_DIR}" ]]; then
    echo "ERROR: local exec_scripts directory not found: ${LOCAL_EXEC_DIR}" >&2
    exit 1
fi

IFS=',' read -r -a HOSTS_RAW <<< "${HOSTS_LINE}"
HOSTS=()
for h in "${HOSTS_RAW[@]}"; do
    h="$(trim "$h")"
    if [[ -n "$h" ]]; then
        HOSTS+=("$h")
    fi
done

if [[ "${#HOSTS[@]}" -eq 0 ]]; then
    echo "ERROR: no hosts found in metadata: ${METADATA_PATH}" >&2
    exit 1
fi

REMOTE_RUN_DIR="${REMOTE_REPO_BASE}/${WS_DIR}/${SCENARIO_DIR}"
REMOTE_EXEC_DIR="${REMOTE_RUN_DIR}/exec_scripts"
REMOTE_ALIAS_DIR="${REMOTE_REPO_BASE}/${WS_DIR}/${SCENARIO_INPUT}"

echo "=== Metadata ==="
echo "metadata_path : ${METADATA_PATH}"
echo "json_path     : ${JSON_PATH:-N/A}"
echo "ws_dir        : ${WS_DIR}"
echo "scenario_dir  : ${SCENARIO_DIR}"
echo "hosts         : ${HOSTS[*]}"
echo "local_exec_dir: ${LOCAL_EXEC_DIR}"
echo "remote_exec_dir: ${REMOTE_EXEC_DIR}"
if [[ "${SCENARIO_INPUT}" != "${SCENARIO_DIR}" ]]; then
    echo "remote_alias_dir: ${REMOTE_ALIAS_DIR} -> ${REMOTE_RUN_DIR}"
fi

failed_hosts=()

for host in "${HOSTS[@]}"; do
    host_exec="${host}_exec.sh"
    host_run="${host}_run.sh"
    host_compose="${host}_compose.yaml"

    echo "=== Validating local files for ${host} ==="
    local_files_ok=true
    for file in "${host_exec}" "${host_run}" "${host_compose}"; do
        if [[ ! -f "${LOCAL_EXEC_DIR}/${file}" ]]; then
            echo "ERROR: missing local file: ${LOCAL_EXEC_DIR}/${file}" >&2
            failed_hosts+=("${host}")
            local_files_ok=false
            break
        fi
    done
    
    if [[ "${local_files_ok}" != "true" ]]; then
        continue
    fi

    echo "=== Copying exec scripts to ${host} ==="
    
    # Create remote directory
    if ! ssh "${host}" "mkdir -p '${REMOTE_EXEC_DIR}'" 2>/dev/null; then
        echo "ERROR: Failed to create directory on ${host}" >&2
        failed_hosts+=("${host}")
        continue
    fi

    # Copy exec scripts
    if ! scp \
        "${LOCAL_EXEC_DIR}/${host_exec}" \
        "${LOCAL_EXEC_DIR}/${host_run}" \
        "${LOCAL_EXEC_DIR}/${host_compose}" \
        "${host}:${REMOTE_EXEC_DIR}/" 2>/dev/null; then
        echo "ERROR: Failed to copy scripts to ${host}" >&2
        failed_hosts+=("${host}")
        continue
    fi

    # Copy metadata
    if ! scp "${LOCAL_RUN_DIR}/metadata.txt" "${host}:${REMOTE_RUN_DIR}/metadata.txt" 2>/dev/null; then
        echo "ERROR: Failed to copy metadata to ${host}" >&2
        failed_hosts+=("${host}")
        continue
    fi

    # Set execute permissions
    if ! ssh "${host}" "chmod +x '${REMOTE_EXEC_DIR}/${host_exec}' '${REMOTE_EXEC_DIR}/${host_run}'" 2>/dev/null; then
        echo "ERROR: Failed to set permissions on ${host}" >&2
        failed_hosts+=("${host}")
        continue
    fi

    if [[ "${SCENARIO_INPUT}" != "${SCENARIO_DIR}" ]]; then
        remote_alias_parent="$(dirname "${REMOTE_ALIAS_DIR}")"
        remote_alias_name="$(basename "${REMOTE_ALIAS_DIR}")"
        remote_target_name="$(basename "${REMOTE_RUN_DIR}")"
        if ! ssh "${host}" "cd '${remote_alias_parent}' && ln -sfn '${remote_target_name}' '${remote_alias_name}'" 2>/dev/null; then
            echo "ERROR: Failed to update alias ${REMOTE_ALIAS_DIR} on ${host}" >&2
            failed_hosts+=("${host}")
            continue
        fi
    fi
    
    echo "=== Done for ${host} ==="
done

echo "=== Distribution complete ==="

if [[ ${#failed_hosts[@]} -gt 0 ]]; then
    echo "ERROR: ${#failed_hosts[@]} host(s) failed: ${failed_hosts[*]}" >&2
    exit 1
fi
