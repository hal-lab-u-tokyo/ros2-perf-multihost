import importlib
import sys

from analysis_config import ZENOH_QOS_BASE, output_path, pdf_path


NOTE = "All network metrics in this report exclude messages received during the first 2 seconds of each trial."


def build_rmw_figures() -> None:
    import build_rmw_comparison_figures as figures

    figures.OUTPUT_DIR = output_path("rmw_comparison_trim2s")
    figures.FIGURE_DIR = figures.OUTPUT_DIR / "figures"
    figures.USE_TRIMMED_2S = True
    figures.main()


def build_rmw_pdf() -> None:
    import build_rmw_comparison_pdf as pdf

    output_dir = output_path("rmw_comparison_trim2s")
    pdf.OUTPUT_DIR = output_dir
    pdf.FIGURE_DIR = output_dir / "figures"
    pdf.OUTPUT_PDF = pdf_path("rmw_comparison_trim2s_report.pdf")
    pdf.REPORT_TITLE = "RMW Comparison Report - First 2 Seconds Excluded"
    pdf.FILTER_NOTE = NOTE
    pdf.build_pdf()


def build_qos_rmw_figures() -> None:
    import build_qos_rmw_comparison_figures as figures

    figures.OUTPUT_DIR = output_path("qos_rmw_comparison_trim2s")
    figures.FIGURE_DIR = figures.OUTPUT_DIR / "figures"
    figures.DATASETS = [
        ("FastDDS", figures.BASE / "fastdds-docker"),
        ("CycloneDDS", figures.BASE / "cyclonedds-docker"),
    ]
    figures.RMW_ORDER = ["FastDDS", "CycloneDDS"]
    figures.COLORS = {"FastDDS": "#1f77b4", "CycloneDDS": "#d62728"}
    figures.MARKERS = {"FastDDS": "o", "CycloneDDS": "s"}
    figures.LINESTYLES = {"FastDDS": "-", "CycloneDDS": "--"}
    figures.USE_TRIMMED_2S = True
    figures.main()


def build_qos_rmw_pdf() -> None:
    import build_qos_rmw_comparison_pdf as pdf

    output_dir = output_path("qos_rmw_comparison_trim2s")
    pdf.OUTPUT_DIR = output_dir
    pdf.FIGURE_DIR = output_dir / "figures"
    pdf.OUTPUT_PDF = pdf_path("qos_rmw_comparison_trim2s_report.pdf")
    pdf.REPORT_TITLE = "QoS And RMW Docker Comparison Report - First 2 Seconds Excluded"
    pdf.FILTER_NOTE = NOTE
    pdf.build_pdf()


def build_zenoh_qos_figures() -> None:
    import build_qos_rmw_comparison_figures as figures

    figures = importlib.reload(figures)
    zenoh_base = ZENOH_QOS_BASE
    figures.OUTPUT_DIR = output_path("zenoh_qos_sweep_trim2s")
    figures.FIGURE_DIR = figures.OUTPUT_DIR / "figures"
    figures.DATASETS = [
        ("Zenoh Docker", zenoh_base / "docker"),
        ("Zenoh Native", zenoh_base / "native"),
    ]
    figures.RMW_ORDER = ["Zenoh Docker", "Zenoh Native"]
    figures.COLORS = {"Zenoh Docker": "#1f77b4", "Zenoh Native": "#ff7f0e"}
    figures.MARKERS = {"Zenoh Docker": "o", "Zenoh Native": "^"}
    figures.LINESTYLES = {"Zenoh Docker": "-", "Zenoh Native": "--"}
    figures.USE_TRIMMED_2S = True
    figures.main()


def build_zenoh_qos_pdf() -> None:
    import build_zenoh_qos_sweep_pdf as pdf

    output_dir = output_path("zenoh_qos_sweep_trim2s")
    pdf.OUTPUT_DIR = output_dir
    pdf.FIGURE_DIR = output_dir / "figures"
    pdf.OUTPUT_PDF = pdf_path("zenoh_qos_sweep_trim2s_report.pdf")
    pdf.REPORT_TITLE = "Zenoh QoS Sweep Report - First 2 Seconds Excluded"
    pdf.FILTER_NOTE = NOTE
    pdf.build_pdf()


def build_payload_figures() -> None:
    import build_payloadsize_rmw_comparison_figures as figures

    figures.OUTPUT_DIR = output_path("payloadsize_rmw_comparison_trim2s")
    figures.FIGURE_DIR = figures.OUTPUT_DIR / "figures"
    figures.USE_TRIMMED_2S = True
    figures.main()


def build_payload_pdf() -> None:
    import build_payloadsize_rmw_comparison_pdf as pdf

    output_dir = output_path("payloadsize_rmw_comparison_trim2s")
    pdf.OUTPUT_DIR = output_dir
    pdf.FIGURE_DIR = output_dir / "figures"
    pdf.OUTPUT_PDF = pdf_path("payloadsize_rmw_comparison_trim2s_report.pdf")
    pdf.REPORT_TITLE = "Payload Size RMW Comparison Report - First 2 Seconds Excluded"
    pdf.FILTER_NOTE = NOTE
    pdf.build_pdf()


def build_figures() -> None:
    build_rmw_figures()
    build_qos_rmw_figures()
    build_zenoh_qos_figures()
    build_payload_figures()


def build_pdfs() -> None:
    build_rmw_pdf()
    build_qos_rmw_pdf()
    build_zenoh_qos_pdf()
    build_payload_pdf()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"
    if mode in ("--figures", "--all"):
        build_figures()
    if mode in ("--pdfs", "--all"):
        build_pdfs()


if __name__ == "__main__":
    main()
