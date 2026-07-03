#!/usr/bin/env python3
"""Estimate host clock skew via REST using NTP-style four timestamps.

This script queries /clock_probe on each host resolved from metadata.txt and
saves detailed samples and summaries as CSV files.
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_PORT = 5000
DEFAULT_SAMPLES = 15
DEFAULT_INTERVAL_SEC = 0.1
DEFAULT_TIMEOUT_SEC = 2.0
DEFAULT_OUTPUT_DIR = "performance_ws/system_perf/clock_skew"


@dataclass
class Sample:
    host: str
    index: int
    manager_send_ns: int
    manager_recv_ns: int
    server_recv_ns: int
    server_send_ns: int
    rtt_ns: int
    server_proc_ns: int
    net_delay_ns: int
    offset_ns: int
    uncertainty_ns: int
    ok: bool
    error: str
    error_category: str
    hint: str


@dataclass
class ProbeStatus:
    ok: bool
    category: str
    detail: str
    hint: str


def post_json(url: str, payload: bytes, timeout_sec: float) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return int(resp.getcode()), resp.read()


def classify_url_error(exc: urllib.error.URLError) -> tuple[str, str, str]:
    reason = exc.reason
    detail = str(reason)
    if isinstance(reason, ConnectionRefusedError):
        return (
            "connection_refused",
            detail,
            "REST server is not running or not listening on the target port. "
            "Start it with manager_scripts/manage_rest_servers.sh start <topology>.",
        )
    if isinstance(reason, socket.timeout):
        return (
            "timeout",
            detail,
            "Request timed out. Check network reachability, firewall, or increase --timeout.",
        )
    if isinstance(reason, socket.gaierror):
        return (
            "name_resolution",
            detail,
            "Hostname resolution failed. Verify --hosts values and DNS/hosts settings.",
        )
    return (
        "url_error",
        detail,
        "HTTP request failed before response. Check host reachability and REST server status.",
    )


def check_clock_probe_availability(host: str, port: int, timeout_sec: float) -> ProbeStatus:
    probe_url = f"http://{host}:{port}/clock_probe"
    payload = b"{}"
    try:
        code, _ = post_json(probe_url, payload, timeout_sec)
        if code == 200:
            return ProbeStatus(True, "ok", "clock_probe available", "")
        return ProbeStatus(
            False,
            "unexpected_status",
            f"/clock_probe returned HTTP {code}",
            "Unexpected status from /clock_probe. Check REST server implementation.",
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Distinguish "REST not running" from "REST running but old version".
            prepare_url = f"http://{host}:{port}/prepare_run"
            try:
                post_json(prepare_url, payload, timeout_sec)
                return ProbeStatus(
                    False,
                    "missing_clock_probe",
                    "/clock_probe returned 404 but /prepare_run is reachable",
                    "Remote rest_server.py seems older than manager script. "
                    "Update remote repository and restart REST server.",
                )
            except urllib.error.HTTPError as prep_exc:
                if prep_exc.code in (400, 404, 500, 504):
                    return ProbeStatus(
                        False,
                        "missing_clock_probe",
                        f"/clock_probe returned 404; /prepare_run returned HTTP {prep_exc.code}",
                        "REST server is reachable but /clock_probe is missing. "
                        "Update remote rest_server.py and restart.",
                    )
            except urllib.error.URLError:
                pass

        return ProbeStatus(
            False,
            "http_error",
            f"HTTP {exc.code} on /clock_probe",
            "REST server responded with an error. Check remote REST logs.",
        )
    except urllib.error.URLError as exc:
        category, detail, hint = classify_url_error(exc)
        return ProbeStatus(False, category, detail, hint)


def make_error_rows(host: str, samples: int, category: str, detail: str, hint: str) -> list[Sample]:
    message = f"{category}: {detail}"
    rows: list[Sample] = []
    for idx in range(1, samples + 1):
        rows.append(
            Sample(
                host=host,
                index=idx,
                manager_send_ns=0,
                manager_recv_ns=0,
                server_recv_ns=0,
                server_send_ns=0,
                rtt_ns=0,
                server_proc_ns=0,
                net_delay_ns=0,
                offset_ns=0,
                uncertainty_ns=0,
                ok=False,
                error=message,
                error_category=category,
                hint=hint,
            )
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate per-host clock skew vs manager using REST /clock_probe "
            "and save CSV outputs."
        )
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"REST server port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLES,
        help=f"Samples per host (default: {DEFAULT_SAMPLES})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SEC,
        help=f"Sleep between samples in seconds (default: {DEFAULT_INTERVAL_SEC})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SEC})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (relative to repository root or absolute path, default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--csv-prefix",
        default=None,
        help=(
            "CSV filename prefix (without extension). "
            "Default: clock_skew_rest_<timestamp>"
        ),
    )
    parser.add_argument(
        "--hosts",
        required=True,
        help="Comma-separated host list (required, e.g. host1,host2,host3)",
    )
    return parser.parse_args()


def parse_hosts_csv(hosts_csv: str) -> list[str]:
    hosts = [h.strip() for h in hosts_csv.split(",") if h.strip()]
    if not hosts:
        raise ValueError("resolved host list is empty")
    return hosts


def call_clock_probe(host: str, port: int, timeout_sec: float) -> tuple[int, int, int, int]:
    url = f"http://{host}:{port}/clock_probe"
    body = b"{}"

    t0 = time.time_ns()
    _, payload = post_json(url, body, timeout_sec)
    t3 = time.time_ns()

    data = json.loads(payload.decode("utf-8"))
    t1 = int(data["server_recv_time_ns"])
    t2 = int(data["server_send_time_ns"])

    return t0, t1, t2, t3


def measure_host(host: str, port: int, samples: int, interval_sec: float, timeout_sec: float) -> list[Sample]:
    rows: list[Sample] = []
    for idx in range(1, samples + 1):
        try:
            t0, t1, t2, t3 = call_clock_probe(host, port, timeout_sec)
            rtt_ns = t3 - t0
            server_proc_ns = t2 - t1
            net_delay_ns = rtt_ns - server_proc_ns
            if net_delay_ns < 0:
                net_delay_ns = 0

            # NTP offset estimate (server_time - manager_time).
            offset_ns = ((t1 - t0) + (t2 - t3)) // 2
            uncertainty_ns = net_delay_ns // 2
            rows.append(
                Sample(
                    host=host,
                    index=idx,
                    manager_send_ns=t0,
                    manager_recv_ns=t3,
                    server_recv_ns=t1,
                    server_send_ns=t2,
                    rtt_ns=rtt_ns,
                    server_proc_ns=server_proc_ns,
                    net_delay_ns=net_delay_ns,
                    offset_ns=offset_ns,
                    uncertainty_ns=uncertainty_ns,
                    ok=True,
                    error="",
                    error_category="",
                    hint="",
                )
            )
        except urllib.error.HTTPError as exc:
            rows.append(
                Sample(
                    host=host,
                    index=idx,
                    manager_send_ns=0,
                    manager_recv_ns=0,
                    server_recv_ns=0,
                    server_send_ns=0,
                    rtt_ns=0,
                    server_proc_ns=0,
                    net_delay_ns=0,
                    offset_ns=0,
                    uncertainty_ns=0,
                    ok=False,
                    error=f"http_error: HTTP {exc.code}",
                    error_category="http_error",
                    hint="REST server responded with an error. Check remote REST logs.",
                )
            )
        except urllib.error.URLError as exc:
            category, detail, hint = classify_url_error(exc)
            rows.append(
                Sample(
                    host=host,
                    index=idx,
                    manager_send_ns=0,
                    manager_recv_ns=0,
                    server_recv_ns=0,
                    server_send_ns=0,
                    rtt_ns=0,
                    server_proc_ns=0,
                    net_delay_ns=0,
                    offset_ns=0,
                    uncertainty_ns=0,
                    ok=False,
                    error=f"{category}: {detail}",
                    error_category=category,
                    hint=hint,
                )
            )
        except (TimeoutError, KeyError, ValueError) as exc:
            rows.append(
                Sample(
                    host=host,
                    index=idx,
                    manager_send_ns=0,
                    manager_recv_ns=0,
                    server_recv_ns=0,
                    server_send_ns=0,
                    rtt_ns=0,
                    server_proc_ns=0,
                    net_delay_ns=0,
                    offset_ns=0,
                    uncertainty_ns=0,
                    ok=False,
                    error=str(exc),
                    error_category="parse_error",
                    hint="Response format is unexpected. Ensure remote REST server is updated.",
                )
            )

        if idx < samples:
            time.sleep(interval_sec)

    return rows


def ns_to_ms_str(ns_value: int | float) -> str:
    return f"{ns_value / 1_000_000.0:.6f}"


def summarize_host(host: str, rows: list[Sample]) -> dict[str, str | int]:
    ok_rows = [r for r in rows if r.ok]
    if not ok_rows:
        first_error = rows[0].error if rows else ""
        first_hint = rows[0].hint if rows else ""
        first_category = rows[0].error_category if rows else ""
        return {
            "host": host,
            "samples_ok": 0,
            "samples_total": len(rows),
            "best_offset_ns": "",
            "best_offset_ms": "",
            "best_uncertainty_ns": "",
            "best_uncertainty_ms": "",
            "best_net_delay_ns": "",
            "best_net_delay_ms": "",
            "mean_offset_ns": "",
            "mean_offset_ms": "",
            "sd_offset_ns": "",
            "sd_offset_ms": "",
            "min_offset_ns": "",
            "min_offset_ms": "",
            "max_offset_ns": "",
            "max_offset_ms": "",
            "failed_samples": len(rows),
            "error_category": first_category,
            "error": first_error,
            "hint": first_hint,
        }

    best = min(ok_rows, key=lambda r: r.net_delay_ns)
    offsets = [r.offset_ns for r in ok_rows]
    mean_offset = int(round(statistics.fmean(offsets)))
    sd_offset = int(round(statistics.pstdev(offsets))
                    ) if len(offsets) > 1 else 0
    min_offset = min(offsets)
    max_offset = max(offsets)

    return {
        "host": host,
        "samples_ok": len(ok_rows),
        "samples_total": len(rows),
        "best_offset_ns": best.offset_ns,
        "best_offset_ms": ns_to_ms_str(best.offset_ns),
        "best_uncertainty_ns": best.uncertainty_ns,
        "best_uncertainty_ms": ns_to_ms_str(best.uncertainty_ns),
        "best_net_delay_ns": best.net_delay_ns,
        "best_net_delay_ms": ns_to_ms_str(best.net_delay_ns),
        "mean_offset_ns": mean_offset,
        "mean_offset_ms": ns_to_ms_str(mean_offset),
        "sd_offset_ns": sd_offset,
        "sd_offset_ms": ns_to_ms_str(sd_offset),
        "min_offset_ns": min_offset,
        "min_offset_ms": ns_to_ms_str(min_offset),
        "max_offset_ns": max_offset,
        "max_offset_ms": ns_to_ms_str(max_offset),
        "failed_samples": len(rows) - len(ok_rows),
        "error_category": "",
        "error": "",
        "hint": "",
    }


def write_samples_csv(path: Path, rows: list[Sample]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "host",
                "sample_idx",
                "ok",
                "error",
                "error_category",
                "hint",
                "manager_send_ns",
                "server_recv_ns",
                "server_send_ns",
                "manager_recv_ns",
                "rtt_ns",
                "server_proc_ns",
                "net_delay_ns",
                "offset_ns",
                "uncertainty_ns",
                "rtt_ms",
                "net_delay_ms",
                "offset_ms",
                "uncertainty_ms",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.host,
                    r.index,
                    int(r.ok),
                    r.error,
                    r.error_category,
                    r.hint,
                    r.manager_send_ns,
                    r.server_recv_ns,
                    r.server_send_ns,
                    r.manager_recv_ns,
                    r.rtt_ns,
                    r.server_proc_ns,
                    r.net_delay_ns,
                    r.offset_ns,
                    r.uncertainty_ns,
                    ns_to_ms_str(r.rtt_ns),
                    ns_to_ms_str(r.net_delay_ns),
                    ns_to_ms_str(r.offset_ns),
                    ns_to_ms_str(r.uncertainty_ns),
                ]
            )


def write_summary_csv(path: Path, rows_by_host: dict[str, list[Sample]]) -> dict[str, dict[str, str | int]]:
    summaries: dict[str, dict[str, str | int]] = {}
    with path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "host",
            "samples_ok",
            "samples_total",
            "failed_samples",
            "best_offset_ns",
            "best_offset_ms",
            "best_uncertainty_ns",
            "best_uncertainty_ms",
            "best_net_delay_ns",
            "best_net_delay_ms",
            "mean_offset_ns",
            "mean_offset_ms",
            "sd_offset_ns",
            "sd_offset_ms",
            "min_offset_ns",
            "min_offset_ms",
            "max_offset_ns",
            "max_offset_ms",
            "error_category",
            "error",
            "hint",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for host, rows in rows_by_host.items():
            summary = summarize_host(host, rows)
            summaries[host] = summary
            writer.writerow(summary)
    return summaries


def write_pairwise_csv(path: Path, summaries: dict[str, dict[str, str | int]], hosts: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "host_a",
                "host_b",
                "best_skew_ns",
                "best_skew_ms",
                "combined_uncertainty_ns",
                "combined_uncertainty_ms",
            ]
        )

        for i in range(len(hosts)):
            for j in range(i + 1, len(hosts)):
                host_a = hosts[i]
                host_b = hosts[j]
                s_a = summaries.get(host_a, {})
                s_b = summaries.get(host_b, {})
                if not s_a or not s_b:
                    continue
                if not s_a.get("best_offset_ns") or not s_b.get("best_offset_ns"):
                    continue

                skew_ns = int(s_b["best_offset_ns"]) - \
                    int(s_a["best_offset_ns"])
                combined_uncertainty_ns = int(s_a["best_uncertainty_ns"]) + int(
                    s_b["best_uncertainty_ns"]
                )
                writer.writerow(
                    [
                        host_a,
                        host_b,
                        skew_ns,
                        ns_to_ms_str(skew_ns),
                        combined_uncertainty_ns,
                        ns_to_ms_str(combined_uncertainty_ns),
                    ]
                )


def _resolve_output_dir(
    repo_root: Path,
    output_dir_arg: str,
) -> Path:
    candidate = Path(output_dir_arg)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def _update_latest_alias(output_dir: Path, run_dir: Path) -> tuple[bool, str]:
    latest_link = output_dir / "latest"
    rel_target = Path(run_dir.name)
    try:
        if latest_link.is_symlink() or latest_link.exists():
            if latest_link.is_dir() and not latest_link.is_symlink():
                return (
                    False,
                    f"{latest_link} exists as a directory; could not update alias",
                )
            latest_link.unlink()
        latest_link.symlink_to(rel_target)
        return True, str(latest_link)
    except OSError as exc:
        return False, f"failed to create latest alias: {exc}"


def main() -> int:
    args = parse_args()
    if args.samples <= 0:
        print("ERROR: --samples must be >= 1", file=sys.stderr)
        return 2
    if args.interval <= 0:
        print("ERROR: --interval must be > 0", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("ERROR: --timeout must be > 0", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]

    try:
        hosts = parse_hosts_csv(args.hosts)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_dir = _resolve_output_dir(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.csv_prefix:
        samples_csv = run_dir / f"{args.csv_prefix}_samples.csv"
        summary_csv = run_dir / f"{args.csv_prefix}_summary.csv"
        pairwise_csv = run_dir / f"{args.csv_prefix}_pairwise.csv"
    else:
        samples_csv = run_dir / "samples.csv"
        summary_csv = run_dir / "summary.csv"
        pairwise_csv = run_dir / "pairwise.csv"
    result_log = run_dir / "result.log"

    rows_by_host: dict[str, list[Sample]] = {}
    all_rows: list[Sample] = []

    with result_log.open("w", encoding="utf-8") as log_fh:
        def out(message: str = "") -> None:
            print(message)
            log_fh.write(f"{message}\n")
            log_fh.flush()

        out("=== REST Clock Skew Check ===")
        out("host_source   : hosts")
        out(f"hosts         : {' '.join(hosts)}")
        out(f"rest_port     : {args.port}")
        out(f"samples       : {args.samples}")
        out(f"interval_sec  : {args.interval}")
        out(f"timeout_sec   : {args.timeout}")
        out(f"output_dir    : {output_dir}")
        out(f"run_dir       : {run_dir}")
        out("")

        for host in hosts:
            out(f"--- {host} ---")
            probe = check_clock_probe_availability(
                host, args.port, args.timeout)
            if not probe.ok and probe.category in (
                "missing_clock_probe",
                "connection_refused",
                "name_resolution",
            ):
                out(f"[{host}] ERROR: {probe.detail}")
                if probe.hint:
                    out(f"[{host}] hint: {probe.hint}")
                rows = make_error_rows(
                    host,
                    args.samples,
                    probe.category,
                    probe.detail,
                    probe.hint,
                )
            else:
                rows = measure_host(
                    host,
                    args.port,
                    args.samples,
                    args.interval,
                    args.timeout,
                )
            rows_by_host[host] = rows
            all_rows.extend(rows)

            ok_rows = [r for r in rows if r.ok]
            failed = len(rows) - len(ok_rows)
            if not ok_rows:
                out(f"[{host}] ERROR: no valid samples (failed={failed}/{len(rows)})")
                first_category = rows[0].error_category if rows else ""
                first_error = rows[0].error if rows else ""
                first_hint = rows[0].hint if rows else ""
                if first_category or first_error:
                    out(f"[{host}] reason: {first_error}")
                if first_hint:
                    out(f"[{host}] hint: {first_hint}")
                continue

            best = min(ok_rows, key=lambda r: r.net_delay_ns)
            mean_offset = int(
                round(statistics.fmean(r.offset_ns for r in ok_rows)))
            sd_offset = int(
                round(statistics.pstdev([r.offset_ns for r in ok_rows]))
            ) if len(ok_rows) > 1 else 0
            out(f"[{host}] samples_ok={len(ok_rows)}/{len(rows)} failed={failed}")
            out(
                f"[{host}] best_offset_vs_manager_ns={best.offset_ns} "
                f"({ns_to_ms_str(best.offset_ns)} ms)"
            )
            out(
                f"[{host}] best_net_delay_ns={best.net_delay_ns} "
                f"({ns_to_ms_str(best.net_delay_ns)} ms), uncertainty=+/-{best.uncertainty_ns} ns"
            )
            out(
                f"[{host}] mean_offset_ns={mean_offset} ({ns_to_ms_str(mean_offset)} ms), "
                f"sd={sd_offset} ns ({ns_to_ms_str(sd_offset)} ms)"
            )
            out("")

        write_samples_csv(samples_csv, all_rows)
        summaries = write_summary_csv(summary_csv, rows_by_host)
        write_pairwise_csv(pairwise_csv, summaries, hosts)

        out("=== Host-to-Host Skew (best estimates) ===")
        pair_count = 0
        for i in range(len(hosts)):
            for j in range(i + 1, len(hosts)):
                host_a = hosts[i]
                host_b = hosts[j]
                s_a = summaries.get(host_a, {})
                s_b = summaries.get(host_b, {})
                if not s_a or not s_b:
                    continue

                if s_a.get("best_offset_ns") in ("", None) or s_b.get("best_offset_ns") in ("", None):
                    continue

                skew_ns = int(s_b["best_offset_ns"]) - \
                    int(s_a["best_offset_ns"])
                combined_uncertainty_ns = int(s_a["best_uncertainty_ns"]) + int(
                    s_b["best_uncertainty_ns"]
                )
                out(
                    f"{host_b} - {host_a} = {skew_ns} ns ({ns_to_ms_str(skew_ns)} ms), "
                    f"combined_uncertainty=+/-{combined_uncertainty_ns} ns"
                )
                pair_count += 1

        if pair_count == 0:
            out("No pairwise skew available (insufficient valid host samples).")

        out("")
        out("=== CSV Output ===")
        out(f"samples  : {samples_csv}")
        out(f"summary  : {summary_csv}")
        out(f"pairwise : {pairwise_csv}")
        out(f"result   : {result_log}")

        latest_ok, latest_msg = _update_latest_alias(output_dir, run_dir)
        if latest_ok:
            out(f"latest   : {latest_msg}")
        else:
            out(f"latest   : unavailable ({latest_msg})")

        any_ok = any(r.ok for r in all_rows)
        if not any_ok:
            out("Completed with errors: no valid samples collected.")
            return 1

        out("Completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
