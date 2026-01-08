#!/bin/bash

HOSTS=("192.168.199.20" "192.168.199.21" "192.168.199.22" "192.168.199.23" "192.168.199.24")
PORT=5000

SSH_OPTS="-n -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5"

for host in "${HOSTS[@]}"; do
  echo "Stopping REST server on $host"

  # まず5000番ポートのLISTENプロセスを特定（優先: lsof、フォールバック: pgrep）
  pids=$(ssh $SSH_OPTS "ubuntu@$host" 'lsof -t -iTCP:5000 -sTCP:LISTEN 2>/dev/null || pgrep -f "/home/ubuntu/ros2-perf-multihost-v2/manager_scripts/manager_scripts.py" || true')

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