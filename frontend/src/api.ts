export type MetricDef = {
  id: string;
  name: string;
  unit: string;
  kind: "valuation" | "technical";
  higher_is_expensive: boolean;
  description: string;
  sources: Record<string, string>;
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
  etf: string;
  quote: { date: string; close: number; change_pct: number } | null;
  moving_averages: MovingAverage[];
  temperature: number | null;
  temperature_basis: { valuation: number; technical: number };
  metrics: Record<string, MetricScore | null>;
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
  target: { id: string; name: string; index: string; etf: string };
  score: (MetricScore & { bands: Record<string, number> | null }) | null;
  points: Point[];
  price: Point[];
};

export type IndexChart = {
  target: { id: string; name: string; index: string; etf: string };
  interval: "daily" | "weekly";
  price: Point[];
  moving_averages: { window: number; points: Point[] }[];
  latest: MovingAverage[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  dashboard: () => get<Dashboard>("/api/dashboard"),
  metricHistory: (metricId: string, target: string, from?: string) =>
    get<MetricHistory>(`/api/metrics/${metricId}/${target}${from ? `?from=${from}` : ""}`),
  indexChart: (target: string, from?: string) =>
    get<IndexChart>(`/api/indices/${target}/chart${from ? `?from=${from}` : ""}`),
};
