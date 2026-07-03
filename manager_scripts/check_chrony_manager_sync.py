#!/usr/bin/env python3
"""Validate chrony Manager-reference setup across Hosts.

This script checks whether each Host is actually synchronized to the given
Manager NTP source (or at least can reach it), and records diagnostics.
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_OUTPUT_DIR = "performance_ws/system_perf/chrony_check"
DEFAULT_SSH_USER = "ubuntu"
DEFAULT_CHRONY_CONF = "/etc/chrony/chrony.conf"


@dataclass
class HostCheckResult:
    host: str
    ssh_ok: bool
    chrony_active: bool
    manager_source_found: bool
    manager_state: str
    manager_reach: str
    configured_with_manager_ip: bool
    status: str
    issue: str
    hint: str
    raw_sources: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether Hosts are synchronized to a Manager NTP source via chrony, "
            "and diagnose common misconfigurations (including Manager allow/subnet issues)."
        )
    )
    parser.add_argument(
        "--manager-ip",
        required=False,
        help=(
            "Manager LAN IP expected as chrony source. "
            "If omitted, auto-detected from route to target hosts."
        ),
    )
    parser.add_argument(
        "--hosts", help="Comma-separated host list (e.g. host1,host2,host3)")
    parser.add_argument(
        "--topology",
        help="Topology JSON path to resolve hosts from hosts[].host_name",
    )
    parser.add_argument("--ssh-user", default=DEFAULT_SSH_USER,
                        help=f"SSH user (default: {DEFAULT_SSH_USER})")
    parser.add_argument(
        "--chrony-conf",
        default=DEFAULT_CHRONY_CONF,
        help=f"Chrony config path on Hosts (default: {DEFAULT_CHRONY_CONF})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Output directory (relative to repository root or absolute path, "
            f"default: {DEFAULT_OUTPUT_DIR})"
        ),
    )
    return parser.parse_args()


def parse_hosts_csv(hosts_csv: str) -> list[str]:
    hosts = [h.strip() for h in hosts_csv.split(",") if h.strip()]
    if not hosts:
        raise ValueError("resolved host list is empty")
    return hosts


def infer_local_ip_to_host(host: str) -> str:
    """Infer local source IP that would be used to reach the given host."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, 123))
            return str(sock.getsockname()[0])
    except OSError as exc:
        raise ValueError(
            f"failed to infer local IP toward host '{host}': {exc}") from exc


def detect_manager_ip(hosts: list[str]) -> tuple[str, dict[str, str]]:
    by_host: dict[str, str] = {}
    for host in hosts:
        by_host[host] = infer_local_ip_to_host(host)

    unique_ips = sorted(set(by_host.values()))
    if not unique_ips:
        raise ValueError("failed to auto-detect manager IP from target hosts")
    if len(unique_ips) > 1:
        details = ", ".join(f"{host}->{ip}" for host, ip in by_host.items())
        raise ValueError(
            "auto-detected multiple local Manager IPs toward Hosts "
            f"({details}). Use --manager-ip explicitly."
        )

    return unique_ips[0], by_host


def resolve_topology_path(repo_root: Path, topology_arg: str) -> Path:
    path = Path(topology_arg)
    if path.is_absolute():
        return path
    return repo_root / path


def parse_hosts_from_topology(topology_path: Path) -> list[str]:
    try:
        with topology_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ValueError(
            f"failed to read topology file: {topology_path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid topology JSON: {topology_path} ({exc})") from exc

    hosts_raw = data.get("hosts")
    if not isinstance(hosts_raw, list) or not hosts_raw:
        raise ValueError("topology JSON must contain non-empty 'hosts' array")

    hosts: list[str] = []
    for idx, item in enumerate(hosts_raw):
        if not isinstance(item, dict):
            raise ValueError(f"topology hosts[{idx}] must be an object")
        host_name = str(item.get("host_name", "")).strip()
        if not host_name:
            raise ValueError(
                f"topology hosts[{idx}].host_name is missing or empty")
        hosts.append(host_name)

    return hosts


def resolve_output_dir(repo_root: Path, output_dir_arg: str) -> Path:
    path = Path(output_dir_arg)
    if path.is_absolute():
        return path
    return repo_root / path


def update_latest_alias(output_dir: Path, run_dir: Path) -> tuple[bool, str]:
    latest_link = output_dir / "latest"
    rel_target = Path(run_dir.name)
    try:
        if latest_link.is_symlink() or latest_link.exists():
            if latest_link.is_dir() and not latest_link.is_symlink():
                return False, f"{latest_link} exists as a directory; could not update alias"
            latest_link.unlink()
        latest_link.symlink_to(rel_target)
        return True, str(latest_link)
    except OSError as exc:
        return False, f"failed to create latest alias: {exc}"


def run_ssh(host: str, ssh_user: str, remote_cmd: str) -> tuple[bool, str, str]:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=5",
        f"{ssh_user}@{host}",
        remote_cmd,
    ]
    cp = subprocess.run(cmd, text=True, capture_output=True)
    return cp.returncode == 0, (cp.stdout or "").strip(), (cp.stderr or "").strip()


def parse_manager_row(raw_sources: str, manager_ip: str) -> tuple[bool, str, str]:
    for line in raw_sources.splitlines():
        line = line.strip()
        if not line:
            continue
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 6:
            continue

        source_name = cols[2].strip("[]")
        if source_name != manager_ip:
            continue

        state = cols[1]
        reach = cols[5]
        return True, state, reach

    return False, "", ""


def check_host(host: str, args: argparse.Namespace) -> HostCheckResult:
    ssh_ok, active_out, active_err = run_ssh(
        host,
        args.ssh_user,
        "systemctl is-active chrony 2>/dev/null || true",
    )
    if not ssh_ok:
        return HostCheckResult(
            host=host,
            ssh_ok=False,
            chrony_active=False,
            manager_source_found=False,
            manager_state="",
            manager_reach="",
            configured_with_manager_ip=False,
            status="error",
            issue=f"ssh failed: {active_err or active_out or 'no details'}",
            hint="Check host reachability, SSH key, and --ssh-user.",
            raw_sources="",
        )

    chrony_active = active_out.strip() == "active"

    conf_cmd = (
        "bash -lc "
        f"'grep -E "
        f"\"^[[:space:]]*(server|pool)[[:space:]]+{args.manager_ip}([[:space:]]|$)\" "
        f"{args.chrony_conf} >/dev/null 2>&1 && echo yes || echo no'"
    )
    _, conf_out, _ = run_ssh(host, args.ssh_user, conf_cmd)
    configured_with_manager_ip = conf_out.strip() == "yes"

    _, sources_out, sources_err = run_ssh(
        host,
        args.ssh_user,
        "chronyc -c -n sources 2>/dev/null || true",
    )

    if not chrony_active:
        return HostCheckResult(
            host=host,
            ssh_ok=True,
            chrony_active=False,
            manager_source_found=False,
            manager_state="",
            manager_reach="",
            configured_with_manager_ip=configured_with_manager_ip,
            status="error",
            issue="chrony service is not active",
            hint="Run: sudo systemctl enable --now chrony",
            raw_sources=sources_out,
        )

    if not sources_out and sources_err:
        return HostCheckResult(
            host=host,
            ssh_ok=True,
            chrony_active=True,
            manager_source_found=False,
            manager_state="",
            manager_reach="",
            configured_with_manager_ip=configured_with_manager_ip,
            status="error",
            issue=f"failed to query sources: {sources_err}",
            hint="Verify chronyc works on host and chronyd is healthy.",
            raw_sources=sources_out,
        )

    found, state, reach = parse_manager_row(sources_out, args.manager_ip)

    if not found:
        issue = f"Manager source {args.manager_ip} not found in chronyc sources"
        hint = (
            "Host may reference a different source. Check /etc/chrony/chrony.conf "
            "server/pool lines and restart chrony."
        )
        status = "error" if not configured_with_manager_ip else "warn"
        return HostCheckResult(
            host=host,
            ssh_ok=True,
            chrony_active=True,
            manager_source_found=False,
            manager_state="",
            manager_reach="",
            configured_with_manager_ip=configured_with_manager_ip,
            status=status,
            issue=issue,
            hint=hint,
            raw_sources=sources_out,
        )

    reach_zero = reach == "0"
    if state in ("*", "+") and not reach_zero:
        return HostCheckResult(
            host=host,
            ssh_ok=True,
            chrony_active=True,
            manager_source_found=True,
            manager_state=state,
            manager_reach=reach,
            configured_with_manager_ip=configured_with_manager_ip,
            status="ok",
            issue="",
            hint="",
            raw_sources=sources_out,
        )

    if reach_zero or state in ("?", "x"):
        return HostCheckResult(
            host=host,
            ssh_ok=True,
            chrony_active=True,
            manager_source_found=True,
            manager_state=state,
            manager_reach=reach,
            configured_with_manager_ip=configured_with_manager_ip,
            status="error",
            issue=(
                f"Manager source present but not reachable/stable (state='{state}', reach='{reach}')"
            ),
            hint=(
                "Possible Manager allow/firewall/subnet mismatch. Verify Manager chrony allow CIDR, "
                "UDP/123 firewall rule, and that --manager-ip is correct."
            ),
            raw_sources=sources_out,
        )

    return HostCheckResult(
        host=host,
        ssh_ok=True,
        chrony_active=True,
        manager_source_found=True,
        manager_state=state,
        manager_reach=reach,
        configured_with_manager_ip=configured_with_manager_ip,
        status="warn",
        issue=f"Manager source is not selected yet (state='{state}', reach='{reach}')",
        hint="Wait for convergence: sudo chronyc waitsync 20 0.001",
        raw_sources=sources_out,
    )


def write_summary_csv(path: Path, rows: list[HostCheckResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "host",
                "status",
                "ssh_ok",
                "chrony_active",
                "configured_with_manager_ip",
                "manager_source_found",
                "manager_state",
                "manager_reach",
                "issue",
                "hint",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.host,
                    r.status,
                    int(r.ssh_ok),
                    int(r.chrony_active),
                    int(r.configured_with_manager_ip),
                    int(r.manager_source_found),
                    r.manager_state,
                    r.manager_reach,
                    r.issue,
                    r.hint,
                ]
            )


def write_sources_csv(path: Path, rows: list[HostCheckResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["host", "raw_sources_csv"])
        for r in rows:
            writer.writerow([r.host, r.raw_sources])


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    hosts_from_arg: list[str] = []
    if args.hosts:
        try:
            hosts_from_arg = parse_hosts_csv(args.hosts)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    hosts_from_topology: list[str] = []
    topology_path: Path | None = None
    if args.topology:
        topology_path = resolve_topology_path(repo_root, args.topology)
        try:
            hosts_from_topology = parse_hosts_from_topology(topology_path)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if not hosts_from_arg and not hosts_from_topology:
        print("ERROR: either --hosts or --topology must be specified", file=sys.stderr)
        return 2

    if hosts_from_arg and hosts_from_topology and hosts_from_arg != hosts_from_topology:
        print(
            "WARNING: --hosts and --topology host list mismatch; check is aborted.",
            file=sys.stderr,
        )
        print(f"  --hosts    : {', '.join(hosts_from_arg)}", file=sys.stderr)
        print(
            f"  --topology : {', '.join(hosts_from_topology)} (from {topology_path})",
            file=sys.stderr,
        )
        return 1

    hosts = hosts_from_arg if hosts_from_arg else hosts_from_topology

    manager_ip = args.manager_ip
    auto_detected = False
    detected_map: dict[str, str] = {}
    if not manager_ip:
        try:
            manager_ip, detected_map = detect_manager_ip(hosts)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        auto_detected = True
    args.manager_ip = manager_ip

    output_dir = resolve_output_dir(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = run_dir / "summary.csv"
    sources_csv = run_dir / "sources_raw.csv"
    result_log = run_dir / "result.log"

    with result_log.open("w", encoding="utf-8") as log_fh:
        def out(message: str = "") -> None:
            print(message)
            log_fh.write(f"{message}\n")
            log_fh.flush()

        out("=== Chrony Manager Sync Check ===")
        if auto_detected:
            out(f"manager_ip    : {args.manager_ip} (auto-detected)")
            out("manager_ip_map:")
            for host in hosts:
                out(f"  {host} -> {detected_map.get(host, 'N/A')}")
        else:
            out(f"manager_ip    : {args.manager_ip}")
        if hosts_from_arg and hosts_from_topology:
            out("host_source   : hosts+topology (validated)")
            out(f"topology      : {topology_path}")
        elif hosts_from_arg:
            out("host_source   : hosts")
        else:
            out("host_source   : topology")
            out(f"topology      : {topology_path}")
        out(f"hosts         : {' '.join(hosts)}")
        out(f"ssh_user      : {args.ssh_user}")
        out(f"chrony_conf   : {args.chrony_conf}")
        out(f"run_dir       : {run_dir}")
        out("")

        rows: list[HostCheckResult] = []
        for host in hosts:
            r = check_host(host, args)
            rows.append(r)
            if r.status == "ok":
                out(
                    f"[{host}] OK: state={r.manager_state} reach={r.manager_reach} "
                    f"configured_with_manager_ip={r.configured_with_manager_ip}"
                )
            else:
                out(f"[{host}] {r.status.upper()}: {r.issue}")
                if r.hint:
                    out(f"[{host}] hint: {r.hint}")

        write_summary_csv(summary_csv, rows)
        write_sources_csv(sources_csv, rows)

        latest_ok, latest_msg = update_latest_alias(output_dir, run_dir)

        out("")
        out("=== Output ===")
        out(f"summary : {summary_csv}")
        out(f"sources : {sources_csv}")
        out(f"result  : {result_log}")
        if latest_ok:
            out(f"latest  : {latest_msg}")
        else:
            out(f"latest  : unavailable ({latest_msg})")

        errors = [r for r in rows if r.status == "error"]
        warns = [r for r in rows if r.status == "warn"]
        out("")
        out(f"status_counts: ok={len(rows) - len(errors) - len(warns)} warn={len(warns)} error={len(errors)}")

        if errors:
            out("Completed with errors.")
            return 1

        if warns:
            out("Completed with warnings.")
            return 0

        out("Completed successfully.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
