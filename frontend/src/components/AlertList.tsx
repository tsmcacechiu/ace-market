import type { AlertLevel, StrategyAlert } from "../api";

export const LEVEL_ICON: Record<AlertLevel, string> = { action: "🔴", soon: "🟡", holding: "⚪" };
export const LEVEL_TEXT: Record<AlertLevel, string> = { action: "要動作", soon: "快觸發", holding: "持有中" };

/** One alert per row in the §9.3 layout: title, then labelled detail lines. */
export function AlertList({ alerts, prefix }: { alerts: StrategyAlert[]; prefix?: string }) {
  if (!alerts.length) return null;
  return (
    <ul className="alerts">
      {alerts.map((a) => (
        <li key={a.key} className={`alert alert-${a.level}`}>
          <div className="alert-title">
            <span aria-label={LEVEL_TEXT[a.level]} title={LEVEL_TEXT[a.level]}>
              {LEVEL_ICON[a.level]}
            </span>{" "}
            {prefix && <b>{prefix}：</b>}
            {a.title}
          </div>
          {a.lines.length > 0 && (
            <dl className="alert-lines">
              {a.lines.map(([label, text]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{text}</dd>
                </div>
              ))}
            </dl>
          )}
        </li>
      ))}
    </ul>
  );
}
