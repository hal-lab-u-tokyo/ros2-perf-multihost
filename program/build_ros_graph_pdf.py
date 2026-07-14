from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas


INPUT_JSON = Path("/Users/kudoutakumi/ros2-perf-multihost/topology_example/five_hosts.json")
OUTPUT_DIR = Path("output/pdf")
OUTPUT_PDF = OUTPUT_DIR / "five_hosts_ros_graph.pdf"
OUTPUT_DOT = OUTPUT_DIR / "five_hosts_ros_graph.dot"


NODE_FILL = colors.HexColor("#94cdb5")
NODE_STROKE = colors.HexColor("#5a8d78")
TOPIC_FILL = colors.HexColor("#c9b1df")
TOPIC_STROKE = colors.HexColor("#8d72a7")
HOST_STROKE = colors.HexColor("#ff6b6b")
HOST_FILL = colors.white
HOST_LABEL_FILL = colors.HexColor("#dcecff")
HOST_LABEL_STROKE = colors.HexColor("#8ca8c7")
EDGE = colors.HexColor("#3f638e")
TEXT = colors.HexColor("#111111")


def topics_from(entries: list[dict] | None) -> list[str]:
    if not entries:
        return []
    return [entry["topic_name"] for entry in entries]


def collect(data: dict) -> tuple[list[dict], dict[str, dict], dict[str, list[str]], list[tuple[str, str]]]:
    hosts = data["hosts"]
    nodes: dict[str, dict] = {}
    topic_subscribers: dict[str, list[str]] = defaultdict(list)
    edges: list[tuple[str, str]] = []

    for host in hosts:
        for node in host["nodes"]:
            name = node["node_name"]
            pubs = topics_from(node.get("publisher"))
            subs = topics_from(node.get("subscriber"))
            for rule in node.get("intermediate", []):
                subs.extend(topics_from(rule.get("subscriber")))
                pubs.extend(topics_from(rule.get("publisher")))

            nodes[name] = {
                "host": host["host_name"],
                "publishes": sorted(set(pubs)),
                "subscribes": sorted(set(subs)),
            }
            for topic in pubs:
                edges.append((f"node:{name}", f"topic:{topic}"))
            for topic in subs:
                topic_subscribers[topic].append(name)

    for topic, subscribers in topic_subscribers.items():
        for node in subscribers:
            edges.append((f"topic:{topic}", f"node:{node}"))

    return hosts, nodes, topic_subscribers, edges


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def node_id(kind: str, value: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in value)
    return f"{kind}_{safe}"


def write_dot(hosts: list[dict], nodes: dict[str, dict], edges: list[tuple[str, str]]) -> None:
    lines = [
        "digraph ros_graph {",
        "  graph [rankdir=TB, label=\"ROS 2\", labelloc=b];",
        "  node [fontname=Helvetica, fontsize=9];",
        "  edge [fontname=Helvetica, fontsize=8];",
    ]
    emitted_topics: set[str] = set()
    for host in hosts:
        host_name = host["host_name"]
        lines.append(f"  subgraph cluster_{host_name} {{")
        lines.append('    graph [color="#ff6b6b", penwidth=1.5, label=""];')
        lines.append(
            f"    {node_id('host_label', host_name)} [label={quote(host_name)}, shape=box, style=filled, fillcolor=\"#dcecff\", color=\"#8ca8c7\"];"
        )
        for node in host["nodes"]:
            name = node["node_name"]
            lines.append(
                f"    {node_id('node', name)} [label={quote(name)}, shape=ellipse, style=filled, fillcolor=\"#94cdb5\", color=\"#5a8d78\"];"
            )
            for topic in nodes[name]["publishes"]:
                emitted_topics.add(topic)
                lines.append(
                    f"    {node_id('topic', topic)} [label={quote(topic)}, shape=box, style=filled, fillcolor=\"#c9b1df\", color=\"#8d72a7\"];"
                )
        lines.append("  }")
    for source, target in edges:
        source_kind, source_name = source.split(":", 1)
        target_kind, target_name = target.split(":", 1)
        lines.append(f"  {node_id(source_kind, source_name)} -> {node_id(target_kind, target_name)};")
    lines.append("}")
    OUTPUT_DOT.write_text("\n".join(lines) + "\n")


def host_layout(page_w: float, page_h: float) -> dict[str, tuple[float, float, float, float]]:
    return {
        "pi0": (42, page_h - 325, 318, 285),
        "pi1": (410, page_h - 370, 282, 245),
        "pi2": (785, page_h - 520, 330, 360),
        "pi3": (395, 115, 285, 280),
        "pi4": (820, 58, 285, 235),
    }


def fallback_host_layout(hosts: list[dict], page_w: float, page_h: float) -> dict[str, tuple[float, float, float, float]]:
    cols = 3
    width = 300
    height = 245
    gap_x = 60
    gap_y = 38
    start_x = 45
    start_y = page_h - height - 45
    layout = {}
    for index, host in enumerate(hosts):
        col = index % cols
        row = index // cols
        layout[host["host_name"]] = (start_x + col * (width + gap_x), start_y - row * (height + gap_y), width, height)
    return layout


def assign_positions(hosts: list[dict], nodes: dict[str, dict], page_w: float, page_h: float) -> tuple[dict[str, tuple], dict[str, tuple]]:
    fixed = host_layout(page_w, page_h)
    if any(host["host_name"] not in fixed for host in hosts):
        fixed = fallback_host_layout(hosts, page_w, page_h)

    shapes: dict[str, tuple] = {}
    host_boxes: dict[str, tuple] = {}
    for host in hosts:
        host_name = host["host_name"]
        x, y, w, h = fixed[host_name]
        host_boxes[host_name] = (x, y, w, h)
        shapes[f"host:{host_name}"] = ("rect", x + w / 2, y + h - 25, 34, 18)

        node_entries = host["nodes"]
        usable_top = y + h - 82
        usable_bottom = y + 54
        step = 0 if len(node_entries) == 1 else (usable_top - usable_bottom) / (len(node_entries) - 1)
        for node_index, node in enumerate(node_entries):
            name = node["node_name"]
            node_y = usable_top - node_index * step
            node_x = x + w * 0.27
            shapes[f"node:{name}"] = ("ellipse", node_x, node_y, 92, 42)

            topics = nodes[name]["publishes"]
            for topic_index, topic in enumerate(topics):
                if len(topics) >= 3:
                    topic_x = x + w * 0.70
                    topic_y = node_y + (len(topics) - 1) * 14 - topic_index * 28
                else:
                    col = topic_index % 2
                    row = topic_index // 2
                    topic_x = x + w * (0.58 + 0.25 * col)
                    topic_y = node_y - 28 * row
                shapes[f"topic:{topic}"] = ("rect", topic_x, topic_y, 76, 22)
    return shapes, host_boxes


def border_point(shape: tuple, toward: tuple[float, float], port_offset: float = 0) -> tuple[float, float]:
    kind, cx, cy, width, height = shape
    dx = toward[0] - cx
    dy = toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    rx = width / 2
    ry = height / 2

    if abs(dx) >= abs(dy):
        y_offset = max(-ry * 0.90, min(ry * 0.90, port_offset))
        if kind == "ellipse":
            x_radius = rx * math.sqrt(max(0.0, 1 - (y_offset / ry) ** 2))
        else:
            x_radius = rx
        return cx + (x_radius if dx > 0 else -x_radius), cy + y_offset

    x_offset = max(-rx * 0.90, min(rx * 0.90, port_offset))
    if kind == "ellipse":
        y_radius = ry * math.sqrt(max(0.0, 1 - (x_offset / rx) ** 2))
    else:
        y_radius = ry
    return cx + x_offset, cy + (y_radius if dy > 0 else -y_radius)


def draw_arrowhead(c: canvas.Canvas, x: float, y: float, angle: float) -> None:
    size = 6.5
    left = angle + math.radians(154)
    right = angle - math.radians(154)
    p = c.beginPath()
    p.moveTo(x, y)
    p.lineTo(x + size * math.cos(left), y + size * math.sin(left))
    p.lineTo(x + size * math.cos(right), y + size * math.sin(right))
    p.close()
    c.setFillColor(EDGE)
    c.drawPath(p, fill=1, stroke=0)


def draw_edge(c: canvas.Canvas, source: tuple, target: tuple, bend_offset: float, source_port: float, target_port: float) -> None:
    source_center = (source[1], source[2])
    target_center = (target[1], target[2])
    start = border_point(source, target_center, source_port)
    end = border_point(target, source_center, target_port)
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    c.setStrokeColor(EDGE)
    c.setLineWidth(1.0)
    if abs(dx) < 95 and abs(dy) < 95:
        c.line(start[0], start[1], end[0], end[1])
        angle = math.atan2(dy, dx)
    else:
        bend = bend_offset
        p1 = (start[0] + dx * 0.33, start[1] + bend)
        p2 = (start[0] + dx * 0.72, end[1] + bend)
        path = c.beginPath()
        path.moveTo(start[0], start[1])
        path.curveTo(p1[0], p1[1], p2[0], p2[1], end[0], end[1])
        c.drawPath(path, stroke=1, fill=0)
        angle = math.atan2(end[1] - p2[1], end[0] - p2[0])
    draw_arrowhead(c, end[0], end[1], angle)


def port_offsets(edges: list[tuple[str, str]]) -> dict[tuple[int, str, str], float]:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, (source, target) in enumerate(edges):
        grouped[("out", source)].append(index)
        grouped[("in", target)].append(index)

    offsets: dict[tuple[int, str, str], float] = {}
    for (role, key), indexes in grouped.items():
        count = len(indexes)
        for order, edge_index in enumerate(indexes):
            offsets[(edge_index, role, key)] = (order - (count - 1) / 2) * 12.0
    return offsets


def draw_shape(c: canvas.Canvas, key: str, shape: tuple) -> None:
    kind, cx, cy, width, height = shape
    _shape_kind, name = key.split(":", 1)
    if key.startswith("node:"):
        c.setFillColor(NODE_FILL)
        c.setStrokeColor(NODE_STROKE)
        c.setLineWidth(1.2)
        c.ellipse(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2, fill=1, stroke=1)
        font_size = 10
    elif key.startswith("topic:"):
        c.setFillColor(TOPIC_FILL)
        c.setStrokeColor(TOPIC_STROKE)
        c.setLineWidth(1.1)
        c.rect(cx - width / 2, cy - height / 2, width, height, fill=1, stroke=1)
        font_size = 8.5
    else:
        c.setFillColor(HOST_LABEL_FILL)
        c.setStrokeColor(HOST_LABEL_STROKE)
        c.setLineWidth(1.0)
        c.rect(cx - width / 2, cy - height / 2, width, height, fill=1, stroke=1)
        font_size = 9

    c.setFillColor(TEXT)
    c.setFont("Helvetica", font_size)
    c.drawCentredString(cx, cy - font_size * 0.35, name)


def build_pdf() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(INPUT_JSON.read_text())
    hosts, nodes, _topic_subscribers, edges = collect(data)
    page_w, page_h = landscape(A3)
    shapes, host_boxes = assign_positions(hosts, nodes, page_w, page_h)
    write_dot(hosts, nodes, edges)
    edge_ports = port_offsets(edges)

    c = canvas.Canvas(str(OUTPUT_PDF), pagesize=landscape(A3))
    c.setTitle("ROS 2 graph from five_hosts.json")

    for host in hosts:
        x, y, w, h = host_boxes[host["host_name"]]
        c.setFillColor(HOST_FILL)
        c.setStrokeColor(HOST_STROKE)
        c.setLineWidth(1.7)
        c.rect(x, y, w, h, fill=0, stroke=1)

    for index, (source, target) in enumerate(edges):
        if source not in shapes or target not in shapes:
            continue
        bend_offset = ((index % 7) - 3) * 22
        source_port = edge_ports.get((index, "out", source), 0)
        target_port = edge_ports.get((index, "in", target), 0)
        draw_edge(c, shapes[source], shapes[target], bend_offset, source_port, target_port)

    for key, shape in shapes.items():
        draw_shape(c, key, shape)

    c.setFillColor(TEXT)
    c.setFont("Helvetica", 17)
    c.drawCentredString(page_w / 2, 26, "ROS 2")
    c.save()


if __name__ == "__main__":
    build_pdf()
    print(f"Saved {OUTPUT_PDF}")
