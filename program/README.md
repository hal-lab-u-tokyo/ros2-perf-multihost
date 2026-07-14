# ROS 2 RMW Analysis Scripts

このフォルダは、これまで作成したグラフ化・PDF化処理を再実行するための分析スクリプト集です。

## 前提

- Python 3.11 以降
- 入力データは主に `~/Downloads` 配下の測定フォルダを参照します。
- 出力先は、このフォルダをカレントディレクトリにして実行した場合、`program/outputs` と `program/output/pdf` です。
- ジッターは raw log から受信間隔を計算し、設定周期 100 ms からの平均絶対ずれとして扱います。raw log に周期情報がある場合は、その値を優先します。
- メッセージロスト数は、受信した message index の欠番から算出しています。

## セットアップ

```bash
cd "/Users/kudoutakumi/Documents/csvグラフ化(pdf)/program"
python3 -m pip install -r requirements.txt
```

## 標準実行

raw-data から 1 秒、2 秒、3 秒トリムの集計を作り、主要PDFを再生成します。

```bash
python3 run_all_analysis.py --all
```

主要PDFだけを再生成する場合:

```bash
python3 run_all_analysis.py --trim2s --jitter
```

## 個別スクリプト

| スクリプト | 内容 |
| --- | --- |
| `extract_trimmed_metrics_from_raw.py` | `~/Downloads/raw-data/*.zip` からレイテンシー、メッセージロスト数、スループット、周期ジッターを抽出 |
| `build_trim2s_reports.py` | 先頭 2 秒を除外した RMW比較、QoS比較、Zenoh QoS、payload比較PDFを生成 |
| `build_rmw_comparison_figures.py` / `build_rmw_comparison_pdf.py` | FastDDS、CycloneDDS、Zenoh の RMW比較 |
| `build_qos_rmw_comparison_figures.py` / `build_qos_rmw_comparison_pdf.py` | FastDDS と CycloneDDS の QoS sweep 比較 |
| `build_zenoh_qos_sweep_figures.py` / `build_zenoh_qos_sweep_pdf.py` | Zenoh docker/native の QoS sweep 比較 |
| `build_payloadsize_rmw_comparison_figures.py` / `build_payloadsize_rmw_comparison_pdf.py` | payload size sweep 比較 |
| `build_jitter_trim_comparison_figures.py` / `build_jitter_trim_comparison_pdf.py` | 1 秒トリムと 3 秒トリムのジッター比較 |
| `build_fastdds_docker_qos_sweep_figures.py` / `build_fastdds_docker_qos_sweep_pdf.py` | FastDDS docker 単体の QoS sweep |
| `build_zenoh_native2_figures.py` | Zenoh native2 単体の図生成 |
| `build_fastdds_pdf.py` / `build_paper_style_figures.py` / `build_fastdds_workbook.mjs` | 初期の FastDDS docker 用レポート、論文風図、Excel生成 |
| `build_ros_graph_pdf.py` | ROS graph PDF生成 |

## 代表的な出力

| 出力PDF | 生成コマンド |
| --- | --- |
| `output/pdf/rmw_comparison_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/qos_rmw_comparison_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/zenoh_qos_sweep_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/payloadsize_rmw_comparison_trim2s_report.pdf` | `python3 build_trim2s_reports.py --all` |
| `output/pdf/jitter_trim1s_3s_report.pdf` | `python3 build_jitter_trim_comparison_pdf.py` |

## 注意

スクリプト内には、今回の測定環境に合わせた絶対パスが残っています。別のPCや別ディレクトリで実行する場合は、各スクリプト先頭の `Path(...)` 定義を変更してください。
