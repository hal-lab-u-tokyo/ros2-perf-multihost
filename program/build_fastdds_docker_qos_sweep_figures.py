from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from period_jitter_data import attach_period_jitter, qos_jitter_trials
from analysis_config import FASTDDS_DOCKER_QOS_BASE, output_path


BASE = FASTDDS_DOCKER_QOS_BASE
OUTPUT_DIR = output_path("fastdds_docker_qos_sweep")
FIGURE_DIR = OUTPUT_DIR / "figures"

CASE_ORDER = [f"qos_case{i}" for i in range(8)]
RELIABILITY_COLORS = {"RELIABLE": "#1f77b4", "BEST_EFFORT": "#d62728"}
RELIABILITY_MARKERS = {"RELIABLE": "o", "BEST_EFFORT": "s"}


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Serif",
            "font.size": 8,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 6,
            "axes.linewidth": 0.8,
            "lines.linewidth": 1.1,
            "lines.markersize": 3.5,
            "grid.color": "#bfbfbf",
            "grid.linewidth": 0.55,
            "grid.alpha": 0.85,
            "savefig.dpi": 240,
            "savefig.bbox": "tight",
        }
    )


def finish_axis(ax, x_grid: bool = False) -> None:
    ax.grid(True, axis="both" if x_grid else "y")
    ax.set_axisbelow(True)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(0.8)


def trial_number(series: pd.Series) -> pd.Series:
    return series.str.extract(r"(\d+)").astype(int)[0]


def case_label(row: pd.Series) -> str:
    history = "KL" if row["history"] == "KEEP_LAST" else "KA"
    reliability = "REL" if row["reliability"] == "RELIABLE" else "BE"
    if row["history"] == "KEEP_ALL":
        return f"{history}-{reliability}"
    return f"{history}-{int(row['depth'])}-{reliability}"


def read_trial_csv(path: Path, usecols: list[int] | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=usecols)
    df = df[df["trial"].astype(str).str.startswith("trial")].copy()
    df["trial_num"] = trial_number(df["trial"].astype(str))
    return df.sort_values("trial_num")


def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary = pd.read_csv(BASE / "qos_sweep_summary.csv")
    summary["qos_case"] = pd.Categorical(summary["qos_case"], categories=CASE_ORDER, ordered=True)
    summary = summary.sort_values("qos_case").reset_index(drop=True)
    summary["case_label"] = summary.apply(case_label, axis=1)

    trial_frames = []
    usage_frames = []
    for _, row in summary.iterrows():
        folder = BASE / str(row["qos_case"])
        latency = read_trial_csv(folder / "total_latency.csv")
        throughput = read_trial_csv(folder / "throughput.csv", usecols=[0, 1, 2])
        trial = latency.merge(throughput, on=["trial", "trial_num"], how="left")
        trial = attach_period_jitter(trial, qos_jitter_trials("FastDDS", str(row["qos_case"])))
        usage = pd.read_csv(folder / "host_trials_usage.csv")
        usage["trial_num"] = trial_number(usage["trial"].astype(str))

        for frame in (trial, usage):
            frame["qos_case"] = row["qos_case"]
            frame["history"] = row["history"]
            frame["depth"] = int(row["depth"])
            frame["reliability"] = row["reliability"]
            frame["case_label"] = row["case_label"]
        trial_frames.append(trial)
        usage_frames.append(usage)

    trials = pd.concat(trial_frames, ignore_index=True)
    usage = pd.concat(usage_frames, ignore_index=True)

    trial_stats = (
        trials.groupby("qos_case", observed=True)
        .agg(
            trial_count=("trial_num", "nunique"),
            latency_mean_std=("mean[ms]", "std"),
            jitter_mean=("jitter[ms]", "mean"),
            jitter_std=("jitter[ms]", "std"),
            throughput_std=("throughput[MB/s]", "std"),
        )
        .reset_index()
    )
    usage_stats = (
        usage.groupby("qos_case", observed=True)
        .agg(
            cpu_mean=("cpu_mean[%]", "mean"),
            cpu_std=("cpu_mean[%]", "std"),
            memory_mean=("mem_mean[%]", "mean"),
            memory_std=("mem_mean[%]", "std"),
            load1_mean=("load1_mean", "mean"),
            load1_std=("load1_mean", "std"),
        )
        .reset_index()
    )
    enriched = summary.merge(trial_stats, on="qos_case", how="left").merge(usage_stats, on="qos_case", how="left")
    enriched["jitter[ms]"] = enriched["jitter_mean"]
    return enriched, trials, usage


def bar_colors(df: pd.DataFrame) -> list[str]:
    return [RELIABILITY_COLORS[value] for value in df["reliability"]]


def metric_bar(ax, df: pd.DataFrame, value_col: str, error_col: str | None, title: str, ylabel: str) -> None:
    x = np.arange(len(df))
    errors = None if error_col is None else df[error_col].to_numpy(dtype=float)
    bars = ax.bar(
        x,
        df[value_col].to_numpy(dtype=float),
        yerr=errors,
        capsize=3 if errors is not None else 0,
        color=bar_colors(df),
        edgecolor="black",
        linewidth=0.6,
        alpha=0.82,
    )
    for bar, history in zip(bars, df["history"]):
        if history == "KEEP_ALL":
            bar.set_hatch("//")
    ax.set_xticks(x, df["case_label"], rotation=35, ha="right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    finish_axis(ax)


def plot_summary_bars(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.9), constrained_layout=True)
    metric_bar(axes[0, 0], summary, "mean[ms]", "latency_mean_std", "Mean latency", "Latency [ms]")
    metric_bar(axes[0, 1], summary, "jitter[ms]", "jitter_std", "Jitter", "Jitter [ms]")
    metric_bar(axes[1, 0], summary, "lost[#]", None, "Message loss", "Messages lost [#]")
    metric_bar(axes[1, 1], summary, "throughput[MB/s]", "throughput_std", "Throughput", "Throughput [MB/s]")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=RELIABILITY_COLORS["RELIABLE"], alpha=0.82, ec="black"),
        plt.Rectangle((0, 0), 1, 1, color=RELIABILITY_COLORS["BEST_EFFORT"], alpha=0.82, ec="black"),
        plt.Rectangle((0, 0), 1, 1, color="white", ec="black", hatch="//"),
    ]
    fig.legend(handles, ["RELIABLE", "BEST_EFFORT", "KEEP_ALL"], loc="lower center", ncol=3, frameon=True)
    path = FIGURE_DIR / "fig01_qos_summary_bars.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def keep_last_depth_plot(summary: pd.DataFrame) -> Path:
    keep_last = summary[summary["history"] == "KEEP_LAST"].copy()
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)
    specs = [
        ("mean[ms]", "Latency", "Latency [ms]"),
        ("jitter[ms]", "Jitter", "Jitter [ms]"),
        ("lost[#]", "Message loss", "Messages lost [#]"),
        ("throughput[MB/s]", "Throughput", "Throughput [MB/s]"),
    ]
    for ax, (col, title, ylabel) in zip(axes.ravel(), specs):
        for reliability in ["RELIABLE", "BEST_EFFORT"]:
            data = keep_last[keep_last["reliability"] == reliability].sort_values("depth")
            ax.plot(
                data["depth"],
                data[col],
                marker=RELIABILITY_MARKERS[reliability],
                color=RELIABILITY_COLORS[reliability],
                label=reliability,
            )
        ax.set_xscale("log")
        ax.set_xticks([1, 10, 100], ["1", "10", "100"])
        ax.set_xlabel("Depth")
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.legend(loc="best", frameon=True)
        finish_axis(ax, x_grid=True)
    path = FIGURE_DIR / "fig02_keep_last_depth_sweep.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_trial_trends(trials: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 5.0), constrained_layout=True)
    for label in trials["case_label"].drop_duplicates():
        data = trials[trials["case_label"] == label].sort_values("trial_num")
        reliability = data["reliability"].iloc[0]
        linestyle = "--" if data["history"].iloc[0] == "KEEP_ALL" else "-"
        axes[0].plot(data["trial_num"], data["mean[ms]"], marker="o", linestyle=linestyle, label=label)
        axes[1].plot(data["trial_num"], data["jitter[ms]"], marker="s", linestyle=linestyle, label=label)
    axes[0].set_title("Trial trend: latency")
    axes[0].set_ylabel("Mean latency [ms]")
    axes[1].set_title("Trial trend: jitter")
    axes[1].set_ylabel("Jitter [ms]")
    for ax in axes:
        ax.set_xlabel("Trial")
        ax.legend(loc="best", frameon=True, ncol=4)
        finish_axis(ax)
    path = FIGURE_DIR / "fig03_trial_trends.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_distributions(trials: pd.DataFrame) -> Path:
    labels = trials["case_label"].drop_duplicates().tolist()
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 5.0), constrained_layout=True)
    for ax, col, title, ylabel in [
        (axes[0], "mean[ms]", "Mean latency distribution", "Latency [ms]"),
        (axes[1], "jitter[ms]", "Jitter distribution", "Jitter [ms]"),
    ]:
        values = [trials[trials["case_label"] == label][col].dropna().to_numpy() for label in labels]
        box = ax.boxplot(values, patch_artist=True, showfliers=False)
        ax.set_xticks(range(1, len(labels) + 1), labels)
        for patch, label in zip(box["boxes"], labels):
            reliability = trials[trials["case_label"] == label]["reliability"].iloc[0]
            patch.set_facecolor(RELIABILITY_COLORS[reliability])
            patch.set_alpha(0.55)
            patch.set_edgecolor("black")
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.tick_params(axis="x", labelrotation=25)
        finish_axis(ax)
    path = FIGURE_DIR / "fig04_distributions.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_resource_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(7.0, 6.4), constrained_layout=True)
    specs = [
        ("cpu_mean", "cpu_std", "CPU mean", "CPU mean [%]"),
        ("memory_mean", "memory_std", "Memory mean", "Memory mean [%]"),
        ("load1_mean", "load1_std", "Load average", "Load average"),
    ]
    for ax, (value_col, error_col, title, ylabel) in zip(axes, specs):
        metric_bar(ax, summary, value_col, error_col, title, ylabel)
    path = FIGURE_DIR / "fig05_resource_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    configure_style()
    summary, trials, usage = load_all()
    summary.to_csv(OUTPUT_DIR / "qos_sweep_enriched_summary.csv", index=False)
    trials.to_csv(OUTPUT_DIR / "qos_sweep_trials.csv", index=False)
    usage.to_csv(OUTPUT_DIR / "qos_sweep_host_usage.csv", index=False)
    paths = [
        plot_summary_bars(summary),
        keep_last_depth_plot(summary),
        plot_trial_trends(trials),
        plot_distributions(trials),
        plot_resource_summary(summary),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
