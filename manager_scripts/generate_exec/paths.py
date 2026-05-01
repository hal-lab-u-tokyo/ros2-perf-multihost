"""Filesystem/path operations for output generation."""

import os
import shutil
import sys


def clear_directory_contents(path):
    """Delete everything directly under the given directory."""
    for name in os.listdir(path):
        target = os.path.join(path, name)
        if os.path.islink(target) or os.path.isfile(target):
            os.remove(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)


def read_existing_json_path(run_dir):
    """Return the json_path field from metadata.txt in run_dir if it exists."""
    metadata_path = os.path.join(run_dir, "metadata.txt")
    if not os.path.isfile(metadata_path):
        return None
    with open(metadata_path) as f:
        for line in f:
            if line.startswith("json_path:"):
                return os.path.normpath(line.split(":", 1)[1].strip())
    return None


def confirm_overwrite(output_dir, force=False, existing_json_path=None, new_json_path=None):
    """Ask whether an existing exec_scripts directory should be overwritten."""
    if force:
        return True
    if not sys.stdin.isatty():
        raise SystemExit(
            f"Error: '{output_dir}' already exists and stdin is not a TTY. "
            "Use --force (-f) to overwrite without confirmation."
        )
    msg = f"'{output_dir}' already exists."
    if (
        existing_json_path is not None
        and new_json_path is not None
    ):
        existing_normalized = os.path.normpath(existing_json_path)
        new_normalized = os.path.normpath(new_json_path)
        if existing_normalized != new_normalized:
            msg += (
                f"\n  WARNING: The existing scripts were generated from '{existing_normalized}',"
                f"\n           but the current input is '{new_normalized}'."
                f"\n  Same filename, different path -- are you sure you want to overwrite?"
            )
    msg += " Overwrite generated files? [y/N]: "
    while True:
        answer = input(msg).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        print("Please answer yes or no.")


def resolve_output_paths(json_path, ws_dir, force=False):
    """Resolve and prepare output directory paths for a topology."""
    project_root = os.getcwd()
    perf_ws_dir = os.path.join(project_root, ws_dir)
    os.makedirs(perf_ws_dir, exist_ok=True)

    json_basename = os.path.splitext(os.path.basename(json_path))[0]
    topology_dir = json_basename
    run_dir = os.path.join(perf_ws_dir, topology_dir)
    output_dir = os.path.join(run_dir, "exec_scripts")

    overwrite = os.path.isdir(output_dir)
    if overwrite:
        existing_json_path = read_existing_json_path(run_dir)
        if not confirm_overwrite(
            output_dir,
            force=force,
            existing_json_path=existing_json_path,
            new_json_path=json_path,
        ):
            raise SystemExit("Canceled by user. No files were generated.")

    return project_root, output_dir, topology_dir, overwrite
