# Docker Image Maintenance

This directory is for maintainers of the shared GitHub Container Registry (GHCR)
image. It is not part of the normal runtime workflow for end users.

Users should pull the published image rather than building it locally. The
script generator selects `latest` for untagged commits and the matching image
tag for an exact `v*` Git tag.

- Published image: [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost)

## Automated Publishing

[publish-docker.yml](../.github/workflows/publish-docker.yml) publishes the
multi-architecture image automatically:

- A push to `main` publishes `:latest`.
- A push of a `v*` Git tag publishes the same image tag, such as `:v0.4.0`.

Creating a GitHub Release with a new tag therefore publishes the corresponding
versioned image. The workflow can also be run manually from GitHub Actions: run
it from the source ref to build, and provide the image tag to publish.

## Development Image Distribution

Use the mutable `:dev` tag to distribute the current development branch to all
benchmark hosts without building the image on every host. Publish it only after
the branch builds and the intended changes have been pushed to GitHub.

```bash
docker buildx build \
	--platform linux/amd64,linux/arm64 \
	--file docker/Dockerfile \
	--tag ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:dev \
	--push \
	.
```

Then pull the image on every benchmark host:

```bash
docker pull ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:dev
```

`dev` is intentionally overwritten by later development builds. It is suitable
for short-lived validation, but not for recording reproducible benchmark
results. Use a version tag for release measurements, and retain the Git commit
SHA in experiment notes when a `dev` image is used.

Do not change `compose.yaml` for this workflow. It is a local multi-platform
build definition; topology-specific Compose files are generated separately and
should select the image tag used for each experiment.

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

Run all commands in this document from the repository root. `docker/compose.yaml`
targets both `linux/amd64` and `linux/arm64`, and the `Dockerfile` uses the
repository root as its build context.

```bash
docker buildx bake -f docker/compose.yaml --load
```

## Push

The following publishes `latest` from the current checkout. Only do this when
that checkout is the intended `main` revision.

```bash
docker buildx bake -f docker/compose.yaml --push
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
