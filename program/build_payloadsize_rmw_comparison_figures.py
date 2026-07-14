from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from period_jitter_data import attach_period_jitter, payload_jitter_trials
from trimmed_metrics_data import apply_trimmed_metrics, payload_trimmed_trials


BASE = Path("/Users/kudoutakumi/Downloads/payloadsize_variant")
OUTPUT_DIR = Path("outputs/payloadsize_rmw_comparison")
FIGURE_DIR = OUTPUT_DIR / "figures"
USE_TRIMMED_2S = False

DATASETS = [
    ("FastDDS", BASE / "fastdds-docker"),
    ("CycloneDDS", BASE / "cyclonedds-docker"),
]
RMW_ORDER = ["FastDDS", "CycloneDDS"]
PAYLOAD_ORDER = ["payload1K", "payload2K", "payload4K", "payload8K", "payload1M", "payload2M"]
PAYLOAD_LABELS = {
    "payload1K": "1K",
    "payload2K": "2K",
    "payload4K": "4K",
    "payload8K": "8K",
    "payload1M": "1M",
    "payload2M": "2M",
}
PAYLOAD_BYTES = {
    "payload1K": 1024,
    "payload2K": 2048,
    "payload4K": 4096,
    "payload8K": 8192,
    "payload1M": 1024 * 1024,
    "payload2M": 2 * 1024 * 1024,
}
COLORS = {"FastDDS": "#1f77b4", "CycloneDDS": "#d62728"}
MARKERS = {"FastDDS": "o", "CycloneDDS": "s"}
PAYLOAD_COLORS = {
    "payload1K": "#4e79a7",
    "payload2K": "#f28e2b",
    "payload4K": "#59a14f",
    "payload8K": "#e15759",
    "payload1M": "#b07aa1",
    "payload2M": "#767f8c",
}


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
            "lines.linewidth": 1.15,
            "lines.markersize": 3.8,
            "grid.color": "#bfbfbf",
            "grid.linewidth": 0.55,
            "grid.alpha": 0.85,
            "savefig.dpi": 240,
            "savefig.bbox": "tight",
        }
    )


def finish_axis(ax, x_grid: bool = True) -> None:
    ax.grid(True, axis="both" if x_grid else "y")
    ax.set_axisbelow(True)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
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


def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trial_frames = []
    usage_frames = []
    summaries = []

    for rmw, folder in DATASETS:
        for payload in PAYLOAD_ORDER:
            case_folder = folder / payload
            if not case_folder.exists():
                continue

            latency = read_trial_csv(case_folder / "total_latency.csv")
            throughput = read_trial_csv(case_folder / "throughput.csv", usecols=[0, 1, 2])
            trial = latency.merge(throughput, on=["trial", "trial_num"], how="left")
            if USE_TRIMMED_2S:
                trial = apply_trimmed_metrics(trial, payload_trimmed_trials(rmw, payload))
            else:
                trial = attach_period_jitter(trial, payload_jitter_trials(rmw, payload))

            usage = pd.read_csv(case_folder / "host_trials_usage.csv")
            usage["trial_num"] = trial_number(usage["trial"].astype(str))

            for frame in (trial, usage):
                frame["RMW"] = rmw
                frame["payload"] = payload
                frame["payload_label"] = PAYLOAD_LABELS[payload]
                frame["payload_bytes"] = PAYLOAD_BYTES[payload]

            trial_frames.append(trial)
            usage_frames.append(usage)
            summaries.append(
                {
                    "RMW": rmw,
                    "payload": payload,
                    "payload_label": PAYLOAD_LABELS[payload],
                    "payload_bytes": PAYLOAD_BYTES[payload],
                    "Trials": int(trial["trial_num"].nunique()),
                    "Msg. lost [#]": int(trial["lost[#]"].sum()),
                    "Latency mean [ms]": trial["mean[ms]"].mean(),
                    "Latency std [ms]": trial["mean[ms]"].std(ddof=1),
                    "Jitter mean [ms]": trial["jitter[ms]"].mean(),
                    "Jitter std [ms]": trial["jitter[ms]"].std(ddof=1),
                    "Throughput mean [MB/s]": trial["throughput[MB/s]"].mean(),
                    "Throughput std [MB/s]": trial["throughput[MB/s]"].std(ddof=1),
                    "CPU mean [%]": usage["cpu_mean[%]"].mean(),
                    "CPU std [%]": usage["cpu_mean[%]"].std(ddof=1),
                    "Memory mean [%]": usage["mem_mean[%]"].mean(),
                    "Memory std [%]": usage["mem_mean[%]"].std(ddof=1),
                    "Load1 mean": usage["load1_mean"].mean(),
                    "Load1 std": usage["load1_mean"].std(ddof=1),
                }
            )

    trials = pd.concat(trial_frames, ignore_index=True)
    usage = pd.concat(usage_frames, ignore_index=True)
    summary = pd.DataFrame(summaries)
    summary["RMW"] = pd.Categorical(summary["RMW"], categories=RMW_ORDER, ordered=True)
    summary["payload"] = pd.Categorical(summary["payload"], categories=PAYLOAD_ORDER, ordered=True)
    summary = summary.sort_values(["payload", "RMW"]).reset_index(drop=True)
    summary["RMW"] = summary["RMW"].astype(str)
    summary["payload"] = summary["payload"].astype(str)
    return summary, trials, usage


def payload_axis(ax) -> None:
    ticks = [PAYLOAD_BYTES[payload] for payload in PAYLOAD_ORDER]
    labels = [PAYLOAD_LABELS[payload] for payload in PAYLOAD_ORDER]
    ax.set_xscale("log", base=2)
    ax.set_xticks(ticks, labels)
    ax.set_xlabel("Payload size")


def plot_metric_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.9))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.20, hspace=0.62, wspace=0.34)
    specs = [
        ("Latency mean [ms]", "Latency std [ms]", "Mean latency", "Latency [ms]"),
        ("Jitter mean [ms]", "Jitter std [ms]", "Jitter", "Jitter [ms]"),
        ("Msg. lost [#]", None, "Message loss", "Messages lost [#]"),
        ("Throughput mean [MB/s]", "Throughput std [MB/s]", "Throughput", "Throughput [MB/s]"),
    ]
    for ax, (value_col, err_col, title, ylabel) in zip(axes.ravel(), specs):
        for rmw in RMW_ORDER:
            data = summary[summary["RMW"] == rmw].sort_values("payload_bytes")
            errors = None if err_col is None else data[err_col].to_numpy(dtype=float)
            ax.errorbar(
                data["payload_bytes"],
                data[value_col],
                yerr=errors,
                marker=MARKERS[rmw],
                color=COLORS[rmw],
                capsize=2.5 if errors is not None else 0,
                label=rmw,
            )
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        payload_axis(ax)
        finish_axis(ax)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.04), ncol=len(RMW_ORDER), frameon=True)
    path = FIGURE_DIR / "fig01_metric_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_resource_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(7.0, 6.2))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.95, bottom=0.13, hspace=0.58)
    specs = [
        ("CPU mean [%]", "CPU std [%]", "CPU mean", "CPU mean [%]"),
        ("Memory mean [%]", "Memory std [%]", "Memory mean", "Memory mean [%]"),
        ("Load1 mean", "Load1 std", "Load average", "Load average"),
    ]
    for ax, (value_col, err_col, title, ylabel) in zip(axes, specs):
        for rmw in RMW_ORDER:
            data = summary[summary["RMW"] == rmw].sort_values("payload_bytes")
            ax.errorbar(
                data["payload_bytes"],
                data[value_col],
                yerr=data[err_col].to_numpy(dtype=float),
                marker=MARKERS[rmw],
                color=COLORS[rmw],
                capsize=2.5,
                label=rmw,
            )
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        payload_axis(ax)
        finish_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.03), ncol=len(RMW_ORDER), frameon=True)
    path = FIGURE_DIR / "fig02_resource_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_distributions(trials: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 5.2))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.15, hspace=0.52)
    labels = [PAYLOAD_LABELS[payload] for payload in PAYLOAD_ORDER]
    for ax, col, title, ylabel in [
        (axes[0], "mean[ms]", "Mean latency distribution", "Latency [ms]"),
        (axes[1], "jitter[ms]", "Jitter distribution", "Jitter [ms]"),
    ]:
        values = []
        positions = []
        colors = []
        tick_positions = []
        base = np.arange(len(PAYLOAD_ORDER)) * 3.0
        for j, payload in enumerate(PAYLOAD_ORDER):
            tick_positions.append(base[j] + 0.5)
            for i, rmw in enumerate(RMW_ORDER):
                subset = trials[(trials["payload"] == payload) & (trials["RMW"] == rmw)]
                values.append(subset[col].dropna().to_numpy())
                positions.append(base[j] + i)
                colors.append(COLORS[rmw])
        box = ax.boxplot(values, positions=positions, widths=0.7, patch_artist=True, showfliers=False)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.55)
            patch.set_edgecolor("black")
        ax.set_xticks(tick_positions, labels)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        finish_axis(ax, x_grid=False)
    fig.legend(
        [plt.Rectangle((0, 0), 1, 1, color=COLORS[rmw], alpha=0.55, ec="black") for rmw in RMW_ORDER],
        RMW_ORDER,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=len(RMW_ORDER),
        frameon=True,
    )
    path = FIGURE_DIR / "fig03_distributions.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_trial_trends(trials: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 6.0))
    fig.subplots_adjust(left=0.09, right=0.82, top=0.94, bottom=0.16, hspace=0.64)
    linestyles = {"FastDDS": "-", "CycloneDDS": "--"}
    for rmw in RMW_ORDER:
        for payload in PAYLOAD_ORDER:
            data = trials[(trials["RMW"] == rmw) & (trials["payload"] == payload)].sort_values("trial_num")
            axes[0].plot(
                data["trial_num"],
                data["mean[ms]"],
                marker=MARKERS[rmw],
                linestyle=linestyles[rmw],
                color=PAYLOAD_COLORS[payload],
                alpha=0.9,
            )
            axes[1].plot(
                data["trial_num"],
                data["jitter[ms]"],
                marker=MARKERS[rmw],
                linestyle=linestyles[rmw],
                color=PAYLOAD_COLORS[payload],
                alpha=0.9,
            )
    axes[0].set_title("Trial trend: latency")
    axes[0].set_ylabel("Latency [ms]")
    axes[1].set_title("Trial trend: jitter")
    axes[1].set_ylabel("Jitter [ms]")
    rmw_handles = [
        Line2D([0], [0], color="#333333", marker=MARKERS[rmw], linestyle=linestyles[rmw], label=rmw)
        for rmw in RMW_ORDER
    ]
    payload_handles = [
        Patch(facecolor=PAYLOAD_COLORS[payload], edgecolor="black", label=PAYLOAD_LABELS[payload])
        for payload in PAYLOAD_ORDER
    ]
    for ax in axes:
        ax.set_xlabel("Trial")
        finish_axis(ax, x_grid=False)
    first_legend = fig.legend(
        handles=rmw_handles,
        loc="center right",
        bbox_to_anchor=(0.985, 0.68),
        frameon=True,
        fontsize=5.8,
        title="RMW",
        title_fontsize=6,
    )
    fig.add_artist(first_legend)
    fig.legend(
        handles=payload_handles,
        loc="lower center",
        bbox_to_anchor=(0.46, 0.025),
        frameon=True,
        fontsize=5.5,
        ncol=6,
        title="Payload",
        title_fontsize=6,
    )
    path = FIGURE_DIR / "fig04_trial_trends.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    configure_style()
    summary, trials, usage = load_all()
    summary.to_csv(OUTPUT_DIR / "payload_summary.csv", index=False)
    trials.to_csv(OUTPUT_DIR / "payload_trials.csv", index=False)
    usage.to_csv(OUTPUT_DIR / "payload_host_usage.csv", index=False)
    paths = [
        plot_metric_summary(summary),
        plot_resource_summary(summary),
        plot_distributions(trials),
        plot_trial_trends(trials),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
