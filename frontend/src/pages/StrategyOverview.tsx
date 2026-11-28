import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type StrategyAlert, type StrategyOverview } from "../api";
import { LEVEL_ICON } from "../components/AlertList";
import { RegimeBadge, STATE_STYLE } from "../components/RegimeBadge";
import { formatNumber, formatPct } from "../format";

const GROUPS = [
  ["market", "大盤 · 商品"],
  ["stock", "個股"],
] as const;

const LEVEL_RANK = { action: 0, soon: 1, holding: 2 } as const;

const dist = (v: number | null) =>
  v === null ? <span className="muted">–</span> : <span className={v >= 0 ? "chg-up" : "chg-down"}>{formatPct(v)}</span>;

/** The most pressing alert of a target (🔴 before 🟡 before ⚪). */
function topAlert(alerts: StrategyAlert[] | undefined): StrategyAlert | null {
  if (!alerts?.length) return null;
  return [...alerts].sort((a, b) => LEVEL_RANK[a.level] - LEVEL_RANK[b.level])[0];
}

function StateTable({ targets }: { targets: StrategyOverview["targets"] }) {
  return (
    <div className="table-scroll">
      <table className="bt overview">
        <thead>
          <tr>
            <th>標的</th>
            <th>狀態</th>
            <th>距 200 日線</th>
            <th>距 500 日線</th>
            <th>建議倉位</th>
            <th>今天的提示</th>
          </tr>
        </thead>
        <tbody>
          {targets.map(({ id, name, regime }) => {
            if (!regime) {
              return (
                <tr key={id}>
                  <td>
                    <Link to={`/index/${id}`}>{name}</Link>
                  </td>
                  <td colSpan={5} className="muted">
                    歷史不足 500 個交易日，還不能判讀
                  </td>
                </tr>
              );
            }
            const a = topAlert(regime.alerts);
            const more = (regime.alerts?.length ?? 0) - 1;
            return (
              <tr key={id}>
                <td>
                  <Link to={`/index/${id}`}>{name}</Link>
                  <span className="bt-sub">{formatNumber(regime.close)}</span>
                </td>
                <td>
                  <RegimeBadge regime={regime} />
                  {regime.window_left === null && <span className="bt-sub">第 {regime.days_in_state} 天</span>}
                </td>
                <td>{dist(regime.dist.ma200)}</td>
                <td>{dist(regime.dist.ma500)}</td>
                <td>{regime.suggested_position.text}</td>
                <td>
                  {a ? (
                    <>
                      {LEVEL_ICON[a.level]} {a.title}
                      {more > 0 && <span className="bt-sub">另外 {more} 則，點標的看全部</span>}
                    </>
                  ) : (
                    <span className="muted">不用動</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 策略一總覽 (SKILL.md §5.4): every target's state in one table, plus the last 90 days of events. */
export function StrategyOverviewPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ["strategy-overview"], queryFn: api.strategyOverview });
  const date = data?.targets.find((t) => t.regime)?.regime?.date;

  return (
    <div className="page">
      <header className="header">
        <h1>策略一總覽</h1>
        {date && <span className="small muted">{date} 收盤</span>}
      </header>
      <p className="small secondary">
        200 / 500 日線多空判讀，每個標的一行。大部分的日子都不用動；有 🔴 才需要在隔天開盤動作。
      </p>
      {isLoading && <div className="muted">載入中…</div>}
      {error && <div className="card error">{String(error)}</div>}
      {data && (
        <>
          {GROUPS.map(([g, title]) => {
            const rows = data.targets.filter((t) => t.group === g);
            return rows.length ? (
              <section key={g} className="card strategy" aria-label={title}>
                <h2>{title}</h2>
                <StateTable targets={rows} />
              </section>
            ) : null;
          })}

          <section className="card strategy" aria-label="最近的事件">
            <h2>最近 {data.days} 天的事件</h2>
            {data.events.length === 0 ? (
              <p className="muted">最近 {data.days} 天沒有任何標的發生事件。</p>
            ) : (
              <div className="table-scroll">
                <table className="bt overview-events">
                  <thead>
                    <tr>
                      <th>日期</th>
                      <th>標的</th>
                      <th>事件</th>
                      <th>當天收盤</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.events.map((e) => (
                      <tr key={`${e.date}-${e.target}-${e.kind}`}>
                        <td>{e.date}</td>
                        <td>
                          <Link to={`/index/${e.target}`}>{e.name}</Link>
                        </td>
                        <td>
                          {e.kind.startsWith("EXIT") ? "💰" : e.state ? STATE_STYLE[e.state].icon : ""} {e.label}
                        </td>
                        <td>{formatNumber(e.close)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="disclaimer">
              跌破 / 站回都要連 3 天收盤確認，事件記在確認的那一天。「波段倉」是策略自己的虛擬倉位，不是你的持股。
              {data.disclaimer}。
            </p>
          </section>
        </>
      )}
    </div>
  );
}
