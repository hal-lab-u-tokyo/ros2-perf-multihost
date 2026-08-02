# docker Directory for Developers

This directory is for maintainers who build the shared Docker image and publish it to GitHub Packages (GHCR). It is not part of the normal runtime workflow for end users.

Users are not expected to build the image from this directory. The intended workflow is to pull the published image instead.

- Published image: [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost)

## Log In to GHCR

```bash
docker login ghcr.io -u <YOUR_GITHUB_USERNAME>
# enter "<YOUR_GITHUB_PAT>" when prompted
```

## Build

`compose.yaml` in this directory targets both `linux/amd64` and `linux/arm64`.
The `Dockerfile` expects the build context to be copied into `/workdir/ros2-perf-multihost/`, so the build context must be the repository root (`..`).

```bash
cd docker
docker buildx bake --load
```

## Push

```bash
cd docker
docker buildx bake --push
```
