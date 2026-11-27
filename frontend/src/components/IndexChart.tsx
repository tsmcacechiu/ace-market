import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { Point, RegimeState } from "../api";
import { formatNumber } from "../format";
import { COMPACT_QUERY, useMediaQuery } from "../hooks/useMediaQuery";
import { useCssVars } from "./MetricChart";
import { STATE_ORDER, STATE_STYLE } from "./RegimeBadge";

type Props = {
  priceName: string;
  price: Point[];
  movingAverages: { window: number; points: Point[] }[];
  logScale: boolean;
  /** 策略一 overlay: state runs as background bands, entry / break events as markers. */
  segments?: [string, string, RegimeState][];
  markers?: [string, string, number][];
};

const BAND_VARS = STATE_ORDER.map((s) => `st-${STATE_STYLE[s].cls}-band`);

/** Chart markers (SKILL.md §5.2): ▲ reclaim, ▼ confirmed break. */
export const MARKER_KINDS: Record<string, { label: string; up: boolean }> = {
  RECLAIM_200: { label: "站回 200 日線", up: true },
  RECLAIM_500: { label: "站回 500 日線", up: true },
  BREAK_200: { label: "跌破 200 日線", up: false },
  BREAK_500: { label: "跌破 500 日線", up: false },
};

function alpha(hex: string, a: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

// Fixed order: the n-th average always gets the n-th categorical slot (validated light + dark).
const MA_COLOR_VARS = ["series-1", "series-2", "series-3"];

/** Index price with its moving averages, all on one price axis. */
export function IndexChart({ priceName, price, movingAverages, logScale, segments, markers }: Props) {
  const c = useCssVars(["surface", "ink", "ink-2", "muted", "grid", "axis", "up", "down", ...MA_COLOR_VARS, ...BAND_VARS]);
  const compact = useMediaQuery(COMPACT_QUERY);

  const option = useMemo(() => {
    const first = price[0]?.[0];
    // Each band runs to the next band's start, so one-day states stay visible and there are no gaps.
    const bands = (segments ?? [])
      .filter(([, end]) => !first || end >= first)
      .map(([start, , state], i, all) => [
        {
          xAxis: first && start < first ? first : start,
          itemStyle: { color: alpha(c[`st-${STATE_STYLE[state].cls}-band`], 0.13) },
        },
        { xAxis: all[i + 1]?.[0] ?? price[price.length - 1]?.[0] },
      ]);
    const marks = (markers ?? []).filter(([, kind]) => kind in MARKER_KINDS);
    const markerSeries = marks.length
      ? [
          {
            name: "訊號",
            type: "scatter",
            data: marks.map(([d, kind, close]) => ({
              value: [d, close, kind],
              symbol: "triangle",
              symbolRotate: MARKER_KINDS[kind].up ? 0 : 180,
              symbolOffset: [0, MARKER_KINDS[kind].up ? 10 : -10],
              itemStyle: { color: MARKER_KINDS[kind].up ? c.up : c.down },
            })),
            symbolSize: compact ? 7 : 9,
            z: 4,
            emphasis: { disabled: true },
          },
        ]
      : [];
    const maSeries = movingAverages.map((ma, i) => {
      const color = c[MA_COLOR_VARS[i % MA_COLOR_VARS.length]];
      return {
        name: `${ma.window}MA`,
        type: "line",
        data: ma.points,
        showSymbol: false,
        lineStyle: { width: 2, color },
        itemStyle: { color },
        emphasis: { disabled: true },
        // Direct label at the line end, in text ink (the line itself carries the color).
        endLabel: { show: true, formatter: `${ma.window}MA`, color: c["ink-2"], fontSize: compact ? 10 : 11 },
      };
    });

    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: { fontFamily: "inherit" },
      legend: {
        data: [priceName, ...movingAverages.map((ma) => `${ma.window}MA`)], // markers explain themselves
        top: 0,
        left: 0,
        icon: "roundRect",
        itemWidth: 14,
        itemHeight: 3,
        textStyle: { color: c["ink-2"], fontSize: 12 },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: c.surface,
        borderColor: c.axis,
        textStyle: { color: c.ink, fontSize: 12 },
        axisPointer: { lineStyle: { color: c.muted } },
        formatter: (params: { seriesName: string; seriesType: string; marker: string; value: [string, number, string?] }[]) => {
          if (!params.length) return "";
          const rows = params.map((p) =>
            p.seriesType === "scatter"
              ? `${p.marker}<b>${MARKER_KINDS[p.value[2] ?? ""]?.label ?? p.value[2]}</b>`
              : `${p.marker}${p.seriesName}：<b>${formatNumber(p.value[1])}</b>`,
          );
          return [params[0].value[0], ...rows].join("<br/>");
        },
      },
      // Phones: tighter margins so the plot gets the width; end labels still fit on the right.
      grid: compact ? { left: 44, right: 48, top: 48, bottom: 56 } : { left: 64, right: 64, top: 36, bottom: 64 },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: c.axis } },
        axisTick: { show: false },
        axisLabel: { color: c.muted, fontSize: 11 },
        splitLine: { show: false },
      },
      yAxis: {
        type: logScale ? "log" : "value",
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: c.muted,
          fontSize: compact ? 10 : 11,
          // Phones: 45,000 -> 45k keeps the axis narrow.
          formatter: (v: number) => (compact && v >= 10_000 ? `${formatNumber(v / 1000, 0)}k` : formatNumber(v, 0)),
        },
        splitLine: { lineStyle: { color: c.grid, width: 1 } },
      },
      dataZoom: [
        { type: "inside" },
        {
          type: "slider",
          bottom: 12,
          height: 20,
          borderColor: c.axis,
          textStyle: { color: c.muted },
          dataBackground: { lineStyle: { color: c.muted }, areaStyle: { opacity: 0 } },
        },
      ],
      series: [
        {
          name: priceName,
          type: "line",
          data: price,
          showSymbol: false,
          lineStyle: { width: 2, color: c.ink },
          itemStyle: { color: c.ink },
          emphasis: { disabled: true },
          z: 3, // price above the averages
          markArea: bands.length ? { silent: true, data: bands } : undefined,
        },
        ...maSeries,
        ...markerSeries,
      ],
    };
  }, [c, priceName, price, movingAverages, logScale, compact, segments, markers]);

  return <ReactECharts option={option} notMerge style={{ height: compact ? 380 : 520 }} />;
}
