# ROS 2 RMW Analysis Scripts

このフォルダは、実験実行後にユーザーが手動で分析コマンドを実行するためのスクリプト集です。
実験完了時に自動で図表やPDFを出力する前提ではありません。

## 前提

- Python 3.11 以降
- 入力データの標準置き場は `program/data`
- 出力先は `program/outputs` と `program/output/pdf`
- 現在の実験結果は `results/latest-<rmw>/analysis` 配下にCSVが出るため、分析前に `import_repo_results.py` で `program/data` へ取り込みます。
- `--ws-dir` の標準値は `performance_ws` です。`ros2_node_impl_ws` など別の作業ディレクトリで実験した場合は `--ws-dir ros2_node_impl_ws` を指定してください。
- ジッターは raw log から受信間隔を計算し、設定周期 100 ms からの平均絶対ずれとして扱います。raw log に周期情報がある場合は、その値を優先します。
- メッセージロスト数は、受信した message index の欠番から算出しています。

## セットアップ

```bash
cd /Users/kudoutakumi/ros2-perf-multihost/program
python3 -m pip install -r requirements.txt
```

## 実験結果の取り込み

QoS sweep の FastDDS docker 結果を取り込む例:

```bash
python3 import_repo_results.py qos-rmw \
  --topology <topology_name> \
  --rmw fastdds \
  --exec-policy docker
```

CycloneDDS docker の QoS sweep:

```bash
python3 import_repo_results.py qos-rmw \
  --topology <topology_name> \
  --rmw cyclonedds \
  --exec-policy docker
```

Zenoh の QoS sweep:

```bash
python3 import_repo_results.py zenoh-qos \
  --topology <topology_name> \
  --rmw zenoh \
  --exec-policy native
```

RMW比較用の通常実験:

```bash
python3 import_repo_results.py rmw-constant \
  --topology <topology_name> \
  --rmw fastdds \
  --exec-policy docker
```

payload sweep:

```bash
python3 import_repo_results.py payload \
  --topology <topology_name> \
  --rmw fastdds \
  --exec-policy docker \
  --payload payload1K
```

`--result-dir` を指定すると、任意の `results/latest-...` ディレクトリを直接取り込めます。

```bash
python3 import_repo_results.py qos-rmw \
  --result-dir /path/to/results/latest-fastdds \
  --rmw fastdds \
  --exec-policy docker
```

標準の取り込み先は以下です。

| 種類 | 取り込み先 |
| --- | --- |
| `qos-rmw --rmw fastdds --exec-policy docker` | `program/data/qos_variant/fastdds-docker` |
| `qos-rmw --rmw cyclonedds --exec-policy docker` | `program/data/qos_variant/cyclonedds-docker` |
| `zenoh-qos --exec-policy docker` | `program/data/zenoh/docker` |
| `zenoh-qos --exec-policy native` | `program/data/zenoh/native` |
| `rmw-constant` | `program/data/qos_constant/<rmw>/<docker または Native>` |
| `payload` | `program/data/payloadsize_variant/<rmw>-<docker または native>/<payload>` |

## 分析コマンド

raw-data から 1 秒、2 秒、3 秒トリムの集計を作り、主要PDFを再生成します。

```bash
python3 run_all_analysis.py --all
```

主要PDFだけを再生成する場合:

```bash
python3 run_all_analysis.py --trim2s --jitter
```

raw zip を別ディレクトリから読む場合:

```bash
python3 extract_trimmed_metrics_from_raw.py 2 --raw-dir /path/to/raw-data
python3 extract_period_jitter_from_raw.py --raw-dir /path/to/raw-data
```

## 個別スクリプト

| スクリプト | 内容 |
| --- | --- |
| `import_repo_results.py` | 現在のリポジトリの `results/latest-<rmw>/analysis` を分析用レイアウトへ手動取り込み |
| `extract_trimmed_metrics_from_raw.py` | `program/data/raw-data/*.zip` からレイテンシー、メッセージロスト数、スループット、周期ジッターを抽出 |
| `build_trim2s_reports.py` | 先頭 2 秒を除外した RMW比較、QoS比較、Zenoh QoS、payload比較PDFを生成 |
| `build_rmw_comparison_figures.py` / `build_rmw_comparison_pdf.py` | FastDDS、CycloneDDS、Zenoh の RMW比較 |
| `build_qos_rmw_comparison_figures.py` / `build_qos_rmw_comparison_pdf.py` | FastDDS と CycloneDDS の QoS sweep 比較 |
| `build_zenoh_qos_sweep_figures.py` / `build_zenoh_qos_sweep_pdf.py` | Zenoh docker/native の QoS sweep 比較 |
| `build_payloadsize_rmw_comparison_figures.py` / `build_payloadsize_rmw_comparison_pdf.py` | payload size sweep 比較 |
| `build_jitter_trim_comparison_figures.py` / `build_jitter_trim_comparison_pdf.py` | 1 秒トリムと 3 秒トリムのジッター比較 |
| `build_fastdds_docker_qos_sweep_figures.py` / `build_fastdds_docker_qos_sweep_pdf.py` | FastDDS docker 単体の QoS sweep |
| `build_zenoh_native2_figures.py` | Zenoh native2 単体の図生成 |
| `build_fastdds_pdf.py` / `build_paper_style_figures.py` / `build_fastdds_workbook.mjs` | FastDDS docker 用レポート、論文風図、Excel生成 |
| `build_ros_graph_pdf.py` | ROS graph PDF生成 |

## 代表的な出力

| 出力PDF | 生成コマンド |
| --- | --- |
| `output/pdf/rmw_comparison_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/qos_rmw_comparison_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/zenoh_qos_sweep_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/payloadsize_rmw_comparison_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/jitter_trim1s_3s_report.pdf` | `python3 build_jitter_trim_comparison_pdf.py` |

## パスの変更

標準以外の場所にデータや出力を置く場合は、環境変数で変更できます。

| 環境変数 | 内容 |
| --- | --- |
| `ROS2_ANALYSIS_DATA_ROOT` | 入力データ全体のルート |
| `ROS2_ANALYSIS_OUTPUT_ROOT` | 図表や中間CSVの出力先 |
| `ROS2_ANALYSIS_PDF_ROOT` | PDFの出力先 |
| `ROS2_ANALYSIS_RAW_DATA_DIR` | raw zip の入力先 |
| `ROS2_ANALYSIS_QOS_BASE` | FastDDS/CycloneDDS QoS sweep の入力先 |
| `ROS2_ANALYSIS_ZENOH_QOS_BASE` | Zenoh QoS sweep の入力先 |
| `ROS2_ANALYSIS_RMW_BASE` | RMW比較の入力先 |
| `ROS2_ANALYSIS_PAYLOAD_BASE` | payload sweep の入力先 |
