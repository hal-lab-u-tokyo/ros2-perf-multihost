FROM ros:jazzy-ros-base

#Install dependencies required to build the ROS 2 workspace
RUN apt update && apt instal -y \
  libcxxopts-dev \
  python3-psutil \
  ros-jazzy-rmw-cyclonedds-cpp \
  ros-jazzy-rmw-zenoh-cpp \
  && apt clean \
  && rm -rf /var/lib/apt/lists/*

#Cerate the workspace, copy this project from the build context, and build it
RUN mkdir -p _workdir/ros2-perf-QoS-multihost
COPY . /workdir/ros2-perf-QoS-multihost
RUN cd /workdir/ros2-perf-QoS-multihost/ros2_node_impl_ws \
  && . /opt/ros/jazzy/setup.sh \
  && colcon build

CMD ["/bin/bash"]