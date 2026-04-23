import { useEffect, useRef, useState, useCallback } from "react";

type SeriesPoint = { t: number; v: number };

type LineChartProps = {
  series: SeriesPoint[];
  width?: number;      // hint only — actual render uses container width
  height?: number;
  stroke?: string;
  label?: string;
  fillArea?: boolean;
  showGrid?: boolean;
  onPointClick?: (point: SeriesPoint) => void;
  pointTitle?: (point: SeriesPoint) => string;
  /** If provided, hovering a dot shows a tooltip card */
  tooltipLabel?: string; // e.g. mechanic name shown in header
  /** Pin the y-axis to a fixed range (e.g. 0–100 for mechanic scores) */
  yMin?: number;
  yMax?: number;
};

type Tooltip = {
  x: number;         // canvas-space x (px)
  y: number;         // canvas-space y (px)
  point: SeriesPoint;
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

function computeScales(series: SeriesPoint[], w: number, h: number, fixedYMin?: number, fixedYMax?: number) {
  const pad = { top: 20, right: 16, bottom: 32, left: 44 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;
  const xs = series.map((p) => p.t);
  const ys = series.map((p) => p.v);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  let minY: number;
  let maxY: number;
  if (fixedYMin !== undefined && fixedYMax !== undefined) {
    minY = fixedYMin;
    maxY = fixedYMax;
  } else {
    const rawMinY = Math.min(...ys);
    const rawMaxY = Math.max(...ys);
    const yRange = rawMaxY - rawMinY || 1;
    minY = Math.max(0, rawMinY - yRange * 0.05);
    maxY = rawMaxY + yRange * 0.05;
  }
  const xScale = (x: number) => pad.left + ((x - minX) / Math.max(1e-6, maxX - minX)) * plotW;
  const yScale = (y: number) => pad.top + plotH - ((y - minY) / Math.max(1e-6, maxY - minY)) * plotH;
  return { pad, plotW, plotH, minX, maxX, minY, maxY, xScale, yScale };
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
  hoveredIdx: number | null = null,
  fixedYMin?: number,
  fixedYMax?: number,
) {
  ctx.clearRect(0, 0, width, height);

  ctx.fillStyle = "#111923";
  ctx.fillRect(0, 0, width, height);

  if (!series.length) {
    ctx.fillStyle = "#9fb5c9";
    ctx.font = "12px Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No data yet", width / 2, height / 2);
    return;
  }

  const { pad, plotW, plotH, minY, maxY, xScale, yScale } = computeScales(series, width, height, fixedYMin, fixedYMax);

  if (label) {
    ctx.fillStyle = "#9fb5c9";
    ctx.font = "600 11px Segoe UI, system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label, pad.left, 14);
  }

  if (showGrid) {
    const step = niceStep(maxY - minY, 4);
    const gridStart = Math.ceil(minY / step) * step;
    ctx.textAlign = "right";
    ctx.font = "10px Segoe UI, system-ui, sans-serif";
    for (let v = gridStart; v <= maxY; v += step) {
      const y = yScale(v);
      ctx.strokeStyle = "rgba(78, 193, 255, 0.08)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(width - pad.right, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#5a7a90";
      ctx.fillText(v % 1 === 0 ? String(Math.round(v)) : v.toFixed(1), pad.left - 6, y + 3.5);
    }
  }

  const xLabelCount = Math.min(5, series.length);
  if (xLabelCount >= 2) {
    ctx.fillStyle = "#5a7a90";
    ctx.font = "10px Segoe UI, system-ui, sans-serif";
    ctx.textAlign = "center";
    for (let i = 0; i < xLabelCount; i++) {
      const idx = Math.round((i / (xLabelCount - 1)) * (series.length - 1));
      const p = series[idx];
      ctx.fillText(fmtDate(p.t), xScale(p.t), height - 8);
    }
  }

  ctx.strokeStyle = "rgba(78, 193, 255, 0.12)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + plotH);
  ctx.lineTo(pad.left + plotW, pad.top + plotH);
  ctx.stroke();

  if (fillArea && series.length > 1) {
    const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    gradient.addColorStop(0, hexToRgba(stroke, 0.15));
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

  const dotInterval = Math.max(1, Math.floor(series.length / 12));
  series.forEach((p, i) => {
    if (i !== 0 && i !== series.length - 1 && i % dotInterval !== 0) return;
    const x = xScale(p.t);
    const y = yScale(p.v);
    const isHovered = i === hoveredIdx;
    const r = isHovered ? 5 : 3;

    ctx.fillStyle = stroke;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#111923";
    ctx.beginPath();
    ctx.arc(x, y, isHovered ? 2.5 : 1.5, 0, Math.PI * 2);
    ctx.fill();
  });
}

function hexToRgba(hex: string, alpha: number): string {
  if (hex.startsWith("rgba") || hex.startsWith("rgb")) {
    return hex.replace(/[\d.]+\)$/, `${alpha})`);
  }
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export default function LineChart({
  series,
  height = 140,
  stroke = "#4ec1ff",
  label,
  fillArea = true,
  showGrid = true,
  onPointClick,
  pointTitle,
  tooltipLabel,
  yMin,
  yMax,
}: LineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState<number>(500);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const hoveredIdxRef = useRef<number | null>(null);

  // Track actual container width
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setContainerWidth(Math.floor(w));
    });
    ro.observe(el);
    // Initial measurement
    const initial = el.getBoundingClientRect().width;
    if (initial > 0) setContainerWidth(Math.floor(initial));
    return () => ro.disconnect();
  }, []);

  // Redraw whenever size, series, or hovered idx changes
  const redraw = useCallback((hoveredIdx: number | null) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = containerWidth;
    const h = height;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    drawChart(ctx, series, w, h, stroke, label, fillArea, showGrid, hoveredIdx, yMin, yMax);
  }, [containerWidth, height, series, stroke, label, fillArea, showGrid, yMin, yMax]);

  useEffect(() => {
    redraw(hoveredIdxRef.current);
  }, [redraw]);

  // Click + hover hit testing
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !series.length) return;

    const getNearest = (clientX: number, clientY: number) => {
      const rect = canvas.getBoundingClientRect();
      const mx = clientX - rect.left;
      const my = clientY - rect.top;
      const { xScale, yScale } = computeScales(series, containerWidth, height, yMin, yMax);
      const dotInterval = Math.max(1, Math.floor(series.length / 12));
      let nearest: { idx: number; point: SeriesPoint; px: number; py: number } | null = null;
      let nearestDist = Infinity;
      series.forEach((point, i) => {
        if (i !== 0 && i !== series.length - 1 && i % dotInterval !== 0) return;
        const px = xScale(point.t);
        const py = yScale(point.v);
        const dist = Math.hypot(px - mx, py - my);
        if (dist < nearestDist) { nearest = { idx: i, point, px, py }; nearestDist = dist; }
      });
      return nearestDist <= 20 ? nearest : null;
    };

    const handleMouseMove = (e: MouseEvent) => {
      const hit = getNearest(e.clientX, e.clientY);
      const newIdx = hit ? hit.idx : null;
      if (newIdx !== hoveredIdxRef.current) {
        hoveredIdxRef.current = newIdx;
        redraw(newIdx);
      }
      if (hit) {
        setTooltip({ x: hit.px, y: hit.py, point: hit.point });
        canvas.style.cursor = "pointer";
      } else {
        setTooltip(null);
        canvas.style.cursor = onPointClick ? "pointer" : "default";
      }
    };

    const handleMouseLeave = () => {
      hoveredIdxRef.current = null;
      redraw(null);
      setTooltip(null);
      canvas.style.cursor = onPointClick ? "pointer" : "default";
    };

    const handleClick = (e: MouseEvent) => {
      if (!onPointClick) return;
      const hit = getNearest(e.clientX, e.clientY);
      if (hit) onPointClick(hit.point);
    };

    canvas.addEventListener("mousemove", handleMouseMove);
    canvas.addEventListener("mouseleave", handleMouseLeave);
    canvas.addEventListener("click", handleClick);
    return () => {
      canvas.removeEventListener("mousemove", handleMouseMove);
      canvas.removeEventListener("mouseleave", handleMouseLeave);
      canvas.removeEventListener("click", handleClick);
    };
  }, [series, containerWidth, height, onPointClick, redraw]);

  // Tooltip position — flip to left if too close to right edge
  const tooltipStyle: React.CSSProperties = tooltip ? (() => {
    const flipX = tooltip.x > containerWidth * 0.65;
    return {
      position: "absolute",
      left: flipX ? undefined : tooltip.x + 12,
      right: flipX ? containerWidth - tooltip.x + 12 : undefined,
      top: Math.max(4, tooltip.y - 60),
      pointerEvents: "none",
      zIndex: 10,
    };
  })() : {};

  const p = tooltip?.point as (SeriesPoint & { replayName?: string }) | undefined;

  return (
    <div ref={wrapRef} style={{ width: "100%", position: "relative", overflow: "visible" }}>
      <canvas
        ref={canvasRef}
        title={pointTitle && series.length ? pointTitle(series[series.length - 1]) : undefined}
        style={{ display: "block", borderRadius: 6 }}
      />
      {tooltip && p && (
        <div className="chart-tooltip" style={tooltipStyle}>
          {tooltipLabel && <div className="chart-tooltip-label">{tooltipLabel}</div>}
          <div className="chart-tooltip-score">{p.v.toFixed(1)}</div>
          <div className="chart-tooltip-name">{p.replayName || fmtDate(p.t)}</div>
        </div>
      )}
    </div>
  );
}
