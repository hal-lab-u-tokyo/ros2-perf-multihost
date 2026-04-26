import requests
import threading
import sys
import os


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
    if len(sys.argv) < 4:
        print(
            "Usage: python start_docker_scripts.py <payload_size> <num_hosts> <run_idx> [ws_dir] [scenario] [hosts_list]")
        sys.exit(1)
    payload_size = sys.argv[1]
    num_hosts = int(sys.argv[2])
    run_idx = int(sys.argv[3])
    ws_dir = sys.argv[4] if len(sys.argv) >= 5 else "performance_ws"
    scenario = sys.argv[5] if len(sys.argv) >= 6 else "latest"

    # Support host list from parameter or resolve from metadata
    if len(sys.argv) >= 7 and sys.argv[6]:
        # Host list passed from performance_test.py (comma-separated)
        hosts = [h.strip() for h in sys.argv[6].split(",") if h.strip()]
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

    failed_hosts = []
    lock = threading.Lock()

    def start(host):
        try:
            print(f"{host}: sending /start_docker request...", flush=True)
            r = requests.post(
                f"http://{host}:5000/start_docker",
                json={
                    "payload_size": payload_size,
                    "run_idx": run_idx,
                    "ws_dir": ws_dir,
                    "scenario": scenario,
                },
                timeout=(5, 300),
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

    threads = []
    for host in hosts:
        t = threading.Thread(target=start, args=(host,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    if failed_hosts:
        print(
            f"ERROR: {len(failed_hosts)}/{len(hosts)} hosts failed: {', '.join(failed_hosts)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
