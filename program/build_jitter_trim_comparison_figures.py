from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from period_jitter_data import CONSTANT_SOURCES, PAYLOAD_SOURCES, QOS_SOURCES, trial_number


TRIMS = [1.0, 3.0]
TRIM_LABELS = {1.0: "Drop first 1s", 3.0: "Drop first 3s"}
INPUT_BY_TRIM = {
    1.0: Path("outputs/raw_trimmed_1s/trimmed_trials.csv"),
    3.0: Path("outputs/raw_trimmed_3s/trimmed_trials.csv"),
}
OUTPUT_DIR = Path("outputs/jitter_trim1s_3s")
FIGURE_DIR = OUTPUT_DIR / "figures"
QOS_BASE = Path("/Users/kudoutakumi/Downloads/qos_variant")
ZENOH_QOS_BASE = Path("/Users/kudoutakumi/Downloads/zenoh")

RMW_ORDER = ["FastDDS", "CycloneDDS", "Zenoh"]
ENV_ORDER = ["Docker", "Native"]
QOS_RMW_ORDER = ["FastDDS", "CycloneDDS"]
ZENOH_ENV_ORDER = ["Zenoh Docker", "Zenoh Native"]
CASE_ORDER = [f"qos_case{i}" for i in range(8)]
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
RMW_COLORS = {"FastDDS": "#1f77b4", "CycloneDDS": "#d62728", "Zenoh": "#2ca02c"}
QOS_COLORS = {"FastDDS": "#1f77b4", "CycloneDDS": "#d62728"}
ZENOH_COLORS = {"Zenoh Docker": "#1f77b4", "Zenoh Native": "#ff7f0e"}
TRIM_COLORS = {1.0: "#4e79a7", 3.0: "#f28e2b"}
MARKERS = {"FastDDS": "o", "CycloneDDS": "s", "Zenoh": "^", "Zenoh Docker": "o", "Zenoh Native": "^"}


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
            "lines.markersize": 3.6,
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


def case_label(row: pd.Series) -> str:
    history = "KL" if row["history"] == "KEEP_LAST" else "KA"
    reliability = "REL" if row["reliability"] == "RELIABLE" else "BE"
    if row["history"] == "KEEP_ALL":
        return f"{history}-{reliability}"
    return f"{history}-{int(row['depth'])}-{reliability}"


def load_case_labels(summary_path: Path) -> dict[str, str]:
    if not summary_path.exists():
        return {case: case.replace("qos_case", "case") for case in CASE_ORDER}
    summary = pd.read_csv(summary_path)
    summary["case_label"] = summary.apply(case_label, axis=1)
    return dict(zip(summary["qos_case"].astype(str), summary["case_label"]))


def read_trimmed_trials() -> pd.DataFrame:
    frames = []
    for trim, path in INPUT_BY_TRIM.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing trimmed data: {path}")
        frame = pd.read_csv(path)
        frame["trim_seconds"] = trim
        frame["trim_label"] = TRIM_LABELS[trim]
        frame["trial_num"] = trial_number(frame["trial"].astype(str))
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def select_rows(df: pd.DataFrame, source_zip: str, case: str | None = None) -> pd.DataFrame:
    selected = df[df["source_zip"] == source_zip].copy()
    if case is not None:
        selected = selected[selected["case"].astype(str) == case].copy()
    return selected


def summary_stats(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    summary = (
        df.groupby(group_cols, observed=True)
        .agg(
            Trials=("trial_num", "nunique"),
            Samples=("jitter_count", "sum"),
            Jitter_mean_ms=("jitter[ms]", "mean"),
            Jitter_std_ms=("jitter[ms]", "std"),
        )
        .reset_index()
    )
    summary["Jitter_std_ms"] = summary["Jitter_std_ms"].fillna(0.0)
    return summary


def build_rmw_frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for (rmw, env), source_zip in CONSTANT_SOURCES.items():
        selected = select_rows(df, source_zip)
        selected["RMW"] = rmw
        selected["Environment"] = env
        rows.append(selected)
    trials = pd.concat(rows, ignore_index=True)
    trials["RMW"] = pd.Categorical(trials["RMW"], categories=RMW_ORDER, ordered=True)
    trials["Environment"] = pd.Categorical(trials["Environment"], categories=ENV_ORDER, ordered=True)
    summary = summary_stats(trials, ["trim_seconds", "trim_label", "Environment", "RMW"])
    summary = summary.sort_values(["trim_seconds", "Environment", "RMW"]).reset_index(drop=True)
    trials["RMW"] = trials["RMW"].astype(str)
    trials["Environment"] = trials["Environment"].astype(str)
    summary["RMW"] = summary["RMW"].astype(str)
    summary["Environment"] = summary["Environment"].astype(str)
    return trials, summary


def build_qos_frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = load_case_labels(QOS_BASE / "fastdds-docker" / "qos_sweep_summary.csv")
    rows = []
    for rmw in QOS_RMW_ORDER:
        source_zip = QOS_SOURCES[rmw]
        for case in CASE_ORDER:
            selected = select_rows(df, source_zip, case)
            selected["RMW"] = rmw
            selected["qos_case"] = case
            selected["case_label"] = labels.get(case, case)
            rows.append(selected)
    trials = pd.concat(rows, ignore_index=True)
    trials["RMW"] = pd.Categorical(trials["RMW"], categories=QOS_RMW_ORDER, ordered=True)
    trials["qos_case"] = pd.Categorical(trials["qos_case"], categories=CASE_ORDER, ordered=True)
    summary = summary_stats(trials, ["trim_seconds", "trim_label", "qos_case", "case_label", "RMW"])
    summary = summary.sort_values(["trim_seconds", "qos_case", "RMW"]).reset_index(drop=True)
    for frame in (trials, summary):
        frame["RMW"] = frame["RMW"].astype(str)
        frame["qos_case"] = frame["qos_case"].astype(str)
    return trials, summary


def build_zenoh_qos_frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = load_case_labels(ZENOH_QOS_BASE / "docker" / "qos_sweep_summary.csv")
    rows = []
    for rmw in ZENOH_ENV_ORDER:
        source_zip = QOS_SOURCES[rmw]
        for case in CASE_ORDER:
            selected = select_rows(df, source_zip, case)
            selected["Dataset"] = rmw
            selected["qos_case"] = case
            selected["case_label"] = labels.get(case, case)
            rows.append(selected)
    trials = pd.concat(rows, ignore_index=True)
    trials["Dataset"] = pd.Categorical(trials["Dataset"], categories=ZENOH_ENV_ORDER, ordered=True)
    trials["qos_case"] = pd.Categorical(trials["qos_case"], categories=CASE_ORDER, ordered=True)
    summary = summary_stats(trials, ["trim_seconds", "trim_label", "qos_case", "case_label", "Dataset"])
    summary = summary.sort_values(["trim_seconds", "qos_case", "Dataset"]).reset_index(drop=True)
    for frame in (trials, summary):
        frame["Dataset"] = frame["Dataset"].astype(str)
        frame["qos_case"] = frame["qos_case"].astype(str)
    return trials, summary


def build_payload_frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for (rmw, payload), source_zip in PAYLOAD_SOURCES.items():
        if payload not in PAYLOAD_ORDER:
            continue
        selected = select_rows(df, source_zip)
        selected["RMW"] = rmw
        selected["payload"] = payload
        selected["payload_label"] = PAYLOAD_LABELS[payload]
        selected["payload_bytes"] = PAYLOAD_BYTES[payload]
        rows.append(selected)
    trials = pd.concat(rows, ignore_index=True)
    trials["RMW"] = pd.Categorical(trials["RMW"], categories=QOS_RMW_ORDER, ordered=True)
    trials["payload"] = pd.Categorical(trials["payload"], categories=PAYLOAD_ORDER, ordered=True)
    summary = summary_stats(trials, ["trim_seconds", "trim_label", "payload", "payload_label", "payload_bytes", "RMW"])
    summary = summary.sort_values(["trim_seconds", "payload", "RMW"]).reset_index(drop=True)
    for frame in (trials, summary):
        frame["RMW"] = frame["RMW"].astype(str)
        frame["payload"] = frame["payload"].astype(str)
    return trials, summary


def plot_rmw_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0), sharey=True)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.24, wspace=0.22)
    width = 0.34
    for ax, env in zip(axes, ENV_ORDER):
        env_data = summary[summary["Environment"] == env]
        x = np.arange(len(RMW_ORDER))
        for i, trim in enumerate(TRIMS):
            values = []
            errors = []
            for rmw in RMW_ORDER:
                row = env_data[(env_data["RMW"] == rmw) & (env_data["trim_seconds"] == trim)]
                values.append(float(row["Jitter_mean_ms"].iloc[0]) if not row.empty else np.nan)
                errors.append(float(row["Jitter_std_ms"].iloc[0]) if not row.empty else 0.0)
            offset = (i - 0.5) * width
            ax.bar(
                x + offset,
                values,
                width=width,
                yerr=errors,
                capsize=2.5,
                color=TRIM_COLORS[trim],
                edgecolor="black",
                linewidth=0.55,
                alpha=0.84,
                label=TRIM_LABELS[trim],
            )
        ax.set_xticks(x, RMW_ORDER)
        ax.set_title(f"{env}: jitter")
        ax.set_ylabel("Jitter [ms]")
        finish_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.045), ncol=2, frameon=True)
    path = FIGURE_DIR / "fig01_rmw_jitter_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def grouped_qos_plot(
    summary: pd.DataFrame,
    category_col: str,
    order: list[str],
    colors: dict[str, str],
    title_prefix: str,
    filename: str,
) -> Path:
    labels = summary.drop_duplicates("qos_case").sort_values("qos_case")["case_label"].tolist()
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.4), sharey=True)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.86, bottom=0.30, wspace=0.18)
    x = np.arange(len(labels))
    width = min(0.78 / len(order), 0.34)
    for ax, trim in zip(axes, TRIMS):
        trim_data = summary[summary["trim_seconds"] == trim]
        for i, category in enumerate(order):
            data = trim_data[trim_data[category_col] == category].sort_values("qos_case")
            offset = (i - (len(order) - 1) / 2) * width
            ax.bar(
                x + offset,
                data["Jitter_mean_ms"].to_numpy(dtype=float),
                width=width,
                yerr=data["Jitter_std_ms"].to_numpy(dtype=float),
                capsize=2.2,
                color=colors[category],
                edgecolor="black",
                linewidth=0.55,
                alpha=0.84,
                label=category,
            )
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_title(f"{title_prefix}: {TRIM_LABELS[trim]}")
        ax.set_ylabel("Jitter [ms]")
        finish_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.035), ncol=len(order), frameon=True)
    path = FIGURE_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def payload_axis(ax) -> None:
    ticks = [PAYLOAD_BYTES[payload] for payload in PAYLOAD_ORDER]
    labels = [PAYLOAD_LABELS[payload] for payload in PAYLOAD_ORDER]
    ax.set_xscale("log", base=2)
    ax.set_xticks(ticks, labels)
    ax.set_xlabel("Payload size")


def plot_payload_summary(summary: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.2), sharey=True)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.86, bottom=0.25, wspace=0.18)
    for ax, trim in zip(axes, TRIMS):
        trim_data = summary[summary["trim_seconds"] == trim]
        for rmw in QOS_RMW_ORDER:
            data = trim_data[trim_data["RMW"] == rmw].sort_values("payload_bytes")
            ax.errorbar(
                data["payload_bytes"],
                data["Jitter_mean_ms"],
                yerr=data["Jitter_std_ms"],
                marker=MARKERS[rmw],
                color=QOS_COLORS[rmw],
                capsize=2.5,
                label=rmw,
            )
        ax.set_title(f"Payload: {TRIM_LABELS[trim]}")
        ax.set_ylabel("Jitter [ms]")
        payload_axis(ax)
        finish_axis(ax, x_grid=True)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.035), ncol=2, frameon=True)
    path = FIGURE_DIR / "fig04_payload_jitter_summary.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_trial_trends(
    trials: pd.DataFrame,
    category_col: str,
    order: list[str],
    colors: dict[str, str],
    title_prefix: str,
    filename: str,
) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.2), sharey=True)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.86, bottom=0.25, wspace=0.18)
    linestyles = {1.0: "-", 3.0: "--"}
    for ax, trim in zip(axes, TRIMS):
        trim_data = trials[trials["trim_seconds"] == trim]
        for category in order:
            data = trim_data[trim_data[category_col] == category].sort_values("trial_num")
            means = data.groupby("trial_num", observed=True)["jitter[ms]"].mean().reset_index()
            mark_every = max(1, len(means) // 10)
            ax.plot(
                means["trial_num"],
                means["jitter[ms]"],
                color=colors[category],
                marker=MARKERS.get(category, "o"),
                markevery=mark_every,
                linestyle=linestyles[trim],
                label=category,
            )
        ax.set_title(f"{title_prefix}: {TRIM_LABELS[trim]}")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Jitter [ms]")
        finish_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.035), ncol=len(order), frameon=True)
    path = FIGURE_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_payload_trends(trials: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.2), sharey=True)
    fig.subplots_adjust(left=0.10, right=0.82, top=0.86, bottom=0.23, wspace=0.18)
    linestyles = {"FastDDS": "-", "CycloneDDS": "--"}
    payload_colors = {
        "payload1K": "#4e79a7",
        "payload2K": "#f28e2b",
        "payload4K": "#59a14f",
        "payload8K": "#e15759",
        "payload1M": "#b07aa1",
        "payload2M": "#767f8c",
    }
    for ax, trim in zip(axes, TRIMS):
        trim_data = trials[trials["trim_seconds"] == trim]
        for rmw in QOS_RMW_ORDER:
            for payload in PAYLOAD_ORDER:
                data = trim_data[(trim_data["RMW"] == rmw) & (trim_data["payload"] == payload)].sort_values("trial_num")
                ax.plot(
                    data["trial_num"],
                    data["jitter[ms]"],
                    color=payload_colors[payload],
                    marker=MARKERS[rmw],
                    linestyle=linestyles[rmw],
                    alpha=0.9,
                )
        ax.set_title(f"Payload trend: {TRIM_LABELS[trim]}")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Jitter [ms]")
        finish_axis(ax)
    rmw_handles = [
        Line2D([0], [0], color="#333333", marker=MARKERS[rmw], linestyle=linestyles[rmw], label=rmw)
        for rmw in QOS_RMW_ORDER
    ]
    payload_handles = [
        Patch(facecolor=payload_colors[payload], edgecolor="black", label=PAYLOAD_LABELS[payload])
        for payload in PAYLOAD_ORDER
    ]
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
        loc="center right",
        bbox_to_anchor=(0.985, 0.38),
        frameon=True,
        fontsize=5.4,
        title="Payload",
        title_fontsize=6,
    )
    path = FIGURE_DIR / "fig08_payload_jitter_trends.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def write_outputs(
    rmw_summary: pd.DataFrame,
    rmw_trials: pd.DataFrame,
    qos_summary: pd.DataFrame,
    qos_trials: pd.DataFrame,
    zenoh_summary: pd.DataFrame,
    zenoh_trials: pd.DataFrame,
    payload_summary: pd.DataFrame,
    payload_trials: pd.DataFrame,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rmw_summary.to_csv(OUTPUT_DIR / "rmw_jitter_summary.csv", index=False)
    rmw_trials.to_csv(OUTPUT_DIR / "rmw_jitter_trials.csv", index=False)
    qos_summary.to_csv(OUTPUT_DIR / "qos_rmw_jitter_summary.csv", index=False)
    qos_trials.to_csv(OUTPUT_DIR / "qos_rmw_jitter_trials.csv", index=False)
    zenoh_summary.to_csv(OUTPUT_DIR / "zenoh_qos_jitter_summary.csv", index=False)
    zenoh_trials.to_csv(OUTPUT_DIR / "zenoh_qos_jitter_trials.csv", index=False)
    payload_summary.to_csv(OUTPUT_DIR / "payload_jitter_summary.csv", index=False)
    payload_trials.to_csv(OUTPUT_DIR / "payload_jitter_trials.csv", index=False)


def main() -> None:
    configure_style()
    df = read_trimmed_trials()
    rmw_trials, rmw_summary = build_rmw_frames(df)
    qos_trials, qos_summary = build_qos_frames(df)
    zenoh_trials, zenoh_summary = build_zenoh_qos_frames(df)
    payload_trials, payload_summary = build_payload_frames(df)
    write_outputs(
        rmw_summary,
        rmw_trials,
        qos_summary,
        qos_trials,
        zenoh_summary,
        zenoh_trials,
        payload_summary,
        payload_trials,
    )
    paths = [
        plot_rmw_summary(rmw_summary),
        grouped_qos_plot(qos_summary, "RMW", QOS_RMW_ORDER, QOS_COLORS, "QoS/RMW Docker jitter", "fig02_qos_rmw_jitter_summary.png"),
        grouped_qos_plot(
            zenoh_summary,
            "Dataset",
            ZENOH_ENV_ORDER,
            ZENOH_COLORS,
            "Zenoh QoS jitter",
            "fig03_zenoh_qos_jitter_summary.png",
        ),
        plot_payload_summary(payload_summary),
        plot_trial_trends(rmw_trials, "RMW", RMW_ORDER, RMW_COLORS, "RMW trial trend", "fig05_rmw_jitter_trends.png"),
        plot_trial_trends(qos_trials, "RMW", QOS_RMW_ORDER, QOS_COLORS, "QoS/RMW trial trend", "fig06_qos_rmw_jitter_trends.png"),
        plot_trial_trends(
            zenoh_trials,
            "Dataset",
            ZENOH_ENV_ORDER,
            ZENOH_COLORS,
            "Zenoh QoS trial trend",
            "fig07_zenoh_qos_jitter_trends.png",
        ),
        plot_payload_trends(payload_trials),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
