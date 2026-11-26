import { Link } from "react-router-dom";
import type { Dashboard } from "../api";
import { formatMetric, LEVELS } from "../format";
import { COMPACT_QUERY, useMediaQuery } from "../hooks/useMediaQuery";
import { MetricList } from "./MetricList";
import { PercentileBadge } from "./PercentileBadge";

export function MetricTable({ data }: { data: Dashboard }) {
  const { targets, metrics, settings } = data;
  const compact = useMediaQuery(COMPACT_QUERY);
  // Metrics where a lower value means more expensive (e.g. ERP, dividend yield).
  const inverted = metrics.filter((m) => !m.higher_is_expensive);

  return (
    <section className="card">
      {compact ? (
        <MetricList data={data} />
      ) : (
        <div className="table-scroll">
          <table className="metrics">
            <thead>
              <tr>
                <th>指標</th>
                {targets.map((t) => (
                  <th key={t.id}>{t.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.id}>
                  <th scope="row" title={m.description}>
                    {m.name}
                    <span className="kind-tag">
                      {m.kind === "valuation" ? "估值" : "技術"}
                      {!m.in_temperature && " · 不計溫度"}
                    </span>
                  </th>
                  {targets.map((t) => {
                    if (!(t.id in m.sources)) {
                      return (
                        <td key={t.id} className="muted">
                          —
                        </td>
                      );
                    }
                    const sc = t.metrics[m.id];
                    return (
                      <td key={t.id} className="cell">
                        {sc ? (
                          <Link to={`/metric/${m.id}/${t.id}`} title={`${m.sources[t.id]}，資料日 ${sc.date}`}>
                            <span className="metric-value">{formatMetric(m, sc.value)}</span>
                            <PercentileBadge
                              expensiveness={sc.expensiveness}
                              percentile={sc.percentile}
                              historyMonths={sc.history_months}
                              minMonths={settings.min_months}
                            />
                          </Link>
                        ) : (
                          <span className="muted">無資料</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="legend small secondary">
        <span>
          P = 近 {settings.percentile_years} 年歷史百分位（P90 = 比過去 90% 的時間都高）：
        </span>
        {LEVELS.map((l) => (
          <span key={l.cls} className={`badge ${l.cls}`} style={{ minWidth: 0 }}>
            {l.label}
          </span>
        ))}
        {inverted.length > 0 && (
          <span className="muted">· {inverted.map((m) => m.name).join("、")}越低越貴，已反向換算</span>
        )}
      </div>
    </section>
  );
}
