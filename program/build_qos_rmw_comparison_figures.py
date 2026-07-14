from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from period_jitter_data import attach_period_jitter, qos_jitter_trials
from trimmed_metrics_data import apply_trimmed_metrics, qos_trimmed_trials
from analysis_config import QOS_VARIANT_BASE, output_path


BASE = QOS_VARIANT_BASE
OUTPUT_DIR = output_path("qos_rmw_comparison")
FIGURE_DIR = OUTPUT_DIR / "figures"
USE_TRIMMED_2S = False

DATASETS = [
    ("FastDDS", BASE / "fastdds-docker"),
    ("CycloneDDS", BASE / "cyclonedds-docker"),
]
RMW_ORDER = ["FastDDS", "CycloneDDS"]
CASE_ORDER = [f"qos_case{i}" for i in range(8)]
COLORS = {"FastDDS": "#1f77b4", "CycloneDDS": "#d62728"}
MARKERS = {"FastDDS": "o", "CycloneDDS": "s"}
LINESTYLES = {"FastDDS": "-", "CycloneDDS": "--"}
CASE_COLORS = {
    "KL-1-REL": "#4e79a7",
    "KL-1-BE": "#f28e2b",
    "KL-10-REL": "#59a14f",
    "KL-10-BE": "#e15759",
    "KL-100-REL": "#b07aa1",
    "KL-100-BE": "#9c755f",
    "KA-REL": "#76b7b2",
    "KA-BE": "#767f8c",
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
            "lines.linewidth": 1.1,
            "lines.markersize": 3.4,
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
    summaries = []
    trial_frames = []
    usage_frames = []

    for rmw, folder in DATASETS:
        summary = pd.read_csv(folder / "qos_sweep_summary.csv")
        summary["qos_case"] = pd.Categorical(summary["qos_case"], categories=CASE_ORDER, ordered=True)
        summary = summary.sort_values("qos_case").reset_index(drop=True)
        summary["case_label"] = summary.apply(case_label, axis=1)
        summary["RMW"] = rmw

        for _, row in summary.iterrows():
            case_folder = folder / str(row["qos_case"])
            latency = read_trial_csv(case_folder / "total_latency.csv")
            throughput = read_trial_csv(case_folder / "throughput.csv", usecols=[0, 1, 2])
            trial = latency.merge(throughput, on=["trial", "trial_num"], how="left")
            if USE_TRIMMED_2S:
                trial = apply_trimmed_metrics(trial, qos_trimmed_trials(rmw, str(row["qos_case"])))
            else:
                trial = attach_period_jitter(trial, qos_jitter_trials(rmw, str(row["qos_case"])))

            usage = pd.read_csv(case_folder / "host_trials_usage.csv")
            usage["trial_num"] = trial_number(usage["trial"].astype(str))

            for frame in (trial, usage):
                frame["RMW"] = rmw
                frame["qos_case"] = row["qos_case"]
                frame["history"] = row["history"]
                frame["depth"] = int(row["depth"])
                frame["reliability"] = row["reliability"]
                frame["case_label"] = row["case_label"]
            trial_frames.append(trial)
            usage_frames.append(usage)

        summaries.append(summary)

    summary_all = pd.concat(summaries, ignore_index=True)
    trials = pd.concat(trial_frames, ignore_index=True)
    usage_all = pd.concat(usage_frames, ignore_index=True)

    trial_stats = (
        trials.groupby(["RMW", "qos_case"], observed=True)
        .agg(
            trial_count=("trial_num", "nunique"),
            latency_mean=("mean[ms]", "mean"),
            latency_mean_std=("mean[ms]", "std"),
            lost_total=("lost[#]", "sum"),
            jitter_mean=("jitter[ms]", "mean"),
            jitter_std=("jitter[ms]", "std"),
            throughput_mean=("throughput[MB/s]", "mean"),
            throughput_std=("throughput[MB/s]", "std"),
        )
        .reset_index()
    )
    usage_stats = (
        usage_all.groupby(["RMW", "qos_case"], observed=True)
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
    enriched = summary_all.merge(trial_stats, on=["RMW", "qos_case"], how="left").merge(usage_stats, on=["RMW", "qos_case"], how="left")
    if USE_TRIMMED_2S:
        enriched["mean[ms]"] = enriched["latency_mean"]
        enriched["lost[#]"] = enriched["lost_total"]
        enriched["throughput[MB/s]"] = enriched["throughput_mean"]
        enriched["throughput[B/s]"] = enriched["throughput_mean"] * 1_000_000.0
    enriched["jitter[ms]"] = enriched["jitter_mean"]
    enriched["RMW"] = pd.Categorical(enriched["RMW"], categories=RMW_ORDER, ordered=True)
    enriched["qos_case"] = pd.Categorical(enriched["qos_case"], categories=CASE_ORDER, ordered=True)
    enriched = enriched.sort_values(["qos_case", "RMW"]).reset_index(drop=True)
    enriched["RMW"] = enriched["RMW"].astype(str)
    enriched["qos_case"] = enriched["qos_case"].astype(str)
    return enriched, trials, usage_all


def grouped_bar(
    ax,
    summary: pd.DataFrame,
    value_col: str,
    err_col: str | None,
    title: str,
    ylabel: str,
    show_legend: bool = True,
) -> None:
    labels = summary.drop_duplicates("qos_case").sort_values("qos_case")["case_label"].tolist()
    x = np.arange(len(labels))
    width = min(0.78 / len(RMW_ORDER), 0.34)
    for i, rmw in enumerate(RMW_ORDER):
        data = summary[summary["RMW"] == rmw].sort_values("qos_case")
        offset = (i - (len(RMW_ORDER) - 1) / 2) * width
        errors = None if err_col is None else data[err_col].to_numpy(dtype=float)
        ax.bar(
            x + offset,
            data[value_col].to_numpy(dtype=float),
            width=width,
            yerr=errors,
            capsize=2.5 if errors is not None else 0,
            color=COLORS[rmw],
            edgecolor="black",
            linewidth=0.55,
            alpha=0.82,
            label=rmw,
        )
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if show_legend:
        ax.legend(loc="best", frameon=True)
    finish_axis(ax)


def plot_metric_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 4.9))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.20, hspace=0.62, wspace=0.34)
    grouped_bar(axes[0, 0], summary, "mean[ms]", "latency_mean_std", "Mean latency", "Latency [ms]", show_legend=False)
    grouped_bar(axes[0, 1], summary, "jitter[ms]", "jitter_std", "Jitter", "Jitter [ms]", show_legend=False)
    grouped_bar(axes[1, 0], summary, "lost[#]", None, "Message loss", "Messages lost [#]", show_legend=False)
    grouped_bar(
        axes[1, 1],
        summary,
        "throughput[MB/s]",
        "throughput_std",
        "Throughput",
        "Throughput [MB/s]",
        show_legend=False,
    )
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.04), ncol=len(RMW_ORDER), frameon=True)
    path = FIGURE_DIR / "fig01_metric_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_keep_last_depth(summary: pd.DataFrame) -> Path:
    keep_last = summary[summary["history"] == "KEEP_LAST"].copy()
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.2))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.93, bottom=0.20, hspace=0.58, wspace=0.34)
    specs = [
        ("mean[ms]", "Latency", "Latency [ms]"),
        ("jitter[ms]", "Jitter", "Jitter [ms]"),
        ("lost[#]", "Message loss", "Messages lost [#]"),
        ("throughput[MB/s]", "Throughput", "Throughput [MB/s]"),
    ]
    for ax, (col, title, ylabel) in zip(axes.ravel(), specs):
        for rmw in RMW_ORDER:
            for reliability, linestyle in [("RELIABLE", "-"), ("BEST_EFFORT", "--")]:
                data = keep_last[(keep_last["RMW"] == rmw) & (keep_last["reliability"] == reliability)].sort_values("depth")
                ax.plot(
                    data["depth"],
                    data[col],
                    marker=MARKERS[rmw],
                    color=COLORS[rmw],
                    linestyle=linestyle,
                    label=f"{rmw} {reliability}",
                )
        ax.set_xscale("log")
        ax.set_xticks([1, 10, 100], ["1", "10", "100"])
        ax.set_xlabel("Depth")
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        finish_axis(ax, x_grid=True)
    rmw_handles = [
        Line2D([0], [0], color=COLORS[rmw], marker=MARKERS[rmw], linestyle="-", label=rmw)
        for rmw in RMW_ORDER
    ]
    reliability_handles = [
        Line2D([0], [0], color="#333333", linestyle="-", label="RELIABLE"),
        Line2D([0], [0], color="#333333", linestyle="--", label="BEST_EFFORT"),
    ]
    first_legend = fig.legend(
        handles=rmw_handles,
        loc="lower center",
        bbox_to_anchor=(0.34, 0.035),
        ncol=len(RMW_ORDER),
        frameon=True,
        fontsize=5.6,
        title="RMW",
        title_fontsize=5.8,
    )
    fig.add_artist(first_legend)
    fig.legend(
        handles=reliability_handles,
        loc="lower center",
        bbox_to_anchor=(0.74, 0.035),
        ncol=2,
        frameon=True,
        fontsize=5.6,
        title="Reliability",
        title_fontsize=5.8,
    )
    path = FIGURE_DIR / "fig02_keep_last_depth.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_distributions(trials: pd.DataFrame) -> Path:
    labels = trials.drop_duplicates("qos_case").sort_values("qos_case")["case_label"].tolist()
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 5.0))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.17, hspace=0.55)
    for ax, col, title, ylabel in [
        (axes[0], "mean[ms]", "Mean latency distribution", "Latency [ms]"),
        (axes[1], "jitter[ms]", "Jitter distribution", "Jitter [ms]"),
    ]:
        positions = []
        values = []
        colors = []
        tick_positions = []
        base = np.arange(len(labels)) * (len(RMW_ORDER) + 1.0)
        for j, label in enumerate(labels):
            tick_positions.append(base[j] + (len(RMW_ORDER) - 1) / 2)
            for i, rmw in enumerate(RMW_ORDER):
                subset = trials[(trials["case_label"] == label) & (trials["RMW"] == rmw)]
                positions.append(base[j] + i)
                values.append(subset[col].dropna().to_numpy())
                colors.append(COLORS[rmw])
        box = ax.boxplot(values, positions=positions, widths=0.7, patch_artist=True, showfliers=False)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.55)
            patch.set_edgecolor("black")
        ax.set_xticks(tick_positions, labels, rotation=25, ha="right")
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        finish_axis(ax)
    fig.legend(
        [plt.Rectangle((0, 0), 1, 1, color=COLORS[rmw], alpha=0.55, ec="black") for rmw in RMW_ORDER],
        RMW_ORDER,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.035),
        ncol=len(RMW_ORDER),
        frameon=True,
    )
    path = FIGURE_DIR / "fig03_distributions.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_resource_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(7.0, 6.4))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.95, bottom=0.12, hspace=0.52)
    specs = [
        ("cpu_mean", "cpu_std", "CPU mean", "CPU mean [%]"),
        ("memory_mean", "memory_std", "Memory mean", "Memory mean [%]"),
        ("load1_mean", "load1_std", "Load average", "Load average"),
    ]
    for ax, (value_col, err_col, title, ylabel) in zip(axes, specs):
        grouped_bar(ax, summary, value_col, err_col, title, ylabel, show_legend=False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.025), ncol=len(RMW_ORDER), frameon=True)
    path = FIGURE_DIR / "fig04_resource_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_trial_trends(trials: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 6.0))
    fig.subplots_adjust(left=0.09, right=0.76, top=0.94, bottom=0.11, hspace=0.48)
    for rmw in RMW_ORDER:
        rmw_data = trials[trials["RMW"] == rmw]
        means = rmw_data.groupby(["case_label", "trial_num"], observed=True).agg(
            latency=("mean[ms]", "mean"),
            jitter=("jitter[ms]", "mean"),
        ).reset_index()
        for label in means["case_label"].drop_duplicates():
            data = means[means["case_label"] == label].sort_values("trial_num")
            linestyle = LINESTYLES.get(rmw, "-")
            color = CASE_COLORS.get(label, COLORS[rmw])
            axes[0].plot(data["trial_num"], data["latency"], color=color, linestyle=linestyle, marker=MARKERS[rmw], markevery=3)
            axes[1].plot(data["trial_num"], data["jitter"], color=color, linestyle=linestyle, marker=MARKERS[rmw], markevery=3)
    axes[0].set_title("Trial trend: latency")
    axes[0].set_ylabel("Latency [ms]")
    axes[1].set_title("Trial trend: jitter")
    axes[1].set_ylabel("Jitter [ms]")
    for ax in axes:
        ax.set_xlabel("Trial")
        rmw_handles = [
            Line2D([0], [0], color="#333333", marker=MARKERS[rmw], linestyle=LINESTYLES.get(rmw, "-"), label=rmw)
            for rmw in RMW_ORDER
        ]
        case_labels = trials.drop_duplicates("qos_case").sort_values("qos_case")["case_label"].tolist()
        case_handles = [
            Line2D([0], [0], color=CASE_COLORS.get(label, "#555555"), linestyle="-", label=label)
            for label in case_labels
        ]
        first_legend = ax.legend(
            handles=rmw_handles,
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            frameon=True,
            fontsize=5.2,
            title="RMW",
            title_fontsize=5.6,
        )
        ax.add_artist(first_legend)
        ax.legend(
            handles=case_handles,
            loc="upper left",
            bbox_to_anchor=(1.01, 0.62),
            frameon=True,
            fontsize=4.8,
            ncol=1,
            title="QoS",
            title_fontsize=5.3,
        )
        finish_axis(ax)
    path = FIGURE_DIR / "fig05_trial_trends.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    configure_style()
    summary, trials, usage = load_all()
    summary.to_csv(OUTPUT_DIR / "qos_rmw_summary.csv", index=False)
    trials.to_csv(OUTPUT_DIR / "qos_rmw_trials.csv", index=False)
    usage.to_csv(OUTPUT_DIR / "qos_rmw_host_usage.csv", index=False)
    paths = [
        plot_metric_summary(summary),
        plot_keep_last_depth(summary),
        plot_distributions(trials),
        plot_resource_summary(summary),
        plot_trial_trends(trials),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
