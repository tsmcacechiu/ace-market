import { levelOf } from "../format";

type Props = {
  expensiveness: number | null;
  percentile: number | null;
  historyMonths: number;
  minMonths: number;
};

/** Level label + historical percentile. Text always carries the meaning; color only reinforces it. */
export function PercentileBadge({ expensiveness, percentile, historyMonths, minMonths }: Props) {
  if (expensiveness === null || percentile === null) {
    return (
      <span className="badge badge-pending" title={`需要至少 ${minMonths} 個月的資料才計算百分位`}>
        累積中 {historyMonths}/{minMonths} 月
      </span>
    );
  }
  const lv = levelOf(expensiveness);
  return (
    <span className={`badge ${lv.cls}`} title={`歷史百分位 ${percentile.toFixed(0)}%`}>
      {lv.label} · P{percentile.toFixed(0)}
    </span>
  );
}
