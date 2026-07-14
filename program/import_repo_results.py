from __future__ import annotations

import argparse
from pathlib import Path

from analysis_config import (
    FASTDDS_DOCKER_QOS_BASE,
    PAYLOADSIZE_BASE,
    QOS_VARIANT_BASE,
    REPO_ROOT,
    RMW_COMPARISON_BASE,
    ZENOH_NATIVE2_BASE,
    ZENOH_QOS_BASE,
)
from repo_results import flatten_result, resolve_result_dir


def normalize_exec_policy(value: str) -> str:
    return "native" if value.lower() == "native" else "docker"


def rmw_folder_name(rmw: str) -> str:
    return "Zenoh" if rmw == "zenoh" else rmw


def default_destination(args: argparse.Namespace) -> Path:
    exec_policy = normalize_exec_policy(args.exec_policy)
    if args.kind == "qos-rmw":
        return QOS_VARIANT_BASE / f"{args.rmw}-{exec_policy}"
    if args.kind == "zenoh-qos":
        return ZENOH_QOS_BASE / exec_policy
    if args.kind == "rmw-constant":
        env_name = "Native" if exec_policy == "native" else "docker"
        return RMW_COMPARISON_BASE / rmw_folder_name(args.rmw) / env_name
    if args.kind == "payload":
        if not args.payload:
            raise SystemExit("payload import requires --payload, for example --payload payload1K")
        return PAYLOADSIZE_BASE / f"{args.rmw}-{exec_policy}" / args.payload
    if args.kind == "fastdds-docker-qos":
        return FASTDDS_DOCKER_QOS_BASE
    if args.kind == "zenoh-native2":
        return ZENOH_NATIVE2_BASE
    raise SystemExit(f"unknown import kind: {args.kind}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import current repository results into program/data for manual analysis commands.",
    )
    parser.add_argument(
        "kind",
        choices=("qos-rmw", "zenoh-qos", "rmw-constant", "payload", "fastdds-docker-qos", "zenoh-native2"),
        help="analysis dataset layout to populate",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="repository root containing ROS 2 workspace directories")
    parser.add_argument("--ws-dir", default="performance_ws", help="workspace directory under the repository root")
    parser.add_argument("--topology", help="topology directory name under --ws-dir")
    parser.add_argument("--rmw", choices=("fastdds", "cyclonedds", "zenoh"), default="fastdds", help="RMW result label")
    parser.add_argument("--exec-policy", choices=("docker", "native"), default="docker", help="execution environment label")
    parser.add_argument("--payload", help="payload case label used with the payload import kind, for example payload1K")
    parser.add_argument("--result-dir", type=Path, help="explicit result directory, such as results/latest-fastdds")
    parser.add_argument("--dest", type=Path, help="explicit destination directory under program/data")
    parser.add_argument("--mode", choices=("copy", "symlink"), default="copy", help="copy files or create symlinks")
    parser.add_argument("--force", action="store_true", help="replace the destination directory before importing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.expanduser().resolve()
    if args.result_dir is None and not args.topology:
        raise SystemExit("--topology is required when --result-dir is not specified")

    result_dir = resolve_result_dir(repo_root, args.ws_dir, args.topology or "", args.rmw, args.result_dir)
    dest_dir = args.dest.expanduser().resolve() if args.dest else default_destination(args)
    info = flatten_result(result_dir, dest_dir, mode=args.mode, force=args.force)

    print(f"Imported: {info['source_result_dir']}")
    print(f"Destination: {info['destination_dir']}")
    print(f"Root CSV files: {', '.join(info['root_files']) or '(none)'}")
    print(f"QoS cases: {len(info['qos_cases'])}")


if __name__ == "__main__":
    main()
