import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, BOARDS } from "../api";
import { IndexChart } from "../components/IndexChart";
import { formatNumber, formatPct } from "../format";

const RANGES = [
  { key: "6M", months: 6 },
  { key: "1Y", months: 12 },
  { key: "3Y", months: 36 },
  { key: "5Y", months: 60 },
  { key: "10Y", months: 120 },
  { key: "全部", months: null },
] as const;

function monthsAgo(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}

export function IndexDetailPage() {
  const { target = "" } = useParams();
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("3Y");
  const [logScale, setLogScale] = useState(false);
  const months = RANGES.find((r) => r.key === range)!.months;
  const from = months === null ? undefined : monthsAgo(months);

  const { data, error, isLoading } = useQuery({
    queryKey: ["indexChart", target, from],
    queryFn: () => api.indexChart(target, from),
    placeholderData: keepPreviousData,
  });

  const last = data?.price[data.price.length - 1];

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
              {data.target.name} <span className="muted small">{data.target.index}</span>
            </h1>
          </header>

          <section className="card">
            <div className="stat-row">
              {last && (
                <div>
                  <div className="stat-label">收盤（{last[0]}）</div>
                  <div className="stat-value">{formatNumber(last[1])}</div>
                </div>
              )}
              {data.latest.map((ma) => (
                <div key={ma.window}>
                  <div className="stat-label">{ma.window} 日均線</div>
                  {ma.value !== null && ma.deviation_pct !== null ? (
                    <>
                      <div className="stat-value secondary">{formatNumber(ma.value)}</div>
                      <div className={`small ${ma.deviation_pct >= 0 ? "chg-up" : "chg-down"}`}>
                        價格{ma.deviation_pct >= 0 ? "高於" : "低於"}均線 {formatPct(ma.deviation_pct)}
                      </div>
                    </>
                  ) : (
                    <div className="muted">資料不足</div>
                  )}
                </div>
              ))}
            </div>
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
              <input type="checkbox" checked={logScale} onChange={(e) => setLogScale(e.target.checked)} />
              對數座標
            </label>
            <span className="small muted">
              均線以完整歷史計算{data.interval === "weekly" ? "；範圍較長，以每週最後一個交易日顯示" : ""}
            </span>
          </div>

          <section className="card">
            {data.price.length ? (
              <IndexChart
                priceName={data.target.name}
                price={data.price}
                movingAverages={data.moving_averages}
                logScale={logScale}
              />
            ) : (
              <div className="muted">這個時間範圍內沒有資料</div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
