from __future__ import annotations

import argparse
import csv
import re
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path

from analysis_config import RAW_DATA_DIR, output_path


RAW_DIR = RAW_DATA_DIR
OUTPUT_DIR = output_path("raw_period_jitter")

MESSAGE_RE = re.compile(r"Pub Node_Name: (?P<node>[^,]+), Index: (?P<idx>\d+), Timestamp: (?P<ts>\d+)")
TRIAL_RE = re.compile(r"/raw_logs/(trial\d+)/")
CASE_RE = re.compile(r"/(qos_case\d+|payload\w+)/raw_logs/")


def text_from_zip(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8", errors="replace")


def parse_metadata(text: str) -> tuple[str | None, dict[str, float], float | None]:
    node_name = None
    topics: list[str] = []
    periods: list[float] = []
    default_period = None

    for line in text.splitlines():
        if line.startswith("Name:"):
            node_name = line.split(":", 1)[1].strip()
        elif line.startswith("Topics(Pub):"):
            topics = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
        elif line.startswith("Topics:"):
            topics = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
        elif line.startswith("Period:"):
            periods = [float(part.strip()) for part in line.split(":", 1)[1].split(",") if part.strip()]

    topic_periods = {}
    if periods:
        default_period = periods[0]
        if topics:
            for i, topic in enumerate(topics):
                topic_periods[topic] = periods[min(i, len(periods) - 1)]
    return node_name, topic_periods, default_period


def topic_from_log_name(name: str) -> str:
    stem = Path(name).name
    for suffix in ("_sub_log.txt", "_pub_log.txt", "_log.txt", ".txt"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return Path(name).stem


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


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0,
            "mean_ms": float("nan"),
            "mean_abs_ms": float("nan"),
            "std_ms": float("nan"),
            "max_abs_ms": float("nan"),
        }
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "mean_abs_ms": statistics.fmean(abs(value) for value in values),
        "std_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
        "max_abs_ms": max(abs(value) for value in values),
    }


def extract_zip(zip_path: Path) -> tuple[list[dict], list[dict]]:
    rmw, family = classify_zip(zip_path)
    stream_rows = []
    trial_values: dict[tuple[str, str], list[float]] = defaultdict(list)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        period_by_node_topic: dict[tuple[str, str], float] = {}
        default_period_by_node: dict[str, float] = {}

        for name in names:
            if not name.endswith("metadata.txt"):
                continue
            node, topic_periods, default_period = parse_metadata(text_from_zip(zf, name))
            if not node:
                continue
            if default_period is not None:
                default_period_by_node[node] = default_period
            for topic, period in topic_periods.items():
                period_by_node_topic[(node, topic)] = period

        for name in names:
            if not name.endswith(".txt") or name.endswith("metadata.txt") or "_monitor_" in name:
                continue
            trial_match = TRIAL_RE.search(name)
            if not trial_match:
                continue
            text = text_from_zip(zf, name)
            messages = []
            for line in text.splitlines():
                match = MESSAGE_RE.search(line)
                if match:
                    messages.append((match.group("node").strip(), int(match.group("idx")), int(match.group("ts"))))
            if len(messages) < 2:
                continue

            case_match = CASE_RE.search(name)
            case = case_match.group(1) if case_match else ""
            trial = trial_match.group(1)
            topic = topic_from_log_name(name)

            by_pub: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for pub_node, index, timestamp in messages:
                by_pub[pub_node].append((index, timestamp))

            for pub_node, rows in by_pub.items():
                rows = sorted(rows)
                period_ms = period_by_node_topic.get((pub_node, topic), default_period_by_node.get(pub_node, 100.0))
                jitters = []
                for (prev_index, prev_ts), (index, ts) in zip(rows, rows[1:]):
                    index_gap = index - prev_index
                    if index_gap <= 0:
                        continue
                    interval_ms = (ts - prev_ts) / 1_000_000.0
                    jitters.append(interval_ms - period_ms * index_gap)
                stats = summarize(jitters)
                if stats["count"] == 0:
                    continue
                trial_values[(case, trial)].extend(jitters)
                stream_rows.append(
                    {
                        "source_zip": zip_path.name,
                        "family": family,
                        "RMW": rmw,
                        "case": case,
                        "trial": trial,
                        "topic": topic,
                        "publisher": pub_node,
                        "receiver_log": name,
                        "period_ms": period_ms,
                        "message_count": len(rows),
                        "jitter_count": stats["count"],
                        "period_jitter_mean_ms": stats["mean_ms"],
                        "period_jitter_mean_abs_ms": stats["mean_abs_ms"],
                        "period_jitter_std_ms": stats["std_ms"],
                        "period_jitter_max_abs_ms": stats["max_abs_ms"],
                    }
                )

    trial_rows = []
    for (case, trial), values in sorted(trial_values.items()):
        stats = summarize(values)
        trial_rows.append(
            {
                "source_zip": zip_path.name,
                "family": family,
                "RMW": rmw,
                "case": case,
                "trial": trial,
                "jitter_count": stats["count"],
                "period_jitter_mean_ms": stats["mean_ms"],
                "period_jitter_mean_abs_ms": stats["mean_abs_ms"],
                "period_jitter_std_ms": stats["std_ms"],
                "period_jitter_max_abs_ms": stats["max_abs_ms"],
            }
        )
    return stream_rows, trial_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract period jitter from raw log zip files.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=output_path("raw_period_jitter"))
    return parser.parse_args()


def main() -> None:
    global RAW_DIR, OUTPUT_DIR

    args = parse_args()
    RAW_DIR = args.raw_dir.expanduser().resolve()
    OUTPUT_DIR = args.output_dir.expanduser().resolve()

    all_stream_rows = []
    all_trial_rows = []
    for zip_path in sorted(RAW_DIR.glob("*.zip")):
        stream_rows, trial_rows = extract_zip(zip_path)
        all_stream_rows.extend(stream_rows)
        all_trial_rows.extend(trial_rows)
        print(f"{zip_path.name}: streams={len(stream_rows)} trials={len(trial_rows)}")

    write_csv(OUTPUT_DIR / "period_jitter_streams.csv", all_stream_rows)
    write_csv(OUTPUT_DIR / "period_jitter_trials.csv", all_trial_rows)
    print(f"Saved {OUTPUT_DIR / 'period_jitter_streams.csv'}")
    print(f"Saved {OUTPUT_DIR / 'period_jitter_trials.csv'}")


if __name__ == "__main__":
    main()
