from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT_DIR = Path("outputs/jitter_trim1s_3s")
FIGURE_DIR = OUTPUT_DIR / "figures"
PDF_DIR = Path("output/pdf")
OUTPUT_PDF = PDF_DIR / "jitter_trim1s_3s_report.pdf"


def add_page_number(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(doc.pagesize[0] - 0.45 * inch, 0.22 * inch, f"Page {doc.page}")
    canvas.restoreState()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def mean(values: list[float]) -> float:
    values = [value for value in values if value == value]
    return sum(values) / len(values) if values else float("nan")


def fmt(value: float, digits: int = 3) -> str:
    return "" if value != value else f"{value:.{digits}f}"


def table_style(font_size: float = 7.0) -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
        ]
    )


def overview_table() -> Table:
    specs = [
        ("RMW comparison", OUTPUT_DIR / "rmw_jitter_summary.csv", "Environment"),
        ("QoS/RMW Docker", OUTPUT_DIR / "qos_rmw_jitter_summary.csv", "RMW"),
        ("Zenoh QoS", OUTPUT_DIR / "zenoh_qos_jitter_summary.csv", "Dataset"),
        ("Payload size", OUTPUT_DIR / "payload_jitter_summary.csv", "RMW"),
    ]
    data = [["Section", "Trim", "Mean jitter [ms]", "Std mean [ms]", "Max mean [ms]"]]
    for section, path, _group_col in specs:
        rows = read_rows(path)
        by_trim: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_trim[row["trim_label"]].append(row)
        for trim_label in ["Drop first 1s", "Drop first 3s"]:
            trim_rows = by_trim.get(trim_label, [])
            means = [float(row["Jitter_mean_ms"]) for row in trim_rows]
            stds = [float(row["Jitter_std_ms"]) for row in trim_rows]
            data.append([section, trim_label, fmt(mean(means)), fmt(mean(stds)), fmt(max(means) if means else float("nan"))])
    table = Table(data, repeatRows=1, colWidths=[1.35 * inch, 1.05 * inch, 1.0 * inch, 0.95 * inch, 0.95 * inch])
    table.setStyle(table_style(7.2))
    return table


def rmw_table() -> Table:
    rows = read_rows(OUTPUT_DIR / "rmw_jitter_summary.csv")
    data = [["Trim", "Env.", "RMW", "Trials", "Jitter mean [ms]", "Jitter std [ms]"]]
    for row in rows:
        data.append(
            [
                row["trim_label"].replace("Drop first ", ""),
                row["Environment"],
                row["RMW"],
                row["Trials"],
                fmt(float(row["Jitter_mean_ms"])),
                fmt(float(row["Jitter_std_ms"])),
            ]
        )
    table = Table(data, repeatRows=1, colWidths=[0.62 * inch, 0.65 * inch, 0.83 * inch, 0.45 * inch, 0.92 * inch, 0.82 * inch])
    table.setStyle(table_style(6.8))
    return table


def add_figure(story, path: Path, caption: str, styles, ratio: float = 0.48) -> None:
    story.append(Image(str(path), width=6.85 * inch, height=6.85 * inch * ratio))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(caption, styles["Caption"]))


def build_pdf() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
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
    story.append(Paragraph("Jitter Comparison Report - First 1s and 3s Excluded", styles["Title"]))
    story.append(
        Paragraph(
            "This report only shows jitter. Each trial is recalculated from raw receive timestamps after excluding messages received during the first 1 second or first 3 seconds. "
            "Jitter is the mean absolute deviation of receive intervals from the configured message period. "
            "When message indexes skip, the expected interval is scaled by the index gap. Error bars show standard deviation across trials.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 0.12 * inch))
    story.append(overview_table())
    story.append(Spacer(1, 0.16 * inch))
    story.append(Paragraph("RMW Comparison", styles["Heading2"]))
    story.append(rmw_table())
    story.append(Spacer(1, 0.10 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig01_rmw_jitter_summary.png",
        "Fig. 1 RMW comparison jitter after dropping the first 1s or 3s of each trial.",
        styles,
        ratio=0.43,
    )

    story.append(PageBreak())
    story.append(Paragraph("QoS/RMW Docker Comparison", styles["Heading2"]))
    add_figure(
        story,
        FIGURE_DIR / "fig02_qos_rmw_jitter_summary.png",
        "Fig. 2 Docker-only FastDDS and CycloneDDS QoS jitter comparison.",
        styles,
        ratio=0.49,
    )
    story.append(Spacer(1, 0.16 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig06_qos_rmw_jitter_trends.png",
        "Fig. 3 Trial trend of Docker-only FastDDS and CycloneDDS jitter.",
        styles,
        ratio=0.46,
    )

    story.append(PageBreak())
    story.append(Paragraph("Zenoh QoS Sweep", styles["Heading2"]))
    add_figure(
        story,
        FIGURE_DIR / "fig03_zenoh_qos_jitter_summary.png",
        "Fig. 4 Zenoh Docker and Zenoh Native QoS jitter comparison.",
        styles,
        ratio=0.49,
    )
    story.append(Spacer(1, 0.16 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig07_zenoh_qos_jitter_trends.png",
        "Fig. 5 Trial trend of Zenoh QoS jitter.",
        styles,
        ratio=0.46,
    )

    story.append(PageBreak())
    story.append(Paragraph("Payload Size Sweep", styles["Heading2"]))
    add_figure(
        story,
        FIGURE_DIR / "fig04_payload_jitter_summary.png",
        "Fig. 6 Payload-size jitter comparison for FastDDS Docker and CycloneDDS Docker.",
        styles,
        ratio=0.46,
    )
    story.append(Spacer(1, 0.16 * inch))
    add_figure(
        story,
        FIGURE_DIR / "fig08_payload_jitter_trends.png",
        "Fig. 7 Trial trend of payload-size jitter.",
        styles,
        ratio=0.46,
    )

    story.append(PageBreak())
    story.append(Paragraph("RMW Trial Trends", styles["Heading2"]))
    add_figure(
        story,
        FIGURE_DIR / "fig05_rmw_jitter_trends.png",
        "Fig. 8 Trial trend of RMW comparison jitter.",
        styles,
        ratio=0.46,
    )

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Saved {OUTPUT_PDF}")


if __name__ == "__main__":
    build_pdf()
