FROM ros:jazzy-ros-base

# ROS 2のワークスペースを構築するための依存関係をインストール
RUN apt update && apt install -y \
  libcxxopts-dev \
  python3-psutil \
  ros-jazzy-rmw-cyclonedds-cpp \
  ros-jazzy-rmw-zenoh-cpp \
  && apt clean \
  && rm -rf /var/lib/apt/lists/*

# ワークスペースを作成し、build context から本プロジェクトをコピーしてビルド
RUN mkdir -p /workdir/ros2-perf-multihost
COPY . /workdir/ros2-perf-multihost
RUN cd /workdir/ros2-perf-multihost/ros2_node_impl_ws \
  && . /opt/ros/jazzy/setup.sh \
  && colcon build

CMD ["/bin/bash"]
