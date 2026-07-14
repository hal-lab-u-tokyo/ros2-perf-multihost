from pathlib import Path

import build_qos_rmw_comparison_figures as qos_figures


ZENOH_BASE = Path("/Users/kudoutakumi/Downloads/zenoh")

qos_figures.OUTPUT_DIR = Path("outputs/zenoh_qos_sweep")
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
