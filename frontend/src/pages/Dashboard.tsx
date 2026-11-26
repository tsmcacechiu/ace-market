import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { IndexCard } from "../components/IndexCard";
import { MetricTable } from "../components/MetricTable";
import { formatDateTime } from "../format";

const STATUS_TEXT = { ok: "✅ 正常", partial: "⚠️ 部分失敗", failed: "❌ 失敗", running: "⏳ 執行中" } as const;

export function DashboardPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });

  if (isLoading) return <div className="page muted">載入中…</div>;
  if (error) {
    return (
      <div className="page">
        <div className="card error">
          無法連線到後端：{String(error)}
          <div className="small muted">請確認已執行 `uv run uvicorn market.api.main:app`（在 backend/ 目錄）。</div>
        </div>
      </div>
    );
  }
  if (!data) return null;

  const { job } = data;
  return (
    <div className="page">
      <header className="header">
        <h1>市場溫度計</h1>
        <div className="small secondary">
          {job ? (
            <>
              資料更新：{formatDateTime(job.finished_at ?? job.started_at)} · {STATUS_TEXT[job.status]}
            </>
          ) : (
            "尚未執行過資料更新（python -m market.jobs.daily）"
          )}
        </div>
      </header>

      <div className="cards">
        {data.targets.map((t) => (
          <IndexCard
            key={t.id}
            target={t}
            hasValuationMetrics={data.metrics.some((m) => m.kind === "valuation" && t.id in m.sources)}
          />
        ))}
      </div>

      <MetricTable data={data} />

      <p className="small muted">
        溫度 = 各指標「貴的程度」的加權平均（估值指標權重 2、技術指標權重 1），只計入已有足夠歷史的指標。
        點表格中的數值可看歷史走勢。本頁僅為資料整理，不構成投資建議。
      </p>

      {job?.detail && (
        <details>
          <summary>最近一次更新紀錄</summary>
          <pre className="job">{job.detail}</pre>
        </details>
      )}
    </div>
  );
}
