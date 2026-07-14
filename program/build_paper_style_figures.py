from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis_config import RMW_COMPARISON_BASE, output_path


BASE = RMW_COMPARISON_BASE / "fastdds" / "docker"
OUTPUT_DIR = output_path("fastdds_docker_usage", "paper_style_figures")


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
            "lines.markersize": 3.2,
            "grid.color": "#bfbfbf",
            "grid.linewidth": 0.55,
            "grid.alpha": 0.85,
            "savefig.dpi": 220,
            "savefig.bbox": "tight",
        }
    )


def finish_axis(ax) -> None:
    ax.grid(True)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(0.8)


def trial_number(series: pd.Series) -> pd.Series:
    return series.str.extract(r"(\d+)").astype(int)[0]


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usage = pd.read_csv(BASE / "host_trials_usage.csv")
    usage["trial_num"] = trial_number(usage["trial"])
    usage = usage.sort_values(["trial_num", "host"])

    latency = pd.read_csv(BASE / "total_latency.csv")
    latency = latency[latency["trial"].str.startswith("trial")].copy()
    latency["trial_num"] = trial_number(latency["trial"])

    throughput = pd.read_csv(BASE / "throughput.csv", usecols=[0, 1, 2], nrows=100)
    throughput["trial_num"] = trial_number(throughput["trial"])
    network = latency.merge(throughput, on=["trial", "trial_num"], how="left")
    return usage, latency, network


def plot_host_summary(usage: pd.DataFrame) -> Path:
    summary = usage.groupby("host", sort=False).agg(
        cpu_mean=("cpu_mean[%]", "mean"),
        mem_mean=("mem_mean[%]", "mean"),
        load1=("load1_mean", "mean"),
        cpu_peak=("cpu_max[%]", "max"),
    )
    x = range(1, len(summary.index) + 1)

    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)
    specs = [
        ("cpu_mean", "CPU mean", "CPU mean [%]"),
        ("mem_mean", "Memory mean", "Memory mean [%]"),
        ("load1", "Load average", "load1"),
        ("cpu_peak", "CPU peak", "CPU max [%]"),
    ]
    for ax, (col, title, ylabel) in zip(axes.ravel(), specs):
        ax.plot(x, summary[col], marker="o", label="FastDDS-Docker")
        ax.set_title(title)
        ax.set_xlabel("Host")
        ax.set_ylabel(ylabel)
        ax.set_xticks(list(x), summary.index)
        ax.legend(loc="best", frameon=True)
        finish_axis(ax)
    path = OUTPUT_DIR / "paper_host_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_trial_usage(usage: pd.DataFrame) -> Path:
    hosts = sorted(usage["host"].unique(), key=lambda v: int("".join(ch for ch in v if ch.isdigit())))
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)
    specs = [
        ("cpu_mean[%]", "CPU mean", "CPU mean [%]"),
        ("cpu_max[%]", "CPU max", "CPU max [%]"),
        ("mem_mean[%]", "Memory mean", "Memory mean [%]"),
        ("load1_mean", "Load average", "load1"),
    ]
    for ax, (col, title, ylabel) in zip(axes.ravel(), specs):
        for host in hosts:
            subset = usage[usage["host"] == host]
            ax.plot(subset["trial_num"], subset[col], marker="o", markevery=10, label=host)
        ax.set_title(title)
        ax.set_xlabel("Trial")
        ax.set_ylabel(ylabel)
        ax.set_xlim(1, 100)
        ax.set_xticks([1, 20, 40, 60, 80, 100])
        ax.legend(loc="best", frameon=True, ncol=1)
        finish_axis(ax)
    path = OUTPUT_DIR / "paper_trial_usage.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_network(network: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)

    axes[0, 0].plot(network["trial_num"], network["mean[ms]"], marker="o", markevery=10, label="mean")
    axes[0, 0].plot(network["trial_num"], network["mid[ms]"], marker="s", markevery=10, label="median")
    axes[0, 0].plot(network["trial_num"], network["max[ms]"], marker="^", markevery=10, label="max")
    axes[0, 0].set_title("Latency")
    axes[0, 0].set_xlabel("Trial")
    axes[0, 0].set_ylabel("Latency [ms]")

    axes[0, 1].plot(network["trial_num"], network["lost[#]"], marker="o", label="messages lost")
    axes[0, 1].set_title("Message loss")
    axes[0, 1].set_xlabel("Trial")
    axes[0, 1].set_ylabel("Messages lost [#]")

    axes[1, 0].plot(network["trial_num"], network["q1[ms]"], marker="o", markevery=10, label="q1")
    axes[1, 0].plot(network["trial_num"], network["mid[ms]"], marker="s", markevery=10, label="median")
    axes[1, 0].plot(network["trial_num"], network["q3[ms]"], marker="^", markevery=10, label="q3")
    axes[1, 0].set_title("Latency quartiles")
    axes[1, 0].set_xlabel("Trial")
    axes[1, 0].set_ylabel("Latency [ms]")

    axes[1, 1].plot(network["trial_num"], network["throughput[MB/s]"], marker="o", markevery=10, label="throughput")
    axes[1, 1].set_title("Throughput")
    axes[1, 1].set_xlabel("Trial")
    axes[1, 1].set_ylabel("Throughput [MB/s]")

    for ax in axes.ravel():
        ax.set_xlim(1, 100)
        ax.set_xticks([1, 20, 40, 60, 80, 100])
        ax.legend(loc="best", frameon=True)
        finish_axis(ax)

    path = OUTPUT_DIR / "paper_network.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_latency_box(network: pd.DataFrame) -> Path:
    bins = pd.cut(network["trial_num"], bins=[0, 20, 40, 60, 80, 100], labels=["1-20", "21-40", "41-60", "61-80", "81-100"])
    grouped = network.groupby(bins, observed=True)
    stats = []
    for label, data in grouped:
        stats.append(
            {
                "label": str(label),
                "whislo": data["min[ms]"].min(),
                "q1": data["q1[ms]"].median(),
                "med": data["mid[ms]"].median(),
                "q3": data["q3[ms]"].median(),
                "whishi": data["max[ms]"].max(),
                "fliers": [],
            }
        )
    fig, ax = plt.subplots(figsize=(6.4, 3.6), constrained_layout=True)
    ax.bxp(stats, showfliers=False, patch_artist=True, boxprops={"facecolor": "#1f77b4", "alpha": 0.55})
    ax.set_xlabel("Trial range")
    ax.set_ylabel("Latency [ms]")
    ax.set_title("Latency distribution by trial range")
    finish_axis(ax)
    path = OUTPUT_DIR / "paper_latency_box.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_style()
    usage, _latency, network = load_data()
    paths = [
        plot_host_summary(usage),
        plot_trial_usage(usage),
        plot_network(network),
        plot_latency_box(network),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
