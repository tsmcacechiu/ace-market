import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { MetricDef, Point } from "../api";
import { formatMetric, formatNumber } from "../format";

type Props = {
  def: MetricDef;
  points: Point[];
  price: Point[];
  priceName: string;
  bands: Record<string, number> | null;
  logPrice: boolean;
};

/** Re-read CSS variables when the OS switches light/dark. */
function useCssVars(names: string[]) {
  const read = () => {
    const cs = getComputedStyle(document.documentElement);
    return Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(`--${n}`).trim()]));
  };
  const [vars, setVars] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setVars(read());
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return vars;
}

const BAND_LABEL: Record<string, string> = { p10: "P10", p25: "P25", p50: "中位數", p75: "P75", p90: "P90" };

/**
 * Two stacked plots on one shared time axis: the metric on top, the index price below.
 * (Two separate y-scales on one plot would invite false correlations.)
 */
export function MetricChart({ def, points, price, priceName, bands, logPrice }: Props) {
  const c = useCssVars(["surface", "ink", "ink-2", "muted", "grid", "axis", "series-1"]);

  const option = useMemo(() => {
    const axisCommon = {
      axisLine: { lineStyle: { color: c.axis } },
      axisTick: { show: false },
      axisLabel: { color: c.muted, fontSize: 11 },
      splitLine: { lineStyle: { color: c.grid, width: 1 } },
    };
    const bandLines = bands
      ? Object.entries(bands).map(([k, v]) => ({
          yAxis: v,
          name: BAND_LABEL[k] ?? k,
          lineStyle: { color: k === "p50" ? c["ink-2"] : c.muted, type: k === "p50" ? "solid" : "dashed", width: 1 },
          label: {
            formatter: `${BAND_LABEL[k] ?? k} ${formatMetric(def, v)}`,
            color: c["ink-2"],
            fontSize: 11,
            position: "insideEndTop",
          },
        }))
      : [];
    const isDense = points.length > 400;

    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: { fontFamily: "inherit" },
      axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: c.muted } },
      tooltip: {
        trigger: "axis",
        backgroundColor: c.surface,
        borderColor: c.axis,
        textStyle: { color: c.ink, fontSize: 12 },
        valueFormatter: undefined,
        formatter: (params: { seriesIndex: number; value: Point; axisValueLabel: string }[]) => {
          if (!params.length) return "";
          const date = params[0].value[0];
          const rows = params.map((p) =>
            p.seriesIndex === 0
              ? `${def.name}：<b>${formatMetric(def, p.value[1])}</b>`
              : `${priceName}：<b>${formatNumber(p.value[1])}</b>`,
          );
          return [date, ...rows].join("<br/>");
        },
      },
      grid: [
        { left: 56, right: 120, top: 28, height: "52%" },
        { left: 56, right: 120, top: "70%", bottom: 56 },
      ],
      xAxis: [
        { type: "time", gridIndex: 0, ...axisCommon, axisLabel: { show: false }, splitLine: { show: false } },
        { type: "time", gridIndex: 1, ...axisCommon, splitLine: { show: false } },
      ],
      yAxis: [
        {
          type: "value",
          gridIndex: 0,
          scale: true,
          name: `${def.name}（${def.unit}）`,
          nameTextStyle: { color: c["ink-2"], align: "left", fontSize: 12 },
          ...axisCommon,
        },
        {
          type: logPrice ? "log" : "value",
          gridIndex: 1,
          scale: true,
          name: priceName,
          nameTextStyle: { color: c["ink-2"], align: "left", fontSize: 12 },
          ...axisCommon,
        },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1] },
        {
          type: "slider",
          xAxisIndex: [0, 1],
          bottom: 12,
          height: 20,
          borderColor: c.axis,
          textStyle: { color: c.muted },
          dataBackground: { lineStyle: { color: c.muted }, areaStyle: { opacity: 0 } },
        },
      ],
      series: [
        {
          name: def.name,
          type: "line",
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: points,
          showSymbol: !isDense,
          symbolSize: 8,
          lineStyle: { width: 2, color: c["series-1"] },
          itemStyle: { color: c["series-1"], borderColor: c.surface, borderWidth: 2 },
          markLine: bandLines.length ? { silent: true, symbol: "none", data: bandLines } : undefined,
        },
        {
          name: priceName,
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: price,
          showSymbol: false,
          lineStyle: { width: 2, color: c["ink-2"] },
          itemStyle: { color: c["ink-2"] },
        },
      ],
    };
  }, [c, def, points, price, priceName, bands, logPrice]);

  return <ReactECharts option={option} notMerge style={{ height: 520 }} />;
}
