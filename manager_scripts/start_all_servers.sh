#!/bin/bash

HOSTS=("192.168.199.20" "192.168.199.21" "192.168.199.22" "192.168.199.23" "192.168.199.24")
PORT=5000

SSH_OPTS="-n -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5"

# macOS(BSD) nc なら -G、GNU nc なら -w
if nc -h 2>&1 | grep -qi 'OpenBSD'; then
  NC_TIMEOUT_OPT=(-G 1)
else
  NC_TIMEOUT_OPT=(-w 1)
fi

pids=()

for host in "${HOSTS[@]}"; do
  (
    echo "[$host] Starting REST server on $host"
    if ! ssh $SSH_OPTS "ubuntu@$host" '
      LOG=/home/ubuntu/rest.log
      PID=/home/ubuntu/rest.pid
      : > "$LOG"
      # 仮想環境の Python を直接起動して完全デタッチ
      setsid nohup /home/ubuntu/ros2-perf-multihost-v2/.venv/bin/python \
        /home/ubuntu/ros2-perf-multihost-v2/manager_scripts/manager_scripts.py \
        >>"$LOG" 2>&1 < /dev/null &
      echo $! > "$PID"
      echo STARTED
    ' ; then
      echo "[$host] WARN: SSH command failed (skipping wait)."
      exit 1
    fi

    echo "[$host] Waiting for REST server to be ready..."
    ready=0
    for i in {1..30}; do
      if nc -z "${NC_TIMEOUT_OPT[@]}" "$host" "$PORT" >/dev/null 2>&1; then
        echo "[$host] REST server is up."
        ready=1
        break
      fi
      sleep 2
    done

    # if [ "$ready" -ne 1 ]; then
    #   echo "[$host] WARN: $host:$PORT not reachable from here. Continuing..."
    #   exit 1
    # fi
  ) &
  pids+=($!)
done

overall_fail=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    overall_fail=1
  fi
done

exit $overall_fail