import requests
import threading
import sys
import time


def main():
    if len(sys.argv) < 4:
        print("Usage: python start_docker_scripts.py <payload_size> <num_hosts> <run_idx>")
        sys.exit(1)
    payload_size = sys.argv[1]
    num_hosts = int(sys.argv[2])
    run_idx = int(sys.argv[3])

    all_hosts = [
        "192.168.11.106",
        "192.168.11.107",
        "192.168.11.108",
    ]
    hosts = all_hosts[:num_hosts]

    def start(host):
        try:
            started_at = time.time()
            print(f"{host}: sending /start_docker request...", flush=True)
            r = requests.post(
                f"http://{host}:5000/start_docker",
                json={"payload_size": payload_size, "run_idx": run_idx},
                timeout=(5, 300),
            )
            elapsed = time.time() - started_at
            print(f"{host}: {r.status_code} ({elapsed:.1f}s) {r.text}")
        except Exception as e:
            elapsed = time.time() - started_at
            print(f"{host}: error ({elapsed:.1f}s) {e}")

    threads = []
    for host in hosts:
        t = threading.Thread(target=start, args=(host,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
