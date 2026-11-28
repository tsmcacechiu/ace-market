import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { LEVEL_ICON } from "../components/AlertList";

const HORIZONS = [
  ["1m", "1 個月"],
  ["3m", "3 個月"],
  ["6m", "6 個月"],
  ["12m", "12 個月"],
] as const;

const ret = (v: number | null) =>
  v === null ? <span className="muted">還沒到</span> : <span className={v >= 0 ? "chg-up" : "chg-down"}>{v > 0 ? "+" : ""}{v.toFixed(1)}%</span>;

/** 訊號紀錄 (SKILL.md §9.6): real alerts and what happened after, next to the backtest. */
export function SignalsPage() {
  const [all, setAll] = useState(false);
  const { data, error, isLoading } = useQuery({
    queryKey: ["signals", all],
    queryFn: () => api.signals(all ? "all" : "action"),
  });

  return (
    <div className="page">
      <header className="header">
        <h1>訊號紀錄</h1>
        <label className="toggle">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
          也顯示 🟡 快觸發
        </label>
      </header>
      <p className="small secondary">
        每天資料更新後發出的策略一提示，以及之後實際的漲跌，跟回測的數字放在一起比。累積一段時間後，就能看出回測在真實情況下準不準。
      </p>
      {isLoading && <div className="muted">載入中…</div>}
      {error && <div className="card error">{String(error)}</div>}
      {data && (
        <section className="card">
          {data.signals.length === 0 ? (
            <p className="muted">還沒有紀錄。每天資料更新後，只要有提示就會記在這裡。</p>
          ) : (
            <div className="table-scroll">
              <table className="bt">
                <thead>
                  <tr>
                    <th>日期 · 標的 · 提示</th>
                    <th>當天收盤</th>
                    {HORIZONS.map(([k, label]) => (
                      <th key={k}>{label}後</th>
                    ))}
                    <th>回測：12 個月上漲</th>
                  </tr>
                </thead>
                <tbody>
                  {data.signals.map((s) => (
                    <tr key={`${s.target}-${s.date}-${s.kind}`}>
                      <td>
                        {s.date} · <Link to={`/index/${s.target}`}>{s.name}</Link>
                        <span className="bt-sub">
                          {LEVEL_ICON[s.level]} {s.title}
                          {s.sent ? " · 已推播" : ""}
                        </span>
                      </td>
                      <td>{s.price.toLocaleString("en-US", { maximumFractionDigits: 2 })}</td>
                      {HORIZONS.map(([k]) => (
                        <td key={k}>{ret(s.returns[k])}</td>
                      ))}
                      <td>
                        {s.backtest ? (
                          <>
                            {s.backtest.win_pct_12m?.toFixed(0)}% · {s.backtest.median_12m !== null && s.backtest.median_12m > 0 ? "+" : ""}
                            {s.backtest.median_12m?.toFixed(1)}%
                            <span className="bt-sub">
                              {s.backtest.pooled ? `${s.backtest.group}合計 · ` : ""}n={s.backtest.n}
                            </span>
                          </>
                        ) : (
                          <span className="muted">–</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="disclaimer">報酬從提示當天的收盤價算起。{data.disclaimer}。</p>
        </section>
      )}
    </div>
  );
}
