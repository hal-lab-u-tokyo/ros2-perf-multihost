from pathlib import Path

import pandas as pd

from period_jitter_data import CONSTANT_SOURCES, PAYLOAD_SOURCES, QOS_SOURCES, trial_number


TRIMMED_CSV = Path("outputs/raw_trimmed_2s/trimmed_trials.csv")
METRIC_COLUMNS = [
    "lost[#]",
    "mean[ms]",
    "sd[ms]",
    "min[ms]",
    "q1[ms]",
    "mid[ms]",
    "q3[ms]",
    "max[ms]",
    "throughput[B/s]",
    "throughput[MB/s]",
    "jitter[ms]",
]


def _load_trimmed() -> pd.DataFrame:
    if not TRIMMED_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(TRIMMED_CSV)
    df["trial_num"] = trial_number(df["trial"])
    return df


def _by_source(source_zip: str | None, case: str | None = None) -> pd.DataFrame:
    if source_zip is None:
        return pd.DataFrame(columns=["trial_num", *METRIC_COLUMNS])
    df = _load_trimmed()
    if df.empty:
        return pd.DataFrame(columns=["trial_num", *METRIC_COLUMNS])
    df = df[df["source_zip"] == source_zip].copy()
    if case is not None:
        df = df[df["case"].astype(str) == str(case)].copy()
    return df[["trial_num", *METRIC_COLUMNS]].sort_values("trial_num")


def constant_trimmed_trials(rmw: str, environment: str) -> pd.DataFrame:
    return _by_source(CONSTANT_SOURCES.get((rmw, environment)))


def qos_trimmed_trials(rmw: str, qos_case: str) -> pd.DataFrame:
    return _by_source(QOS_SOURCES.get(rmw), qos_case)


def payload_trimmed_trials(rmw: str, payload: str) -> pd.DataFrame:
    return _by_source(PAYLOAD_SOURCES.get((rmw, payload)))


def apply_trimmed_metrics(trials: pd.DataFrame, trimmed_trials: pd.DataFrame) -> pd.DataFrame:
    if trimmed_trials.empty:
        return trials
    trials = trials.drop(columns=[col for col in METRIC_COLUMNS if col in trials.columns], errors="ignore")
    return trials.merge(trimmed_trials, on="trial_num", how="left")
