import { useEffect, useRef } from "react";

type SeriesPoint = { t: number; v: number };

type LineChartProps = {
  series: SeriesPoint[];
  width?: number;
  height?: number;
  stroke?: string;
  label?: string;
  fillArea?: boolean;
  showGrid?: boolean;
};

function fmtDate(ts: number): string {
  const d = new Date(ts * 1000);
  const mon = d.toLocaleString("en", { month: "short" });
  return `${mon} ${d.getDate()}`;
}

function niceStep(range: number, targetTicks: number): number {
  const rough = range / targetTicks;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const res = rough / mag;
  if (res <= 1.5) return mag;
  if (res <= 3) return 2 * mag;
  if (res <= 7) return 5 * mag;
  return 10 * mag;
}

function drawChart(
  ctx: CanvasRenderingContext2D,
  series: SeriesPoint[],
  width: number,
  height: number,
  stroke: string,
  label?: string,
  fillArea = true,
  showGrid = true,
) {
  ctx.clearRect(0, 0, width, height);

  // Background
  ctx.fillStyle = "#111923";
  ctx.fillRect(0, 0, width, height);

  // No data state
  if (!series.length) {
    ctx.fillStyle = "#9fb5c9";
    ctx.font = "12px Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No data yet", width / 2, height / 2);
    return;
  }

  const pad = { top: 20, right: 16, bottom: 32, left: 52 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const xs = series.map((p) => p.t);
  const ys = series.map((p) => p.v);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const rawMinY = Math.min(...ys);
  const rawMaxY = Math.max(...ys);
  // Add 5% headroom
  const yRange = rawMaxY - rawMinY || 1;
  const minY = Math.max(0, rawMinY - yRange * 0.05);
  const maxY = rawMaxY + yRange * 0.05;

  const xScale = (x: number) => pad.left + ((x - minX) / Math.max(1e-6, maxX - minX)) * plotW;
  const yScale = (y: number) => pad.top + plotH - ((y - minY) / Math.max(1e-6, maxY - minY)) * plotH;

  // Label
  if (label) {
    ctx.fillStyle = "#9fb5c9";
    ctx.font = "600 11px Segoe UI, system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label, pad.left, 14);
  }

  // Grid lines & Y-axis labels
  if (showGrid) {
    const step = niceStep(maxY - minY, 4);
    const gridStart = Math.ceil(minY / step) * step;
    ctx.textAlign = "right";
    ctx.font = "10px Segoe UI, system-ui, sans-serif";

    for (let v = gridStart; v <= maxY; v += step) {
      const y = yScale(v);
      // Gridline
      ctx.strokeStyle = "rgba(78, 193, 255, 0.1)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(width - pad.right, y);
      ctx.stroke();
      ctx.setLineDash([]);
      // Label
      ctx.fillStyle = "#6b8da8";
      ctx.fillText(v % 1 === 0 ? String(Math.round(v)) : v.toFixed(1), pad.left - 8, y + 3.5);
    }
  }

  // X-axis labels
  const xLabelCount = Math.min(5, series.length);
  if (xLabelCount >= 2) {
    ctx.fillStyle = "#6b8da8";
    ctx.font = "10px Segoe UI, system-ui, sans-serif";
    ctx.textAlign = "center";
    for (let i = 0; i < xLabelCount; i++) {
      const idx = Math.round((i / (xLabelCount - 1)) * (series.length - 1));
      const p = series[idx];
      const x = xScale(p.t);
      ctx.fillText(fmtDate(p.t), x, height - 8);
    }
  }

  // Axes
  ctx.strokeStyle = "rgba(78, 193, 255, 0.2)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + plotH);
  ctx.lineTo(pad.left + plotW, pad.top + plotH);
  ctx.stroke();

  // Area fill
  if (fillArea && series.length > 1) {
    const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    gradient.addColorStop(0, stroke.replace(")", ", 0.22)").replace("rgb(", "rgba("));
    // Fallback for hex colors
    if (!stroke.startsWith("rgb")) {
      gradient.addColorStop(0, hexToRgba(stroke, 0.18));
    }
    gradient.addColorStop(1, "rgba(0,0,0,0)");

    ctx.fillStyle = gradient;
    ctx.beginPath();
    series.forEach((p, i) => {
      const x = xScale(p.t);
      const y = yScale(p.v);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(xScale(series[series.length - 1].t), pad.top + plotH);
    ctx.lineTo(xScale(series[0].t), pad.top + plotH);
    ctx.closePath();
    ctx.fill();
  }

  // Line
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();
  series.forEach((p, i) => {
    const x = xScale(p.t);
    const y = yScale(p.v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Data point dots
  const dotInterval = Math.max(1, Math.floor(series.length / 12));
  series.forEach((p, i) => {
    if (i !== 0 && i !== series.length - 1 && i % dotInterval !== 0) return;
    const x = xScale(p.t);
    const y = yScale(p.v);
    ctx.fillStyle = stroke;
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
    // White center
    ctx.fillStyle = "#111923";
    ctx.beginPath();
    ctx.arc(x, y, 1.5, 0, Math.PI * 2);
    ctx.fill();
  });
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export default function LineChart({
  series,
  width = 500,
  height = 140,
  stroke = "#4ec1ff",
  label,
  fillArea = true,
  showGrid = true,
}: LineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    const w = width;
    const h = height;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    drawChart(ctx, series, w, h, stroke, label, fillArea, showGrid);
  }, [series, width, height, stroke, label, fillArea, showGrid]);

  return (
    <div ref={wrapRef} style={{ width: "100%", overflow: "hidden" }}>
      <canvas ref={canvasRef} style={{ display: "block", maxWidth: "100%", borderRadius: 6 }} />
    </div>
  );
}
