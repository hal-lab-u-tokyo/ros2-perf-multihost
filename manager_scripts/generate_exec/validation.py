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


def _is_valid_identifier(value):
    """Check if value is a valid ROS-compatible identifier.

    Allows alphanumerics, underscores, and hyphens; no spaces or shell metacharacters.
    """
    import re
    return bool(re.match(r"^[A-Za-z0-9_-]+$", value))


def _is_valid_host_name(value):
    """Check if value is a safe hostname (subset of identifier).

    Allows alphanumerics, underscores, and hyphens; prevents path traversal and shell injection.
    """
    return _is_valid_identifier(value)


def ensure_only_allowed_keys(entry, allowed_keys, context):
    """Reject unknown keys to catch topology JSON typos early."""
    unknown_keys = sorted(set(entry.keys()) - set(allowed_keys))
    if unknown_keys:
        raise ValueError(
            f"{context}: unknown key(s): {', '.join(unknown_keys)}"
        )


def validate_qos_case_schema(qos, context):
    """Validate one QoS case object."""
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


def validate_qos_schema(qos):
    """Validate optional qos object or qos sweep array."""
    context = "root.qos"
    if isinstance(qos, list):
        if not qos:
            raise ValueError(f"{context}: must be a non-empty array")
        for idx, qos_case in enumerate(qos):
            validate_qos_case_schema(qos_case, f"{context}[{idx}]")
        return

    validate_qos_case_schema(qos, context)


def normalize_qos_cases(qos):
    """Return QoS cases with defaults filled, preserving array order."""
    if qos is None:
        qos_values = [{}]
    elif isinstance(qos, list):
        qos_values = qos
    else:
        qos_values = [qos]

    normalized = []
    for qos_case in qos_values:
        history = qos_case.get("history", "KEEP_LAST")
        normalized.append(
            {
                "history": history,
                "depth": int(qos_case.get("depth", 1)),
                "reliability": qos_case.get("reliability", "RELIABLE"),
            }
        )
    return normalized


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
        topic_name_str = require_non_empty_string(
            pub, "topic_name", pub_context)
        if not _is_valid_identifier(topic_name_str):
            raise ValueError(
                f"{pub_context}: 'topic_name' must be a valid ROS identifier (alphanumerics, underscores, hyphens; no spaces or special characters)"
            )
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
        topic_name_str = require_non_empty_string(
            sub, "topic_name", sub_context)
        if not _is_valid_identifier(topic_name_str):
            raise ValueError(
                f"{sub_context}: 'topic_name' must be a valid ROS identifier (alphanumerics, underscores, hyphens; no spaces or special characters)"
            )


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


def _normalize_node_roles(node, node_context):
    """Normalize one node entry to internal role keys.

    Internal keys are: node_name, publisher, subscriber, intermediate.
    """
    if not isinstance(node, dict):
        raise ValueError(f"{node_context}: must be an object")

    ensure_only_allowed_keys(
        node,
        {
            "node_name",
            "publishers",
            "subscribers",
        },
        node_context,
    )

    node_name_str = require_non_empty_string(node, "node_name", node_context)
    if not _is_valid_identifier(node_name_str):
        raise ValueError(
            f"{node_context}: 'node_name' must be a valid ROS identifier (alphanumerics, underscores, hyphens; no spaces or special characters)"
        )

    publisher_entries = node.get("publishers")
    subscriber_entries = node.get("subscribers")

    has_role = publisher_entries is not None or subscriber_entries is not None
    if not has_role:
        raise ValueError(
            f"{node_context}: at least one of publishers/subscribers is required"
        )

    normalized = {"node_name": node_name_str}

    if publisher_entries is not None:
        validate_publisher_entries(
            publisher_entries,
            f"{node_context}.publishers",
        )
        normalized["publisher"] = publisher_entries

    if subscriber_entries is not None:
        validate_subscriber_entries(
            subscriber_entries,
            f"{node_context}.subscribers",
        )
        normalized["subscriber"] = subscriber_entries

    return normalized


def resolve_hosts_with_nodes(json_content):
    """Resolve host->node assignments for the current topology schema.

    Returns a list of host dicts with shape:
      [{"host_name": <name>, "nodes": [<normalized node>, ...]}, ...]
    """
    hosts = json_content.get("hosts")
    if not isinstance(hosts, list):
        return []

    nodes = json_content.get("nodes")
    if not isinstance(nodes, list):
        return []

    node_by_name = {}
    for idx, node in enumerate(nodes):
        node_context = f"root.nodes[{idx}]"
        normalized = _normalize_node_roles(node, node_context)
        node_name = normalized["node_name"]
        if node_name in node_by_name:
            raise ValueError(
                f"{node_context}: duplicate node_name '{node_name}' in root.nodes"
            )
        node_by_name[node_name] = normalized

    resolved_hosts = []
    for host_idx, host in enumerate(hosts):
        host_context = f"root.hosts[{host_idx}]"
        if not isinstance(host, dict):
            raise ValueError(f"{host_context}: must be an object")
        host_name = require_non_empty_string(host, "host_name", host_context)
        node_names = host.get("node_names")
        if not isinstance(node_names, list) or not node_names:
            raise ValueError(
                f"{host_context}.node_names: must be a non-empty array")

        resolved_nodes = []
        for node_name_idx, node_name in enumerate(node_names):
            item_context = f"{host_context}.node_names[{node_name_idx}]"
            if not isinstance(node_name, str) or not node_name.strip():
                raise ValueError(f"{item_context}: must be a non-empty string")
            stripped_name = node_name.strip()
            if not _is_valid_identifier(stripped_name):
                raise ValueError(
                    f"{item_context}: must be a valid ROS identifier (alphanumerics, underscores, hyphens; no spaces or special characters)"
                )
            if stripped_name not in node_by_name:
                raise ValueError(
                    f"{item_context}: unknown node_name '{stripped_name}' (not found in root.nodes)"
                )
            resolved_nodes.append(node_by_name[stripped_name])

        resolved_hosts.append(
            {
                "host_name": host_name,
                "nodes": resolved_nodes,
            }
        )

    return resolved_hosts


def validate_topology_json_schema(json_content):
    """Validate topology JSON against topology_example/README.md."""
    root_context = "root"
    if not isinstance(json_content, dict):
        raise ValueError("root: must be an object")

    if "hosts" not in json_content:
        raise ValueError("root: 'hosts' is required")
    if "nodes" not in json_content:
        raise ValueError("root: 'nodes' is required")

    ensure_only_allowed_keys(
        json_content, {"qos", "hosts", "nodes"}, root_context)

    if "qos" in json_content:
        validate_qos_schema(json_content["qos"])

    hosts = json_content.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        raise ValueError("root.hosts: must be a non-empty array")

    nodes = json_content.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("root.nodes: must be a non-empty array")

    for host_idx, host in enumerate(hosts):
        host_context = f"root.hosts[{host_idx}]"
        if not isinstance(host, dict):
            raise ValueError(f"{host_context}: must be an object")
        ensure_only_allowed_keys(
            host, {"host_name", "node_names"}, host_context)
        host_name_str = require_non_empty_string(
            host, "host_name", host_context)
        if not _is_valid_host_name(host_name_str):
            raise ValueError(
                f"{host_context}: 'host_name' must contain only alphanumerics, underscores, and hyphens (no spaces, slashes, or special characters)"
            )
        if "node_names" not in host:
            raise ValueError(f"{host_context}: 'node_names' is required")

    # resolve_hosts_with_nodes validates nodes[] and host node references.
    resolve_hosts_with_nodes(json_content)


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
