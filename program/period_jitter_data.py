from pathlib import Path

import pandas as pd


JITTER_CSV = Path("outputs/raw_period_jitter/period_jitter_trials.csv")
JITTER_VALUE_COL = "period_jitter_mean_abs_ms"

CONSTANT_SOURCES = {
    ("FastDDS", "Docker"): "2026-07-06_17-13-58-fastdds.zip",
    ("FastDDS", "Native"): "2026-07-06_18-29-27-fastdds.zip",
    ("CycloneDDS", "Docker"): "2026-07-06_21-47-19-cyclonedds.zip",
    ("CycloneDDS", "Native"): "2026-07-06_22-22-02-cyclonedds.zip",
    ("Zenoh", "Docker"): "2026-07-07_07-56-01-zenoh.zip",
    ("Zenoh", "Native"): "2026-07-07_12-19-02-zenoh.zip",
}

QOS_SOURCES = {
    "FastDDS": "2026-07-07_09-44-25-fastdds.zip",
    "CycloneDDS": "2026-07-07_11-06-20-cyclonedds.zip",
    "Zenoh": "2026-07-08_15-42-13-zenoh.zip",
    "Zenoh Docker": "2026-07-08_15-42-13-zenoh.zip",
    "Zenoh Native": "2026-07-08_16-53-54-zenoh.zip",
}

PAYLOAD_SOURCES = {
    ("FastDDS", "payload1K"): "2026-07-07_15-33-38-fastdds.zip",
    ("FastDDS", "payload2K"): "2026-07-07_15-57-41-fastdds.zip",
    ("FastDDS", "payload4K"): "2026-07-07_16-19-27-fastdds.zip",
    ("FastDDS", "payload8K"): "2026-07-07_16-37-33-fastdds.zip",
    ("FastDDS", "payload1M"): "2026-07-07_16-57-45-fastdds.zip",
    ("FastDDS", "payload2M"): "2026-07-08_18-18-32-fastdds.zip",
    ("CycloneDDS", "payload1K"): "2026-07-07_15-43-49-cyclonedds.zip",
    ("CycloneDDS", "payload2K"): "2026-07-07_16-07-24-cyclonedds.zip",
    ("CycloneDDS", "payload4K"): "2026-07-07_16-27-42-cyclonedds.zip",
    ("CycloneDDS", "payload8K"): "2026-07-07_16-45-14-cyclonedds.zip",
    ("CycloneDDS", "payload1M"): "2026-07-07_17-05-45-cyclonedds.zip",
    ("CycloneDDS", "payload2M"): "2026-07-08_18-27-19-cyclonedds.zip",
}


def trial_number(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d+)").astype(int)[0]


def _load_jitter() -> pd.DataFrame:
    if not JITTER_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(JITTER_CSV)
    df["trial_num"] = trial_number(df["trial"])
    return df


def _jitter_by_source(source_zip: str, case: str | None = None) -> pd.DataFrame:
    df = _load_jitter()
    if df.empty:
        return pd.DataFrame(columns=["trial_num", "jitter[ms]"])
    df = df[df["source_zip"] == source_zip].copy()
    if case is not None:
        df = df[df["case"].astype(str) == str(case)].copy()
    return (
        df[["trial_num", JITTER_VALUE_COL]]
        .rename(columns={JITTER_VALUE_COL: "jitter[ms]"})
        .sort_values("trial_num")
    )


def constant_jitter_trials(rmw: str, environment: str) -> pd.DataFrame:
    source_zip = CONSTANT_SOURCES.get((rmw, environment))
    if source_zip is None:
        return pd.DataFrame(columns=["trial_num", "jitter[ms]"])
    return _jitter_by_source(source_zip)


def qos_jitter_trials(rmw: str, qos_case: str) -> pd.DataFrame:
    source_zip = QOS_SOURCES.get(rmw)
    if source_zip is None:
        return pd.DataFrame(columns=["trial_num", "jitter[ms]"])
    return _jitter_by_source(source_zip, qos_case)


def payload_jitter_trials(rmw: str, payload: str) -> pd.DataFrame:
    source_zip = PAYLOAD_SOURCES.get((rmw, payload))
    if source_zip is None:
        return pd.DataFrame(columns=["trial_num", "jitter[ms]"])
    return _jitter_by_source(source_zip)


def attach_period_jitter(trials: pd.DataFrame, jitter_trials: pd.DataFrame) -> pd.DataFrame:
    fallback = trials["max[ms]"] - trials["min[ms]"]
    trials = trials.drop(columns=["jitter[ms]"], errors="ignore").merge(jitter_trials, on="trial_num", how="left")
    trials["jitter[ms]"] = trials["jitter[ms]"].fillna(fallback)
    return trials
