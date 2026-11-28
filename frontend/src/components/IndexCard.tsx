import { Link } from "react-router-dom";
import type { TargetSummary } from "../api";
import { formatNumber, formatPct, levelOf } from "../format";
import { confirmHint, RegimeBadge } from "./RegimeBadge";

type Props = {
  target: TargetSummary;
  /** False for assets without earnings (gold, bitcoin): no valuation metric applies at all. */
  hasValuationMetrics: boolean;
};

export function IndexCard({ target, hasValuationMetrics }: Props) {
  const { quote, temperature } = target;
  const movingAverages = target.moving_averages ?? []; // absent in responses from an older backend
  const lv = temperature !== null ? levelOf(temperature) : null;

  return (
    <section className="card" aria-label={target.name}>
      <div className="index-name">
        <Link to={`/index/${target.id}`} className="card-link">
          {target.name} <span className="muted small">{target.symbol}</span>
          <span className="card-link-hint small">走勢圖 →</span>
        </Link>
      </div>
      {quote ? (
        <>
          <div className="index-price">{formatNumber(quote.close)}</div>
          <div className="small">
            <span className={quote.change_pct >= 0 ? "chg-up" : "chg-down"}>
              {quote.change_pct >= 0 ? "▲" : "▼"} {formatPct(quote.change_pct)}
            </span>
            <span className="muted"> · {quote.date}</span>
          </div>
          {target.regime && (
            <div className="regime-line">
              <RegimeBadge regime={target.regime} />
              <div className="small secondary">
                {confirmHint(target.regime) ?? `建議：${target.regime.suggested_position.text}`}
              </div>
            </div>
          )}
          {movingAverages.length > 0 && (
            <table className="ma-table small" aria-label="移動平均線">
              <tbody>
                {movingAverages.map((ma) => (
                  <tr key={ma.window}>
                    <th scope="row" className="secondary">
                      {ma.window}MA
                    </th>
                    {ma.value !== null && ma.deviation_pct !== null ? (
                      <>
                        <td>{formatNumber(ma.value)}</td>
                        <td className={ma.deviation_pct >= 0 ? "chg-up" : "chg-down"}>
                          {formatPct(ma.deviation_pct)}
                        </td>
                      </>
                    ) : (
                      <td colSpan={2} className="muted">
                        資料不足
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : (
        <div className="muted">尚無價格資料</div>
      )}

      <div className="temp">
        <div className="temp-row">
          <span className="secondary small">市場溫度</span>
          {temperature !== null && lv ? (
            <span>
              <span className="temp-value">{temperature.toFixed(0)}</span>
              <span className="muted small"> / 100 · </span>
              <span className={`badge ${lv.cls}`} style={{ minWidth: 0 }}>
                {lv.label}
              </span>
            </span>
          ) : (
            <span className="muted small">資料不足</span>
          )}
        </div>
        <div
          className="meter"
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={temperature ?? undefined}
          aria-label="市場溫度"
        >
          {temperature !== null && <div className="meter-marker" style={{ left: `${temperature}%` }} />}
        </div>
        <div className="meter-scale">
          <span>便宜</span>
          <span>昂貴</span>
        </div>
        {temperature !== null && target.temperature_basis.valuation === 0 && (
          <div className="small secondary" style={{ marginTop: 6 }}>
            {hasValuationMetrics
              ? "⚠️ 只根據技術指標：估值資料還在累積，目前反映的是漲跌位置，不是估值高低"
              : "ℹ️ 沒有盈餘，沒有估值指標：溫度只反映價格相對歷史的位置，不是估值高低"}
          </div>
        )}
      </div>
    </section>
  );
}
