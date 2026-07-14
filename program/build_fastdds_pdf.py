from pathlib import Path

import pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from analysis_config import RMW_COMPARISON_BASE, output_path, pdf_path


INPUT_CSV = RMW_COMPARISON_BASE / "fastdds" / "docker" / "host_trials_usage.csv"
EXCEL_RENDER_DIR = output_path("fastdds_docker_usage")
PAPER_FIGURE_DIR = EXCEL_RENDER_DIR / "paper_style_figures"
TMP_DIR = Path("tmp/pdfs")
OUTPUT_PDF = pdf_path("fastdds_docker_usage_report.pdf")
OUTPUT_DIR = OUTPUT_PDF.parent


def prepare_data() -> pd.DataFrame:
    df = pd.read_csv(INPUT_CSV)
    df["trial_num"] = df["trial"].str.extract(r"(\d+)").astype(int)
    return df.sort_values(["trial_num", "host"])


def host_order(df: pd.DataFrame) -> list[str]:
    return sorted(df["host"].unique(), key=lambda value: int("".join(ch for ch in value if ch.isdigit())))


def summary_table(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("host", sort=False)
    return pd.DataFrame(
        {
            "Avg CPU mean %": grouped["cpu_mean[%]"].mean(),
            "Avg CPU max %": grouped["cpu_max[%]"].mean(),
            "Peak CPU max %": grouped["cpu_max[%]"].max(),
            "Avg memory mean %": grouped["mem_mean[%]"].mean(),
            "Peak memory max %": grouped["mem_max[%]"].max(),
            "Avg load1": grouped["load1_mean"].mean(),
            "Peak swap %": grouped["swap_max[%]"].max(),
            "Total samples": grouped["samples"].sum(),
        }
    ).reset_index()


def crop_excel_render(source: Path, target: Path) -> None:
    with PILImage.open(source) as image:
        width, height = image.size
        cropped = image.crop((39, 20, width, height))
        cropped.save(target)


def add_page_number(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(doc.pagesize[0] - 0.45 * inch, 0.22 * inch, f"Page {doc.page}")
    canvas.restoreState()


def add_figure(story, path: Path, caption: str, styles, width: float = 6.8 * inch) -> None:
    story.append(Image(str(path), width=width, height=width * 0.69))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(caption, styles["BodyText"]))


def build_pdf(df: pd.DataFrame, summary: pd.DataFrame, figure_paths: dict[str, Path]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
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
    story = []

    story.append(Paragraph("Fast DDS Docker Usage Report", styles["Title"]))
    story.append(Paragraph(f"Source CSV: {INPUT_CSV}", styles["BodyText"]))
    story.append(
        Paragraph(
            f"Rows: {len(df):,} | Hosts: {df['host'].nunique()} | Trials per host: {df['trial_num'].nunique()} | "
            f"Samples per trial: {int(df['samples'].iloc[0])} | Peak swap: {df['swap_max[%]'].max():.3f}%",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 0.12 * inch))

    display = summary.copy()
    numeric_cols = [col for col in display.columns if col not in ["host", "Total samples"]]
    display[numeric_cols] = display[numeric_cols].round(3)
    display["Total samples"] = display["Total samples"].astype(int)
    table_data = [display.columns.tolist()] + display.values.tolist()
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.0),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.2 * inch))
    add_figure(story, figure_paths["host_summary"], "Fig. 1 Host-level resource usage summary.", styles)

    story.append(PageBreak())
    story.append(Paragraph("Trial-Level Resource Usage", styles["Heading2"]))
    story.append(Spacer(1, 0.12 * inch))
    add_figure(story, figure_paths["trial_usage"], "Fig. 2 CPU, memory, and load trends across 100 trials.", styles)

    story.append(PageBreak())
    story.append(Paragraph("Latency, Message Loss, And Throughput", styles["Heading2"]))
    story.append(Spacer(1, 0.12 * inch))
    add_figure(story, figure_paths["network"], "Fig. 3 Latency, message loss, and throughput trends.", styles)

    story.append(PageBreak())
    story.append(Paragraph("Latency Distribution", styles["Heading2"]))
    story.append(Spacer(1, 0.12 * inch))
    story.append(Image(str(figure_paths["latency_box"]), width=6.8 * inch, height=3.85 * inch))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph("Fig. 4 Latency distribution summarized by trial range.", styles["BodyText"]))

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)


def main() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    df = prepare_data()
    hosts = host_order(df)
    summary = summary_table(df).set_index("host").loc[hosts].reset_index()
    figure_paths = {
        "host_summary": PAPER_FIGURE_DIR / "paper_host_summary.png",
        "trial_usage": PAPER_FIGURE_DIR / "paper_trial_usage.png",
        "network": PAPER_FIGURE_DIR / "paper_network.png",
        "latency_box": PAPER_FIGURE_DIR / "paper_latency_box.png",
    }
    build_pdf(df, summary, figure_paths)
    print(f"Saved {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
