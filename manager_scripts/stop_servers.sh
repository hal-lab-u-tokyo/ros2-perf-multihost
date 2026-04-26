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

Stop REST servers on all hosts from metadata.txt.

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

for host in "${HOSTS[@]}"; do
    echo "Stopping REST server on $host"

    # まず5000番ポートのLISTENプロセスを特定（優先: lsof、フォールバック: pgrep）
    pids=$(ssh $SSH_OPTS "ubuntu@$host" 'lsof -t -iTCP:5000 -sTCP:LISTEN 2>/dev/null || pgrep -f "/home/ubuntu/ros2-perf-multihost/manager_scripts/rest_server.py" || true')

    if [ -z "$pids" ]; then
        echo "$host: no REST server process found."
        continue
    fi

    echo "$host: target PIDs: $pids"

    # まず穏やかに終了(SIGTERM)
    ssh $SSH_OPTS "ubuntu@$host" "for pid in $pids; do kill -TERM \$pid 2>/dev/null || true; done"

    # 最大10秒待って終了を確認
    for i in {1..10}; do
        sleep 1
        alive=$(ssh $SSH_OPTS "ubuntu@$host" "for pid in $pids; do if kill -0 \$pid 2>/dev/null; then echo alive; break; fi; done")
        if [ -z "$alive" ]; then
            break
        fi
    done

    # まだ生きていれば強制終了(SIGKILL)
    alive=$(ssh $SSH_OPTS "ubuntu@$host" "for pid in $pids; do if kill -0 \$pid 2>/dev/null; then echo alive; break; fi; done")
    if [ -n "$alive" ]; then
        echo "$host: forcing kill..."
        ssh $SSH_OPTS "ubuntu@$host" "for pid in $pids; do kill -KILL \$pid 2>/dev/null || true; done"
    fi

    # ポート閉塞確認
    listening_count=$(ssh $SSH_OPTS "ubuntu@$host" 'lsof -nP -iTCP:5000 -sTCP:LISTEN 2>/dev/null | wc -l')
    if [ "$listening_count" -eq 0 ]; then
        echo "$host: REST server stopped."
    else
        echo "WARN: $host: port $PORT still listening."
    fi
done
