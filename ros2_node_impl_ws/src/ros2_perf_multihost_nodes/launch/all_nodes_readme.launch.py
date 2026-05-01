from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="ros2_perf_multihost_nodes",
                executable="publisher_node",
                output="screen",
                arguments=[
                    "--node-name",
                    "pub1",
                    "--topic-names",
                    "topic1",
                    "--size",
                    "64",
                    "--period",
                    "100",
                ],
            ),
            Node(
                package="ros2_perf_multihost_nodes",
                executable="subscriber_node",
                output="screen",
                arguments=[
                    "--node-name",
                    "sub1",
                    "--topic-names",
                    "topic1",
                ],
            ),
            Node(
                package="ros2_perf_multihost_nodes",
                executable="intermediate_node",
                output="screen",
                arguments=[
                    "--node-name",
                    "relay1",
                    "--topic-names-pub",
                    "topic_out",
                    "--topic-names-sub",
                    "topic_in",
                    "--size",
                    "64",
                    "--period",
                    "100",
                ],
            ),
        ]
    )
