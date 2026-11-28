/** Which page an asset belongs to: home dashboard or 個股診斷. */
export type Group = "market" | "stock";

export const BOARDS: Record<Group, { path: string; title: string }> = {
  market: { path: "/", title: "市場總覽" },
  stock: { path: "/stocks", title: "個股診斷" },
};

export type MetricDef = {
  id: string;
  name: string;
  unit: string;
  kind: "valuation" | "technical";
  higher_is_expensive: boolean;
  description: string;
  sources: Record<string, string>;
  /** False = reference only, not part of the market temperature. */
  in_temperature: boolean;
};

export type MetricScore = {
  value: number;
  date: string;
  percentile: number | null;
  expensiveness: number | null;
  history_months: number;
};

export type Job = {
  id: number;
  status: "running" | "ok" | "partial" | "failed";
  started_at: string;
  finished_at: string | null;
  detail: string | null;
};

export type MovingAverage = { window: number; value: number | null; deviation_pct: number | null };

export type TargetSummary = {
  id: string;
  name: string;
  symbol: string;
  etf: string | null;
  quote: { date: string; close: number; change_pct: number } | null;
  moving_averages: MovingAverage[];
  temperature: number | null;
  temperature_basis: { valuation: number; technical: number };
  metrics: Record<string, MetricScore | null>;
  /** 策略一 state for the latest close; absent from an older backend, null without 500 days. */
  regime?: Regime | null;
};

// ---- 策略一：200 / 500 日線 (plan/strategy-1/SKILL.md) ----

export type RegimeState =
  | "BULL"
  | "BREAK_200"
  | "RECLAIM_200"
  | "BEAR_200"
  | "NEAR_500"
  | "BREAK_500"
  | "RECLAIM_500"
  | "CRISIS";

export type AlertLevel = "action" | "soon" | "holding";
/** 策略一 alert (SKILL.md §9): 🔴 action · 🟡 soon · ⚪ holding. */
export type StrategyAlert = {
  level: AlertLevel;
  kind: string;
  title: string;
  /** [label, text] rows, e.g. ["為什麼", "連 3 天收盤站上 200 日線"]. */
  lines: [string, string][];
  key: string;
};

export type Regime = {
  date: string;
  close: number;
  state: RegimeState;
  label: string;
  color: string;
  days_in_state: number;
  window_day: number | null;
  window_left: number | null;
  window: number;
  event: string | null;
  suggested_position: { base: [number, number]; swing: number; text: string };
  near_500: boolean;
  episode_entered_500: boolean;
  /** Pending confirmation: `days` of `needed` closes above ("up") / below ("down") MA`ma`. */
  confirm: { ma: number; dir: "up" | "down"; days: number; needed: number; next_threshold: number | null };
  dist: Record<"ma50" | "ma200" | "ma500", number | null>;
  /** Closes in a row below each MA, and tomorrow's close that sits exactly on it. */
  below_days: Record<"ma50" | "ma200" | "ma500", number>;
  thresholds: Record<"ma50" | "ma200" | "ma500", number | null>;
  exit_confirm: number;
  /** Absent from an older backend. */
  alerts?: StrategyAlert[];
  ma: Record<"ma20" | "ma50" | "ma200" | "ma500", number | null>;
  /** The strategy's own virtual swing sleeve (one 30% slot). */
  position: {
    kind: "RECLAIM_200" | "RECLAIM_500";
    share: number;
    entry_date: string;
    entry_price: number;
    return_pct: number;
    exit_ma: number;
    exit_days: number;
    exit_threshold: number | null;
    exit_line: number | null;
  } | null;
};

export type HorizonStat = {
  n: number;
  win_pct: number | null;
  median: number | null;
  worst: number | null;
  worst_dip: number | null;
};
export type EventKind = "RECLAIM_200" | "BEAR_200" | "NEAR_500" | "RECLAIM_500" | "CRISIS";
export type EventStats = Record<EventKind, { count: number; horizons: Record<string, HorizonStat> }>;
export type TradeStat = {
  n: number;
  open: number;
  win_pct: number | null;
  mean: number | null;
  median: number | null;
  worst: number | null;
  days_median: number | null;
};
export type TradeStats = Record<"RECLAIM_200" | "RECLAIM_500", TradeStat>;

export type StrategyOverview = {
  days: number;
  targets: { id: string; name: string; group: "market" | "stock"; regime: Regime | null }[];
  events: { date: string; target: string; name: string; kind: string; label: string; close: number; state: RegimeState | null }[];
  disclaimer: string;
};

export type SignalLog = {
  signals: {
    target: string;
    name: string;
    date: string;
    kind: string;
    level: AlertLevel;
    title: string;
    price: number;
    sent: boolean;
    returns: Record<string, number | null>;
    backtest: { win_pct_12m: number | null; median_12m: number | null; n: number; pooled: boolean; group: string } | null;
  }[];
  disclaimer: string;
};

export type StrategyDetail = {
  target: { id: string; name: string; group: "指數" | "其他"; is_stock: boolean };
  params: {
    window: number;
    break_confirm: number;
    reclaim_confirm: number;
    exit_confirm: number;
    touch_band_pct: number;
    exit_200: [number, number][];
    exit_500: [number, number][];
    min_samples: number;
    horizons: string[];
  };
  states: Record<RegimeState, { label: string; color: string; position: string }>;
  regime: Regime | null;
  /** [start, end, state] runs, for chart backgrounds. */
  segments: [string, string, RegimeState][];
  /** [date, event, close] for every state-machine event (incl. BREAK_200 / BREAK_500). */
  markers: [string, string, number][];
  events: { date: string; kind: EventKind; close: number; first_500: boolean | null; returns: Record<string, number | null> }[];
  stats: { target: EventStats; group: EventStats | null; group_name: string; group_members: string[] };
  trades: {
    target: TradeStats;
    group: TradeStats | null;
    fill: "next_open";
    list: { kind: string; entry_date: string; entry_price: number; exit_date: string | null; ret: number | null; days: number; open: boolean }[];
  };
  disclaimer: string;
};

export type Dashboard = {
  settings: { percentile_years: number; min_months: number };
  job: Job | null;
  metrics: MetricDef[];
  targets: TargetSummary[];
};

export type Point = [string, number];

export type MetricHistory = {
  metric: MetricDef;
  target: { id: string; name: string; index: string; etf: string | null; group: Group };
  score: (MetricScore & { bands: Record<string, number> | null }) | null;
  points: Point[];
  price: Point[];
};

export type IndexChart = {
  target: { id: string; name: string; index: string; etf: string | null; group: Group };
  interval: "daily" | "weekly";
  price: Point[];
  moving_averages: { window: number; points: Point[] }[];
  latest: MovingAverage[];
};

/**
 * Backend origin, e.g. "https://market-api.onrender.com". Set VITE_API_BASE at build time.
 * Empty in local dev: requests stay relative and Vite proxies /api to 127.0.0.1:8000.
 */
const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  dashboard: () => get<Dashboard>("/api/dashboard"),
  stocks: () => get<Dashboard>("/api/stocks"),
  metricHistory: (metricId: string, target: string, from?: string) =>
    get<MetricHistory>(`/api/metrics/${metricId}/${target}${from ? `?from=${from}` : ""}`),
  indexChart: (target: string, from?: string) =>
    get<IndexChart>(`/api/indices/${target}/chart${from ? `?from=${from}` : ""}`),
  strategyOverview: () => get<StrategyOverview>("/api/strategy/overview"),
  signals: (level: "action" | "all" = "action") => get<SignalLog>(`/api/strategy/signals?level=${level}`),
  strategy1: (target: string, from?: string) =>
    get<StrategyDetail>(`/api/strategy/1/${target}${from ? `?from=${from}` : ""}`),
};
