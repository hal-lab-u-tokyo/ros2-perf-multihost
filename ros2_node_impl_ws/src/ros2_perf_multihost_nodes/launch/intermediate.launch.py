from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("node_name", default_value="relay1"),
            DeclareLaunchArgument("eval_time", default_value="60"),
            DeclareLaunchArgument("topic_names_pub", default_value="topic_out"),
            DeclareLaunchArgument("topic_names_sub", default_value="topic_in"),
            DeclareLaunchArgument("size", default_value="64"),
            DeclareLaunchArgument("period", default_value="100"),
            DeclareLaunchArgument("qos_history", default_value="KEEP_LAST"),
            DeclareLaunchArgument("qos_depth", default_value="1"),
            DeclareLaunchArgument("qos_reliability", default_value="RELIABLE"),
            Node(
                package="ros2_perf_multihost_nodes",
                executable="intermediate_node",
                output="screen",
                arguments=[
                    "--node-name",
                    LaunchConfiguration("node_name"),
                    "--eval-time",
                    LaunchConfiguration("eval_time"),
                    "--topic-names-pub",
                    LaunchConfiguration("topic_names_pub"),
                    "--topic-names-sub",
                    LaunchConfiguration("topic_names_sub"),
                    "--size",
                    LaunchConfiguration("size"),
                    "--period",
                    LaunchConfiguration("period"),
                    "--qos-history",
                    LaunchConfiguration("qos_history"),
                    "--qos-depth",
                    LaunchConfiguration("qos_depth"),
                    "--qos-reliability",
                    LaunchConfiguration("qos_reliability"),
                ],
            ),
        ]
    )
