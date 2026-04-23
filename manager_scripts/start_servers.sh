#!/bin/bash

HOSTS=("192.168.11.106" "192.168.11.107" "192.168.11.108")
PORT=5000

SSH_OPTS="-n -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5"

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
    python3 /home/ubuntu/ros2-perf-multihost/manager_scripts/manager_scripts.py \
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
