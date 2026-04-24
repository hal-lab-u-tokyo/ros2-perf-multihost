FROM ros:jazzy-ros-base

# ROS 2のワークスペースを構築するための依存関係をインストール
RUN apt update && apt install -y \
  libcxxopts-dev \
  ros-jazzy-rmw-cyclonedds-cpp \
  ros-jazzy-rmw-zenoh-cpp \
  && apt clean \
  && rm -rf /var/lib/apt/lists/*

# ワークスペースを作成し、本プロジェクトをクローンしてビルド
RUN apt update \
  && mkdir -p /ros2_perf_ws/src \
  && cd /ros2_perf_ws/src \
  && git clone https://github.com/hal-lab-u-tokyo/ros2-perf-multihost.git \
  && cd /ros2_perf_ws \
  && . /opt/ros/jazzy/setup.sh \
  && colcon build

CMD ["/bin/bash"]
