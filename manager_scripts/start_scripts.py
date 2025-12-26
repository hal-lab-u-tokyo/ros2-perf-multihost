import requests
import threading
import sys


def main():
    if len(sys.argv) < 3:
        print("Usage: python start_scripts.py <payload_size> <num_hosts>")
        sys.exit(1)
    payload_size = sys.argv[1]
    num_hosts = int(sys.argv[2])

    all_hosts = ["pi0", "pi1", "pi2", "pi3", "pi4"]  # 必要に応じて拡張
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
