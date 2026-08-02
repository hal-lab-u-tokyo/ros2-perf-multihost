FROM ros:jazzy-ros-base

# Install dependencies required to build the ROS 2 workspace
RUN apt update && apt install -y \
  libcxxopts-dev \
  python3-psutil \
  ros-jazzy-rmw-cyclonedds-cpp \
  ros-jazzy-rmw-zenoh-cpp \
  && apt clean \
  && rm -rf /var/lib/apt/lists/*

# Create the workspace, copy this project from the build context, and build it
RUN mkdir -p /workdir/ros2-perf-multihost
COPY . /workdir/ros2-perf-multihost
RUN cd /workdir/ros2-perf-multihost/ros2_node_impl_ws \
  && . /opt/ros/jazzy/setup.sh \
  && colcon build

CMD ["/bin/bash"]
