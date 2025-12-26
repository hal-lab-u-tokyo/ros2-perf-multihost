#!/bin/bash

HOSTS=("pi0" "pi1" "pi2" "pi3" "pi4") # 必要なホスト名に調整

for host in "${HOSTS[@]}"; do
  echo "Starting REST server on $host"
  ssh "$host" 'source /home/pi/ros2-perf-multihost-v2/.venv/bin/activate && nohup python /home/pi/ros2-perf-multihost-v2/manager_scripts/manager_scripts.py > /home/pi/rest.log 2>&1 &'
done