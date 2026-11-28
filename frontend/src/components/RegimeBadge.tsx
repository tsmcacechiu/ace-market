import type { Regime, RegimeState } from "../api";
import { formatNumber } from "../format";

/** Icon + CSS class per 策略一 state (colors in index.css: --st-<cls>-bg / -fg / -band). */
export const STATE_STYLE: Record<RegimeState, { icon: string; cls: string }> = {
  BULL: { icon: "🟢", cls: "bull" },
  BREAK_200: { icon: "🟡", cls: "break200" },
  RECLAIM_200: { icon: "✅", cls: "reclaim200" },
  BEAR_200: { icon: "🟠", cls: "bear200" },
  NEAR_500: { icon: "🔵", cls: "near500" },
  BREAK_500: { icon: "🔴", cls: "break500" },
  RECLAIM_500: { icon: "✅", cls: "reclaim500" },
  CRISIS: { icon: "🛑", cls: "crisis" },
};

export const STATE_ORDER: RegimeState[] = [
  "BULL",
  "RECLAIM_200",
  "BREAK_200",
  "BEAR_200",
  "NEAR_500",
  "BREAK_500",
  "CRISIS",
  "RECLAIM_500",
];

export function RegimeBadge({ regime }: { regime: Regime }) {
  const st = STATE_STYLE[regime.state];
  return (
    <span className={`badge st st-${st.cls}`} title={`策略一：${regime.label}`}>
      {st.icon} {regime.label}
    </span>
  );
}

/**
 * "站回 200 日線第 2 / 3 天，明天收盤高於 7,350.67 就確認" — only while a streak is building
 * (the strategy ignores day 1–2 of a move: they are a heads-up, not a signal).
 */
export function confirmHint(regime: Regime): string | null {
  const { ma, dir, days, needed, next_threshold } = regime.confirm;
  if (days <= 0 || days >= needed) return null;
  const verb = dir === "up" ? "站上" : "跌破";
  const thr = next_threshold === null ? "" : `，明天收盤${dir === "up" ? "高於" : "低於"} ${formatNumber(next_threshold)} 就確認`;
  return `${verb} ${ma} 日線第 ${days} / ${needed} 天${thr}`;
}
