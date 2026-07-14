from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from period_jitter_data import attach_period_jitter, constant_jitter_trials
from analysis_config import ZENOH_NATIVE2_BASE, output_path


BASE = ZENOH_NATIVE2_BASE
OUTPUT_DIR = output_path("zenoh_native2")
FIGURE_DIR = OUTPUT_DIR / "figures"


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
            "savefig.dpi": 240,
            "savefig.bbox": "tight",
        }
    )


def finish_axis(ax) -> None:
    ax.grid(True)
    ax.set_axisbelow(True)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(0.8)


def trial_number(series: pd.Series) -> pd.Series:
    return series.str.extract(r"(\d+)").astype(int)[0]


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usage = pd.read_csv(BASE / "host_trials_usage.csv")
    usage["trial_num"] = trial_number(usage["trial"].astype(str))
    usage = usage.sort_values(["trial_num", "host"])

    latency = pd.read_csv(BASE / "total_latency.csv")
    latency = latency[latency["trial"].astype(str).str.startswith("trial")].copy()
    latency["trial_num"] = trial_number(latency["trial"].astype(str))

    throughput = pd.read_csv(BASE / "throughput.csv", usecols=[0, 1, 2])
    throughput = throughput[throughput["trial"].astype(str).str.startswith("trial")].copy()
    throughput["trial_num"] = trial_number(throughput["trial"].astype(str))

    network = latency.merge(throughput, on=["trial", "trial_num"], how="left")
    network = attach_period_jitter(network, constant_jitter_trials("Zenoh", "Native"))
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
        ax.bar(x, summary[col], color="#2ca02c", edgecolor="black", linewidth=0.6, alpha=0.82, label="Zenoh Native2")
        ax.set_title(title)
        ax.set_xlabel("Host")
        ax.set_ylabel(ylabel)
        ax.set_xticks(list(x), summary.index)
        ax.legend(loc="best", frameon=True)
        finish_axis(ax)
    path = FIGURE_DIR / "fig01_host_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_trial_usage(usage: pd.DataFrame) -> Path:
    hosts = sorted(usage["host"].unique(), key=lambda value: int("".join(ch for ch in value if ch.isdigit())))
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
            ax.plot(subset["trial_num"], subset[col], marker="o", markevery=5, label=host)
        ax.set_title(title)
        ax.set_xlabel("Trial")
        ax.set_ylabel(ylabel)
        ax.set_xlim(1, int(usage["trial_num"].max()))
        ax.set_xticks([1, 10, 20, 30, 40, 50])
        ax.legend(loc="best", frameon=True, ncol=1)
        finish_axis(ax)
    path = FIGURE_DIR / "fig02_trial_usage.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_network(network: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)

    axes[0, 0].plot(network["trial_num"], network["mean[ms]"], marker="o", markevery=5, label="mean")
    axes[0, 0].plot(network["trial_num"], network["mid[ms]"], marker="s", markevery=5, label="median")
    axes[0, 0].plot(network["trial_num"], network["max[ms]"], marker="^", markevery=5, label="max")
    axes[0, 0].set_title("Latency")
    axes[0, 0].set_xlabel("Trial")
    axes[0, 0].set_ylabel("Latency [ms]")

    axes[0, 1].plot(network["trial_num"], network["jitter[ms]"], marker="o", markevery=5, color="#9467bd", label="jitter")
    axes[0, 1].set_title("Jitter")
    axes[0, 1].set_xlabel("Trial")
    axes[0, 1].set_ylabel("Jitter [ms]")

    axes[1, 0].plot(network["trial_num"], network["lost[#]"], marker="o", color="#d62728", label="messages lost")
    axes[1, 0].set_title("Message loss")
    axes[1, 0].set_xlabel("Trial")
    axes[1, 0].set_ylabel("Messages lost [#]")

    axes[1, 1].plot(network["trial_num"], network["throughput[MB/s]"], marker="o", markevery=5, label="throughput")
    axes[1, 1].set_title("Throughput")
    axes[1, 1].set_xlabel("Trial")
    axes[1, 1].set_ylabel("Throughput [MB/s]")

    for ax in axes.ravel():
        ax.set_xlim(1, int(network["trial_num"].max()))
        ax.set_xticks([1, 10, 20, 30, 40, 50])
        ax.legend(loc="best", frameon=True)
        finish_axis(ax)

    path = FIGURE_DIR / "fig03_network.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_distribution(network: pd.DataFrame) -> Path:
    bins = pd.cut(network["trial_num"], bins=[0, 10, 20, 30, 40, 50], labels=["1-10", "11-20", "21-30", "31-40", "41-50"])
    grouped = network.groupby(bins, observed=True)

    fig, axes = plt.subplots(2, 1, figsize=(7.0, 4.8), constrained_layout=True)
    specs = [("mean[ms]", "Mean latency distribution", "Mean latency [ms]"), ("jitter[ms]", "Jitter distribution", "Jitter [ms]")]
    for ax, (col, title, ylabel) in zip(axes, specs):
        values = [data[col].dropna().to_numpy() for _label, data in grouped]
        labels = [str(label) for label, _data in grouped]
        box = ax.boxplot(values, patch_artist=True, showfliers=False)
        ax.set_xticks(range(1, len(labels) + 1), labels)
        for patch in box["boxes"]:
            patch.set_facecolor("#2ca02c")
            patch.set_alpha(0.55)
            patch.set_edgecolor("black")
        ax.set_title(title)
        ax.set_xlabel("Trial range")
        ax.set_ylabel(ylabel)
        finish_axis(ax)

    path = FIGURE_DIR / "fig04_distributions.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def write_summary(usage: pd.DataFrame, network: pd.DataFrame) -> None:
    summary = pd.DataFrame(
        [
            {
                "Dataset": "Zenoh Native2",
                "Trials": int(network["trial_num"].nunique()),
                "Messages lost total [#]": int(network["lost[#]"].sum()),
                "Latency mean [ms]": network["mean[ms]"].mean(),
                "Latency std [ms]": network["mean[ms]"].std(ddof=1),
                "Latency max [ms]": network["max[ms]"].max(),
                "Jitter mean [ms]": network["jitter[ms]"].mean(),
                "Jitter std [ms]": network["jitter[ms]"].std(ddof=1),
                "Throughput mean [MB/s]": network["throughput[MB/s]"].mean(),
                "Throughput std [MB/s]": network["throughput[MB/s]"].std(ddof=1),
                "CPU mean [%]": usage["cpu_mean[%]"].mean(),
                "Memory mean [%]": usage["mem_mean[%]"].mean(),
                "Load1 mean": usage["load1_mean"].mean(),
            }
        ]
    )
    summary.to_csv(OUTPUT_DIR / "summary.csv", index=False)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    configure_style()
    usage, _latency, network = load_data()
    usage.to_csv(OUTPUT_DIR / "host_trials_usage.csv", index=False)
    network.to_csv(OUTPUT_DIR / "network_trials.csv", index=False)
    write_summary(usage, network)
    paths = [
        plot_host_summary(usage),
        plot_trial_usage(usage),
        plot_network(network),
        plot_distribution(network),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
