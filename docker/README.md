# docker ディレクトリ（開発者向け）

このディレクトリは、利用者向けの実行環境ではなく、開発者が共通Dockerイメージをビルドして GitHub Packages (GHCR) に公開するための管理ディレクトリです。

利用者はこのディレクトリで build する必要はありません．公開済みイメージを pull して使ってもらう運用想定です。

- 公開イメージ: [`ghcr.io/hal-lab-u-tokyo/ros2-perf-multihost:latest`](https://github.com/hal-lab-u-tokyo/ros2-perf-multihost/pkgs/container/ros2-perf-multihost)

## GHCR ログイン

```bash
docker login ghcr.io -u <YOUR_GITHUB_USERNAME>
### input "<YOUR_GITHUB_PAT>"
```

## ビルド

このディレクトリの `compose.yaml` は `linux/amd64` と `linux/arm64` を対象にしています。
`Dockerfile` は build context の中身を `/workdir/ros2-perf-multihost/` にコピーする前提なので、build context はリポジトリルート（`..`）です。

```bash
cd docker
docker buildx bake --load
```

## Push

```bash
cd docker
docker buildx bake --push
```
