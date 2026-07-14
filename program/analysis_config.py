from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


DATA_ROOT = _path_from_env("ROS2_ANALYSIS_DATA_ROOT", ROOT / "data")
OUTPUT_ROOT = _path_from_env("ROS2_ANALYSIS_OUTPUT_ROOT", ROOT / "outputs")
PDF_ROOT = _path_from_env("ROS2_ANALYSIS_PDF_ROOT", ROOT / "output" / "pdf")

RAW_DATA_DIR = _path_from_env("ROS2_ANALYSIS_RAW_DATA_DIR", DATA_ROOT / "raw-data")
RMW_COMPARISON_BASE = _path_from_env("ROS2_ANALYSIS_RMW_BASE", DATA_ROOT / "qos_constant")
QOS_VARIANT_BASE = _path_from_env("ROS2_ANALYSIS_QOS_BASE", DATA_ROOT / "qos_variant")
ZENOH_QOS_BASE = _path_from_env("ROS2_ANALYSIS_ZENOH_QOS_BASE", DATA_ROOT / "zenoh")
PAYLOADSIZE_BASE = _path_from_env("ROS2_ANALYSIS_PAYLOAD_BASE", DATA_ROOT / "payloadsize_variant")
FASTDDS_DOCKER_QOS_BASE = _path_from_env("ROS2_ANALYSIS_FASTDDS_DOCKER_QOS_BASE", DATA_ROOT / "fastdds-docker")
ZENOH_NATIVE2_BASE = _path_from_env("ROS2_ANALYSIS_ZENOH_NATIVE2_BASE", DATA_ROOT / "native2")


def output_path(*parts: str) -> Path:
    return OUTPUT_ROOT.joinpath(*parts)


def pdf_path(filename: str) -> Path:
    return PDF_ROOT / filename
