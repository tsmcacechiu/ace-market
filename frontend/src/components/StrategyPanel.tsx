import type { EventKind, HorizonStat, StrategyDetail, TradeStat } from "../api";
import { formatNumber, formatPct } from "../format";
import { AlertList } from "./AlertList";
import { confirmHint, RegimeBadge, STATE_ORDER, STATE_STYLE } from "./RegimeBadge";

const EVENT_ROWS: { kind: EventKind; label: string; note?: string }[] = [
  { kind: "RECLAIM_200", label: "站回 200 日線" },
  { kind: "RECLAIM_500", label: "站回 500 日線", note: "每波只算第一次" },
  { kind: "NEAR_500", label: "靠近 500 日線", note: "每波只算第一次" },
  { kind: "BEAR_200", label: "一個月沒站回 200" },
  { kind: "CRISIS", label: "一個月沒站回 500" },
];

const HORIZON_LABEL: Record<string, string> = { "1m": "1 個月", "3m": "3 個月", "6m": "6 個月", "12m": "12 個月" };

const signed = (v: number | null, digits = 1) => (v === null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`);

/** Use the target's own number unless it has too few samples; then the group's, labelled. */
function pick<T extends { n: number }>(own: T | undefined, group: T | undefined, min: number) {
  if (own && own.n >= min) return { s: own, pooled: false };
  if (group && group.n >= min) return { s: group, pooled: true };
  return { s: own ?? group, pooled: false, thin: true };
}

function HorizonCell({ own, group, min, groupName }: { own?: HorizonStat; group?: HorizonStat; min: number; groupName: string }) {
  const { s, pooled, thin } = pick(own, group, min);
  if (!s || s.n === 0) return <td className="muted">–</td>;
  return (
    <td>
      {s.win_pct === null ? "–" : `${s.win_pct.toFixed(0)}%`} · {signed(s.median)}
      <span className="bt-sub">
        {thin ? "樣本不足 · " : pooled ? `${groupName}合計 · ` : ""}n={s.n}
      </span>
    </td>
  );
}

function TradeRow({ label, own, group, min, groupName }: { label: string; own: TradeStat; group?: TradeStat; min: number; groupName: string }) {
  const { s, pooled, thin } = pick(own, group, min);
  if (!s || s.n === 0) {
    return (
      <tr>
        <td>{label}</td>
        <td colSpan={5} className="muted">
          還沒有完成的交易
        </td>
      </tr>
    );
  }
  return (
    <tr>
      <td>
        {label}
        <span className="bt-sub">
          {thin ? "樣本不足 · " : pooled ? `${groupName}合計 · ` : ""}n={s.n}
          {s.open ? ` · 持有中 ${s.open}` : ""}
        </span>
      </td>
      <td>{s.win_pct === null ? "–" : `${s.win_pct.toFixed(0)}%`}</td>
      <td>{signed(s.mean)}</td>
      <td>{signed(s.median)}</td>
      <td>{signed(s.worst)}</td>
      <td>{s.days_median === null ? "–" : `${s.days_median.toFixed(0)} 天`}</td>
    </tr>
  );
}

export function StrategyPanel({ data }: { data: StrategyDetail }) {
  const { regime, params, stats, trades } = data;
  const min = params.min_samples;
  const groupName = stats.group_name;
  const pos = regime?.position;
  const hint = regime ? confirmHint(regime) : null;

  return (
    <section className="card strategy" aria-label="策略一">
      <h2>策略一：200 / 500 日線多空判讀</h2>
      {regime ? (
        <>
          <div className="strategy-head">
            <RegimeBadge regime={regime} />
            <span className="small muted">
              {regime.date} 收盤 · 這個狀態第 {regime.days_in_state} 天
            </span>
          </div>
          <AlertList alerts={regime.alerts ?? []} />
          <dl className="facts">
            <div>
              <dt>建議倉位</dt>
              <dd>{regime.suggested_position.text}</dd>
            </div>
            <div>
              <dt>下一步</dt>
              <dd>
                {hint ??
                  (regime.confirm.dir === "up"
                    ? `等連 ${regime.confirm.needed} 天收盤站上 ${regime.confirm.ma} 日線`
                    : `連 ${regime.confirm.needed} 天收盤低於 ${regime.confirm.ma} 日線才算跌破`)}
                {regime.window_left !== null && (
                  <span className="bt-sub">
                    觀察期剩 {regime.window_left} 天（共 {regime.window} 天）
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt>距離均線</dt>
              <dd>
                {(["ma50", "ma200", "ma500"] as const).map((k) => (
                  <span key={k} style={{ marginRight: 12 }}>
                    {k.slice(2)}MA{" "}
                    <span className={(regime.dist[k] ?? 0) >= 0 ? "chg-up" : "chg-down"}>
                      {regime.dist[k] === null ? "–" : formatPct(regime.dist[k]!)}
                    </span>
                  </span>
                ))}
              </dd>
            </div>
            <div>
              <dt>策略的虛擬波段倉</dt>
              <dd>
                {pos ? (
                  <>
                    {pos.kind === "RECLAIM_500" ? "站回 500" : "站回 200"}進場（{pos.entry_date}，
                    {formatNumber(pos.entry_price)}）·{" "}
                    <span className={pos.return_pct >= 0 ? "chg-up" : "chg-down"}>{formatPct(pos.return_pct)}</span>
                    {pos.share < 1 && <> · 剩 {Math.round(pos.share * 100)}%</>}
                    <span className="bt-sub">
                      出場線 {pos.exit_ma} 日線 {pos.exit_line === null ? "" : formatNumber(pos.exit_line)}
                      {pos.exit_days > 0
                        ? ` · 已跌破 ${pos.exit_days} / ${params.exit_confirm} 天`
                        : " · 不用動"}
                    </span>
                  </>
                ) : (
                  <span className="secondary">空手（只在站回 200 / 500 時進場，不追高）</span>
                )}
              </dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="muted">歷史不足 500 個交易日，還不能判讀。</p>
      )}

      <div className="state-legend" aria-label="圖上背景色">
        {STATE_ORDER.map((s) => (
          <span key={s}>
            <i style={{ background: `var(--st-${STATE_STYLE[s].cls}-band)` }} />
            {data.states[s].label}
          </span>
        ))}
        <span>
          <span className="chg-up">▲</span> 站回 · <span className="chg-down">▼</span> 跌破
        </span>
      </div>

      <h3>事件之後直接抱著：上漲機率 · 報酬中位數</h3>
      <div className="table-scroll">
        <table className="bt">
          <thead>
            <tr>
              <th>事件</th>
              <th>次數</th>
              {params.horizons.map((h) => (
                <th key={h}>{HORIZON_LABEL[h] ?? h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {EVENT_ROWS.map((row) => {
              const own = stats.target[row.kind];
              const grp = stats.group?.[row.kind];
              return (
                <tr key={row.kind}>
                  <td>
                    {row.label}
                    {row.note && <span className="bt-sub">{row.note}</span>}
                  </td>
                  <td>{own.count}</td>
                  {params.horizons.map((h) => (
                    <HorizonCell key={h} own={own.horizons[h]} group={grp?.horizons[h]} min={min} groupName={groupName} />
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h3>照規則進出的波段倉</h3>
      <div className="table-scroll">
        <table className="bt">
          <thead>
            <tr>
              <th>進場點 · 出場規則</th>
              <th>勝率</th>
              <th>平均</th>
              <th>中位數</th>
              <th>最差</th>
              <th>持有（中位數）</th>
            </tr>
          </thead>
          <tbody>
            <TradeRow
              label="站回 200：跌破 50 日線賣一半、跌破 200 日線賣剩下的"
              own={trades.target.RECLAIM_200}
              group={trades.group?.RECLAIM_200}
              min={min}
              groupName={groupName}
            />
            <TradeRow
              label="站回 500（每波第一次）：跌破 500 日線全部賣出"
              own={trades.target.RECLAIM_500}
              group={trades.group?.RECLAIM_500}
              min={min}
              groupName={groupName}
            />
          </tbody>
        </table>
      </div>
      <p className="small secondary">
        站回 500 進場的交易，歷史上大約 6 成會小賠出場，獲利主要來自少數幾次大反彈。照規則做，不要賠一次就停手。
      </p>

      <p className="disclaimer">
        跌破 / 站回都要連 {params.break_confirm} 天收盤確認；觀察期 {params.window} 個交易日。
        波段倉以訊號隔天開盤成交計算，每筆交易各自計算，未計手續費。樣本少於 {min} 次時改用{groupName}（
        {stats.group_members.join("、")}）合計的數字。
        {data.target.is_stock && " 個股另有公司本身的風險，回測結果要跟大盤分開看。"}
        <br />
        {data.disclaimer}。
      </p>
    </section>
  );
}
