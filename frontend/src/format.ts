import type { MetricDef } from "./api";

// Metrics where the sign matters (distance from an average / a high).
const SIGNED = new Set(["drawdown", "rel_strength", "erp"]);
const isSigned = (id: string) => SIGNED.has(id) || /^ma\d+_dev$/.test(id);

export function formatMetric(def: MetricDef, value: number): string {
  const sign = isSigned(def.id) && value > 0 ? "+" : "";
  switch (def.unit) {
    case "x":
      return `${value.toFixed(1)}x`;
    case "%":
      return `${sign}${value.toFixed(def.id === "buffett" ? 0 : 1)}%`;
    case "pp":
      return `${sign}${value.toFixed(2)} pp`;
    default:
      return value.toFixed(2);
  }
}

export const formatNumber = (v: number, digits = 2) =>
  v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const formatPct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Five buckets on the 0 (cheap) … 100 (expensive) scale. Colors come from CSS variables. */
export const LEVELS = [
  { max: 20, label: "便宜", cls: "lv-0" },
  { max: 40, label: "偏低", cls: "lv-1" },
  { max: 60, label: "中性", cls: "lv-2" },
  { max: 80, label: "偏高", cls: "lv-3" },
  { max: Infinity, label: "昂貴", cls: "lv-4" },
] as const;

export const levelOf = (expensiveness: number) => LEVELS.find((l) => expensiveness < l.max)!;
