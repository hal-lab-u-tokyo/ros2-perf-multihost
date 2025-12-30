#!/usr/bin/env python3
"""
Host-side docker monitor:
usage: monitor_docker.py <container_name_or_id> <interval_sec> <out_csv>
Writes CSV with header:
timestamp_ns,cpu_percent,mem_used_bytes,mem_total_bytes
"""

import sys
import time
import subprocess
import csv
import signal


def parse_mem(mem_str):
    # "12.34MiB / 1.94GiB" -> used_bytes, total_bytes
    try:
        used, _, total = mem_str.partition(" / ")

        def to_bytes(s):
            s = s.strip()
            if s.endswith("KiB"):
                return float(s[:-3]) * 1024
            if s.endswith("MiB"):
                return float(s[:-3]) * 1024**2
            if s.endswith("GiB"):
                return float(s[:-3]) * 1024**3
            if s.endswith("B"):
                return float(s[:-1])
            # fallback: try plain number
            return float(s)

        return int(to_bytes(used)), int(to_bytes(total))
    except Exception:
        return -1, -1


def sample(container, out_csv):
    # format: Container,Name,CPUPerc,MemUsage
    cmd = ["docker", "stats", "--no-stream", "--format", "{{.Container}},{{.Name}},{{.CPUPerc}},{{.MemUsage}}", container]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    line = proc.stdout.strip()
    if not line:
        return None
    parts = line.split(",", 3)
    if len(parts) < 4:
        return None
    _, _, cpu_perc, mem_usage = parts
    cpu_val = cpu_perc.strip().rstrip("%")
    used, total = parse_mem(mem_usage)
    try:
        cpu_val_f = float(cpu_val)
    except Exception:
        cpu_val_f = -1.0
    return int(time.time_ns()), cpu_val_f, used, total


def main():
    if len(sys.argv) < 4:
        print("usage: monitor_docker.py <container> <interval_sec> <out_csv>")
        sys.exit(2)
    container = sys.argv[1]
    interval = float(sys.argv[2])
    out_csv = sys.argv[3]

    stop = False

    def handle(sig, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ns", "cpu_percent", "mem_used_bytes", "mem_total_bytes"])
        while not stop:
            row = sample(container, out_csv)
            if row:
                writer.writerow(row)
                f.flush()
            time.sleep(interval)


if __name__ == "__main__":
    main()
