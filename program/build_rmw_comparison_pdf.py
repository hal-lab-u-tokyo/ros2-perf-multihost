from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from analysis_config import RMW_COMPARISON_BASE, ZENOH_NATIVE2_BASE, output_path, pdf_path


OUTPUT_DIR = output_path("rmw_comparison")
FIGURE_DIR = OUTPUT_DIR / "figures"
OUTPUT_PDF = pdf_path("rmw_comparison_report.pdf")
PDF_DIR = OUTPUT_PDF.parent
SOURCE_DIR = RMW_COMPARISON_BASE
ZENOH_NATIVE_SOURCE = ZENOH_NATIVE2_BASE
REPORT_TITLE = "RMW Comparison Report"
FILTER_NOTE = ""


def add_page_number(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(doc.pagesize[0] - 0.45 * inch, 0.22 * inch, f"Page {doc.page}")
    canvas.restoreState()


def figure(story, path: Path, caption: str, styles, width: float = 6.85 * inch, ratio: float = 0.69) -> None:
    story.append(Image(str(path), width=width, height=width * ratio))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(caption, styles["Caption"]))


def summary_table(summary: pd.DataFrame) -> Table:
    display = summary[
        [
            "Environment",
            "RMW",
            "Trials",
            "Lost total [#]",
            "Latency mean [ms]",
            "Jitter mean [ms]",
            "Throughput mean [MB/s]",
            "CPU mean [%]",
            "Memory mean [%]",
            "Load1 mean",
        ]
    ].copy()
    display = display.rename(
        columns={
            "Environment": "Env.",
            "Lost total [#]": "Msg. lost [#]",
            "Latency mean [ms]": "Latency [ms]",
            "Jitter mean [ms]": "Jitter [ms]",
            "Throughput mean [MB/s]": "Throughput [MB/s]",
            "CPU mean [%]": "CPU [%]",
            "Memory mean [%]": "Memory [%]",
            "Load1 mean": "Load1",
        }
    )
    for col in ["Latency [ms]", "Jitter [ms]", "CPU [%]", "Memory [%]", "Load1"]:
        display[col] = display[col].map(lambda value: f"{value:.3f}")
    display["Throughput [MB/s]"] = display["Throughput [MB/s]"].map(lambda value: f"{value:.6f}")
    display["Msg. lost [#]"] = display["Msg. lost [#]"].astype(int)
    display["Trials"] = display["Trials"].astype(int)

    data = [display.columns.tolist()] + display.values.tolist()
    table = Table(
        data,
        repeatRows=1,
        colWidths=[
            0.62 * inch,
            0.82 * inch,
            0.38 * inch,
            0.50 * inch,
            0.66 * inch,
            0.64 * inch,
            0.90 * inch,
            0.48 * inch,
            0.58 * inch,
            0.42 * inch,
        ],
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.35),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def build_pdf() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(OUTPUT_DIR / "summary.csv")

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
            "FastDDS, CycloneDDS, and Zenoh are compared under Docker and Native environments. "
            "Jitter is computed from raw receive timestamp intervals as the mean absolute deviation from the configured 100 ms message period. "
            "Message-index gaps are accounted for, and error bars indicate the standard deviation across trials. "
            f"{FILTER_NOTE}",
            styles["BodyText"],
        )
    )
    story.append(Paragraph(f"Source directory: {SOURCE_DIR}", styles["BodyText"]))
    story.append(Paragraph(f"Zenoh Native source replaced with: {ZENOH_NATIVE_SOURCE}", styles["BodyText"]))
    story.append(Spacer(1, 0.12 * inch))
    story.append(summary_table(summary))
    story.append(Spacer(1, 0.16 * inch))
    figure(
        story,
        FIGURE_DIR / "fig01_latency_jitter_summary.png",
        "Fig. 1 Mean latency and jitter by RMW. Error bars show standard deviation.",
        styles,
    )

    story.append(PageBreak())
    story.append(Paragraph("Message Loss And Throughput", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    figure(
        story,
        FIGURE_DIR / "fig02_loss_throughput_summary.png",
        "Fig. 2 Total message loss and mean throughput by RMW. Throughput error bars show standard deviation.",
        styles,
    )

    story.append(PageBreak())
    story.append(Paragraph("Trial Trends", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    figure(
        story,
        FIGURE_DIR / "fig03_trial_trends.png",
        "Fig. 3 Trial-by-trial trends of mean latency and jitter.",
        styles,
    )

    story.append(PageBreak())
    story.append(Paragraph("Distribution", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    figure(
        story,
        FIGURE_DIR / "fig04_distributions.png",
        "Fig. 4 Distributions of mean latency and jitter across trials. Outlier markers are omitted for readability.",
        styles,
    )

    story.append(PageBreak())
    story.append(Paragraph("Host Resource Usage", styles["Heading2"]))
    story.append(Spacer(1, 0.08 * inch))
    figure(
        story,
        FIGURE_DIR / "fig05_resource_summary.png",
        "Fig. 5 CPU, memory, and load average summarized from host trial usage logs. Error bars show standard deviation.",
        styles,
        ratio=0.97,
    )

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Saved {OUTPUT_PDF}")


if __name__ == "__main__":
    build_pdf()
