import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, BOARDS } from "../api";
import { MetricChart } from "../components/MetricChart";
import { PercentileBadge } from "../components/PercentileBadge";
import { formatMetric } from "../format";

const RANGES = [
  { key: "1Y", years: 1 },
  { key: "5Y", years: 5 },
  { key: "10Y", years: 10 },
  { key: "30Y", years: 30 },
  { key: "全部", years: null },
] as const;

function yearsAgo(years: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
}

export function MetricDetailPage() {
  const { metricId = "", target = "" } = useParams();
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("10Y");
  const [logPrice, setLogPrice] = useState(false);
  const years = RANGES.find((r) => r.key === range)!.years;
  const from = years === null ? undefined : yearsAgo(years);

  const { data, error, isLoading } = useQuery({
    queryKey: ["metric", metricId, target, from],
    queryFn: () => api.metricHistory(metricId, target, from),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="page">
      <p className="small">
        <Link to={BOARDS[data?.target.group ?? "market"].path}>
          ← 回{BOARDS[data?.target.group ?? "market"].title}
        </Link>
      </p>
      {isLoading && <div className="muted">載入中…</div>}
      {error && <div className="card error">{String(error)}</div>}
      {data && (
        <>
          <header className="header">
            <h1>
              {data.target.name} · {data.metric.name}
            </h1>
            <span className="small muted">{data.metric.sources[target]}</span>
          </header>

          <section className="card">
            {data.score ? (
              <div className="stat-row">
                <div>
                  <div className="stat-label">最新值（{data.score.date}）</div>
                  <div className="stat-value">{formatMetric(data.metric, data.score.value)}</div>
                </div>
                <div>
                  <div className="stat-label">近 30 年位置</div>
                  <PercentileBadge
                    expensiveness={data.score.expensiveness}
                    percentile={data.score.percentile}
                    historyMonths={data.score.history_months}
                    minMonths={12}
                  />
                </div>
                {data.score.bands && (
                  <div>
                    <div className="stat-label">近 30 年中位數</div>
                    <div className="stat-value secondary">{formatMetric(data.metric, data.score.bands.p50)}</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="muted">尚無資料</div>
            )}
            <p className="small secondary">{data.metric.description}</p>
          </section>

          <div className="toolbar">
            <div className="seg" role="group" aria-label="時間範圍">
              {RANGES.map((r) => (
                <button key={r.key} aria-pressed={range === r.key} onClick={() => setRange(r.key)}>
                  {r.key}
                </button>
              ))}
            </div>
            <label className="toggle">
              <input type="checkbox" checked={logPrice} onChange={(e) => setLogPrice(e.target.checked)} />
              指數價格用對數座標
            </label>
            <span className="small muted">虛線為近 30 年的 P10 / P25 / P75 / P90，實線為中位數</span>
          </div>

          <section className="card">
            {data.points.length ? (
              <MetricChart
                def={data.metric}
                points={data.points}
                price={data.price}
                priceName={data.target.index}
                bands={data.score?.bands ?? null}
                logPrice={logPrice}
              />
            ) : (
              <div className="muted">這個時間範圍內沒有資料</div>
            )}
          </section>

          <details style={{ marginTop: 14 }}>
            <summary>資料表（最近 24 筆）</summary>
            <table className="metrics">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>{data.metric.name}</th>
                </tr>
              </thead>
              <tbody>
                {data.points
                  .slice(-24)
                  .reverse()
                  .map(([d, v]) => (
                    <tr key={d}>
                      <td>{d}</td>
                      <td>{formatMetric(data.metric, v)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </div>
  );
}
