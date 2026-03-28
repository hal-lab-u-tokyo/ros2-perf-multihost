#!/usr/bin/env python3
"""
Host-level monitor:
usage: monitor_host.py <interval_s> <out.csv>
Writes CSV: timestamp_ns,cpu_percent,load1,load5,load15,mem_total,mem_available,mem_used,mem_percent,swap_total,swap_used,swap_percent
"""

import sys
import time
import csv
import signal
import psutil
import os

if len(sys.argv) < 3:
    print("usage: monitor_host.py <interval_s> <out_csv>")
    sys.exit(2)

interval = float(sys.argv[1])
out_csv = sys.argv[2]

stop = False


def handle(sig, frame):
    global stop
    stop = True


signal.signal(signal.SIGINT, handle)
signal.signal(signal.SIGTERM, handle)

with open(out_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(
        [
            "timestamp_ns",
            "cpu_percent",
            "load1",
            "load5",
            "load15",
            "mem_total",
            "mem_available",
            "mem_used",
            "mem_percent",
            "swap_total",
            "swap_used",
            "swap_percent",
        ]
    )
    # warm-up
    psutil.cpu_percent(interval=None)

    while not stop:
        try:
            ts = time.time_ns()
            cpu = psutil.cpu_percent(interval=None)

            try:
                load1, load5, load15 = os.getloadavg()
            except Exception:
                load1 = load5 = load15 = -1.0

            try:
                vm = psutil.virtual_memory()
                mem_total = vm.total
                mem_available = vm.available
                mem_used = vm.used
                mem_percent = vm.percent
            except Exception as e:
                print(f"Error getting memory info: {e}", file=sys.stderr)
                mem_total = mem_available = mem_used = -1
                mem_percent = -1.0

            try:
                sw = psutil.swap_memory()
                swap_total = sw.total
                swap_used = sw.used
                swap_percent = sw.percent
            except Exception as e:
                print(f"Error getting swap info: {e}", file=sys.stderr)
                swap_total = swap_used = -1
                swap_percent = -1.0

            w.writerow(
                [
                    ts,
                    cpu,
                    load1,
                    load5,
                    load15,
                    mem_total,
                    mem_available,
                    mem_used,
                    mem_percent,
                    swap_total,
                    swap_used,
                    swap_percent,
                ]
            )
            f.flush()

        except Exception as e:
            print(f"Error in monitoring loop: {e}", file=sys.stderr)
            # エラーが発生してもループを継続

        time.sleep(interval)
