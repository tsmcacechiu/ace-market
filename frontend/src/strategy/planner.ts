/**
 * 倉位計算機 (plan/strategy-1/SKILL.md §5.2 item 3, §9.7). Pure functions, no React.
 * Holdings live only in this browser's localStorage, never on the server.
 */
import type { Regime, StrategyAlert } from "../api";

export type SwingKind = "none" | "r200" | "r200_half" | "r500";

export type Holding = {
  /** Money available for this asset (底倉 + 波段倉 + 現金). */
  capital: number;
  base: number;
  swing: number;
  swingKind: SwingKind;
  entryPrice: number | null;
  entryDate: string | null;
};

export const EMPTY_HOLDING: Holding = {
  capital: 0,
  base: 0,
  swing: 0,
  swingKind: "none",
  entryPrice: null,
  entryDate: null,
};

export const SWING_KIND_LABEL: Record<SwingKind, string> = {
  none: "沒有波段倉",
  r200: "站回 200 進場（還沒賣過）",
  r200_half: "站回 200 進場（已賣一半）",
  r500: "站回 500 進場",
};

/** Exit MA per swing kind, from §2: MA50 then MA200 for a 200 entry, MA500 for a 500 entry. */
const EXIT_MA: Record<Exclude<SwingKind, "none">, 50 | 200 | 500> = { r200: 50, r200_half: 200, r500: 500 };

export type Plan = {
  base: {
    pct: number;
    range: [number, number];
    /** Money to add (> 0) or take out (< 0) to land on the nearest edge of the range. */
    delta: number;
    status: "add" | "reduce" | "ok";
  };
  swing:
    | { status: "enter"; amount: number; why: string }
    | { status: "wait"; why: string }
    | {
        status: "hold" | "warn" | "sell";
        exitMa: number;
        exitLine: number | null;
        threshold: number | null;
        belowDays: number;
        needed: number;
        /** Money to sell when status is "sell" (half for the first leg of a 200 entry). */
        sellAmount: number;
        returnPct: number | null;
        distPct: number | null;
      };
  totalPct: number;
};

const round = (v: number) => Math.round(v);

export function plan(h: Holding, regime: Regime): Plan | null {
  if (!(h.capital > 0)) return null;
  const { base: [lo, hi], swing: swingPct } = regime.suggested_position;
  const basePct = (h.base / h.capital) * 100;
  let delta = 0;
  if (basePct < lo) delta = (h.capital * lo) / 100 - h.base;
  else if (basePct > hi) delta = (h.capital * hi) / 100 - h.base;
  const base = {
    pct: basePct,
    range: [lo, hi] as [number, number],
    delta: round(delta),
    status: delta > 0.5 ? "add" : delta < -0.5 ? "reduce" : "ok",
  } as Plan["base"];

  let swing: Plan["swing"];
  if (h.swingKind === "none" || !(h.swing > 0)) {
    // Enter only while a reclaim is fresh (the state shows it for a few days), never chase a BULL.
    const fresh200 = regime.state === "RECLAIM_200";
    const fresh500 = regime.state === "RECLAIM_500" && regime.position?.kind === "RECLAIM_500";
    if ((fresh200 || fresh500) && swingPct > 0) {
      swing = {
        status: "enter",
        amount: round((h.capital * swingPct) / 100),
        why: fresh200 ? "剛站回 200 日線" : "這一波第一次站回 500 日線",
      };
    } else if (regime.state === "RECLAIM_500") {
      swing = { status: "wait", why: "這一波已經在站回 500 時進場過，不重複進場" };
    } else {
      swing = { status: "wait", why: "波段倉只在站回 200 / 500 日線時進場，不追高" };
    }
  } else {
    const k = EXIT_MA[h.swingKind];
    const key = `ma${k}` as const;
    const belowDays = regime.below_days[key];
    const needed = regime.exit_confirm;
    const status = belowDays >= needed ? "sell" : belowDays > 0 ? "warn" : "hold";
    const exitLine = regime.ma[key];
    swing = {
      status,
      exitMa: k,
      exitLine,
      threshold: regime.thresholds[key],
      belowDays,
      needed,
      sellAmount: round(h.swingKind === "r200" ? h.swing / 2 : h.swing),
      returnPct: h.entryPrice ? (regime.close / h.entryPrice - 1) * 100 : null,
      distPct: exitLine ? (regime.close / exitLine - 1) * 100 : null,
    };
  }

  return { base, swing, totalPct: ((h.base + h.swing) / h.capital) * 100 };
}

const money = (v: number) => Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 });

/** Alerts from the user's own holdings (§9.4 last row, §9.7), in the server's alert shape. */
export function planAlerts(p: Plan | null): StrategyAlert[] {
  if (!p) return [];
  const out: StrategyAlert[] = [];
  const [lo, hi] = p.base.range;
  if (p.base.status !== "ok") {
    const over = p.base.status === "reduce";
    out.push({
      level: "action",
      kind: "MY_BASE",
      title: `你的底倉 ${p.base.pct.toFixed(0)}%，${over ? "超出上限" : "低於下限"}（${lo === hi ? `${lo}%` : `${lo}–${hi}%`}），${over ? "減" : "加"} ${money(p.base.delta)} 元`,
      lines: [],
      key: `MY_BASE:${p.base.status}`,
    });
  }
  const s = p.swing;
  if (s.status === "enter") {
    out.push({ level: "action", kind: "MY_ENTRY", title: `你的波段倉：${s.why} → 進場 ${money(s.amount)} 元`, lines: [], key: "MY_ENTRY" });
  } else if (s.status === "sell") {
    out.push({
      level: "action",
      kind: "MY_EXIT",
      title: `你的波段倉：連 ${s.needed} 天跌破 ${s.exitMa} 日線 → 賣 ${money(s.sellAmount)} 元`,
      lines: [],
      key: `MY_EXIT:${s.exitMa}`,
    });
  } else if (s.status === "warn") {
    out.push({
      level: "soon",
      kind: "MY_EXIT_PENDING",
      title: `你的波段倉：跌破 ${s.exitMa} 日線第 ${s.belowDays} 天，明天收盤還低於 ${s.threshold?.toLocaleString("en-US", { maximumFractionDigits: 2 }) ?? "–"} 就賣`,
      lines: [],
      key: `MY_EXIT_PENDING:${s.exitMa}:${s.belowDays}`,
    });
  }
  return out;
}

const KEY = (target: string) => `strategy1:holding:${target}`;

export function loadHolding(target: string): Holding | null {
  try {
    const raw = localStorage.getItem(KEY(target));
    return raw ? { ...EMPTY_HOLDING, ...(JSON.parse(raw) as Partial<Holding>) } : null;
  } catch {
    return null;
  }
}

export function saveHolding(target: string, h: Holding | null): void {
  if (h === null) localStorage.removeItem(KEY(target));
  else localStorage.setItem(KEY(target), JSON.stringify(h));
}
