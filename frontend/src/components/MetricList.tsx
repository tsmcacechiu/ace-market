import { useState } from "react";
import { Link } from "react-router-dom";
import type { Dashboard } from "../api";
import { formatMetric } from "../format";
import { PercentileBadge } from "./PercentileBadge";

/** Phone layout of the metric table: pick one asset, then list its metrics one per row. */
export function MetricList({ data }: { data: Dashboard }) {
  const { targets, metrics, settings } = data;
  const [selected, setSelected] = useState(targets[0]?.id);
  const target = targets.find((t) => t.id === selected) ?? targets[0];
  if (!target) return null;
  const applicable = metrics.filter((m) => target.id in m.sources);

  return (
    <>
      <div className="chips" role="tablist" aria-label="選擇資產">
        {targets.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={t.id === target.id}
            className="chip"
            onClick={() => setSelected(t.id)}
          >
            {t.name}
          </button>
        ))}
      </div>

      <ul className="metric-list" role="tabpanel" aria-label={`${target.name} 的指標`}>
        {applicable.map((m) => {
          const sc = target.metrics[m.id];
          const label = (
            <>
              <span className="metric-list-name">
                {m.name}
                <span className="kind-tag">
                  {m.kind === "valuation" ? "估值" : "技術"}
                  {!m.in_temperature && " · 不計溫度"}
                </span>
              </span>
              {sc ? (
                <span className="metric-list-value">
                  <span className="metric-value">{formatMetric(m, sc.value)}</span>
                  <PercentileBadge
                    expensiveness={sc.expensiveness}
                    percentile={sc.percentile}
                    historyMonths={sc.history_months}
                    minMonths={settings.min_months}
                  />
                </span>
              ) : (
                <span className="muted">無資料</span>
              )}
            </>
          );
          return (
            <li key={m.id}>
              {sc ? (
                <Link to={`/metric/${m.id}/${target.id}`} className="metric-list-row">
                  {label}
                </Link>
              ) : (
                <div className="metric-list-row">{label}</div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
