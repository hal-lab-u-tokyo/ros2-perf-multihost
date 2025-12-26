import requests
import threading
import sys


def main():
    if len(sys.argv) < 3:
        print("Usage: python start_scripts.py <payload_size> <num_hosts>")
        sys.exit(1)
    payload_size = sys.argv[1]
    num_hosts = int(sys.argv[2])

    all_hosts = [
        "192.168.199.20",  # pi0
        "192.168.199.21",  # pi1
        "192.168.199.22",  # pi2
        "192.168.199.23",  # pi3
        "192.168.199.24",  # pi4
    ]
    hosts = all_hosts[:num_hosts]

    def start(host):
        try:
            r = requests.post(f"http://{host}:5000/start", json={"payload_size": payload_size}, timeout=2)
            print(f"{host}: {r.status_code} {r.text}")
        except Exception as e:
            print(f"{host}: error {e}")

    threads = []
    for host in hosts:
        t = threading.Thread(target=start, args=(host,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
