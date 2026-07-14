from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT_DIR = Path("outputs/fastdds_docker_qos_sweep")
FIGURE_DIR = OUTPUT_DIR / "figures"
PDF_DIR = Path("output/pdf")
OUTPUT_PDF = PDF_DIR / "fastdds_docker_qos_sweep_report.pdf"
SOURCE_CSV = Path("/Users/kudoutakumi/Downloads/fastdds-docker/qos_sweep_summary.csv")


def add_page_number(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(doc.pagesize[0] - 0.45 * inch, 0.22 * inch, f"Page {doc.page}")
    canvas.restoreState()


def add_figure(story, path: Path, caption: str, styles, width: float = 6.85 * inch, ratio: float = 0.70) -> None:
    story.append(Image(str(path), width=width, height=width * ratio))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(caption, styles["Caption"]))


def summary_table(summary: pd.DataFrame) -> Table:
    display = summary[
        [
            "case_label",
            "history",
            "depth",
            "reliability",
            "lost[#]",
            "mean[ms]",
            "jitter[ms]",
            "throughput[MB/s]",
            "cpu_mean",
            "memory_mean",
            "load1_mean",
        ]
    ].copy()
    display = display.rename(
        columns={
            "case_label": "Case",
            "history": "History",
            "depth": "Depth",
            "reliability": "Reliability",
            "lost[#]": "Msg. lost [#]",
            "mean[ms]": "Latency [ms]",
            "jitter[ms]": "Jitter [ms]",
            "throughput[MB/s]": "Throughput [MB/s]",
            "cpu_mean": "CPU [%]",
            "memory_mean": "Memory [%]",
            "load1_mean": "Load1",
        }
    )
    for col in ["Latency [ms]", "Jitter [ms]", "CPU [%]", "Memory [%]", "Load1"]:
        display[col] = display[col].map(lambda value: f"{value:.3f}")
    display["Throughput [MB/s]"] = display["Throughput [MB/s]"].map(lambda value: f"{value:.6f}")
    display["Depth"] = display["Depth"].astype(int)
    display["Msg. lost [#]"] = display["Msg. lost [#]"].astype(int)

    data = [display.columns.tolist()] + display.values.tolist()
    table = Table(
        data,
        repeatRows=1,
        colWidths=[
            0.58 * inch,
            0.68 * inch,
            0.34 * inch,
            0.74 * inch,
            0.48 * inch,
            0.54 * inch,
            0.50 * inch,
            0.78 * inch,
            0.42 * inch,
            0.52 * inch,
            0.36 * inch,
        ],
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 5.55),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def build_pdf() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(OUTPUT_DIR / "qos_sweep_enriched_summary.csv")

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.42 * inch,
        bottomMargin=0.42 * inch,
    )
    styles = getSampleStyleSheet()
    styles["Title"].fontName = "Times-Roman"
    styles["Heading2"].fontName = "Times-Bold"
    styles["BodyText"].fontName = "Times-Roman"
    styles["BodyText"].fontSize = 8.5
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["BodyText"],
            fontName="Times-Roman",
            fontSize=8,
            leading=10,
            spaceAfter=4,
        )
    )

    story = []
    story.append(Paragraph("FastDDS Docker QoS Sweep Report", styles["Title"]))
    story.append(
        Paragraph(
            "This report summarizes FastDDS measurements collected in Docker while sweeping QoS settings. "
            "KL denotes KEEP_LAST, KA denotes KEEP_ALL, REL denotes RELIABLE, and BE denotes BEST_EFFORT. "
            "Jitter is computed from raw receive timestamp intervals as the mean absolute deviation from the configured 100 ms message period. "
            "Message-index gaps are accounted for, and error bars indicate standard deviation across trials where applicable.",
            styles["BodyText"],
        )
    )
    story.append(Paragraph(f"Source CSV: {SOURCE_CSV}", styles["BodyText"]))
    story.append(Spacer(1, 0.12 * inch))
    story.append(summary_table(summary))
    story.append(Spacer(1, 0.15 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig01_qos_summary_bars.png",
        "Fig. 1 QoS case summary for latency, jitter, message loss, and throughput. Hatched bars indicate KEEP_ALL.",
        styles,
    )

    story.append(PageBreak())
    story.append(Paragraph("KEEP_LAST Depth Sweep", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig02_keep_last_depth_sweep.png",
        "Fig. 2 Effect of depth on KEEP_LAST QoS cases, shown separately for RELIABLE and BEST_EFFORT.",
        styles,
    )

    story.append(PageBreak())
    story.append(Paragraph("Trial Trends", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig03_trial_trends.png",
        "Fig. 3 Trial-by-trial trends of mean latency and jitter for all QoS cases.",
        styles,
        ratio=0.72,
    )

    story.append(PageBreak())
    story.append(Paragraph("Distributions", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig04_distributions.png",
        "Fig. 4 Latency and jitter distributions across ten trials. Outlier markers are omitted for readability.",
        styles,
        ratio=0.72,
    )

    story.append(PageBreak())
    story.append(Paragraph("Host Resource Usage", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig05_resource_summary.png",
        "Fig. 5 CPU, memory, and load average summarized from host trial usage logs.",
        styles,
        ratio=0.91,
    )

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Saved {OUTPUT_PDF}")


if __name__ == "__main__":
    build_pdf()
