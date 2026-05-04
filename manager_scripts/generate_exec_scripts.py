"""Generate topology-specific execution scripts and compose files."""

import argparse
import json
import os
import shutil

from generate_exec.metadata import generate_metadata_file
from generate_exec.paths import (
    clear_directory_contents,
    resolve_output_paths,
)
from generate_exec.script_generation import (
    GenerationSettings,
    generate_compose,
    generate_compose_per_host,
    generate_exec_scripts,
    generate_host_exec_native_scripts,
    generate_host_exec_scripts,
    generate_local_run_script,
)
from generate_exec.validation import normalize_ws_dir, validate_topology_json_schema


PROJECT_ROOT_IN_CONTAINER = "/workdir/ros2-perf-multihost"
ROS_WS_IN_CONTAINER = f"{PROJECT_ROOT_IN_CONTAINER}/ros2_node_impl_ws"
ZENOH_CONFIG_DIR_IN_CONTAINER = f"{ROS_WS_IN_CONTAINER}/zenoh_config"
IMAGE_NAME = "ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest"
DEFAULT_PERF_WS_DIR = "performance_ws"
DEFAULT_EVAL_TIME = 60


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Docker execution scripts and compose files from a JSON topology",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=(
            "%(prog)s <topology.json> [--ws-dir|-w <dir>] [--force|-f] "
            "[--help|-h]"
        ),
        epilog="""
Examples:
    python3 manager_scripts/generate_exec_scripts.py topology_example/simple.json --ws-dir performance_ws
    short: python3 manager_scripts/generate_exec_scripts.py topology_example/simple.json -w performance_ws
""",
    )
    parser.add_argument("json_path", help="Path to the input JSON file")
    parser.add_argument(
        "-w",
        "--ws-dir",
        type=normalize_ws_dir,
        default=DEFAULT_PERF_WS_DIR,
        help=f"Base directory for generated artifacts (default: {DEFAULT_PERF_WS_DIR})",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output directory without confirmation",
    )
    args = parser.parse_args()

    settings = GenerationSettings(
        project_root_in_container=PROJECT_ROOT_IN_CONTAINER,
        ros_ws_in_container=ROS_WS_IN_CONTAINER,
        zenoh_config_dir_in_container=ZENOH_CONFIG_DIR_IN_CONTAINER,
        image_name=IMAGE_NAME,
        perf_ws_dir=args.ws_dir,
        default_eval_time=DEFAULT_EVAL_TIME,
    )

    project_root, output_dir, topology_dir, overwrite = resolve_output_paths(
        args.json_path, args.ws_dir, force=args.force
    )

    with open(args.json_path, "r") as f:
        json_content = json.load(f)

    validate_topology_json_schema(json_content)

    # Generate into a temporary directory first, then swap it in after success.
    tmp_dir = output_dir + ".tmp"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)

    try:
        generate_exec_scripts(json_content, tmp_dir, settings)
        generate_compose(json_content, tmp_dir, project_root, settings)
        generate_compose_per_host(
            json_content, tmp_dir, project_root, settings)
        generate_host_exec_scripts(
            json_content, tmp_dir, project_root, settings)
        generate_host_exec_native_scripts(
            json_content, tmp_dir, project_root, settings)
        generate_local_run_script(
            json_content, tmp_dir, project_root, settings)

        # Generation succeeded; replace the existing directory atomically.
        if overwrite:
            clear_directory_contents(output_dir)
            shutil.rmtree(output_dir)
        os.rename(tmp_dir, output_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    generate_metadata_file(
        json_content,
        args.json_path,
        args.ws_dir,
        project_root,
        topology_dir,
    )

    print(
        f"Generated host*.launch.py, host*_exec_docker.sh, host*_exec_native.sh, host*_compose.yaml, local_exec.sh, local_compose.yaml "
        f"in {settings.perf_ws_dir}/{topology_dir}/exec_scripts "
        f"for {len(json_content['hosts'])} host(s)"
    )
