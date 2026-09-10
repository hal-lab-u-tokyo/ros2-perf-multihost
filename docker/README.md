# Docker Image Maintenance

This directory is for maintainers of the shared GitHub Container Registry (GHCR)
image. It is not part of the normal runtime workflow for end users.

Users should pull the published image rather than building it locally. They use
`latest` with the current `main` branch, or an image tag matching their checked
out release tag.

- Published image: [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost)

## Automated Publishing

[publish-docker.yml](../.github/workflows/publish-docker.yml) publishes the
multi-architecture image automatically:

- A push to `main` publishes `:latest`.
- A push of a `v*` Git tag publishes the same image tag, such as `:v0.4.0`.

Creating a GitHub Release with a new tag therefore publishes the corresponding
versioned image. The workflow can also be run manually from GitHub Actions: run
it from the source ref to build, and provide the image tag to publish.

## Manual Publishing

Use manual publishing only to recover from a failed workflow or when an
intentional manual publish is required. Avoid overwriting an existing versioned
tag, because it prevents reproducible benchmark environments.

## Log In to GHCR

```bash
docker login ghcr.io -u <YOUR_GITHUB_USERNAME>
# enter "<YOUR_GITHUB_PAT>" when prompted
```

## Local Build

`compose.yaml` in this directory targets both `linux/amd64` and `linux/arm64`.
The `Dockerfile` expects the build context to be copied into `/workdir/ros2-perf-multihost/`, so the build context must be the repository root (`..`).

```bash
cd docker
docker buildx bake --load
```

## Push

The following publishes `latest` from the current checkout. Only do this when
that checkout is the intended `main` revision.

```bash
cd docker
docker buildx bake --push
```

To publish a versioned image manually, run this command from the repository
root and replace `<tag>` with the matching Git tag:

```bash
docker buildx build \
	--platform linux/amd64,linux/arm64 \
	--file docker/Dockerfile \
	--tag ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:<tag> \
	--push \
	.
```
