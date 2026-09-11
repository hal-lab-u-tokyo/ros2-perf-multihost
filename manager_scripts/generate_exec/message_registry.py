"""Derive supported benchmark message metadata from ROS interface files."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re


PRIMITIVE_BYTE_SIZES = {
    "bool": 1,
    "byte": 1,
    "char": 1,
    "float32": 4,
    "float64": 8,
    "int8": 1,
    "uint8": 1,
    "int16": 2,
    "uint16": 2,
    "int32": 4,
    "uint32": 4,
    "int64": 8,
    "uint64": 8,
}


@dataclass(frozen=True)
class MessageSpec:
    topology_name: str
    ros_name: str
    header_name: str
    variable_size: bool
    fixed_payload_size: int


def _to_snake_case(value):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _msg_directory():
    return Path(__file__).resolve().parents[2] / "ros2_node_impl_ws" / "src" / "ros2_perf_multihost_nodes" / "msg"


def load_message_specs(msg_directory=None):
    """Load supported typed benchmark messages from their .msg definitions."""
    directory = Path(msg_directory) if msg_directory else _msg_directory()
    specs = []
    for msg_path in sorted(directory.glob("Stamped*.msg")):
        fields = [line.split() for line in msg_path.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
        if len(fields) != 2 or fields[0] != ["PerformanceHeader", "header"]:
            raise ValueError(f"{msg_path}: expected 'PerformanceHeader header'")
        data_fields = [field for field in fields[1:] if field[1] == "data"]
        if len(data_fields) != 1 or len(fields) != 2:
            raise ValueError(f"{msg_path}: expected exactly one data field")

        data_type = data_fields[0][0]
        match = re.fullmatch(r"([a-zA-Z0-9_]+)(?:\[(\d*)\])?", data_type)
        if match is None or match.group(1) not in PRIMITIVE_BYTE_SIZES:
            raise ValueError(f"{msg_path}: data must use a primitive type")
        element_type, array_size = match.groups()
        if array_size == "":
            variable_size = True
            fixed_payload_size = 0
        elif array_size is None:
            variable_size = False
            fixed_payload_size = PRIMITIVE_BYTE_SIZES[element_type]
        else:
            variable_size = False
            fixed_payload_size = PRIMITIVE_BYTE_SIZES[element_type] * int(array_size)

        ros_name = msg_path.stem
        specs.append(MessageSpec(
            topology_name=_to_snake_case(ros_name),
            ros_name=ros_name,
            header_name=_to_snake_case(ros_name),
            variable_size=variable_size,
            fixed_payload_size=fixed_payload_size,
        ))
    if not specs:
        raise ValueError(f"No supported Stamped*.msg files found in {directory}")
    return tuple(specs)


def get_message_spec(msg_type):
    for spec in load_message_specs():
        if spec.topology_name == msg_type:
            return spec
    raise KeyError(msg_type)


def generate_cpp_header(msg_directory, output_path):
    """Generate C++ dispatch metadata consumed by benchmark_node.cpp."""
    specs = load_message_specs(msg_directory)
    output = Path(output_path)
    lines = [
        "#ifndef ROS2_PERF_MULTIHOST_NODES__GENERATED_MESSAGE_REGISTRY_HPP_",
        "#define ROS2_PERF_MULTIHOST_NODES__GENERATED_MESSAGE_REGISTRY_HPP_",
        "",
    ]
    lines.extend(
        f'#include "ros2_perf_multihost_nodes/msg/{spec.header_name}.hpp"'
        for spec in specs
    )
    lines.extend([
        "",
        "#define ROS2_PERF_FOR_EACH_MESSAGE_TYPE(X) \\",
    ])
    for index, spec in enumerate(specs):
        suffix = " \\" if index < len(specs) - 1 else ""
        variable_size = "true" if spec.variable_size else "false"
        lines.append(
            f"  X({spec.topology_name}, {spec.ros_name}, {variable_size}, "
            f"{spec.fixed_payload_size}){suffix}"
        )
    lines.extend([
        "",
        "#endif",
        "",
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--msg-dir", required=True)
    parser.add_argument("--cpp-output", required=True)
    arguments = parser.parse_args()
    generate_cpp_header(arguments.msg_dir, arguments.cpp_output)