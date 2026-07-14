from __future__ import annotations

import json
import shutil
from pathlib import Path


KNOWN_ANALYSIS_FILES = (
    "total_latency.csv",
    "throughput.csv",
    "host_trials_usage.csv",
    "host_usage_summary.csv",
    "qos_sweep_summary.csv",
)


def resolve_result_dir(repo_root: Path, ws_dir: str, topology: str, rmw: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    return (repo_root / ws_dir / topology / "results" / f"latest-{rmw}").resolve()


def analysis_file(folder: Path, filename: str) -> Path:
    candidates = (folder / filename, folder / "analysis" / filename)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"{filename} was not found under {folder} or {folder / 'analysis'}")


def _copy_or_link(src: Path, dst: Path, mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "symlink":
        dst.symlink_to(src)
    else:
        shutil.copy2(src, dst)


def _copy_existing_analysis_files(src_folder: Path, dst_folder: Path, mode: str) -> list[str]:
    copied = []
    for filename in KNOWN_ANALYSIS_FILES:
        try:
            src = analysis_file(src_folder, filename)
        except FileNotFoundError:
            continue
        _copy_or_link(src, dst_folder / filename, mode)
        copied.append(filename)
    return copied


def flatten_result(result_dir: Path, dest_dir: Path, mode: str = "copy", force: bool = False) -> dict:
    result_dir = result_dir.expanduser().resolve()
    dest_dir = dest_dir.expanduser().resolve()
    if not result_dir.exists():
        raise FileNotFoundError(f"result directory does not exist: {result_dir}")
    if mode not in {"copy", "symlink"}:
        raise ValueError("mode must be 'copy' or 'symlink'")
    if dest_dir.exists() and force:
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    root_files = _copy_existing_analysis_files(result_dir, dest_dir, mode)
    case_dirs = list(result_dir.glob("qos_case*"))
    analysis_dir = result_dir / "analysis"
    if analysis_dir.exists():
        case_dirs.extend(analysis_dir.glob("qos_case*"))

    copied_cases: dict[str, list[str]] = {}
    for case_dir in sorted(case_dirs):
        if not case_dir.is_dir():
            continue
        copied = _copy_existing_analysis_files(case_dir, dest_dir / case_dir.name, mode)
        if copied:
            copied_cases[case_dir.name] = copied

    for filename in ("qos_cases.json", "metadata.txt"):
        src = result_dir / filename
        if src.exists():
            _copy_or_link(src, dest_dir / filename, mode)

    info = {
        "source_result_dir": str(result_dir),
        "destination_dir": str(dest_dir),
        "mode": mode,
        "root_files": root_files,
        "qos_cases": copied_cases,
    }
    (dest_dir / "source_info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return info
