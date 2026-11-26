import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { Point } from "../api";
import { formatNumber } from "../format";
import { COMPACT_QUERY, useMediaQuery } from "../hooks/useMediaQuery";
import { useCssVars } from "./MetricChart";

type Props = {
  priceName: string;
  price: Point[];
  movingAverages: { window: number; points: Point[] }[];
  logScale: boolean;
};

// Fixed order: the n-th average always gets the n-th categorical slot (validated light + dark).
const MA_COLOR_VARS = ["series-1", "series-2", "series-3"];

/** Index price with its moving averages, all on one price axis. */
export function IndexChart({ priceName, price, movingAverages, logScale }: Props) {
  const c = useCssVars(["surface", "ink", "ink-2", "muted", "grid", "axis", ...MA_COLOR_VARS]);
  const compact = useMediaQuery(COMPACT_QUERY);

  const option = useMemo(() => {
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
        formatter: (params: { seriesName: string; marker: string; value: Point }[]) => {
          if (!params.length) return "";
          const rows = params.map((p) => `${p.marker}${p.seriesName}：<b>${formatNumber(p.value[1])}</b>`);
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
        },
        ...maSeries,
      ],
    };
  }, [c, priceName, price, movingAverages, logScale, compact]);

  return <ReactECharts option={option} notMerge style={{ height: compact ? 380 : 520 }} />;
}
