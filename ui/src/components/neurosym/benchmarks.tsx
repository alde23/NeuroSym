import { formatEur } from "@/lib/neurosym/api";
import type { DomainStatistics } from "@/lib/neurosym/types";
import { Panel, Stat } from "./shell";
import { BarChart3 } from "lucide-react";

export function BudgetDistribution({
  stats,
  requested,
}: {
  stats: DomainStatistics;
  requested?: number | null | undefined;
}) {
  const points: { label: string; value: number }[] = [
    { label: "p5", value: stats.budget_p5 },
    { label: "p25", value: stats.budget_p25 },
    { label: "p50", value: stats.budget_p50 },
    { label: "p75", value: stats.budget_p75 },
    { label: "p95", value: stats.budget_p95 },
    { label: "p98", value: stats.budget_p98 },
  ];
  const max = Math.max(...points.map((p) => p.value), requested ?? 0) || 1;

  return (
    <div className="space-y-3">
      {points.map((p) => (
        <div key={p.label} className="flex items-center gap-3">
          <span className="w-9 shrink-0 font-mono text-[11px] text-muted-foreground">{p.label}</span>
          <div className="h-6 flex-1 overflow-hidden rounded-md bg-background/60">
            <div
              className="h-full rounded-md bg-gradient-to-r from-primary/70 to-chart-4/70"
              style={{ width: `${Math.max(2, (p.value / max) * 100)}%` }}
            />
          </div>
          <span className="w-20 shrink-0 text-right font-mono text-[11px] text-muted-foreground">
            {formatEur(p.value)}
          </span>
        </div>
      ))}

      {requested ? (
        <div className="flex items-center gap-3 border-t border-border pt-3">
          <span className="w-9 shrink-0 font-mono text-[11px] text-conditional">req</span>
          <div className="h-6 flex-1 overflow-hidden rounded-md bg-background/60">
            <div
              className="h-full rounded-md bg-conditional/80"
              style={{ width: `${Math.max(2, (requested / max) * 100)}%` }}
            />
          </div>
          <span className="w-20 shrink-0 text-right font-mono text-[11px] text-conditional">
            {formatEur(requested)}
          </span>
        </div>
      ) : null}
    </div>
  );
}

export function BenchmarkPanel({
  stats,
  requestedBudget,
  partnerCount,
  durationMonths,
}: {
  stats: DomainStatistics;
  requestedBudget?: number | null | undefined;
  partnerCount?: number | null | undefined;
  durationMonths?: number | null | undefined;
}) {
  return (
    <Panel
      title="Statistical benchmark"
      subtitle={`${stats.comparable_project_count.toLocaleString()} comparable CORDIS projects${stats.funding_scheme ? ` · ${stats.funding_scheme}` : ""}${stats.topic ? ` · ${stats.topic}` : ""}`}
      icon={BarChart3}
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Median EU grant" value={formatEur(stats.budget_p50)} hint={`mean ${formatEur(stats.budget_mean)}`} />
        <Stat
          label="Your percentile"
          value={stats.requested_budget_percentile != null ? `p${stats.requested_budget_percentile}` : "—"}
          hint={requestedBudget ? formatEur(requestedBudget) : "no budget stated"}
        />
        <Stat
          label="Median partners"
          value={stats.median_partner_count}
          hint={`${partnerCount ?? "—"} declared · avg ${stats.avg_partner_count.toFixed(1)}`}
        />
        <Stat
          label="Avg duration"
          value={`${stats.avg_duration_months.toFixed(1)} mo`}
          hint={durationMonths ? `${durationMonths} mo requested` : "no duration stated"}
        />
      </div>

      <div className="mt-6">
        <h3 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          EU contribution distribution
        </h3>
        <BudgetDistribution stats={stats} requested={requestedBudget ?? null} />
      </div>
    </Panel>
  );
}
