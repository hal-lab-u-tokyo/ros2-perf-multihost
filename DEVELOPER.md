# Developer Guide

This guide is for contributors and users who modify the source code or maintain a private fork. It assumes that the Manager and Hosts are already configured according to [SETUP.md](./SETUP.md).

## Development Workflow

After changing source code, regenerate affected artifacts before running a benchmark:

```bash
cd ~/ros2-perf-multihost
python3 manager_scripts/generate_exec_scripts.py \
  topology_example/simple.json \
  --image-tag <image-tag> \
  --force
```

For `docker` and `native` execution, distribute the generated artifacts manually when you want to inspect or refresh that step separately:

```bash
./manager_scripts/distribute_exec_scripts.sh \
  simple \
  --remote-repo-base /home/ubuntu/ros2-perf-multihost
```

Normal `performance_test.py` runs in `docker` and `native` modes perform this distribution automatically.

Restart the long-running REST servers after updating their checkout:

```bash
./manager_scripts/manage_rest_servers.sh restart \
  --hosts host1,host2,host3 \
  --force
./manager_scripts/manage_rest_servers.sh status \
  --hosts host1,host2,host3
```

## Development Docker Image

For a development branch that changes Docker-executed code or dependencies, build and publish the mutable `:dev` image as described in [docker/README.md](./docker/README.md#development-image-distribution):

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file docker/Dockerfile \
  --tag ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:dev \
  --push \
  .
```

Pull the image on every Docker benchmark Host, then regenerate artifacts with `--image-tag dev`:

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:dev
python3 manager_scripts/generate_exec_scripts.py \
  topology_example/simple.json \
  --image-tag dev \
  --force
```

`:dev` is mutable and is intended for short-lived validation, not reproducible measurements. Record the source Git commit when using it.

## Native Package Rebuild

When changing the ROS 2 node implementation or native dependencies, rebuild the package on every Host that runs native benchmarks:

```bash
cd ~/ros2-perf-multihost
source /opt/ros/jazzy/setup.bash
cd ros2_node_impl_ws
colcon build --packages-select ros2_perf_multihost_nodes
```

## Validation

Use focused checks for the files you changed:

```bash
python3 -m py_compile path/to/changed_file.py
git diff --check
```

`py_compile` checks Python syntax only; it does not replace tests or an end-to-end smoke test.

For a local smoke test:

```bash
python3 performance_test/performance_test.py \
  simple \
  --rmw fastdds \
  --exec-policy local \
  --eval-time 10 \
  --trials 1
```

For multiple RMW implementations:

```bash
python3 performance_test/performance_test.py \
  simple \
  --rmw fastdds,cyclonedds,zenoh \
  --exec-policy native \
  --eval-time 10 \
  --trials 1
```

## Updating a Deployed Development Branch

For a source update on a development branch:

1. Update the Manager and capture the revision.
2. Check out the same revision on every Host.
3. If Docker is used, publish and pull the matching `:dev` image.
4. Rebuild native packages when needed.
5. Regenerate and distribute topology artifacts.
6. Restart the REST servers.
7. Verify the revision and generated `metadata.txt` on the Manager and Hosts.

The detailed image publishing procedures are maintained in [docker/README.md](./docker/README.md). The environment and SSH prerequisites remain in [SETUP.md](./SETUP.md).
