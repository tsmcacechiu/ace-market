import { Link } from "react-router-dom";
import type { StrategyAlert, TargetSummary } from "../api";
import { loadHolding, plan, planAlerts } from "../strategy/planner";
import { AlertList } from "./AlertList";
import { RegimeBadge } from "./RegimeBadge";

type Row = { target: TargetSummary; alerts: StrategyAlert[]; mine: StrategyAlert[] };

const urgent = (a: StrategyAlert) => a.level === "action" || a.level === "soon";

/**
 * 今日待辦 (SKILL.md §9.2): 🔴 / 🟡 on top, everything else folded away — most days nothing
 * needs doing, and the page should say so instead of inviting action.
 */
export function TodayPanel({ targets }: { targets: TargetSummary[] }) {
  const rows: Row[] = targets
    .filter((t) => t.regime)
    .map((t) => {
      const holding = loadHolding(t.id);
      return {
        target: t,
        alerts: t.regime!.alerts ?? [],
        mine: holding ? planAlerts(plan(holding, t.regime!)) : [],
      };
    });
  if (!rows.length) return null;
  const todo = rows.filter((r) => r.alerts.some(urgent) || r.mine.some(urgent));
  const rest = rows.filter((r) => !todo.includes(r));
  const actions = todo.filter((r) => [...r.alerts, ...r.mine].some((a) => a.level === "action")).length;

  return (
    <section className="card today" aria-label="今日待辦">
      <h2>
        今日待辦 <span className="small muted">策略一 · {rows[0].target.regime!.date} 收盤</span>
      </h2>
      {todo.length === 0 ? (
        <p className="secondary">🟢 今天每個標的都不用動。</p>
      ) : (
        <>
          <p className="small secondary">
            {actions > 0 ? `${actions} 個標的要動作，` : ""}
            {todo.length - actions > 0 ? `${todo.length - actions} 個快觸發。` : ""}
            確認都以收盤價為準，隔天開盤再動作。
          </p>
          {todo.map(({ target, alerts, mine }) => (
            <div key={target.id} className="today-row">
              <div className="today-head">
                <Link to={`/index/${target.id}`}>{target.name}</Link>
                <RegimeBadge regime={target.regime!} />
              </div>
              <AlertList alerts={mine.filter(urgent)} />
              <AlertList alerts={alerts.filter(urgent)} />
            </div>
          ))}
        </>
      )}
      {rest.length > 0 && (
        <details>
          <summary>其他標的：不用動（{rest.map((r) => r.target.name).join("、")}）</summary>
          {rest.map(({ target, alerts }) => (
            <div key={target.id} className="today-row">
              <div className="today-head">
                <Link to={`/index/${target.id}`}>{target.name}</Link>
                <RegimeBadge regime={target.regime!} />
              </div>
              <AlertList alerts={alerts} />
            </div>
          ))}
        </details>
      )}
      <p className="disclaimer">依歷史均線規則推算，不構成投資建議。</p>
    </section>
  );
}
