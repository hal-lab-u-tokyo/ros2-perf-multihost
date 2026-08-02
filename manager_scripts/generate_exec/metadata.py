"""Metadata generation for created execution script sets."""

import json
import os
import shlex
import sys
from datetime import datetime

from .validation import (
    normalize_qos_cases,
    require_positive_int,
    resolve_hosts_with_nodes,
)


def collect_metadata_node_names(json_content):
    """Collect host names, node names, and topic counts for metadata.txt."""
    host_names = []
    publisher_names = []
    subscriber_names = []
    intermediate_names = []
    topic_names = set()

    for host_dict in resolve_hosts_with_nodes(json_content):
        host_names.append(host_dict["host_name"])
        for node in host_dict["nodes"]:
            node_name = node["node_name"]
            pub_entries = node.get("publisher")
            sub_entries = node.get("subscriber")

            if pub_entries and sub_entries:
                intermediate_names.append(node_name)
            elif pub_entries:
                publisher_names.append(node_name)
            elif sub_entries:
                subscriber_names.append(node_name)

            if pub_entries:
                for publisher in pub_entries:
                    topic_names.add(publisher["topic_name"])
            if sub_entries:
                for subscriber in sub_entries:
                    topic_names.add(subscriber["topic_name"])

    return host_names, publisher_names, subscriber_names, intermediate_names, topic_names


def collect_topic_runtime_config(json_content):
    """Collect topic -> payload/period/publisher_count from topology."""
    topic_cfg = {}

    def add_publisher_topic(entry, context):
        topic = entry.get("topic_name")
        if not topic:
            raise ValueError(f"{context}: missing topic_name")
        payload_size = require_positive_int(entry, "payload_size", context)
        period_ms = require_positive_int(entry, "period_ms", context)

        cfg = topic_cfg.setdefault(
            topic,
            {
                "payload_size": payload_size,
                "period_ms": period_ms,
                "publisher_count": 0,
            },
        )
        if cfg["payload_size"] != payload_size or cfg["period_ms"] != period_ms:
            raise ValueError(
                f"Inconsistent payload/period for topic '{topic}' in topology JSON"
            )
        cfg["publisher_count"] += 1

    for host in resolve_hosts_with_nodes(json_content):
        for node in host["nodes"]:
            node_name = node.get("node_name", "?")
            for pub_idx, publisher in enumerate(node.get("publisher", []) or []):
                add_publisher_topic(
                    publisher, f"node '{node_name}' publisher[{pub_idx}]"
                )

    return topic_cfg


def unique_in_order(items):
    """Remove duplicates while preserving the original order."""
    return list(dict.fromkeys(items))


def generate_metadata_file(
    json_content, json_path, ws_dir, project_root, topology_dir
):
    """Generate <ws-dir>/<topology>/metadata.txt."""
    topology_root = os.path.join(project_root, ws_dir, topology_dir)
    metadata_path = os.path.join(topology_root, "metadata.txt")

    (
        host_names,
        publisher_names,
        subscriber_names,
        intermediate_names,
        topic_names,
    ) = collect_metadata_node_names(json_content)
    host_names = unique_in_order(host_names)
    publisher_names = unique_in_order(publisher_names)
    subscriber_names = unique_in_order(subscriber_names)
    intermediate_names = unique_in_order(intermediate_names)
    topic_runtime_cfg = collect_topic_runtime_config(json_content)

    all_nodes = [
        node
        for host in resolve_hosts_with_nodes(json_content)
        for node in host["nodes"]
    ]
    node_count = len(all_nodes)

    qos_cases = normalize_qos_cases(json_content.get("qos"))
    default_qos = qos_cases[0]
    qos_mode = "sweep" if isinstance(
        json_content.get("qos"), list) else "single"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sections = [
        [
            "# --- 1. general info ---",
            f"command: {shlex.join(sys.argv)}",
            f"timestamp: {timestamp}",
            f"json: {os.path.basename(json_path)}",
            f"json_path: {json_path}",
            f"ws_dir: {ws_dir}",
            f"topology_dir: {topology_dir}",
        ],
        [
            "# --- 2. test config ---",
            f"qos_mode: {qos_mode}",
            f"qos_case_count: {len(qos_cases)}",
            (
                "qos_json: "
                f"{json.dumps(qos_cases, separators=(',', ':'), sort_keys=True)}"
            ),
            f"qos_history: {default_qos['history']}",
            f"qos_depth: {default_qos['depth']}",
            f"qos_reliability: {default_qos['reliability']}",
        ],
        [
            "# --- 3. topology stats ---",
            f"host_count: {len(host_names)}",
            f"node_count: {node_count}",
            f"publisher_count: {len(publisher_names)}",
            f"subscriber_count: {len(subscriber_names)}",
            f"intermediate_count: {len(intermediate_names)}",
            f"topic_count: {len(topic_names)}",
            f"hosts: {', '.join(host_names)}",
            f"publishers: {', '.join(publisher_names)}",
            f"subscribers: {', '.join(subscriber_names)}",
            f"intermediates: {', '.join(intermediate_names)}",
            f"topics: {', '.join(sorted(topic_names))}",
            (
                "topic_runtime_json: "
                f"{json.dumps(topic_runtime_cfg, separators=(',', ':'), sort_keys=True)}"
            ),
        ],
    ]

    with open(metadata_path, "w") as f:
        f.write("\n\n".join("\n".join(section) for section in sections) + "\n")
