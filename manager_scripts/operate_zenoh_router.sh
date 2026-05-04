#!/usr/bin/env bash
set -eo pipefail

# Configuration
# TODO: adjust as needed for your environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
PID_FILE="$LOG_DIR/zenoh_router.pid"
OUT_FILE="$LOG_DIR/zenoh_router.out"
PORT="${ZENOH_PORT:-7447}"

usage() {
    echo "Usage: $0 {start|foreground|stop|status|wait}"
    echo "  start       : start in the background with nohup, PID, and log management"
    echo "  foreground  : start in the foreground and stop with CTRL-C"
    echo "  stop        : stop the router process using the PID if available"
    echo "  status      : show process and listening port status"
    echo "  wait        : wait until port ${PORT} starts listening"
    echo "Env: ZENOH_CONFIG_OVERRIDE, RUST_LOG, ZENOH_PORT"
}

ensure_env() {
    # Load the ROS 2 environment when available.
    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source /opt/ros/jazzy/setup.bash
    fi
    export RMW_IMPLEMENTATION=rmw_zenoh_cpp
    export RUST_LOG="${RUST_LOG:-zenoh=warn,zenoh_transport=warn}"
}

start_bg() {
    ensure_env
    mkdir -p "$LOG_DIR"
    # Stop an existing rmw_zenohd process before starting a new one.
    if pgrep -x rmw_zenohd >/dev/null 2>&1; then
        echo "Existing rmw_zenohd found — killing it"
        pkill -x rmw_zenohd || true
        sleep 1
    fi
    echo "Starting rmw_zenohd with ZENOH_CONFIG_OVERRIDE='${ZENOH_CONFIG_OVERRIDE:-}'"
    nohup ros2 run rmw_zenoh_cpp rmw_zenohd >"$OUT_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    echo "rmw_zenohd started (PID $(cat "$PID_FILE")), log: $OUT_FILE"
}

start_fg() {
    ensure_env
    echo "Starting rmw_zenohd (foreground) with ZENOH_CONFIG_OVERRIDE='${ZENOH_CONFIG_OVERRIDE:-}'"
    ros2 run rmw_zenoh_cpp rmw_zenohd
}

stop_router() {
    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE")"
        kill "$PID" 2>/dev/null || true
        rm -f "$PID_FILE"
        echo "Stopped rmw_zenohd (PID $PID)"
    else
        pkill -x rmw_zenohd 2>/dev/null || true
        echo "Stopped rmw_zenohd (no PID file)"
    fi
}

status_router() {
    if pgrep -x rmw_zenohd >/dev/null 2>&1; then
        PIDS="$(pgrep -x rmw_zenohd | paste -sd, -)"
        echo "rmw_zenohd running (PID(s): $PIDS)"
    else
        echo "rmw_zenohd not running"
    fi
    echo "Listening sockets on TCP:${PORT}:"
    lsof -iTCP:"$PORT" -sTCP:LISTEN -nP || true
}

wait_ready() {
    echo "Waiting for zenoh router on port ${PORT}..."
    for i in $(seq 1 30); do
        if nc -z 127.0.0.1 "$PORT" 2>/dev/null || nc -z localhost "$PORT" 2>/dev/null; then
            echo "Zenoh router is up on port ${PORT}."
            return 0
        fi
        sleep 1
    done
    echo "Timeout waiting for zenoh router on port ${PORT}."
    return 1
}

cmd="${1:-}"
case "$cmd" in
start) start_bg ;;
foreground) start_fg ;;
stop) stop_router ;;
status) status_router ;;
wait) wait_ready ;;
*)
    usage
    exit 1
    ;;
esac
