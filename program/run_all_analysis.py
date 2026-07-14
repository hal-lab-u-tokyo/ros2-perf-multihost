from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_script(script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / script), *args]
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def extract_trimmed_metrics() -> None:
    for trim in ("1", "2", "3"):
        run_script("extract_trimmed_metrics_from_raw.py", trim)


def build_trim2s_reports() -> None:
    run_script("build_trim2s_reports.py", "--all")


def build_jitter_reports() -> None:
    run_script("build_jitter_trim_comparison_figures.py")
    run_script("build_jitter_trim_comparison_pdf.py")


def build_fastdds_qos_report() -> None:
    run_script("build_fastdds_docker_qos_sweep_figures.py")
    run_script("build_fastdds_docker_qos_sweep_pdf.py")


def build_zenoh_native2_figures() -> None:
    run_script("build_zenoh_native2_figures.py")


def build_ros_graph() -> None:
    run_script("build_ros_graph_pdf.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ROS 2 RMW analysis scripts.")
    parser.add_argument("--all", action="store_true", help="Run the standard full pipeline.")
    parser.add_argument("--extract", action="store_true", help="Extract trimmed metrics from raw-data zip files.")
    parser.add_argument("--trim2s", action="store_true", help="Build the first-2-seconds-excluded reports.")
    parser.add_argument("--jitter", action="store_true", help="Build the jitter trim comparison report.")
    parser.add_argument("--fastdds-qos", action="store_true", help="Build the FastDDS docker QoS sweep report.")
    parser.add_argument("--zenoh-native2", action="store_true", help="Build Zenoh native2 figures.")
    parser.add_argument("--ros-graph", action="store_true", help="Build the ROS graph PDF.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_all = args.all or not any(
        (
            args.extract,
            args.trim2s,
            args.jitter,
            args.fastdds_qos,
            args.zenoh_native2,
            args.ros_graph,
        )
    )

    if run_all or args.extract:
        extract_trimmed_metrics()
    if run_all or args.trim2s:
        build_trim2s_reports()
    if run_all or args.jitter:
        build_jitter_reports()
    if args.fastdds_qos:
        build_fastdds_qos_report()
    if args.zenoh_native2:
        build_zenoh_native2_figures()
    if args.ros_graph:
        build_ros_graph()


if __name__ == "__main__":
    main()
