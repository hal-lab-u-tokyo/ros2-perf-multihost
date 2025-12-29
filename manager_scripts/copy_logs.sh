#!/bin/bash

HOSTS=("pi0" "pi1" "pi2" "pi3" "pi4")
REMOTE_LOG_DIR="/home/ubuntu/ros2-perf-multihost-v2/performance_test/logs_local"
LOCAL_LOG_DIR="./logs"

for host in "${HOSTS[@]}"; do
  echo "Copying logs from $host"
  scp -r $ubuntu@${host}:${REMOTE_LOG_DIR}/* "$LOCAL_LOG_DIR/"
done