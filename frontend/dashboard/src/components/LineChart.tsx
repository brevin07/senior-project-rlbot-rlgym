import { useEffect, useRef } from "react";

type SeriesPoint = { t: number; v: number };

type LineChartProps = {
  series: SeriesPoint[];
  width?: number;
  height?: number;
  stroke?: string;
  label?: string;
};

function drawChart(ctx: CanvasRenderingContext2D, series: SeriesPoint[], width: number, height: number, stroke: string) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#18222e";
  ctx.fillRect(0, 0, width, height);
  if (!series.length) {
    ctx.fillStyle = "#9fb5c9";
    ctx.font = "12px Segoe UI, sans-serif";
    ctx.fillText("No data", 12, 20);
    return;
  }
  const xs = series.map((p) => p.t);
  const ys = series.map((p) => p.v);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = 10;
  const xScale = (x: number) => pad + ((x - minX) / Math.max(1e-6, maxX - minX)) * (width - pad * 2);
  const yScale = (y: number) =>
    height - pad - ((y - minY) / Math.max(1e-6, maxY - minY)) * (height - pad * 2);

  ctx.strokeStyle = "rgba(78, 193, 255, 0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, pad);
  ctx.lineTo(pad, height - pad);
  ctx.lineTo(width - pad, height - pad);
  ctx.stroke();

  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2;
  ctx.beginPath();
  series.forEach((p, i) => {
    const x = xScale(p.t);
    const y = yScale(p.v);
    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();
}

export default function LineChart({ series, width = 500, height = 140, stroke = "#4ec1ff" }: LineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    drawChart(ctx, series, width, height, stroke);
  }, [series, width, height, stroke]);

  return <canvas ref={canvasRef} width={width} height={height} />;
}
