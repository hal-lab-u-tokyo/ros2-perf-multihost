import build_qos_rmw_comparison_figures as qos_figures
from analysis_config import ZENOH_QOS_BASE, output_path


ZENOH_BASE = ZENOH_QOS_BASE

qos_figures.OUTPUT_DIR = output_path("zenoh_qos_sweep")
qos_figures.FIGURE_DIR = qos_figures.OUTPUT_DIR / "figures"
qos_figures.DATASETS = [
    ("Zenoh Docker", ZENOH_BASE / "docker"),
    ("Zenoh Native", ZENOH_BASE / "native"),
]
qos_figures.RMW_ORDER = ["Zenoh Docker", "Zenoh Native"]
qos_figures.COLORS = {"Zenoh Docker": "#1f77b4", "Zenoh Native": "#ff7f0e"}
qos_figures.MARKERS = {"Zenoh Docker": "o", "Zenoh Native": "^"}
qos_figures.LINESTYLES = {"Zenoh Docker": "-", "Zenoh Native": "--"}


if __name__ == "__main__":
    qos_figures.main()
