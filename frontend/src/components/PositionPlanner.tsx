import { useEffect, useState } from "react";
import type { Regime } from "../api";
import { formatNumber, formatPct } from "../format";
import {
  EMPTY_HOLDING,
  loadHolding,
  plan,
  saveHolding,
  SWING_KIND_LABEL,
  type Holding,
  type SwingKind,
} from "../strategy/planner";

const money = (v: number) => Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 });

function NumberField({ label, value, onChange, step }: { label: string; value: number | null; onChange: (v: number | null) => void; step?: number }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        inputMode="decimal"
        min={0}
        step={step ?? 1000}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    </label>
  );
}

/** 倉位計算機: the user's own numbers for one asset, kept only in this browser. */
export function PositionPlanner({ target, regime }: { target: string; regime: Regime }) {
  const [h, setH] = useState<Holding>(() => loadHolding(target) ?? EMPTY_HOLDING);
  useEffect(() => setH(loadHolding(target) ?? EMPTY_HOLDING), [target]);

  const update = (patch: Partial<Holding>) => {
    const next = { ...h, ...patch };
    setH(next);
    saveHolding(target, next);
  };
  const p = plan(h, regime);

  return (
    <section className="card strategy" aria-label="倉位計算機">
      <h2>倉位計算機</h2>
      <p className="small muted">只存在這台裝置的瀏覽器裡，不會送到伺服器。</p>
      <div className="planner-form">
        <NumberField label="這個標的可投入的總資金" value={h.capital || null} onChange={(v) => update({ capital: v ?? 0 })} />
        <NumberField label="現在底倉市值" value={h.base || null} onChange={(v) => update({ base: v ?? 0 })} />
        <NumberField label="現在波段倉市值" value={h.swing || null} onChange={(v) => update({ swing: v ?? 0 })} />
        <label className="field">
          <span>波段倉是怎麼進場的</span>
          <select value={h.swingKind} onChange={(e) => update({ swingKind: e.target.value as SwingKind })}>
            {(Object.keys(SWING_KIND_LABEL) as SwingKind[]).map((k) => (
              <option key={k} value={k}>
                {SWING_KIND_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        {h.swingKind !== "none" && (
          <>
            <NumberField label="波段倉進場價" value={h.entryPrice} step={0.01} onChange={(v) => update({ entryPrice: v })} />
            <label className="field">
              <span>進場日期</span>
              <input type="date" value={h.entryDate ?? ""} onChange={(e) => update({ entryDate: e.target.value || null })} />
            </label>
          </>
        )}
      </div>

      {p ? (
        <dl className="facts planner-out">
          <div>
            <dt>底倉（目標 {p.base.range[0] === p.base.range[1] ? `${p.base.range[0]}%` : `${p.base.range[0]}–${p.base.range[1]}%`}）</dt>
            <dd>
              現在 {p.base.pct.toFixed(1)}% →{" "}
              {p.base.status === "ok" ? (
                <span className="chg-up">在區間內，不用動</span>
              ) : (
                <b>
                  {p.base.status === "add" ? "加" : "減"} {money(p.base.delta)} 元
                </b>
              )}
            </dd>
          </div>
          <div>
            <dt>波段倉</dt>
            <dd>
              {p.swing.status === "enter" && (
                <b>
                  {p.swing.why} → 進場 {money(p.swing.amount)} 元
                </b>
              )}
              {p.swing.status === "wait" && <span className="secondary">{p.swing.why}</span>}
              {(p.swing.status === "hold" || p.swing.status === "warn" || p.swing.status === "sell") && (
                <>
                  {p.swing.returnPct !== null && (
                    <span className={p.swing.returnPct >= 0 ? "chg-up" : "chg-down"}>{formatPct(p.swing.returnPct)} · </span>
                  )}
                  {p.swing.status === "hold" && "不用動"}
                  {p.swing.status === "warn" &&
                    `跌破 ${p.swing.exitMa} 日線第 ${p.swing.belowDays} / ${p.swing.needed} 天，明天收盤還低於 ${p.swing.threshold === null ? "–" : formatNumber(p.swing.threshold)} 就賣`}
                  {p.swing.status === "sell" && (
                    <b>
                      連 {p.swing.needed} 天跌破 {p.swing.exitMa} 日線 → 賣 {money(p.swing.sellAmount)} 元
                    </b>
                  )}
                  <span className="bt-sub">
                    出場線（停損價）：{p.swing.exitMa} 日線 {p.swing.exitLine === null ? "–" : formatNumber(p.swing.exitLine)}
                    {p.swing.distPct !== null && `（距離 ${formatPct(p.swing.distPct)}）`}
                  </span>
                </>
              )}
            </dd>
          </div>
          <div>
            <dt>總倉位（上限 70%）</dt>
            <dd className={p.totalPct > 70 ? "chg-down" : undefined}>{p.totalPct.toFixed(1)}%</dd>
          </div>
        </dl>
      ) : (
        <p className="small secondary">輸入總資金後，會依照現在的狀態算出底倉要加減多少、波段倉要不要進出場。</p>
      )}
      {h !== EMPTY_HOLDING && (
        <button
          className="link-button small"
          onClick={() => {
            saveHolding(target, null);
            setH(EMPTY_HOLDING);
          }}
        >
          清除這個標的的資料
        </button>
      )}
    </section>
  );
}
