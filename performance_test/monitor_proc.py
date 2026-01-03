#!/usr/bin/env python3
import time
import csv
import sys
import psutil

if len(sys.argv) < 4:
    print("Usage: monitor_proc.py <proc_name_or_pid> <interval_s> <out.csv>")
    sys.exit(1)

target = sys.argv[1]
interval = float(sys.argv[2])
out = sys.argv[3]


def find_pid(target):
    if target.isdigit():
        return int(target)
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        if target == p.info["name"] or (p.info["cmdline"] and target in " ".join(p.info["cmdline"])):
            return p.info["pid"]
    return None


with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp_ns", "pid", "cpu_percent", "rss_bytes", "vms_bytes", "num_threads"])
    while True:
        pid = find_pid(target)
        if not pid:
            time.sleep(interval)
            continue
        try:
            p = psutil.Process(pid)
            p.cpu_percent()  # warmup
            while True:
                ts = time.time_ns()
                cpu = p.cpu_percent(interval=None)
                mem = p.memory_info()
                w.writerow([ts, pid, cpu, mem.rss, mem.vms, p.num_threads()])
                f.flush()
                time.sleep(interval)
        except psutil.NoSuchProcess:
            time.sleep(interval)
        except KeyboardInterrupt:
            break
