from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from period_jitter_data import attach_period_jitter, constant_jitter_trials
from trimmed_metrics_data import apply_trimmed_metrics, constant_trimmed_trials
from analysis_config import RMW_COMPARISON_BASE, ZENOH_NATIVE2_BASE, output_path


BASE = RMW_COMPARISON_BASE
OUTPUT_DIR = output_path("rmw_comparison")
FIGURE_DIR = OUTPUT_DIR / "figures"
USE_TRIMMED_2S = False

DATASETS = [
    ("FastDDS", "Docker", BASE / "fastdds" / "docker"),
    ("FastDDS", "Native", BASE / "fastdds" / "Native"),
    ("CycloneDDS", "Docker", BASE / "cyclonedds" / "docker"),
    ("CycloneDDS", "Native", BASE / "cyclonedds" / "Native"),
    ("Zenoh", "Docker", BASE / "Zenoh" / "docker"),
    ("Zenoh", "Native", ZENOH_NATIVE2_BASE),
]

RMW_ORDER = ["FastDDS", "CycloneDDS", "Zenoh"]
ENV_ORDER = ["Docker", "Native"]
COLORS = {"FastDDS": "#1f77b4", "CycloneDDS": "#d62728", "Zenoh": "#2ca02c"}
MARKERS = {"FastDDS": "o", "CycloneDDS": "s", "Zenoh": "^"}


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
    ax.grid(True, axis="y")
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(0.8)


def trial_number(series: pd.Series) -> pd.Series:
    return series.str.extract(r"(\d+)").astype(int)[0]


def read_trial_csv(path: Path, usecols: list[int] | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=usecols)
    df = df[df["trial"].astype(str).str.startswith("trial")].copy()
    df["trial_num"] = trial_number(df["trial"].astype(str))
    return df.sort_values("trial_num")


def load_dataset(rmw: str, env: str, folder: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    latency = read_trial_csv(folder / "total_latency.csv")
    throughput = read_trial_csv(folder / "throughput.csv", usecols=[0, 1, 2])
    usage = pd.read_csv(folder / "host_trials_usage.csv")
    usage["trial_num"] = trial_number(usage["trial"].astype(str))

    network = latency.merge(throughput, on=["trial", "trial_num"], how="left")
    if USE_TRIMMED_2S:
        network = apply_trimmed_metrics(network, constant_trimmed_trials(rmw, env))
    else:
        network = attach_period_jitter(network, constant_jitter_trials(rmw, env))
    for frame in (network, usage):
        frame["rmw"] = rmw
        frame["environment"] = env
    return network, usage, latency


def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    networks = []
    usages = []
    summaries = []
    for rmw, env, folder in DATASETS:
        network, usage, _latency = load_dataset(rmw, env, folder)
        networks.append(network)
        usages.append(usage)
        summaries.append(
            {
                "RMW": rmw,
                "Environment": env,
                "Trials": int(network["trial_num"].nunique()),
                "Lost total [#]": int(network["lost[#]"].sum()),
                "Latency mean [ms]": network["mean[ms]"].mean(),
                "Latency std [ms]": network["mean[ms]"].std(ddof=1),
                "Latency median mean [ms]": network["mid[ms]"].mean(),
                "Latency max [ms]": network["max[ms]"].max(),
                "Jitter mean [ms]": network["jitter[ms]"].mean(),
                "Jitter std [ms]": network["jitter[ms]"].std(ddof=1),
                "Throughput mean [MB/s]": network["throughput[MB/s]"].mean(),
                "Throughput std [MB/s]": network["throughput[MB/s]"].std(ddof=1),
                "CPU mean [%]": usage["cpu_mean[%]"].mean(),
                "CPU std [%]": usage["cpu_mean[%]"].std(ddof=1),
                "Memory mean [%]": usage["mem_mean[%]"].mean(),
                "Memory std [%]": usage["mem_mean[%]"].std(ddof=1),
                "Load1 mean": usage["load1_mean"].mean(),
                "Load1 std": usage["load1_mean"].std(ddof=1),
            }
        )
    network_all = pd.concat(networks, ignore_index=True)
    usage_all = pd.concat(usages, ignore_index=True)
    summary = pd.DataFrame(summaries)
    summary["RMW"] = pd.Categorical(summary["RMW"], categories=RMW_ORDER, ordered=True)
    summary["Environment"] = pd.Categorical(summary["Environment"], categories=ENV_ORDER, ordered=True)
    summary = summary.sort_values(["Environment", "RMW"]).reset_index(drop=True)
    summary["RMW"] = summary["RMW"].astype(str)
    summary["Environment"] = summary["Environment"].astype(str)
    return network_all, usage_all, summary


def env_subset(summary: pd.DataFrame, env: str) -> pd.DataFrame:
    return summary[summary["Environment"] == env].set_index("RMW").loc[RMW_ORDER].reset_index()


def metric_bar(ax, data: pd.DataFrame, mean_col: str, std_col: str | None, title: str, ylabel: str) -> None:
    values = data[mean_col].to_numpy(dtype=float)
    errors = None if std_col is None else data[std_col].to_numpy(dtype=float)
    x = np.arange(len(data))
    ax.bar(
        x,
        values,
        yerr=errors,
        capsize=3 if errors is not None else 0,
        color=[COLORS[rmw] for rmw in data["RMW"]],
        edgecolor="black",
        linewidth=0.6,
        alpha=0.82,
    )
    ax.set_xticks(x, data["RMW"], rotation=0)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    finish_axis(ax)


def plot_latency_jitter_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)
    for col, env in enumerate(ENV_ORDER):
        data = env_subset(summary, env)
        metric_bar(axes[0, col], data, "Latency mean [ms]", "Latency std [ms]", f"{env}: latency", "Mean latency [ms]")
        metric_bar(axes[1, col], data, "Jitter mean [ms]", "Jitter std [ms]", f"{env}: jitter", "Jitter [ms]")
    path = FIGURE_DIR / "fig01_latency_jitter_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_loss_throughput_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)
    for col, env in enumerate(ENV_ORDER):
        data = env_subset(summary, env)
        metric_bar(axes[0, col], data, "Lost total [#]", None, f"{env}: message loss", "Messages lost [#]")
        metric_bar(
            axes[1, col],
            data,
            "Throughput mean [MB/s]",
            "Throughput std [MB/s]",
            f"{env}: throughput",
            "Throughput [MB/s]",
        )
    path = FIGURE_DIR / "fig02_loss_throughput_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_trial_trends(network: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8))
    fig.subplots_adjust(left=0.10, right=0.98, top=0.92, bottom=0.16, hspace=0.48, wspace=0.34)
    for col, env in enumerate(ENV_ORDER):
        env_data = network[network["environment"] == env]
        for rmw in RMW_ORDER:
            data = env_data[env_data["rmw"] == rmw].sort_values("trial_num")
            mark_every = max(1, len(data) // 10)
            axes[0, col].plot(
                data["trial_num"],
                data["mean[ms]"],
                marker=MARKERS[rmw],
                markevery=mark_every,
                color=COLORS[rmw],
                label=rmw,
            )
            axes[1, col].plot(
                data["trial_num"],
                data["jitter[ms]"],
                marker=MARKERS[rmw],
                markevery=mark_every,
                color=COLORS[rmw],
                label=rmw,
            )
        axes[0, col].set_title(f"{env}: latency trend")
        axes[0, col].set_ylabel("Mean latency [ms]")
        axes[1, col].set_title(f"{env}: jitter trend")
        axes[1, col].set_ylabel("Jitter [ms]")
        for row in range(2):
            axes[row, col].set_xlabel("Trial")
            finish_axis(axes[row, col])
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.025), ncol=3, frameon=True)
    path = FIGURE_DIR / "fig03_trial_trends.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_distributions(network: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.8), constrained_layout=True)
    metrics = [("mean[ms]", "Mean latency [ms]", 0), ("jitter[ms]", "Jitter [ms]", 1)]
    for col, env in enumerate(ENV_ORDER):
        env_data = network[network["environment"] == env]
        for metric, ylabel, row in metrics:
            values = [env_data[env_data["rmw"] == rmw][metric].dropna().to_numpy() for rmw in RMW_ORDER]
            box = axes[row, col].boxplot(values, patch_artist=True, showfliers=False)
            axes[row, col].set_xticks(range(1, len(RMW_ORDER) + 1), RMW_ORDER)
            for patch, rmw in zip(box["boxes"], RMW_ORDER):
                patch.set_facecolor(COLORS[rmw])
                patch.set_alpha(0.55)
                patch.set_edgecolor("black")
            axes[row, col].set_title(f"{env}: {ylabel.lower()}")
            axes[row, col].set_ylabel(ylabel)
            finish_axis(axes[row, col])
    path = FIGURE_DIR / "fig04_distributions.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_resource_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(3, 2, figsize=(7.0, 6.8), constrained_layout=True)
    specs = [
        ("CPU mean [%]", "CPU std [%]", "CPU mean [%]"),
        ("Memory mean [%]", "Memory std [%]", "Memory mean [%]"),
        ("Load1 mean", "Load1 std", "Load average"),
    ]
    for row, (mean_col, std_col, ylabel) in enumerate(specs):
        for col, env in enumerate(ENV_ORDER):
            data = env_subset(summary, env)
            metric_bar(axes[row, col], data, mean_col, std_col, f"{env}: {ylabel}", ylabel)
    path = FIGURE_DIR / "fig05_resource_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    configure_style()
    network, usage, summary = load_all()
    network.to_csv(OUTPUT_DIR / "network_trials.csv", index=False)
    usage.to_csv(OUTPUT_DIR / "host_trials_usage.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "summary.csv", index=False)

    paths = [
        plot_latency_jitter_summary(summary),
        plot_loss_throughput_summary(summary),
        plot_trial_trends(network),
        plot_distributions(network),
        plot_resource_summary(summary),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
