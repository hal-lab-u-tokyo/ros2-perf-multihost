#!/bin/bash

HOSTS=("pi0" "pi1" "pi2" "pi3" "pi4")

for host in "${HOSTS[@]}"; do
  echo "Starting REST server on $host"
  ssh "$host" '(source /home/ubuntu/ros2-perf-multihost-v2/.venv/bin/activate && nohup python /home/ubuntu/ros2-perf-multihost-v2/manager_scripts/manager_scripts.py > /home/ubuntu/rest.log 2>&1 &) < /dev/null'
done