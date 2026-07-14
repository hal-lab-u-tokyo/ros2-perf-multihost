import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const programDir = path.dirname(fileURLToPath(import.meta.url));
const rmwBase = process.env.ROS2_ANALYSIS_RMW_BASE ?? path.join(programDir, "data", "qos_constant");
const fastddsDockerBase = path.join(rmwBase, "fastdds", "docker");
const inputCsv = path.join(fastddsDockerBase, "host_trials_usage.csv");
const latencyCsv = path.join(fastddsDockerBase, "total_latency.csv");
const throughputCsv = path.join(fastddsDockerBase, "throughput.csv");
const outputRoot = process.env.ROS2_ANALYSIS_OUTPUT_ROOT ?? path.join(programDir, "outputs");
const outputDir = path.join(outputRoot, "fastdds_docker_usage");
const outputXlsx = path.join(outputDir, "fastdds_docker_usage_graphs.xlsx");
const paperFigureDir = path.join(outputDir, "paper_style_figures");

const csvText = await fs.readFile(inputCsv, "utf8");
const latencyText = await fs.readFile(latencyCsv, "utf8");
const throughputText = await fs.readFile(throughputCsv, "utf8");
const lines = csvText.trim().split(/\r?\n/);
const dataRows = lines.slice(1);
const rawLastRow = lines.length;

function parseCsvRows(text) {
  return text.trim().split(/\r?\n/).map((line) => line.split(","));
}

const latencyRows = parseCsvRows(latencyText);
const latencyHeader = latencyRows[0];
const latencyTrialRows = latencyRows.slice(1).filter((row) => row[0]?.startsWith("trial"));
const throughputRows = parseCsvRows(throughputText);
const throughputTrialRows = throughputRows.slice(1).filter((row) => row[0]?.startsWith("trial"));
const throughputByTrial = new Map(throughputTrialRows.map((row) => [row[0], row]));
const networkRows = latencyTrialRows.map((row) => {
  const trialNum = Number(row[0].replace(/\D/g, ""));
  const throughput = throughputByTrial.get(row[0]) ?? [row[0], null, null];
  return [
    trialNum,
    row[0],
    Number(row[1]),
    Number(row[2]),
    Number(row[3]),
    Number(row[4]),
    Number(row[5]),
    Number(row[6]),
    Number(row[7]),
    Number(row[8]),
    throughput[1] === null ? null : Number(throughput[1]),
    throughput[2] === null ? null : Number(throughput[2]),
  ];
});
const networkLastRow = networkRows.length + 1;

const hosts = [...new Set(dataRows.map((line) => line.split(",")[0]))].sort((a, b) => {
  const an = Number(a.replace(/\D/g, ""));
  const bn = Number(b.replace(/\D/g, ""));
  return an - bn;
});
const trials = [...new Set(dataRows.map((line) => line.split(",")[1]))].sort((a, b) => {
  const an = Number(a.replace(/\D/g, ""));
  const bn = Number(b.replace(/\D/g, ""));
  return an - bn;
});
const trialCount = trials.length;
const samplesPerTrial = Number(dataRows[0].split(",")[9]);

function colName(index) {
  let n = index;
  let out = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    out = String.fromCharCode(65 + rem) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

function styleHeader(range, fill = "#1F4E79") {
  range.format = {
    fill,
    font: { bold: true, color: "#FFFFFF" },
    borders: { preset: "outside", style: "thin", color: "#A6A6A6" },
  };
}

function styleSectionTitle(range) {
  range.format = {
    fill: "#EAF2F8",
    font: { bold: true, color: "#17365D" },
    borders: { preset: "outside", style: "thin", color: "#B7C9D6" },
  };
}

function rawRef(col) {
  return `'Raw Data'!$${col}$2:$${col}$${rawLastRow}`;
}

function chartDataRef(col, startRow) {
  return `'Chart Data'!$${col}$${startRow + 1}:$${col}$${startRow + trialCount}`;
}

function addSingleSeriesBar(sheet, title, seriesName, categoryFormula, valueFormula, topLeft, bottomRight, numberFormatCode) {
  const chart = sheet.charts.add("bar", { chartType: "bar", title, hasLegend: false });
  const series = chart.series.add(seriesName);
  series.categoryFormula = categoryFormula;
  series.formula = valueFormula;
  chart.title = title;
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = false;
  chart.xAxis = { numberFormatCode };
  chart.yAxis = { numberFormatCode };
  chart.setPosition(topLeft, bottomRight);
  return chart;
}

function addLineChart(sheet, title, metricStartRow, topLeft, bottomRight, numberFormatCode) {
  const chart = sheet.charts.add("line", { chartType: "line", title, hasLegend: true });
  hosts.forEach((host, index) => {
    const series = chart.series.add(host);
    const valueCol = colName(index + 2);
    series.categoryFormula = chartDataRef("A", metricStartRow);
    series.formula = chartDataRef(valueCol, metricStartRow);
  });
  chart.title = title;
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis" };
  chart.yAxis = { numberFormatCode };
  chart.setPosition(topLeft, bottomRight);
  return chart;
}

function addNetworkLineChart(sheet, title, seriesSpecs, topLeft, bottomRight, numberFormatCode) {
  const chart = sheet.charts.add("line", { chartType: "line", title, hasLegend: true });
  for (const spec of seriesSpecs) {
    const series = chart.series.add(spec.name);
    series.categoryFormula = `'Network Data'!$A$2:$A$${networkLastRow}`;
    series.formula = `'Network Data'!$${spec.col}$2:$${spec.col}$${networkLastRow}`;
  }
  chart.title = title;
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis" };
  chart.yAxis = { numberFormatCode };
  chart.setPosition(topLeft, bottomRight);
  return chart;
}

function addNetworkSingleSeriesChart(sheet, chartType, title, seriesName, valueCol, topLeft, bottomRight, numberFormatCode) {
  const chart = sheet.charts.add(chartType, { chartType, title, hasLegend: false });
  const series = chart.series.add(seriesName);
  series.categoryFormula = `'Network Data'!$A$2:$A$${networkLastRow}`;
  series.formula = `'Network Data'!$${valueCol}$2:$${valueCol}$${networkLastRow}`;
  chart.title = title;
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = false;
  chart.xAxis = { axisType: "textAxis" };
  chart.yAxis = { numberFormatCode };
  chart.setPosition(topLeft, bottomRight);
  return chart;
}

async function addImageIfExists(sheet, filePath, row, col, widthPx, heightPx) {
  try {
    const bytes = await fs.readFile(filePath);
    const dataUrl = `data:image/png;base64,${bytes.toString("base64")}`;
    sheet.images.add({
      dataUrl,
      anchor: { from: { row, col }, extent: { widthPx, heightPx } },
    });
  } catch (error) {
    console.warn(`Skipped missing figure: ${filePath}`);
  }
}

function writeMetricTable(sheet, startRow, title, metricCol, numberFormat) {
  sheet.getRange(`A${startRow}:F${startRow}`).values = [[title, ...hosts]];
  styleHeader(sheet.getRange(`A${startRow}:F${startRow}`), "#4F81BD");

  const body = [];
  for (let t = 1; t <= trialCount; t += 1) {
    const row = startRow + t;
    const formulas = hosts.map((_, hostIndex) => {
      const hostHeaderCol = colName(hostIndex + 2);
      return `=AVERAGEIFS(${rawRef(metricCol)},${rawRef("A")},${hostHeaderCol}$${startRow},${rawRef("B")},"trial"&$A${row})`;
    });
    body.push([t, ...formulas]);
  }
  sheet.getRange(`A${startRow + 1}:F${startRow + trialCount}`).formulas = body;
  sheet.getRange(`A${startRow + 1}:A${startRow + trialCount}`).setNumberFormat("0");
  sheet.getRange(`B${startRow + 1}:F${startRow + trialCount}`).setNumberFormat(numberFormat);
  sheet.getRange(`A${startRow}:F${startRow + trialCount}`).format.borders = {
    preset: "all",
    style: "thin",
    color: "#D9E2F3",
  };
}

await fs.mkdir(outputDir, { recursive: true });

const workbook = await Workbook.fromCSV(csvText, { sheetName: "Raw Data" });
const raw = workbook.worksheets.getItem("Raw Data");
const dashboard = workbook.worksheets.add("Dashboard");
const trends = workbook.worksheets.add("Trial Trends");
const network = workbook.worksheets.add("Network Metrics");
const paperFigures = workbook.worksheets.add("Paper Style Figures");
const networkData = workbook.worksheets.add("Network Data");
const chartData = workbook.worksheets.add("Chart Data");

for (const sheet of [dashboard, trends, network, paperFigures, networkData, chartData, raw]) {
  sheet.showGridLines = false;
}

raw.freezePanes.freezeRows(1);
raw.getRange(`A1:J${rawLastRow}`).format.borders = { preset: "all", style: "thin", color: "#E6E6E6" };
styleHeader(raw.getRange("A1:J1"), "#1F4E79");
raw.getRange(`C2:I${rawLastRow}`).setNumberFormat("0.0000");
raw.getRange(`J2:J${rawLastRow}`).setNumberFormat("0");
raw.tables.add(`A1:J${rawLastRow}`, true, "RawUsageTable");
raw.getRange("A1:J25").format.autofitColumns();

dashboard.getRange("A1:P1").merge();
dashboard.getRange("A1").values = [["Fast DDS Docker Host Usage"]];
dashboard.getRange("A1:P1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF" },
};
dashboard.getRange("A2:P2").merge();
dashboard.getRange("A2").values = [["RMW Fast DDS measurements in Docker - host_trials_usage.csv"]];
dashboard.getRange("A2:P2").format = {
  fill: "#EAF2F8",
  font: { bold: true, color: "#17365D" },
};
dashboard.getRange("A3:P3").merge();
dashboard.getRange("A3").values = [[`Source CSV: ${inputCsv}`]];
dashboard.getRange("A3:P3").format.wrapText = true;

dashboard.getRange("A5:I5").values = [[
  "Host",
  "Avg CPU mean %",
  "Avg CPU max %",
  "Peak CPU max %",
  "Avg memory mean %",
  "Peak memory max %",
  "Avg load1",
  "Total samples",
  "Peak swap %",
]];
styleHeader(dashboard.getRange("A5:I5"));

dashboard.getRange("A6:A10").values = hosts.map((host) => [host]);
const summaryFormulas = hosts.map((_, index) => {
  const row = 6 + index;
  return [
    `=AVERAGEIF(${rawRef("A")},$A${row},${rawRef("C")})`,
    `=AVERAGEIF(${rawRef("A")},$A${row},${rawRef("D")})`,
    `=MAXIFS(${rawRef("D")},${rawRef("A")},$A${row})`,
    `=AVERAGEIF(${rawRef("A")},$A${row},${rawRef("E")})`,
    `=MAXIFS(${rawRef("F")},${rawRef("A")},$A${row})`,
    `=AVERAGEIF(${rawRef("A")},$A${row},${rawRef("G")})`,
    `=SUMIF(${rawRef("A")},$A${row},${rawRef("J")})`,
    `=MAXIFS(${rawRef("I")},${rawRef("A")},$A${row})`,
  ];
});
dashboard.getRange("B6:I10").formulas = summaryFormulas;
dashboard.getRange("A5:I10").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
dashboard.getRange("B6:F10").setNumberFormat("0.000");
dashboard.getRange("G6:G10").setNumberFormat("0.0000");
dashboard.getRange("H6:H10").setNumberFormat("#,##0");
dashboard.getRange("I6:I10").setNumberFormat("0.000");

dashboard.getRange("K5:P5").values = [["Rows", "Hosts", "Trials/host", "Samples/trial", "CPU peak max", "Swap peak max"]];
styleHeader(dashboard.getRange("K5:P5"), "#4472C4");
dashboard.getRange("K6:P6").formulas = [[
  `=COUNTA(${rawRef("A")})`,
  `=COUNTA(A6:A10)`,
  trialCount,
  samplesPerTrial,
  `=MAX(D6:D10)`,
  `=MAX(I6:I10)`,
]];
dashboard.getRange("K6:N6").setNumberFormat("#,##0");
dashboard.getRange("O6").setNumberFormat("0.0");
dashboard.getRange("P6").setNumberFormat("0.000");
dashboard.getRange("K5:P6").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };

addSingleSeriesBar(
  dashboard,
  "Average CPU mean by host (%)",
  "Avg CPU mean %",
  "'Dashboard'!$A$6:$A$10",
  "'Dashboard'!$B$6:$B$10",
  "A13",
  "H29",
  "0.00"
);
addSingleSeriesBar(
  dashboard,
  "Average memory mean by host (%)",
  "Avg memory mean %",
  "'Dashboard'!$A$6:$A$10",
  "'Dashboard'!$E$6:$E$10",
  "I13",
  "P29",
  "0.00"
);
addSingleSeriesBar(
  dashboard,
  "Average load1 by host",
  "Avg load1",
  "'Dashboard'!$A$6:$A$10",
  "'Dashboard'!$G$6:$G$10",
  "A31",
  "H47",
  "0.000"
);
addSingleSeriesBar(
  dashboard,
  "Peak CPU max by host (%)",
  "Peak CPU max %",
  "'Dashboard'!$A$6:$A$10",
  "'Dashboard'!$D$6:$D$10",
  "I31",
  "P47",
  "0.0"
);
dashboard.getRange("A1:P47").format.autofitColumns();

trends.getRange("A1:P1").merge();
trends.getRange("A1").values = [["Trial trends by host"]];
trends.getRange("A1:P1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF" },
};
addLineChart(trends, "CPU mean by trial (%)", 1, "A3", "H22", "0.00");
addLineChart(trends, "CPU max by trial (%)", 105, "I3", "P22", "0.0");
addLineChart(trends, "Memory mean by trial (%)", 209, "A24", "H43", "0.00");
addLineChart(trends, "Load1 mean by trial", 313, "I24", "P43", "0.000");

networkData.freezePanes.freezeRows(1);
networkData.getRange("A1:L1").values = [[
  "trial_num",
  latencyHeader[0],
  latencyHeader[1],
  latencyHeader[2],
  latencyHeader[3],
  latencyHeader[4],
  latencyHeader[5],
  latencyHeader[6],
  latencyHeader[7],
  latencyHeader[8],
  "throughput[B/s]",
  "throughput[MB/s]",
]];
networkData.getRange(`A2:L${networkLastRow}`).values = networkRows;
styleHeader(networkData.getRange("A1:L1"), "#1F4E79");
networkData.getRange(`A1:L${networkLastRow}`).format.borders = {
  preset: "all",
  style: "thin",
  color: "#E6E6E6",
};
networkData.getRange(`A2:C${networkLastRow}`).setNumberFormat("0");
networkData.getRange(`D2:J${networkLastRow}`).setNumberFormat("0.000000");
networkData.getRange(`K2:K${networkLastRow}`).setNumberFormat("#,##0.00");
networkData.getRange(`L2:L${networkLastRow}`).setNumberFormat("0.000000");
networkData.tables.add(`A1:L${networkLastRow}`, true, "NetworkDataTable");
networkData.getRange("A1:L25").format.autofitColumns();

network.getRange("A1:P1").merge();
network.getRange("A1").values = [["Fast DDS Latency, Packet Loss, And Throughput"]];
network.getRange("A1:P1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF" },
};
network.getRange("A2:P2").merge();
network.getRange("A2").values = [["Sources: total_latency.csv and throughput.csv"]];
network.getRange("A2:P2").format = {
  fill: "#EAF2F8",
  font: { bold: true, color: "#17365D" },
};

network.getRange("A4:H4").values = [[
  "Trials",
  "Total lost #",
  "Trials with loss",
  "Avg mean latency ms",
  "Median latency ms",
  "Max latency ms",
  "Avg throughput MB/s",
  "Min throughput MB/s",
]];
styleHeader(network.getRange("A4:H4"), "#4472C4");
network.getRange("A5:H5").formulas = [[
  `=COUNTA('Network Data'!$A$2:$A$${networkLastRow})`,
  `=SUM('Network Data'!$C$2:$C$${networkLastRow})`,
  `=COUNTIF('Network Data'!$C$2:$C$${networkLastRow},">0")`,
  `=AVERAGE('Network Data'!$D$2:$D$${networkLastRow})`,
  `=MEDIAN('Network Data'!$H$2:$H$${networkLastRow})`,
  `=MAX('Network Data'!$J$2:$J$${networkLastRow})`,
  `=AVERAGE('Network Data'!$L$2:$L$${networkLastRow})`,
  `=MIN('Network Data'!$L$2:$L$${networkLastRow})`,
]];
network.getRange("A5:C5").setNumberFormat("#,##0");
network.getRange("D5:F5").setNumberFormat("0.000000");
network.getRange("G5:H5").setNumberFormat("0.000000");
network.getRange("A4:H5").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };

network.getRange("J4:P4").values = [["Trial", "Lost #", "Mean ms", "Median ms", "Q3 ms", "Max ms", "Throughput MB/s"]];
styleHeader(network.getRange("J4:P4"), "#1F4E79");
const lossRows = networkRows.filter((row) => row[2] > 0).map((row) => [row[1], row[2], row[3], row[7], row[8], row[9], row[11]]);
if (lossRows.length > 0) {
  network.getRange(`J5:P${4 + lossRows.length}`).values = lossRows;
  network.getRange(`K5:K${4 + lossRows.length}`).setNumberFormat("0");
  network.getRange(`L5:P${4 + lossRows.length}`).setNumberFormat("0.000000");
  network.getRange(`J4:P${4 + lossRows.length}`).format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
}

addNetworkLineChart(
  network,
  "Latency trend by trial (ms)",
  [
    { name: "mean", col: "D" },
    { name: "median", col: "H" },
    { name: "max", col: "J" },
  ],
  "A13",
  "H32",
  "0.000"
);
addNetworkSingleSeriesChart(network, "bar", "Packet loss by trial (lost #)", "lost #", "C", "I13", "P32", "0");
addNetworkLineChart(
  network,
  "Latency quartiles by trial (ms)",
  [
    { name: "q1", col: "G" },
    { name: "median", col: "H" },
    { name: "q3", col: "I" },
  ],
  "A34",
  "H53",
  "0.000"
);
addNetworkSingleSeriesChart(network, "line", "Throughput by trial (MB/s)", "throughput MB/s", "L", "I34", "P53", "0.000000");
network.getRange("A1:P53").format.autofitColumns();

paperFigures.getRange("A1:P1").merge();
paperFigures.getRange("A1").values = [["Paper Style Figures"]];
paperFigures.getRange("A1:P1").format = {
  fill: "#FFFFFF",
  font: { bold: true, color: "#000000", size: 14 },
};
paperFigures.getRange("A2:P2").merge();
paperFigures.getRange("A2").values = [["Figures styled after the attached IPSJ SIG Technical Report: white background, thin lines, markers, light grids, compact legends."]];
paperFigures.getRange("A2:P2").format = {
  fill: "#FFFFFF",
  font: { color: "#333333" },
};
await addImageIfExists(paperFigures, path.join(paperFigureDir, "paper_host_summary.png"), 3, 0, 730, 500);
await addImageIfExists(paperFigures, path.join(paperFigureDir, "paper_trial_usage.png"), 3, 8, 730, 500);
await addImageIfExists(paperFigures, path.join(paperFigureDir, "paper_network.png"), 30, 0, 730, 500);
await addImageIfExists(paperFigures, path.join(paperFigureDir, "paper_latency_box.png"), 30, 8, 730, 410);

chartData.freezePanes.freezeRows(1);
writeMetricTable(chartData, 1, "CPU mean %", "C", "0.000");
writeMetricTable(chartData, 105, "CPU max %", "D", "0.000");
writeMetricTable(chartData, 209, "Memory mean %", "E", "0.000");
writeMetricTable(chartData, 313, "Load1 mean", "G", "0.0000");
chartData.getRange("A1:F413").format.autofitColumns();

const summaryInspect = await workbook.inspect({
  kind: "table",
  range: "Dashboard!A5:I10",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 10,
});
console.log(summaryInspect.ndjson);

const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errorScan.ndjson);

const previewSpecs = [
  ["Dashboard", "A1:P47", "dashboard.png"],
  ["Trial Trends", "A1:P43", "trial_trends.png"],
  ["Network Metrics", "A1:P53", "network_metrics.png"],
  ["Paper Style Figures", "A1:P54", "paper_style_figures_sheet.png"],
  ["Network Data", "A1:L25", "network_data.png"],
  ["Chart Data", "A1:F25", "chart_data.png"],
  ["Raw Data", "A1:J25", "raw_data.png"],
];
for (const [sheetName, range, filename] of previewSpecs) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, filename), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputXlsx);
console.log(`Saved ${outputXlsx}`);
