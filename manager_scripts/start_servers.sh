#!/bin/bash

HOSTS=("192.168.199.20" "192.168.199.21" "192.168.199.22" "192.168.199.23" "192.168.199.24")
PORT=5000

for host in "${HOSTS[@]}"; do
  echo "Starting REST server on $host"
  ssh "ubuntu@$host" '(source /home/ubuntu/ros2-perf-multihost-v2/.venv/bin/activate && nohup python /home/ubuntu/ros2-perf-multihost-v2/manager_scripts/manager_scripts.py > /home/ubuntu/rest.log 2>&1 &) < /dev/null'

  # 起動確認: ポート5000が開くまで待つ
  echo "Waiting for REST server on $host to be ready..."
  for i in {1..30}; do
    if nc -z "$host" $PORT; then
      echo "$host REST server is up."
      break
    fi
    sleep 2
  done
done