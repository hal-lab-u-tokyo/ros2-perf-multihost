from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="ros2_perf_multihost_nodes",
                executable="benchmark_node",
                output="screen",
                arguments=[
                    "--node-name",
                    "pub1",
                    "--topic-names-pub",
                    "topic1",
                    "--msg-types-pub",
                    "stamped_vector",
                    "--msg-sizes-pub",
                    "64",
                    "--msg-pass-by-pub",
                    "const_ref",
                    "--period",
                    "100",
                ],
            ),
            Node(
                package="ros2_perf_multihost_nodes",
                executable="benchmark_node",
                output="screen",
                arguments=[
                    "--node-name",
                    "sub1",
                    "--topic-names-sub",
                    "topic1",
                    "--msg-types-sub",
                    "stamped_vector",
                ],
            ),
            Node(
                package="ros2_perf_multihost_nodes",
                executable="benchmark_node",
                output="screen",
                arguments=[
                    "--node-name",
                    "relay1",
                    "--topic-names-pub",
                    "topic_out",
                    "--topic-names-sub",
                    "topic_in",
                    "--msg-types-pub",
                    "stamped_vector",
                    "--msg-types-sub",
                    "stamped_vector",
                    "--msg-sizes-pub",
                    "64",
                    "--msg-pass-by-pub",
                    "unique_ptr",
                    "--msg-pass-by-sub",
                    "const_shared_ptr_with_info",
                    "--period",
                    "100",
                ],
            ),
        ]
    )
