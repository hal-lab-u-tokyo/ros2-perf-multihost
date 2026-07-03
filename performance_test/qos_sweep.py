import json
import os


def get_metadata_value(key, metadata_path):
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}:"):
                    return line[len(key) + 1:].strip()
    except (FileNotFoundError, IOError):
        pass
    return None


def load_qos_cases(ws_dir, topology_name):
    metadata_path = os.path.join(ws_dir, topology_name, "metadata.txt")
    qos_json = get_metadata_value("qos_json", metadata_path)
    if qos_json:
        loaded = json.loads(qos_json)
        if not isinstance(loaded, list) or not loaded:
            raise ValueError(f"qos_json must be a non-empty array in {metadata_path}")
        return [_normalize_qos_case(qos, idx) for idx, qos in enumerate(loaded)]

    qos = {
        "history": get_metadata_value("qos_history", metadata_path) or "KEEP_LAST",
        "depth": get_metadata_value("qos_depth", metadata_path) or 1,
        "reliability": get_metadata_value("qos_reliability", metadata_path) or "RELIABLE",
    }
    return [_normalize_qos_case(qos, 0)]


def _normalize_qos_case(qos, idx):
    if not isinstance(qos, dict):
        raise ValueError(f"qos case {idx} must be an object")

    history = qos.get("history", "KEEP_LAST")
    if history not in ("KEEP_LAST", "KEEP_ALL"):
        raise ValueError(f"qos case {idx}: history must be KEEP_LAST or KEEP_ALL")

    try:
        depth = int(qos.get("depth", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"qos case {idx}: depth must be an integer") from exc
    if depth <= 0:
        raise ValueError(f"qos case {idx}: depth must be > 0")

    reliability = qos.get("reliability", "RELIABLE")
    if reliability not in ("RELIABLE", "BEST_EFFORT"):
        raise ValueError(
            f"qos case {idx}: reliability must be RELIABLE or BEST_EFFORT"
        )

    return {
        "history": history,
        "depth": depth,
        "reliability": reliability,
    }


def qos_case_label(qos_case_idx):
    return f"qos_case{qos_case_idx}"
