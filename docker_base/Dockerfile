FROM ros:jazzy-ros-base

ENV ROS_DISTRO=jazzy
ENV CMAKE_PREFIX_PATH=/opt/ros/jazzy

# ワークスペースを作成し、本プロジェクトをクローン
RUN apt update \
    && mkdir -p ~/performance_ws/src \
    && cd ~/performance_ws/src \
    && git clone https://github.com/hal-lab-u-tokyo/ros2-perf-multihost.git

# プロジェクトのビルド
# RUNコマンドではbashファイルを叩けないしsourceもつかえない。→　.でshファイルを叩く
RUN git clone https://github.com/jarro2783/cxxopts.git \
    && . /opt/ros/jazzy/setup.sh \
    && cd cxxopts \
    && mkdir build && cd build \
    && cmake .. \
    && make && sudo make install \
    && cd /root/performance_ws \
    && colcon build
    
