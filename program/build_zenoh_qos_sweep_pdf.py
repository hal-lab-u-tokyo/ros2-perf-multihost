from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from build_qos_rmw_comparison_pdf import add_figure, add_page_number, summary_table


OUTPUT_DIR = Path("outputs/zenoh_qos_sweep")
FIGURE_DIR = OUTPUT_DIR / "figures"
PDF_DIR = Path("output/pdf")
OUTPUT_PDF = PDF_DIR / "zenoh_qos_sweep_report.pdf"
SOURCE_DIR = Path("/Users/kudoutakumi/Downloads/zenoh")
REPORT_TITLE = "Zenoh QoS Sweep Report"
FILTER_NOTE = ""


def build_pdf() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(OUTPUT_DIR / "qos_rmw_summary.csv")

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
    story.append(Paragraph(REPORT_TITLE, styles["Title"]))
    story.append(
        Paragraph(
            "Zenoh Docker and Zenoh Native are compared across the same QoS cases. "
            "Jitter is computed from raw receive timestamp intervals as the mean absolute deviation from the configured 100 ms message period. "
            "Message-index gaps are accounted for, and error bars indicate standard deviation across trials where applicable. "
            f"{FILTER_NOTE}",
            styles["BodyText"],
        )
    )
    story.append(Paragraph(f"Source directory: {SOURCE_DIR}", styles["BodyText"]))
    story.append(Spacer(1, 0.10 * inch))
    story.append(summary_table(summary))

    story.append(PageBreak())
    story.append(Paragraph("QoS Case Summary", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig01_metric_summary.png",
        "Fig. 1 Zenoh QoS case summary for latency, jitter, message loss, and throughput.",
        styles,
        ratio=0.68,
    )

    story.append(PageBreak())
    story.append(Paragraph("KEEP_LAST Depth Sweep", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig02_keep_last_depth.png",
        "Fig. 2 KEEP_LAST depth sweep. Solid lines denote RELIABLE; dashed lines denote BEST_EFFORT.",
        styles,
        ratio=0.76,
    )

    story.append(PageBreak())
    story.append(Paragraph("Distributions", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig03_distributions.png",
        "Fig. 3 Trial-level distributions of mean latency and jitter for each QoS case.",
        styles,
        ratio=0.72,
    )

    story.append(PageBreak())
    story.append(Paragraph("Host Resource Usage", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig04_resource_summary.png",
        "Fig. 4 CPU, memory, and load average summarized from host trial usage logs.",
        styles,
        ratio=0.91,
    )

    story.append(PageBreak())
    story.append(Paragraph("Trial Trends", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig05_trial_trends.png",
        "Fig. 5 Trial-by-trial trends of latency and jitter.",
        styles,
        ratio=0.86,
    )

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Saved {OUTPUT_PDF}")


if __name__ == "__main__":
    build_pdf()
