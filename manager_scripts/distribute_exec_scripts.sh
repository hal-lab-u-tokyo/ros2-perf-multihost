#!/usr/bin/env bash
set -euo pipefail

# Distribute host-specific exec_scripts based on metadata.txt.
# Assumptions:
# - Each host_name is reachable over SSH by name
# - REMOTE_REPO_BASE already exists on the remote host

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_WS_DIR="performance_ws"
DEFAULT_REMOTE_REPO_BASE="/home/ubuntu/ros2-perf-multihost"

WS_DIR_INPUT="${DEFAULT_WS_DIR}"
TOPOLOGY_INPUT=""
REMOTE_REPO_BASE="${DEFAULT_REMOTE_REPO_BASE}"

print_help() {
    cat <<EOF
Usage: $(basename "$0") <topology> [OPTIONS]

Distribute host-specific exec scripts using values from metadata.txt.

Options:
    -w, --ws-dir DIR           Workspace directory that contains topologies
                             (default: ${DEFAULT_WS_DIR})
    -b, --remote-repo-base DIR Remote repository base directory
                             (default: ${DEFAULT_REMOTE_REPO_BASE})
  -h, --help                 Show this help message and exit

Examples:
    $(basename "$0") simple
    $(basename "$0") simple -w performance_ws -b /home/ubuntu/ros2-perf-multihost
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -w|--ws-dir)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: $1 requires a value" >&2
                exit 2
            fi
            WS_DIR_INPUT="$2"
            shift 2
            ;;
        -b|--remote-repo-base)
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
        -* )
            echo "ERROR: unknown option: $1" >&2
            echo "Use --help to see available options." >&2
            exit 2
            ;;
        *)
            if [[ -n "${TOPOLOGY_INPUT}" ]]; then
                echo "ERROR: topology is already set to '${TOPOLOGY_INPUT}', unexpected argument: $1" >&2
                exit 2
            fi
            TOPOLOGY_INPUT="$1"
            shift
            ;;
    esac
done

if [[ -z "${TOPOLOGY_INPUT}" ]]; then
    echo "ERROR: topology is required." >&2
    echo "Use --help to see usage." >&2
    exit 2
fi

METADATA_PATH="${REPO_DIR}/${WS_DIR_INPUT}/${TOPOLOGY_INPUT}/metadata.txt"

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
TOPOLOGY_DIR="$(get_metadata_value "topology_dir" "${METADATA_PATH}")"
HOSTS_LINE="$(get_metadata_value "hosts" "${METADATA_PATH}")"
JSON_PATH="$(get_metadata_value "json_path" "${METADATA_PATH}")"

if [[ -z "${WS_DIR}" || -z "${TOPOLOGY_DIR}" || -z "${HOSTS_LINE}" ]]; then
    echo "ERROR: metadata is missing one of ws_dir/topology_dir/hosts in ${METADATA_PATH}" >&2
    exit 1
fi

LOCAL_RUN_DIR="${REPO_DIR}/${WS_DIR}/${TOPOLOGY_DIR}"
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

REMOTE_RUN_DIR="${REMOTE_REPO_BASE}/${WS_DIR}/${TOPOLOGY_DIR}"
REMOTE_EXEC_DIR="${REMOTE_RUN_DIR}/exec_scripts"

echo "=== Metadata ==="
echo "metadata_path : ${METADATA_PATH}"
echo "json_path     : ${JSON_PATH:-N/A}"
echo "ws_dir        : ${WS_DIR}"
echo "topology_dir  : ${TOPOLOGY_DIR}"
echo "hosts         : ${HOSTS[*]}"
echo "local_exec_dir: ${LOCAL_EXEC_DIR}"
echo "remote_exec_dir: ${REMOTE_EXEC_DIR}"

failed_hosts=()

for host in "${HOSTS[@]}"; do
    host_launch="${host}.launch.py"
    host_exec="${host}_exec_docker.sh"
    host_compose="${host}_compose.yaml"

    echo "=== Validating local files for ${host} ==="
    local_files_ok=true
    for file in "${host_launch}" "${host_exec}" "${host_compose}"; do
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
    if ! err="$(ssh "${host}" "mkdir -p '${REMOTE_EXEC_DIR}'" 2>&1)"; then
        echo "ERROR: Failed to create directory on ${host}" >&2
        if [[ -n "${err}" ]]; then
            echo "  ssh: ${err}" >&2
        fi
        failed_hosts+=("${host}")
        continue
    fi

    # Copy exec scripts
    if ! err="$(scp \
        "${LOCAL_EXEC_DIR}/${host_launch}" \
        "${LOCAL_EXEC_DIR}/${host_exec}" \
        "${LOCAL_EXEC_DIR}/${host_compose}" \
        "${host}:${REMOTE_EXEC_DIR}/" 2>&1)"; then
        echo "ERROR: Failed to copy scripts to ${host}" >&2
        if [[ -n "${err}" ]]; then
            echo "  scp: ${err}" >&2
        fi
        failed_hosts+=("${host}")
        continue
    fi

    # Copy metadata
    if ! err="$(scp "${LOCAL_RUN_DIR}/metadata.txt" "${host}:${REMOTE_RUN_DIR}/metadata.txt" 2>&1)"; then
        echo "ERROR: Failed to copy metadata to ${host}" >&2
        if [[ -n "${err}" ]]; then
            echo "  scp: ${err}" >&2
        fi
        failed_hosts+=("${host}")
        continue
    fi

    # Set execute permissions
    if ! err="$(ssh "${host}" "chmod +x '${REMOTE_EXEC_DIR}/${host_exec}'" 2>&1)"; then
        echo "ERROR: Failed to set permissions on ${host}" >&2
        if [[ -n "${err}" ]]; then
            echo "  ssh: ${err}" >&2
        fi
        failed_hosts+=("${host}")
        continue
    fi

    echo "=== Done for ${host} ==="
done

echo "=== Distribution complete ==="

if [[ ${#failed_hosts[@]} -gt 0 ]]; then
    echo "ERROR: ${#failed_hosts[@]} host(s) failed: ${failed_hosts[*]}" >&2
    exit 1
fi
