#!/bin/bash
set -euo pipefail

DEFAULT_WS_DIR="performance_ws"
DEFAULT_SCENARIO="latest"
WS_DIR="${DEFAULT_WS_DIR}"
SCENARIO="${DEFAULT_SCENARIO}"
PORT=5000

SSH_OPTS="-n -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5"

# Helper functions
print_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Start REST servers on all hosts from metadata.txt.

Options:
  -s, --scenario NAME  Scenario directory (default: ${DEFAULT_SCENARIO})
  -w, --ws-dir DIR     Workspace directory (default: ${DEFAULT_WS_DIR})
  -h, --help           Show this help
EOF
}

get_metadata_value() {
    local key="$1"
    local file="$2"
    awk -v key="$key" 'index($0, key ": ") == 1 {print substr($0, length(key) + 3); exit}' "$file"
}

resolve_hosts() {
    local ws_dir="$1"
    local scenario="$2"
    local metadata_path="${ws_dir}/${scenario}/metadata.txt"
    
    if [[ ! -f "${metadata_path}" ]]; then
        echo "ERROR: metadata.txt not found: ${metadata_path}" >&2
        return 1
    fi
    
    local hosts_line
    hosts_line=$(get_metadata_value "hosts" "${metadata_path}")
    if [[ -z "${hosts_line}" ]]; then
        echo "ERROR: No 'hosts' field in ${metadata_path}" >&2
        return 1
    fi
    
    # Convert comma-separated hosts to array
    IFS=',' read -r -a hosts_array <<< "${hosts_line}"
    local trimmed_hosts=()
    for h in "${hosts_array[@]}"; do
        trimmed_hosts+=("$(echo "$h" | xargs)")
    done
    printf '%s\n' "${trimmed_hosts[@]}"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--scenario)
            SCENARIO="$2"
            shift 2
            ;;
        -w|--ws-dir)
            WS_DIR="$2"
            shift 2
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            echo "ERROR: unknown option: $1" >&2
            print_help
            exit 1
            ;;
    esac
done

# Get hosts from metadata
if ! mapfile -t HOSTS < <(resolve_hosts "${WS_DIR}" "${SCENARIO}"); then
    echo "ERROR: Failed to resolve hosts from metadata" >&2
    exit 1
fi

if [[ ${#HOSTS[@]} -eq 0 ]]; then
    echo "ERROR: No hosts found in metadata" >&2
    exit 1
fi

echo "Found ${#HOSTS[@]} host(s): ${HOSTS[*]}"

# macOS(BSD) nc なら -G、GNU nc なら -w
if nc -h 2>&1 | grep -qi 'OpenBSD'; then
    NC_TIMEOUT_OPT=(-G 1)
else
    NC_TIMEOUT_OPT=(-w 1)
fi

for host in "${HOSTS[@]}"; do
    echo "Starting REST server on $host"
    if ! ssh $SSH_OPTS "ubuntu@$host" '
    LOG=/home/ubuntu/rest.log
    PID=/home/ubuntu/rest.pid
    : > "$LOG"
    # Python を直接起動して完全デタッチ
        python3 /home/ubuntu/ros2-perf-multihost/manager_scripts/rest_server.py \
      >>"$LOG" 2>&1 < /dev/null &
    echo $! > "$PID"
    echo STARTED
  '; then
        echo "WARN: SSH command failed on $host (skipping wait)."
        continue
    fi

    echo "Waiting for REST server on $host to be ready..."
    ready=0
    for i in {1..30}; do
        if nc -z "${NC_TIMEOUT_OPT[@]}" "$host" "$PORT" >/dev/null 2>&1; then
            echo "$host REST server is up."
            ready=1
            break
        fi
        sleep 2
    done

    if [ "$ready" -ne 1 ]; then
        echo "WARN: $host:$PORT not reachable from here. Continuing..."
    fi
done
