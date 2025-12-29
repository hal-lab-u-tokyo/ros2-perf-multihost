#!/bin/bash

declare -A HOSTS
HOSTS=( 
  [pi0]="192.168.199.20"
  [pi1]="192.168.199.21"
  [pi2]="192.168.199.22"
  [pi3]="192.168.199.23"
  [pi4]="192.168.199.24"
)

PORT=5000

for host in pi0 pi1 pi2 pi3 pi4; do
  addr="${HOSTS[$host]}"
  echo "Starting REST server on $host ($addr)"
  ssh "$addr" '(source /home/ubuntu/ros2-perf-multihost-v2/.venv/bin/activate && nohup python /home/ubuntu/ros2-perf-multihost-v2/manager_scripts/manager_scripts.py > /home/ubuntu/rest.log 2>&1 &) < /dev/null'

  # 起動確認: ポート5000が開くまで待つ
  echo "Waiting for REST server on $host ($addr) to be ready..."
  for i in {1..30}; do
    if nc -z "$addr" $PORT; then
      echo "$host REST server is up."
      break
    fi
    sleep 2
  done
done