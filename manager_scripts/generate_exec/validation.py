"""Validation helpers for topology JSON input."""

import argparse
import os


def require_positive_int(entry, key, context):
    """Read a required positive integer field from entry."""
    if key not in entry:
        raise ValueError(f"{context}: '{key}' is required")
    try:
        value = int(entry[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{context}: '{key}' must be an integer"
        ) from exc
    if value <= 0:
        raise ValueError(f"{context}: '{key}' must be > 0")
    return value


def require_non_empty_string(entry, key, context):
    """Read a required non-empty string field from entry."""
    if key not in entry:
        raise ValueError(f"{context}: '{key}' is required")
    value = entry[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: '{key}' must be a non-empty string")
    return value


def ensure_only_allowed_keys(entry, allowed_keys, context):
    """Reject unknown keys to catch topology JSON typos early."""
    unknown_keys = sorted(set(entry.keys()) - set(allowed_keys))
    if unknown_keys:
        raise ValueError(
            f"{context}: unknown key(s): {', '.join(unknown_keys)}"
        )


def validate_qos_schema(qos):
    """Validate optional qos object."""
    context = "root.qos"
    if not isinstance(qos, dict):
        raise ValueError(f"{context}: must be an object")

    ensure_only_allowed_keys(qos, {"history", "depth", "reliability"}, context)

    if "history" in qos:
        history = qos["history"]
        if history not in ("KEEP_LAST", "KEEP_ALL"):
            raise ValueError(
                f"{context}: 'history' must be one of KEEP_LAST, KEEP_ALL"
            )
    if "depth" in qos:
        try:
            depth = int(qos["depth"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context}: 'depth' must be an integer") from exc
        if depth <= 0:
            raise ValueError(f"{context}: 'depth' must be > 0")
    if "reliability" in qos:
        reliability = qos["reliability"]
        if reliability not in ("RELIABLE", "BEST_EFFORT"):
            raise ValueError(
                f"{context}: 'reliability' must be one of RELIABLE, BEST_EFFORT"
            )


def validate_publisher_entries(pub_entries, context):
    """Validate publisher[] or intermediate[].publisher[] entries."""
    if not isinstance(pub_entries, list) or not pub_entries:
        raise ValueError(f"{context}: must be a non-empty array")

    for pub_idx, pub in enumerate(pub_entries):
        pub_context = f"{context}[{pub_idx}]"
        if not isinstance(pub, dict):
            raise ValueError(f"{pub_context}: must be an object")
        ensure_only_allowed_keys(
            pub,
            {"topic_name", "payload_size", "period_ms"},
            pub_context,
        )
        require_non_empty_string(pub, "topic_name", pub_context)
        require_positive_int(pub, "payload_size", pub_context)
        require_positive_int(pub, "period_ms", pub_context)


def validate_subscriber_entries(sub_entries, context):
    """Validate subscriber[] or intermediate[].subscriber[] entries."""
    if not isinstance(sub_entries, list) or not sub_entries:
        raise ValueError(f"{context}: must be a non-empty array")

    for sub_idx, sub in enumerate(sub_entries):
        sub_context = f"{context}[{sub_idx}]"
        if not isinstance(sub, dict):
            raise ValueError(f"{sub_context}: must be an object")
        ensure_only_allowed_keys(sub, {"topic_name"}, sub_context)
        require_non_empty_string(sub, "topic_name", sub_context)


def normalize_intermediate_entries(intermediate_value, node_name):
    """Validate and return intermediate entries as an array."""
    if not isinstance(intermediate_value, list):
        raise ValueError(
            f"node '{node_name}': intermediate must be an array"
        )
    if not intermediate_value:
        raise ValueError(
            f"node '{node_name}': intermediate cannot be empty"
        )

    for idx, entry in enumerate(intermediate_value):
        if not isinstance(entry, dict):
            raise ValueError(
                f"node '{node_name}': intermediate[{idx}] must be an object"
            )
        if "publisher" not in entry or "subscriber" not in entry:
            raise ValueError(
                f"node '{node_name}': intermediate[{idx}] must include both publisher and subscriber"
            )

    return intermediate_value


def validate_topology_json_schema(json_content):
    """Validate topology JSON against topology_example/README.md."""
    root_context = "root"
    if not isinstance(json_content, dict):
        raise ValueError("root: must be an object")

    if "hosts" not in json_content:
        raise ValueError("root: 'hosts' is required")

    ensure_only_allowed_keys(json_content, {"qos", "hosts"}, root_context)

    if "qos" in json_content:
        validate_qos_schema(json_content["qos"])

    hosts = json_content.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        raise ValueError("root.hosts: must be a non-empty array")

    for host_idx, host in enumerate(hosts):
        host_context = f"root.hosts[{host_idx}]"
        if not isinstance(host, dict):
            raise ValueError(f"{host_context}: must be an object")
        ensure_only_allowed_keys(host, {"host_name", "nodes"}, host_context)
        require_non_empty_string(host, "host_name", host_context)

        if "nodes" not in host:
            raise ValueError(f"{host_context}: 'nodes' is required")
        nodes = host["nodes"]
        if not isinstance(nodes, list) or not nodes:
            raise ValueError(
                f"{host_context}.nodes: must be a non-empty array")

        for node_idx, node in enumerate(nodes):
            node_context = f"{host_context}.nodes[{node_idx}]"
            if not isinstance(node, dict):
                raise ValueError(f"{node_context}: must be an object")

            ensure_only_allowed_keys(
                node,
                {"node_name", "publisher", "subscriber", "intermediate"},
                node_context,
            )
            require_non_empty_string(node, "node_name", node_context)

            has_role = any(
                role in node for role in ("publisher", "subscriber", "intermediate")
            )
            if not has_role:
                raise ValueError(
                    f"{node_context}: at least one of publisher/subscriber/intermediate is required"
                )

            if "publisher" in node:
                validate_publisher_entries(
                    node["publisher"], f"{node_context}.publisher"
                )

            if "subscriber" in node:
                validate_subscriber_entries(
                    node["subscriber"], f"{node_context}.subscriber"
                )

            if "intermediate" in node:
                intermediate = node["intermediate"]
                if not isinstance(intermediate, list) or not intermediate:
                    raise ValueError(
                        f"{node_context}.intermediate: must be a non-empty array"
                    )
                for inter_idx, inter in enumerate(intermediate):
                    inter_context = f"{node_context}.intermediate[{inter_idx}]"
                    if not isinstance(inter, dict):
                        raise ValueError(f"{inter_context}: must be an object")
                    ensure_only_allowed_keys(
                        inter,
                        {"publisher", "subscriber"},
                        inter_context,
                    )
                    if "publisher" not in inter or "subscriber" not in inter:
                        raise ValueError(
                            f"{inter_context}: both 'publisher' and 'subscriber' are required"
                        )
                    validate_publisher_entries(
                        inter["publisher"], f"{inter_context}.publisher"
                    )
                    validate_subscriber_entries(
                        inter["subscriber"], f"{inter_context}.subscriber"
                    )


def normalize_ws_dir(ws_dir):
    """Normalize and validate the value passed to --ws-dir."""
    normalized = os.path.normpath(ws_dir.strip())
    if not normalized or normalized == ".":
        raise argparse.ArgumentTypeError("--ws-dir cannot be empty or '.'.")
    if os.path.isabs(normalized):
        raise argparse.ArgumentTypeError("--ws-dir must be a relative path.")
    if normalized == ".." or normalized.startswith(".." + os.sep):
        raise argparse.ArgumentTypeError(
            "--ws-dir cannot point outside the project directory.")
    return normalized
