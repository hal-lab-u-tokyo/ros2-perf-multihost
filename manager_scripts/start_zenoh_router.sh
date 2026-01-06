#!/usr/bin/env bash
set -eo pipefail

# 設定
# TODO: 必要に応じて編集
CONFIG_DEFAULT="$HOME/rmw_test/ros2-perf-multihost-v2/config/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5"
CONFIG="${ZENOH_ROUTER_CONFIG_URI:-$CONFIG_DEFAULT}"
LOG_DIR="$HOME/rmw_test/ros2-perf-multihost-v2/logs"
PID_FILE="$LOG_DIR/zenoh_router.pid"
OUT_FILE="$LOG_DIR/zenoh_router.out"
PORT="${ZENOH_PORT:-7447}"

usage() {
  echo "Usage: $0 {start|foreground|stop|status|wait}"
  echo "  start       : 背景起動 (nohup)・PID/ログ管理"
  echo "  foreground  : 前景起動 (CTRL-Cで停止)"
  echo "  stop        : PID/プロセスを停止"
  echo "  status      : プロセス/ポートの状態表示"
  echo "  wait        : ポート${PORT}がLISTENになるまで待機"
  echo "Env: ZENOH_ROUTER_CONFIG_URI, RUST_LOG, ZENOH_PORT"
}

ensure_env() {
  # ROS 2環境を可能なら読み込み
  if [ -f "/opt/ros/jazzy/setup.bash" ]; then
    source /opt/ros/jazzy/setup.bash
  fi
  export RMW_IMPLEMENTATION=rmw_zenoh_cpp
  export ZENOH_ROUTER_CONFIG_URI="$CONFIG"
  export RUST_LOG="${RUST_LOG:-zenoh=warn,zenoh_transport=warn}"
}

start_bg() {
  ensure_env
  mkdir -p "$LOG_DIR"
  # 既存のrmw_zenohdがあれば止める
  if pgrep -x rmw_zenohd >/dev/null 2>&1; then
    echo "Existing rmw_zenohd found — killing it"
    pkill -x rmw_zenohd || true
    sleep 1
  fi
  echo "Starting rmw_zenohd with config: $ZENOH_ROUTER_CONFIG_URI"
  nohup ros2 run rmw_zenoh_cpp rmw_zenohd >"$OUT_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "rmw_zenohd started (PID $(cat "$PID_FILE")), log: $OUT_FILE"
}

start_fg() {
  ensure_env
  echo "Starting rmw_zenohd (foreground) with config: $ZENOH_ROUTER_CONFIG_URI"
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
  start)      start_bg ;;
  foreground) start_fg ;;
  stop)       stop_router ;;
  status)     status_router ;;
  wait)       wait_ready ;;
  *)          usage; exit 1 ;;
esac