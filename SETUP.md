# SETUP

This document describes one-time environment preparation steps for Manager and Hosts.

## Requirements

Here is the baseline environment we have tested so far.

- Ubuntu 24.04
- Verified devices: Raspberry Pi 4 and Raspberry Pi 5.
  - Other devices or servers should also work if Ubuntu 24.04 is available.
- User and repository path assumption:
  - Scripts and examples in this repository assume user `ubuntu` and `/home/ubuntu/ros2-perf-multihost`.
  - If your username and path differ, how to override these settings is described later.
  - The default `ubuntu` user needs passwordless `sudo` only for `chronyc` (described later).

## SSH access (on the Manager)

This framework assumes that the Manager can SSH into each Host by hostname only, without a password (using key-based authentication).
Therefore, configure the following settings on the Manager machine to meet this requirement.

- Generate and register SSH keys (e.g., `ssh-keygen -t ed25519 && ssh-copy-id ubuntu@host1`).
- Ensure hostnames are resolvable from the Manager.
- Consider assigning static IP addresses to each Host to avoid SSH connectivity issues after a reboot or DHCP lease renewal.
- Recommended Manager-side configuration examples:
  - `/etc/hosts`:
    ```text
    <snipped.>
    192.168.10.11 host1
    192.168.10.12 host2
    192.168.10.13 host3
    <snipped.>
    ```
  - `~/.ssh/config`:
    ```text
    Host host1
        User ubuntu
        IdentityFile ~/.ssh/id_ed25519
    Host host2
        User ubuntu
        IdentityFile ~/.ssh/id_ed25519
    Host host3
        User ubuntu
        IdentityFile ~/.ssh/id_ed25519
    ```

## Clone this repository

Clone this repository on each Host. We recommend cloning it into the home directory.

```bash
cd ~
git clone https://github.com/hal-lab-u-tokyo/ros2-perf-multihost.git
```

## Docker and the published image

Install Docker Engine and enable non-root usage.

- Follow the official [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) guide.
- To run Docker commands as a non-root user, add your user to the `docker` group:
  ```bash
  sudo usermod -aG docker $USER
  ```
  Then log out and log back in, or run `newgrp docker` to update the group membership.

Pull the published GitHub Packages image [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost).

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest
```

For details on the Docker image, see [docker/README.md](./docker/README.md).

## [Optional] Native ROS 2 Environment

If you want to evaluate native execution mode as well, install ROS 2 and build the package.

Follow the official [ROS 2 Jazzy Installation steps](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html).
Other ROS 2 distributions may also work, but they are not officially tested yet.

To benchmark with non-default RMW implementations, install the corresponding packages:

```bash
# For CycloneDDS (rmw_cyclonedds_cpp)
sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp

# For Zenoh (rmw_zenoh_cpp)
sudo apt install -y ros-jazzy-rmw-zenoh-cpp
```

Then, build the ROS 2 package used by this framework in `ros2_node_impl_ws/` (see [ros2_node_impl_ws/README.md](./ros2_node_impl_ws/README.md) for details on ROS 2 node features).

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_node_impl_ws
colcon build --packages-select ros2_perf_multihost_nodes
```

It is recommended to add the following to your `~/.bashrc` so the built package is automatically sourced in every shell session:

```bash
echo "source ~/ros2-perf-multihost/ros2_node_impl_ws/install/local_setup.bash" >> ~/.bashrc
```

## Python dependencies

Install the following packages on each target Host:

```bash
sudo apt update
sudo apt install -y python3-flask python3-psutil
```

Note that the `python3-requests` package is required on the Manager machine.
Therefore, install the following package on the Manager (not on each Host):

```bash
sudo apt update
sudo apt install -y python3-requests
```

## Clock synchronization for REST benchmark (chrony)

For remote benchmark reproducibility, the REST server uses [chrony](https://chrony-project.org/) to synchronize the clock between Hosts.

Use the following procedure when you want all Hosts to synchronize to the Manager as the LAN-side NTP server.

Important: install and enable `chrony` on both Manager and all Hosts.

1) Install and enable chrony on all machines (Manager and each Host)

```bash
# on Manager and each Host
sudo apt update
sudo apt install -y chrony
sudo systemctl enable --now chrony
```

2) Manager: allow LAN clients and keep upstream time source

In the examples below, replace `192.168.0.0/24` with your actual LAN subnet.

Edit `/etc/chrony/chrony.conf` on the Manager and add/update entries like the following:

```conf
# Manager uses upstream sources (example)
pool ntp.ubuntu.com        iburst maxsources 4
pool 0.ubuntu.pool.ntp.org iburst maxsources 1
pool 1.ubuntu.pool.ntp.org iburst maxsources 1
pool 2.ubuntu.pool.ntp.org iburst maxsources 2

# Add: allow Hosts in your LAN to query this Manager
allow 192.168.0.0/24
```

Then reload/restart chrony and verify:

```bash
# on Manager
sudo systemctl restart chrony
chronyc sources -v
chronyc tracking
```

If UFW is enabled on Manager, allow NTP from LAN Hosts:

```bash
# Replace 192.168.0.0/24 with your actual LAN subnet
sudo ufw allow from 192.168.0.0/24 to any port 123 proto udp
```

3) Hosts: configure chrony to use Manager

Replace `<MANAGER_LAN_IP>` with the actual IP of your Manager on the same LAN as Hosts.

On each Host, edit `/etc/chrony/chrony.conf` and set the Manager as source:

```conf
# Disable or remove default pool/server lines, then set Manager
server <MANAGER_LAN_IP> iburst prefer
```

Apply and verify on each Host:

```bash
# on each Host
sudo systemctl restart chrony
chronyc sources -v
chronyc tracking
```

You can also wait until correction converges on each Host:

```bash
sudo chronyc waitsync 20 0.001
```

After applying Manager/Host chrony settings, run the Manager-side checker below to validate that each Host is actually synchronized to the expected Manager source and to catch likely `allow` CIDR/firewall mistakes:

```bash
python3 manager_scripts/system_perf/check_chrony_manager_sync.py \
  --hosts host1,host2,host3

# optional: resolve Hosts from topology JSON instead
python3 manager_scripts/system_perf/check_chrony_manager_sync.py \
  --topology topology_example/simple.json
```

`--hosts` is the primary input. `--topology` is optional and can be used when you want to resolve host names from a topology JSON.
With the current topology schema, host names are resolved from `hosts[].host_name`.

`--manager-ip` is optional. If omitted, the script auto-detects the Manager local IP from the route to target Hosts.
If your Manager has multiple NICs/routes and auto-detection becomes ambiguous, specify `--manager-ip` explicitly.

For options and output fields, see [manager_scripts/system_perf/README.md#check_chrony_manager_syncpy](./manager_scripts/system_perf/README.md#check_chrony_manager_syncpy).

Because the REST server invokes `sudo -n chronyc` (non-interactive), the `ubuntu` user must be allowed to run `chronyc` via `sudo` without a password.
The sudoers entry below grants passwordless `sudo` only for `/usr/bin/chronyc`, so no other commands are affected.

Check the permission, and if needed, configure the sudoers entry on each Host as follows:

```bash
# Check the permission required by rest_server.py (makestep)
sudo -k
sudo -n chronyc -a makestep

# If this command fails because a password is required, configure the sudoers entry as follows.
cat <<'EOF' | sudo tee /etc/sudoers.d/ros2-perf-chrony
ubuntu ALL=(root) NOPASSWD:/usr/bin/chronyc
EOF
sudo chmod 440 /etc/sudoers.d/ros2-perf-chrony
```

If startup sync fails because `sudo` for `chronyc` requires a password, `rest_server.py` exits and prints guidance with the setup URL.
For other startup sync failures (for example, temporary NTP reachability issues), the server continues startup by default and reports the error in logs. To fail fast on any startup sync failure, set `ROS2_PERF_CHRONY_FAIL_FAST_ON_STARTUP=1`.

For details on synchronization behavior and environment variables, see [remote_hosts_scripts/README.md](./remote_hosts_scripts/README.md#clock-synchronization-chrony).
