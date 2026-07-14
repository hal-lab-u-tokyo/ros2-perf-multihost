from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path

from analysis_config import RAW_DATA_DIR, output_path


RAW_DIR = RAW_DATA_DIR
OUTPUT_DIR = output_path("raw_trimmed_2s")
TRIM_SECONDS = 2.0

PUB_MESSAGE_RE = re.compile(r"Pub Node_Name: (?P<node>[^,]+), Index: (?P<idx>\d+), Timestamp: (?P<ts>\d+)")
INDEX_MESSAGE_RE = re.compile(r"^Index: (?P<idx>\d+), Timestamp: (?P<ts>\d+)")
START_RE = re.compile(r"StartTime: (?P<ts>\d+)")
END_RE = re.compile(r"EndTime: (?P<ts>\d+)")
TRIAL_RE = re.compile(r"/raw_logs/(trial\d+)/")
CASE_RE = re.compile(r"/(qos_case\d+|payload\w+)/raw_logs/")
NODE_DIR_RE = re.compile(r"/raw_logs/trial\d+/([^/]+)_log/")


def text_from_zip(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8", errors="replace")


def topic_from_log_name(name: str) -> str:
    stem = Path(name).name
    for suffix in ("_sub_log.txt", "_pub_log.txt", "_log.txt", ".txt"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return Path(name).stem


def parse_metadata(text: str) -> dict:
    node = None
    node_type = None
    pub_topics: list[str] = []
    periods: list[float] = []
    payloads: list[float] = []

    for line in text.splitlines():
        if line.startswith("Name:"):
            node = line.split(":", 1)[1].strip()
        elif line.startswith("NodeType:"):
            node_type = line.split(":", 1)[1].strip()
        elif line.startswith("Topics(Pub):"):
            pub_topics = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
        elif line.startswith("Topics:"):
            pub_topics = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
        elif line.startswith("Period:"):
            periods = [float(part.strip()) for part in line.split(":", 1)[1].split(",") if part.strip()]
        elif line.startswith("PayloadSize:"):
            payloads = [float(part.strip()) for part in line.split(":", 1)[1].split(",") if part.strip()]

    if not node:
        return {}
    if periods and len(periods) < len(pub_topics):
        periods.extend([periods[-1]] * (len(pub_topics) - len(periods)))
    if payloads and len(payloads) < len(pub_topics):
        payloads.extend([payloads[-1]] * (len(pub_topics) - len(payloads)))

    return {
        "node": node,
        "node_type": node_type,
        "pub_topics": pub_topics,
        "period_by_topic": {topic: periods[i] for i, topic in enumerate(pub_topics) if i < len(periods)},
        "payload_by_topic": {topic: payloads[i] for i, topic in enumerate(pub_topics) if i < len(payloads)},
    }


def classify_zip(zip_path: Path) -> tuple[str, str]:
    lower = zip_path.name.lower()
    rmw = "FastDDS" if "fastdds" in lower else "CycloneDDS" if "cyclonedds" in lower else "Zenoh" if "zenoh" in lower else "Unknown"
    if "2026-07-06" in lower:
        family = "rmw_constant"
    elif "2026-07-07_09" in lower or "2026-07-07_11" in lower or "2026-07-08_15" in lower or "2026-07-08_16" in lower:
        family = "qos_sweep"
    elif "2026-07-07_15" in lower or "2026-07-07_16" in lower or "2026-07-07_17" in lower or "2026-07-08_18" in lower:
        family = "payload_sweep"
    else:
        family = "unknown"
    return rmw, family


def latency_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "mean[ms]": math.nan,
            "sd[ms]": math.nan,
            "min[ms]": math.nan,
            "q1[ms]": math.nan,
            "mid[ms]": math.nan,
            "q3[ms]": math.nan,
            "max[ms]": math.nan,
        }
    ordered = sorted(values)

    def quantile(q: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        pos = (len(ordered) - 1) * q
        low = math.floor(pos)
        high = math.ceil(pos)
        if low == high:
            return ordered[low]
        return ordered[low] * (high - pos) + ordered[high] * (pos - low)

    return {
        "mean[ms]": statistics.fmean(ordered),
        "sd[ms]": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "min[ms]": ordered[0],
        "q1[ms]": quantile(0.25),
        "mid[ms]": quantile(0.50),
        "q3[ms]": quantile(0.75),
        "max[ms]": ordered[-1],
    }


def parse_messages(text: str) -> tuple[int | None, int | None, list[tuple[str | None, int, int]]]:
    start = None
    end = None
    messages = []
    for line in text.splitlines():
        if start is None:
            match = START_RE.search(line)
            if match:
                start = int(match.group("ts"))
                continue
        if end is None:
            match = END_RE.search(line)
            if match:
                end = int(match.group("ts"))
                continue
        match = PUB_MESSAGE_RE.search(line)
        if match:
            messages.append((match.group("node").strip(), int(match.group("idx")), int(match.group("ts"))))
            continue
        match = INDEX_MESSAGE_RE.search(line)
        if match:
            messages.append((None, int(match.group("idx")), int(match.group("ts"))))
    return start, end, messages


def extract_zip(zip_path: Path) -> list[dict]:
    rmw, family = classify_zip(zip_path)
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        metadata_by_node: dict[str, dict] = {}
        for name in zf.namelist():
            if not name.endswith("metadata.txt"):
                continue
            metadata = parse_metadata(text_from_zip(zf, name))
            if metadata:
                metadata_by_node[metadata["node"]] = metadata

        grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
        for name in zf.namelist():
            if not name.endswith(".txt") or name.endswith("metadata.txt") or "_monitor_" in name:
                continue
            trial_match = TRIAL_RE.search(name)
            if not trial_match:
                continue
            case_match = CASE_RE.search(name)
            case = case_match.group(1) if case_match else ""
            grouped[(case, trial_match.group(1))].append(name)

        for (case, trial), names in sorted(grouped.items()):
            starts = []
            ends = []
            sends: dict[tuple[str, str], dict[int, int]] = defaultdict(dict)
            receives: dict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
            pub_topics_seen: set[tuple[str, str]] = set()

            for name in names:
                node_match = NODE_DIR_RE.search(name)
                if not node_match:
                    continue
                node = node_match.group(1)
                topic = topic_from_log_name(name)
                metadata = metadata_by_node.get(node, {})
                pub_topics = set(metadata.get("pub_topics", []))
                start, end, messages = parse_messages(text_from_zip(zf, name))
                if start is not None:
                    starts.append(start)
                if end is not None:
                    ends.append(end)
                if not messages:
                    continue

                if topic in pub_topics:
                    pub_topics_seen.add((node, topic))
                    for pub_node, index, timestamp in messages:
                        sends[(node, topic)][index] = timestamp
                else:
                    for pub_node, index, timestamp in messages:
                        if pub_node is not None:
                            receives[(node, pub_node, topic)].append((index, timestamp))

            if not starts or not ends:
                continue
            cutoff_ns = min(starts) + int(TRIM_SECONDS * 1_000_000_000)
            end_ns = max(ends)
            duration_s = max((end_ns - cutoff_ns) / 1_000_000_000, 0.0)

            latencies = []
            jitter_values = []
            lost_total = 0
            for (_receiver, pub_node, topic), stream_rows in receives.items():
                send_by_index = sends.get((pub_node, topic), {})
                if not send_by_index:
                    continue
                kept = [(index, ts) for index, ts in stream_rows if ts >= cutoff_ns and index in send_by_index]
                for index, recv_ts in kept:
                    latencies.append((recv_ts - send_by_index[index]) / 1_000_000.0)

                received_indices = {index for index, _recv_ts in kept}
                if received_indices:
                    lost_total += max(0, max(received_indices) - min(received_indices) + 1 - len(received_indices))

                period_ms = metadata_by_node.get(pub_node, {}).get("period_by_topic", {}).get(topic, 100.0)
                for (prev_index, prev_ts), (index, ts) in zip(sorted(kept), sorted(kept)[1:]):
                    index_gap = index - prev_index
                    if index_gap <= 0:
                        continue
                    jitter_values.append((ts - prev_ts) / 1_000_000.0 - period_ms * index_gap)

            bytes_sent = 0.0
            for pub_node, topic in pub_topics_seen:
                payload = metadata_by_node.get(pub_node, {}).get("payload_by_topic", {}).get(topic, 64.0)
                bytes_sent += payload * sum(1 for ts in sends.get((pub_node, topic), {}).values() if cutoff_ns <= ts <= end_ns)
            throughput_bps = bytes_sent / duration_s if duration_s > 0 else math.nan

            stats = latency_stats(latencies)
            row = {
                "source_zip": zip_path.name,
                "family": family,
                "RMW": rmw,
                "case": case,
                "trial": trial,
                "trim_seconds": TRIM_SECONDS,
                "message_count": len(latencies),
                "lost[#]": lost_total,
                **stats,
                "throughput[B/s]": throughput_bps,
                "throughput[MB/s]": throughput_bps / 1_000_000.0 if not math.isnan(throughput_bps) else math.nan,
                "jitter[ms]": statistics.fmean(abs(value) for value in jitter_values) if jitter_values else math.nan,
                "jitter_count": len(jitter_values),
            }
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def trim_tag(seconds: float) -> str:
    return f"{seconds:g}s".replace(".", "p")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract per-trial metrics after dropping an initial time window.")
    parser.add_argument("trim_seconds", nargs="?", type=float, default=2.0)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    global RAW_DIR, OUTPUT_DIR, TRIM_SECONDS

    args = parse_args()
    TRIM_SECONDS = args.trim_seconds
    RAW_DIR = args.raw_dir.expanduser().resolve()
    OUTPUT_DIR = args.output_dir.expanduser().resolve() if args.output_dir else output_path(f"raw_trimmed_{trim_tag(TRIM_SECONDS)}")

    all_rows = []
    for zip_path in sorted(RAW_DIR.glob("*.zip")):
        rows = extract_zip(zip_path)
        all_rows.extend(rows)
        print(f"{zip_path.name}: trials={len(rows)}")
    write_csv(OUTPUT_DIR / "trimmed_trials.csv", all_rows)
    print(f"Saved {OUTPUT_DIR / 'trimmed_trials.csv'}")


if __name__ == "__main__":
    main()
