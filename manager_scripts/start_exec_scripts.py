"""
Unified script to start test execution on all hosts.
Supports both Docker and native execution modes.

Usage:
  # Docker mode (sends /start_docker requests)
    python3 start_exec_scripts.py --exec-policy docker <run_idx> <num_hosts> [ws_dir] [scenario] [hosts_list]

  # Native mode (sends /start requests)
    python3 start_exec_scripts.py --exec-policy native <run_idx> <num_hosts> [ws_dir] [scenario] [hosts_list]
"""

import requests
import threading
import sys
import os
import argparse


def get_metadata_value(key, metadata_path):
    """Extract a value from metadata.txt by key."""
    try:
        with open(metadata_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}:"):
                    return line[len(key) + 1:].strip()
    except (FileNotFoundError, IOError):
        pass
    return None


def resolve_host_list(ws_dir, scenario, num_hosts):
    """Resolve host list from environment or metadata.txt."""
    # Check environment variable first
    env_hosts = os.environ.get("ROS2_PERF_HOSTS")
    if env_hosts:
        hosts = [h.strip() for h in env_hosts.split(",") if h.strip()]
        return hosts[:num_hosts] if num_hosts else hosts

    # Read from metadata.txt (required)
    metadata_path = os.path.join(ws_dir, scenario, "metadata.txt")
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"metadata.txt not found: {metadata_path}")

    # Try deployment_hosts first, then hosts
    metadata_hosts = get_metadata_value("deployment_hosts", metadata_path)
    if not metadata_hosts:
        metadata_hosts = get_metadata_value("hosts", metadata_path)

    if not metadata_hosts:
        raise ValueError(
            f"No hosts found in {metadata_path}. "
            "Define 'hosts' or 'deployment_hosts' in metadata.txt"
        )

    hosts = [h.strip() for h in metadata_hosts.split(",") if h.strip()]
    return hosts[:num_hosts] if num_hosts else hosts


def main():
    parser = argparse.ArgumentParser(
        description="Start test execution on all hosts (Docker or native)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Docker mode
    python3 start_exec_scripts.py --exec-policy docker 1 3 performance_ws latest host1,host2,host3

  # Native mode
    python3 start_exec_scripts.py --exec-policy native 1 3 performance_ws latest host1,host2,host3
        """
    )
    parser.add_argument(
        "--exec-policy",
        choices=["docker", "native"],
        default="docker",
        help="Execution mode. docker sends /start_docker, native sends /start (default: docker)",
    )
    parser.add_argument("run_idx", type=int,
                        help="Run index (trial number)")
    parser.add_argument("num_hosts", type=int,
                        help="Number of hosts to use from metadata")
    parser.add_argument("ws_dir", nargs="?", default="performance_ws",
                        help="Workspace directory (default: performance_ws)")
    parser.add_argument("scenario", nargs="?", default="latest",
                        help="Scenario directory name (default: latest)")
    parser.add_argument("hosts_list", nargs="?", default=None,
                        help="Comma-separated list of hosts (optional; if not provided, resolved from metadata)")

    # Parse known args to support backward compatibility
    args, unknown = parser.parse_known_args()

    # Support old command-line style (backward compatibility)
    # Old style: python3 start_scripts.py <payload_size> <num_hosts> <run_idx> [ws_dir] [scenario] [hosts_list]
    # New style: python3 start_exec_scripts.py [--exec-policy {docker,native}] <run_idx> <num_hosts> [ws_dir] [scenario] [hosts_list]
    if len(sys.argv) >= 2 and not sys.argv[1].startswith("-"):
        # Old style: first arg is positional
        if len(sys.argv) < 4:
            print("ERROR: Insufficient arguments", file=sys.stderr)
            parser.print_help()
            sys.exit(1)

    run_idx = args.run_idx
    num_hosts = args.num_hosts
    ws_dir = args.ws_dir
    scenario = args.scenario
    hosts_list = args.hosts_list

    # Support host list from parameter or resolve from metadata
    if hosts_list:
        # Host list passed from performance_test.py (comma-separated)
        hosts = [h.strip() for h in hosts_list.split(",") if h.strip()]
    else:
        # Resolve from environment or metadata
        try:
            hosts = resolve_host_list(ws_dir, scenario, num_hosts)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    if not hosts:
        print("ERROR: No hosts to process", file=sys.stderr)
        sys.exit(1)

    # Read test parameters from environment only when explicitly provided.
    payload_size = os.environ.get("PAYLOAD_SIZE")
    period_ms = os.environ.get("PERIOD_MS")
    eval_time = os.environ.get("EVAL_TIME")

    # Determine endpoint and timeout based on mode
    if args.exec_policy == "docker":
        endpoint = "/start_docker"
        timeout = (5, 300)  # (connect, read) in seconds
        print(f"Using Docker mode: {endpoint} endpoint with timeout {timeout}")
    else:
        endpoint = "/start"
        timeout = 100  # seconds
        print(
            f"Using native mode: {endpoint} endpoint with timeout {timeout}s")

    failed_hosts = []
    lock = threading.Lock()

    def start(host):
        try:
            if args.exec_policy == "docker":
                print(
                    f"{host}: sending {endpoint} request (Docker mode)...", flush=True)
            else:
                print(f"{host}: sending {endpoint} request...", flush=True)

            request_body = {
                "run_idx": run_idx,
                "ws_dir": ws_dir,
                "scenario": scenario,
            }
            if payload_size is not None:
                request_body["payload_size"] = payload_size
            if period_ms is not None:
                request_body["period_ms"] = period_ms
            if eval_time is not None:
                request_body["eval_time"] = eval_time

            r = requests.post(
                f"http://{host}:5000{endpoint}",
                json=request_body,
                timeout=timeout,
            )
            if r.status_code < 200 or r.status_code >= 300:
                print(
                    f"{host}: ERROR status code {r.status_code}: {r.text}", file=sys.stderr)
                with lock:
                    failed_hosts.append(host)
            else:
                print(f"{host}: {r.status_code} {r.text}")
        except Exception as e:
            print(f"{host}: ERROR {e}", file=sys.stderr)
            with lock:
                failed_hosts.append(host)

    # Start requests in parallel
    threads = []
    for host in hosts:
        t = threading.Thread(target=start, args=(host,))
        t.start()
        threads.append(t)

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Check for failures
    if failed_hosts:
        print(
            f"ERROR: {len(failed_hosts)}/{len(hosts)} host(s) failed: {failed_hosts}", file=sys.stderr)
        sys.exit(1)

    print(f"Successfully started on all {len(hosts)} hosts")


if __name__ == "__main__":
    main()
